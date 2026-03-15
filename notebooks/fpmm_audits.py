# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2024 Valory AG
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

"""Script for profiling market resolution accuracy by comparing with OpenAI answers."""

import argparse
import json
import os
import sys
import textwrap
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from pathlib import Path

# Add repo root to path for .env loading
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import google.genai as genai
import pandas as pd
from dotenv import load_dotenv
from omen_markets import (
    INVALID_ANSWER_HEX,
    MarketState,
    answer_mapping,
    get_fpmms,
    get_market_current_answer,
    get_market_state,
)
from openai import OpenAI
from tqdm import tqdm


# Add local Grok-Api repo to path
_GROK_API_DIR = Path(__file__).resolve().parent.parent.parent / "Grok-Api"
sys.path.insert(0, str(_GROK_API_DIR))
from core import Grok


load_dotenv()


class AuditProvider(str, Enum):
    """AI audit provider names."""

    OPENAI = "openai"
    GROK = "grok"
    GEMINI = "gemini"

    def __str__(self) -> str:
        """Return pretty-printed provider name."""
        return self.value.lower()


_CACHE_DIR = Path(__file__).resolve().parent / ".cache"
AUDITS_JSON_PATH = str(_CACHE_DIR / "fpmm_audits.json")
OPENAI_MODEL = "gpt-5.2"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROK_MODEL = "grok-3-fast"
GROK_API_KEY = os.getenv("GROK_API_KEY")
GEMINI_MODEL = "gemini-flash-latest"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
RETRY_SECONDS = 2
N_RETRIES = 5


def load_existing_audits() -> dict:
    """Load previously computed results from file and migrate if needed."""
    try:
        with open(AUDITS_JSON_PATH, "r", encoding="UTF-8") as json_file:
            data = json.load(json_file)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}


def save_results(results: dict) -> None:
    """Save audit results under the `fpmmAudits` root element."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(AUDITS_JSON_PATH, "w", encoding="utf-8") as file:
        json.dump({"fpmmAudits": results}, file, indent=2, sort_keys=True)


def create_audit_prompt(question: str, outcomes: list[str]) -> str:
    """Create a unified audit prompt for all AI providers."""
    outcomes_str = "\n".join(
        [f"{i+1}. {outcome}" for i, outcome in enumerate(outcomes)]
    )

    return textwrap.dedent(
        f"""
        CRITICAL: You must respond with ONLY valid JSON. No markdown, no explanations, no text before or after the JSON.
        
        INSTRUCTIONS:
        You are an information verification assistant. Your task is to fact-check a prediction market question
        and determine the correct outcome based only on reliable, verifiable sources. Follow these steps:
        1. Determine the correct outcome with high confidence. If unsure, answer "UNKNOWN".
        2. Provide a list of credible sources (URLs) that support your answer.
        3. Explain your reasoning clearly and concisely.
                           
        Question: {question}

        Possible outcomes:
        {outcomes_str}


        RESPONSE FORMAT - YOU MUST OUTPUT ONLY THIS JSON STRUCTURE, NOTHING ELSE:
        {{
          "answer": "<exact outcome text from the list above, or 'UNKNOWN' if uncertain>",
          "sources": ["<URL1>", "<URL2>"],
          "reasoning": "<brief explanation>"
        }}

        RESPONSE REQUIREMENTS:
        - Start your response with {{ and end with }}
        - Do NOT use markdown code blocks (no ```)
        - Do NOT add any explanatory text outside the JSON
        - The "answer" value must exactly match one of the outcomes listed above, or "UNKNOWN"
        - Include at least 2 credible source URLs
        - Keep reasoning under 200 words
        
        OUTPUT ONLY THE JSON NOW:
    """
    ).strip()


def get_openai_audit(fpmm: dict) -> dict | None:
    """Query OpenAI as a fact-checker for a prediction market question."""
    question_data = fpmm.get("question", {})
    question = question_data.get("title", "")
    outcomes = question_data.get("outcomes", [])

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt = create_audit_prompt(question, outcomes)

    response = client.responses.create(
        model=OPENAI_MODEL,
        tools=[{"type": "web_search"}],  # enable web search
        input=prompt,
        temperature=0,
    )

    try:
        result = {
            "provider": AuditProvider.OPENAI,
            "model": OPENAI_MODEL,
            "timestamp": int(time.time()),
            "response": json.loads(response.output_text),
        }

        return result
    except json.JSONDecodeError:
        return None


def get_grok_audit(fpmm: dict) -> dict | None:
    """Query Grok as a fact-checker for a prediction market question."""
    question_data = fpmm.get("question", {})
    question = question_data.get("title", "")
    outcomes = question_data.get("outcomes", [])

    prompt = create_audit_prompt(question, outcomes)

    response_text = "..."
    # Retry logic for heavy usage
    for attempt in range(N_RETRIES):
        error_occurred = False
        response = None

        try:
            grok = Grok(GROK_MODEL)
            response = grok.start_convo(prompt)
        except (ConnectionError, TimeoutError, OSError, ValueError, RuntimeError) as e:
            error_occurred = True
            print(f"[Attempt {attempt + 1}/{N_RETRIES}] Grok exception: {str(e)}")

        # Check if an exception occurred or if response contains an error
        if error_occurred or (isinstance(response, dict) and "error" in response):
            if attempt < N_RETRIES - 1:
                wait_time = RETRY_SECONDS * (attempt + 1)
                print(
                    f"[Attempt {attempt + 1}/{N_RETRIES}] Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
                continue
            else:
                # Last attempt failed
                return None

        # Try to parse the response
        try:
            # Grok returns a dict with "response" key containing JSON string (may be a tuple of strings)
            response_text = response["response"]

            # Handle response as tuple/list of strings - join them
            if isinstance(response_text, (tuple, list)):
                response_text = "".join(response_text)

            parsed_response = json.loads(response_text)
            result = {
                "provider": AuditProvider.GROK,
                "model": GROK_MODEL,
                "timestamp": int(time.time()),
                "response": parsed_response,
            }
            # if result["response"].get("answer").lower() not in [outcome.lower() for outcome in outcomes]:
            #     return None
            return result
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(
                f"[Attempt {attempt + 1}/{N_RETRIES}] Error parsing response: {str(e)} \n {response_text=}"
            )
            if attempt < N_RETRIES - 1:
                wait_time = RETRY_SECONDS * (attempt + 1)
                print(
                    f"[Attempt {attempt + 1}/{N_RETRIES}] Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
                continue
            else:
                # Last attempt failed
                return None

    # Should not reach here, but just in case
    return None


def get_gemini_audit(fpmm: dict) -> dict | None:
    """Query Gemini as a fact-checker for a prediction market question."""
    if not genai or not GEMINI_API_KEY:
        print("Gemini API not available or GEMINI_API_KEY not set")
        return None

    question_data = fpmm.get("question", {})
    question = question_data.get("title", "")
    outcomes = question_data.get("outcomes", [])

    prompt = create_audit_prompt(question, outcomes)

    response_text = "..."
    # Retry logic for heavy usage
    for attempt in range(N_RETRIES):
        error_occurred = False
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model=f"models/{GEMINI_MODEL}",
                contents=prompt,
            )
            response_text = response.text
        except Exception as e:
            error_occurred = True
            print(f"[Attempt {attempt + 1}/{N_RETRIES}] Gemini exception: {str(e)}")

        if error_occurred:
            if attempt < N_RETRIES - 1:
                wait_time = RETRY_SECONDS * (attempt + 1)
                print(
                    f"[Attempt {attempt + 1}/{N_RETRIES}] Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
                continue
            else:
                return None

        # Try to parse the response
        try:
            # Clean up common markdown artifacts before parsing
            cleaned_response = response_text.strip()

            # Remove markdown code blocks if present
            if cleaned_response.startswith("```"):
                cleaned_response = cleaned_response.split("```", 2)[1]
                if cleaned_response.startswith("json"):
                    cleaned_response = cleaned_response[4:]
                cleaned_response = cleaned_response.strip()

            # Remove any leading explanatory text before the first {
            if "{" in cleaned_response:
                first_brace = cleaned_response.index("{")
                if first_brace > 0:
                    cleaned_response = cleaned_response[first_brace:]

            # Remove any trailing text after the last }
            if "}" in cleaned_response:
                last_brace = cleaned_response.rindex("}") + 1
                cleaned_response = cleaned_response[:last_brace]

            parsed_response = json.loads(cleaned_response)
            result = {
                "provider": AuditProvider.GEMINI,
                "model": GEMINI_MODEL,
                "timestamp": int(time.time()),
                "response": parsed_response,
            }
            # if result["response"].get("answer").lower() not in [outcome.lower() for outcome in outcomes]:
            #     return None
            return result
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(
                f"[Attempt {attempt + 1}/{N_RETRIES}] Error parsing response: {str(e)}"
            )
            if attempt < N_RETRIES - 1:
                wait_time = RETRY_SECONDS * (attempt + 1)
                print(
                    f"[Attempt {attempt + 1}/{N_RETRIES}] Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
                continue
            else:
                return None

    return None


# Mapping between AuditProvider and corresponding audit method
AUDIT_METHODS = {
    AuditProvider.GROK: get_grok_audit,
    AuditProvider.OPENAI: get_openai_audit,
    AuditProvider.GEMINI: get_gemini_audit,
}


def create_audit_dataframe(fpmms: dict, audits: dict) -> pd.DataFrame:
    """Create a dataframe comparing market answers with AI audit predictions"""
    rows = []

    for fpmm_id, audit in audits.items():
        if fpmm_id not in fpmms:
            continue

        fpmm = fpmms[fpmm_id]
        question = fpmm.get("question", {}).get("title", "N/A")
        market_answer = answer_mapping.get(fpmm.get("currentAnswer"), "N/A")

        row = {
            "market_id": fpmm_id,
            "question": question,
            "answer": market_answer,
        }

        # Collect answers for each provider
        for provider in AuditProvider:
            answers = []
            for audit_data in audit.values():
                if (
                    isinstance(audit_data, dict)
                    and audit_data.get("provider") == provider
                ):
                    if audit_data.get("response"):
                        answer = audit_data["response"].get("answer", "N/A")
                        if answer != "N/A":
                            answers.append(answer)

            row[provider] = ", ".join(answers) if answers else "N/A"

        rows.append(row)

    return pd.DataFrame(rows)


def get_markets_to_audit(
    fpmms: dict, current_audits: dict, num_markets: int
) -> list[dict]:
    """Returns the latest num_markets closed markets that have not been audited yet."""

    already_analyzed_ids = current_audits.keys()
    output = []

    for _, fpmm in fpmms.items():
        state = get_market_state(fpmm)
        if state != MarketState.CLOSED or not fpmm.get("resolutionTimestamp"):
            continue
        if fpmm["id"] in already_analyzed_ids:
            continue
        output.append(fpmm)

    output.sort(key=lambda x: int(x.get("resolutionTimestamp", 0)), reverse=True)

    return output[:num_markets]


def audit_market(fpmm: dict) -> dict:
    """Audit a single market using specified providers, excluding failed audits."""
    providers = AUDIT_METHODS.keys()
    result = {}

    with ThreadPoolExecutor(max_workers=len(providers)) as executor:
        futures = {
            executor.submit(AUDIT_METHODS[provider], fpmm): provider
            for provider in providers
        }

        for future in futures:
            provider = futures[future]
            audit = future.result()
            if audit is not None:
                result[f"{provider}-{uuid.uuid4()}"] = audit

    return result


def fill_missing_audits(fpmms: dict, audits: dict) -> None:
    """Fill in missing audits for markets that lack any provider responses."""
    print("\nFilling missing audits...")
    markets_needing_audits = []

    for fpmm_id, audit in audits.items():
        if not isinstance(audit, dict):
            continue

        # Check which providers are missing
        missing_providers = set()
        for provider in AUDIT_METHODS:
            has_provider = any(
                isinstance(provider_audit, dict)
                and provider_audit.get("provider") == provider
                and provider_audit.get("response") is not None
                for provider_audit in audit.values()
            )
            if not has_provider:
                missing_providers.add(provider)

        if missing_providers:
            markets_needing_audits.append((fpmm_id, audit, missing_providers))

    if markets_needing_audits:
        print(f"Found {len(markets_needing_audits)} markets with missing audits")
        for fpmm_id, audit, missing_providers in tqdm(
            markets_needing_audits, desc="Filling missing audits"
        ):
            if fpmm_id in fpmms:
                fpmm = fpmms[fpmm_id]

                for provider in missing_providers:
                    provider_audit = AUDIT_METHODS[provider](fpmm)
                    if provider_audit is not None:
                        audit[f"{provider}-{uuid.uuid4()}"] = provider_audit

                audits[fpmm_id] = audit
                save_results(audits)
    else:
        print("All markets have complete audits")


def get_matching_audits(market: dict, audits: dict) -> tuple[int, int, int]:
    """Gets the number of matching, valid, and total audits for a market.

    Returns:
        (matching, valid, total) where:
        - total: audits with a response
        - valid: audits whose answer is one of the market outcomes
        - matching: valid audits that agree with the market answer
    """
    market_answer_str = get_market_current_answer(market).lower()
    question = market.get("question") or {}
    outcomes = [outcome.lower() for outcome in question.get("outcomes", [])]

    total = 0
    matching = 0
    valid = 0
    for _, audit in audits.items():
        if not isinstance(audit, dict):
            continue

        audit_answer = audit.get("response", {}).get("answer")
        if not isinstance(audit_answer, str):
            continue
        total += 1

        audit_answer_str = audit_answer.lower()
        if audit_answer_str not in outcomes:
            continue
        valid += 1
        if market_answer_str == audit_answer_str:
            matching += 1

    return matching, valid, total


def display_audit_results_html(df: pd.DataFrame, fpmms: dict, audits: dict) -> None:
    """Export audit results to HTML file and open in browser."""
    if len(df) == 0:
        print("No audited markets to display.")
        return

    # Structure: {num_valid_audits: {num_matching: count}}
    audit_breakdown: dict = {}
    total_audited_markets = 0
    invalid_audited_markets = 0

    for fpmm_id, market_audits in audits.items():
        total_audited_markets += 1
        market = fpmms.get(fpmm_id)

        if not isinstance(market, dict):
            continue

        current_answer = market.get("currentAnswer")
        if (
            isinstance(current_answer, str)
            and current_answer.lower() == INVALID_ANSWER_HEX.lower()
        ):
            invalid_audited_markets += 1
            continue

        matching, valid, _ = get_matching_audits(market, market_audits)

        # Initialize nested dict if needed
        if valid not in audit_breakdown:
            audit_breakdown[valid] = {}

        # Count markets by (valid, matching)
        audit_breakdown[valid][matching] = audit_breakdown[valid].get(matching, 0) + 1

    # Build detailed breakdown HTML
    breakdown_html = ""
    for n in sorted(audit_breakdown.keys()):
        matches_dist = audit_breakdown[n]
        total_for_n = sum(matches_dist.values())

        breakdown_html += f"<h3>Valid markets with {n} valid audits:</h3>\n<ul>\n"
        for m in sorted(matches_dist.keys()):
            count = matches_dist[m]
            breakdown_html += (
                f"  <li>Markets matching {m} audit(s): <strong>{count}</strong></li>\n"
            )
        breakdown_html += f"  <li><strong>Total: {total_for_n}</strong></li>\n"
        breakdown_html += "</ul>\n"

    # Calculate accuracy:
    # X = number of valid markets with >0 valid audits AND matches 0 audits
    # Y = number of valid markets with >0 valid audits AND matching audits = num audits
    X = 0
    Y = 0

    for n in audit_breakdown:
        if n > 0:  # valid audits > 0
            matches_dist = audit_breakdown[n]
            # Markets matching 0 audits
            X += matches_dist.get(0, 0)
            # Markets matching all N audits
            Y += matches_dist.get(n, 0)

    denominator = X + Y
    accuracy = (Y / denominator) if denominator > 0 else 0.0

    summary_html = f"""
        <h2>Audit Summary</h2>
        <p><strong>Total audited markets: {total_audited_markets}</strong></p>
        <p><strong>Invalid audited markets: {invalid_audited_markets}</strong></p>
        <hr>
        {breakdown_html}
        <hr>
        <h3>Accuracy Calculation</h3>
        <p>X = Number of valid markets with &gt;0 valid audits AND matches 0 audits: <strong>{X}</strong></p>
        <p>Y = Number of valid markets with &gt;0 valid audits AND matching audits = num audits: <strong>{Y}</strong></p>
        <p><strong>Accuracy = {Y} / ({X} + {Y}) = {accuracy:.4f} ({accuracy*100:.2f}%)</strong></p>
    """

    html_file = "market_resolution_audits.html"
    html_content = df.to_html(index=False, escape=False)

    # Add CSS styling
    styled_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Market Resolution Audits</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                background-color: #f5f5f5;
            }}
            h1 {{
                color: #333;
                text-align: center;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                background-color: white;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            th {{
                background-color: #4CAF50;
                color: white;
                padding: 12px;
                text-align: left;
                font-weight: bold;
            }}
            td {{
                padding: 10px;
                border-bottom: 1px solid #ddd;
            }}
            tr:hover {{
                background-color: #f9f9f9;
            }}
            tr:nth-child(even) {{
                background-color: #f2f2f2;
            }}
        </style>
    </head>
    <body>
        <h1>Market Resolution Audit Results</h1>
        <p><strong>Total Audited Markets:</strong> {len(df)}</p>
        {summary_html}
        {html_content}
    </body>
    </html>
    """

    # Write to file
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(styled_html)

    # Open in browser
    file_path = Path(html_file).resolve()
    webbrowser.open(f"file://{file_path}")
    print(f"\nResults saved to: {html_file}")
    print(f"Opening in browser...")


def load_audits_df(fpmms: dict, audits: dict | None = None) -> pd.DataFrame:
    """Build a per-market audit summary DataFrame.

    Args:
        fpmms: mapping of market_id -> market dict (needed for valid/matching)
        audits: mapping of market_id -> audit_dict. If None, loads from cache.

    Returns:
        DataFrame with columns: market_id, n_audits, n_valid_audits, n_matching_audits
    """
    if audits is None:
        audits = load_existing_audits().get("fpmmAudits", {})

    rows = []
    for market_id, market_audits in audits.items():
        market = fpmms.get(market_id)
        if not isinstance(market, dict):
            continue

        matching, valid, total = get_matching_audits(market, market_audits)

        rows.append(
            {
                "market_id": market_id,
                "n_audits": total,
                "n_valid_audits": valid,
                "n_matching_audits": matching,
            }
        )

    return pd.DataFrame(rows)


def main() -> None:
    """Main entry point for command-line execution."""

    parser = argparse.ArgumentParser(
        description="Profile market resolution accuracy by comparing with OpenAI predictions."
    )
    parser.add_argument(
        "--creator",
        type=str,
        default="0x89c5cc945dd550BcFfb72Fe42BfF002429F46Fec",
        help="One or more creator addresses to analyze markets for",
    )
    parser.add_argument(
        "-n",
        "--num-markets",
        type=int,
        default=0,
        help="Number of recent closed, unaudited markets to analyze.",
    )
    parser.add_argument(
        "-f",
        "--fill-missing",
        action="store_true",
        help="Fill in missing audits for markets that lack any provider audit results.",
    )

    args = parser.parse_args()
    fpmms_data = get_fpmms(args.creator)
    fpmms = fpmms_data.get("fixedProductMarketMakers", {})
    audits = load_existing_audits().get("fpmmAudits", {})
    markets_to_audit = get_markets_to_audit(fpmms, audits, args.num_markets)

    print(f"Found {len(markets_to_audit)} closed markets to analyze")

    for fpmm in tqdm(markets_to_audit, desc="Auditing market resolution"):
        audit = audit_market(fpmm)
        fpmm_id = fpmm["id"]
        audits[fpmm_id] = audit
        save_results(audits)

    # Fill in missing audits if requested
    if args.fill_missing:
        fill_missing_audits(fpmms, audits)

    # Display results as HTML
    df = create_audit_dataframe(fpmms, audits)
    display_audit_results_html(df, fpmms, audits)


if __name__ == "__main__":
    main()

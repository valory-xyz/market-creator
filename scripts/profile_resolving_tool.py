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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

from omen_subgraph_utils import get_fpmms, get_market_state, MarketState, answer_mapping


load_dotenv()


RESULTS_JSON_PATH = "profile_resolving_tool.json"
OPENAI_MODEL = "gpt-5.2"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def migrate_old_format(results: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate old format to new format with nested ai_responses."""
    if "markets" not in results:
        return results
    
    migrated = False
    for market_id, market_data in results["markets"].items():
        # Check if this is old format (has openai_answer and openai_response at top level)
        if "openai_answer" in market_data or "openai_response" in market_data:
            migrated = True
            
            # Get the openai response or reconstruct it
            openai_response = market_data.get("openai_response", {})
            if not openai_response:
                openai_response = {
                    "answer": market_data.get("openai_answer", "UNKNOWN"),
                    "sources": [],
                    "reasoning": "",
                    "model": "unknown"
                }
            
            # Create new format
            market_data["ai_responses"] = {
                f"openai{OPENAI_MODEL}": openai_response
            }
            
            # Recalculate match based on new format
            openai_answer = openai_response.get("answer", "UNKNOWN")
            actual_answer = market_data.get("actual_answer")
            if openai_answer != "UNKNOWN" and actual_answer is not None:
                market_data["match"] = (openai_answer == actual_answer)
            else:
                market_data["match"] = None
            
            # Remove old fields
            market_data.pop("openai_answer", None)
            market_data.pop("openai_response", None)
    
    if migrated:
        print(f"Migrated {len(results['markets'])} markets to new format")
    
    return results


def load_existing_results() -> Dict[str, Any]:
    """Load previously computed results from file and migrate if needed."""
    try:
        with open(RESULTS_JSON_PATH, "r", encoding="UTF-8") as json_file:
            results = json.load(json_file)
            return migrate_old_format(results)
    except FileNotFoundError:
        return {"markets": {}}


def save_results(results: Dict[str, Any]) -> None:
    """Save results to file."""
    with open(RESULTS_JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, sort_keys=True)


def get_openai_response(question: str, outcomes: List[str]) -> Dict:
    """Query OpenAI as a fact-checker for a prediction market question.
    
    Returns structured JSON with:
        - answer: the verified outcome or 'UNKNOWN'
        - sources: URLs supporting the claim
        - reasoning: explanation of the verification process
    """
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Format outcomes with 1-based numbering
    outcomes_str = "\n".join([f"{i+1}. {outcome}" for i, outcome in enumerate(outcomes)])

    # Prompt clearly instructing JSON output
    prompt = f"""
You are an information verification assistant. Your task is to fact-check a prediction market question
and determine the correct outcome based only on reliable, verifiable sources.

Question: {question}

Possible outcomes:
{outcomes_str}

Instructions:
1. Determine the correct outcome with high confidence. If unsure, answer "UNKNOWN".
2. Provide a list of credible sources (URLs) that support your answer.
3. Explain your reasoning clearly and concisely.

Output **only** valid JSON in the following format:

{{
  "answer": "<the correct outcome, or 'UNKNOWN'>",
  "sources": ["<list of URLs used for verification>"],
  "reasoning": "<concise explanation of why this outcome is correct or why UNKNOWN>"
}}
"""

    response = client.responses.create(
        model=OPENAI_MODEL,
        tools=[{"type": "web_search"}],  # enable web search
        input=prompt,
        temperature=0,
    )

    # Parse the JSON from the text output
    try:
        result = json.loads(response.output_text)
        result["model"] = OPENAI_MODEL
        return result
    except json.JSONDecodeError:
        # fallback
        return {
            "answer": "UNKNOWN",
            "model": OPENAI_MODEL,
            "sources": [],
            "reasoning": response.output_text
        }


def get_recent_closed_markets(fpmms: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    """Get the most recent closed markets, excluding already analyzed ones."""
    # Load existing results to know which markets we've already analyzed
    existing_results = load_existing_results()
    already_analyzed_ids = set(existing_results.get("markets", {}).keys())
    
    closed_markets = []
    
    for _, fpmm in fpmms.items():
        state = get_market_state(fpmm)

        if state != MarketState.CLOSED or not fpmm.get("resolutionTimestamp"):  # TODO fixme, why some markets don't have resolutionTimestamp?
            continue
        
        # Skip markets we've already analyzed
        if fpmm["id"] in already_analyzed_ids:
            continue

        closed_markets.append(fpmm)
    
    # Sort by answerFinalizedTimestamp (most recent first)
    closed_markets.sort(
        key=lambda x: int(x.get("resolutionTimestamp", 0)),
        reverse=True
    )
    
    return closed_markets[:limit]


def analyze_market(fpmm: Dict[str, Any], existing_results: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze a single market by comparing actual answer with OpenAI prediction."""
    fpmm_id = fpmm["id"]
    
    # Check if we already have results for this market
    if fpmm_id in existing_results.get("markets", {}):
        return existing_results["markets"][fpmm_id]
    
    question_data = fpmm.get("question", {})
    question_title = question_data.get("title", "")
        
    actual_answer = answer_mapping.get(fpmm.get("currentAnswer"))
    
    openai_response = get_openai_response(question_title, question_data.get("outcomes", []))
    openai_answer = openai_response.get("answer", "UNKNOWN")
    
    # Only calculate match if OpenAI provided a definitive answer (not UNKNOWN)
    match = None
    if openai_answer != "UNKNOWN" and actual_answer is not None:
        match = (openai_answer == actual_answer)
   
    return {
        "fpmm_id": fpmm_id,
        "question": question_title,
        "actual_answer": actual_answer,
        "ai_responses": {
            "openai": openai_response
        },
        "match": match,
        "analyzed_timestamp": datetime.now(timezone.utc).isoformat(),
        "answer_finalized_timestamp": fpmm.get("answerFinalizedTimestamp")
    }


def main() -> None:
    """Main entry point for command-line execution."""
    
    parser = argparse.ArgumentParser(
        description="Profile market resolution accuracy by comparing with OpenAI predictions."
    )
    parser.add_argument(
        "--creators",
        type=str,
        nargs="+",
        default=["0x89c5cc945dd550BcFfb72Fe42BfF002429F46Fec"],
        help="One or more creator addresses to analyze markets for"
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=5,
        help="Number of most recent closed markets to analyze (default: 5)"
    )
    
    args = parser.parse_args()
    
    print(f"Fetching FPMMs for {len(args.creators)} creator(s)...")
    fpmms = get_fpmms(args.creators, populate_trades=False)
    
    print(f"Filtering closed markets without trades...")
    closed_markets = get_recent_closed_markets(fpmms, args.limit)
    print(f"Found {len(closed_markets)} closed markets to analyze")
    
    existing_results = load_existing_results()
    
    # Analyze markets
    results = existing_results.copy()
    if "markets" not in results:
        results["markets"] = {}
    
    correct_count = 0
    incorrect_count = 0
    unknown_count = 0
    
    for fpmm in tqdm(closed_markets, desc="Analyzing markets"):
        result = analyze_market(fpmm, existing_results)
        results["markets"][result["fpmm_id"]] = result
        save_results(results)
    
    # Recalculate statistics from ALL markets in the file
    correct_count = 0
    incorrect_count = 0
    unknown_count = 0
    
    for _, market_result in results["markets"].items():
        if market_result["match"] is True:
            correct_count += 1
        elif market_result["match"] is False:
            incorrect_count += 1
        else:
            unknown_count += 1
    
    total_analyzed = correct_count + incorrect_count + unknown_count
    accuracy = (correct_count / (correct_count + incorrect_count) * 100) if (correct_count + incorrect_count) > 0 else 0
    
    results["statistics"] = {
        "total_markets_analyzed": total_analyzed,
        "correct_predictions": correct_count,
        "incorrect_predictions": incorrect_count,
        "unknown_predictions": unknown_count,
        "accuracy_percentage": round(accuracy, 2),
        "last_updated": datetime.now(timezone.utc).isoformat()
    }
    
    save_results(results)
    
    print(f"\n{'='*50}")
    print(f"Analysis Complete")
    print(f"{'='*50}")
    print(f"Total markets analyzed: {total_analyzed}")
    print(f"Correct predictions: {correct_count}")
    print(f"Incorrect predictions: {incorrect_count}")
    print(f"Unknown predictions: {unknown_count}")
    print(f"Accuracy: {accuracy:.2f}%")
    print(f"\nResults saved to: {RESULTS_JSON_PATH}")


if __name__ == "__main__":
    main()
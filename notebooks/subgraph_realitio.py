# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2024-2026 Valory AG
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

"""Fetch Realitio question responses from the Reality.eth subgraph.

Queries individual answer submissions (responses) for a set of question IDs.
This gives the full submission history — not just distinct answer values — so
we can accurately determine whether a question was challenged, how many times,
and whether the answer was flipped.
"""

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

import pandas as pd
from dotenv import load_dotenv
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport
from tqdm import tqdm
from web3 import Web3

# Reality.eth contract on Gnosis Chain
REALITIO_CONTRACT = "0x79e32aE03fb27B07C89c0c568F80287C01ca2E57"
MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"
_RPC_URL = os.getenv("GNOSIS_RPC", "https://gnosis-rpc.publicnode.com")

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

REALITIO_SUBGRAPH_ID = "E7ymrCnNcQdAAgLbdFWzGE5mvr5Mb5T9VfT43FqA7bNh"
_API_KEY = os.getenv("THEGRAPH_API_KEY", "")
REALITIO_SUBGRAPH_URL = (
    f"https://gateway.thegraph.com/api/{_API_KEY}/subgraphs/id/{REALITIO_SUBGRAPH_ID}"
)

RESPONSES_QUERY = """
query responses_query($question_ids: [Bytes!]!) {
  questions(where: {questionId_in: $question_ids}, first: 1000) {
    id
    questionId
    currentAnswer
    currentAnswerBond
    responses(orderBy: timestamp, orderDirection: asc) {
      id
      timestamp
      answer
      bond
      user
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_realitio_responses(
    question_ids: List[str],
) -> Dict[str, Any]:
    """Fetch Realitio responses for a list of question IDs.

    The Omen subgraph stores question IDs as the raw question hash
    (``questionId`` in the Realitio schema), while the Realitio subgraph
    ``id`` is a compound key (``{contract}-{questionId}``).  We query by
    ``questionId_in`` and key the result dict by ``questionId`` so it
    matches the Omen DataFrame's ``question_id`` column.

    :param question_ids: list of Realitio question hashes (from Omen subgraph)
    :return: dict of question_id -> question data with responses
    """
    transport = RequestsHTTPTransport(url=REALITIO_SUBGRAPH_URL)
    client = Client(transport=transport, fetch_schema_from_transport=True)

    result: Dict[str, Any] = {}
    batch_size = 100
    n_total = len(question_ids)
    pbar = tqdm(total=n_total, desc="Fetching Realitio responses")
    for i in range(0, n_total, batch_size):
        batch = question_ids[i : i + batch_size]
        response = client.execute(
            gql(RESPONSES_QUERY),
            variable_values={"question_ids": batch},
        )
        for q in response.get("questions", []):
            result[q["questionId"]] = q
        pbar.update(len(batch))
    pbar.close()

    print(f"  Realitio: {len(result)}/{len(question_ids)} questions fetched")
    return result


def realitio_to_dataframe(questions: Dict[str, Any]) -> pd.DataFrame:
    """Convert Realitio question data to a DataFrame.

    :param questions: dict of question_id -> question data as returned by
        ``fetch_realitio_responses()``
    :return: DataFrame with one row per question and columns for response
        count, challenge status, and flip detection.
    """
    rows = []
    for qid, q in questions.items():
        responses = q.get("responses") or []
        n_responses = len(responses)
        current_answer = q.get("currentAnswer")

        first_response_answer = responses[0]["answer"] if responses else None
        is_challenged = n_responses > 1
        is_flipped = (
            is_challenged
            and current_answer is not None
            and first_response_answer is not None
            and current_answer.lower() != first_response_answer.lower()
        )

        responders = sorted({r["user"].lower() for r in responses if r.get("user")})

        rows.append(
            {
                "question_id": qid,
                "n_responses": n_responses,
                "is_challenged": is_challenged,
                "is_flipped": is_flipped,
                "first_response_answer": first_response_answer,
                "responders": responders,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "question_id",
                "n_responses",
                "is_challenged",
                "is_flipped",
                "first_response_answer",
                "responders",
            ]
        )
    return pd.DataFrame(rows)


def normalize_realitio_answer(answer_hex) -> str:
    """Normalize a raw Realitio answer hex to ``Yes``/``No``/``Invalid``/``Unknown``.

    Assumes the standard binary-market outcome encoding used by Omen:
      - ``0x00..00`` → ``Yes`` (outcome index 0)
      - ``0x00..01`` → ``No`` (outcome index 1)
      - ``0xff..ff`` → ``Invalid`` (special sentinel)
      - anything else, None, or unparseable → ``Unknown``

    :param answer_hex: raw answer bytes32 as a hex string (with or without 0x),
        or None.
    :return: verdict label.
    """
    if not isinstance(answer_hex, str) or not answer_hex:
        return "Unknown"
    cleaned = answer_hex.lower().strip()
    if cleaned.startswith("0x"):
        cleaned = cleaned[2:]
    if len(cleaned) != 64:
        return "Unknown"
    if cleaned == "f" * 64:
        return "Invalid"
    try:
        idx = int(cleaned, 16)
    except ValueError:
        return "Unknown"
    if idx == 0:
        return "Yes"
    if idx == 1:
        return "No"
    return "Unknown"


# ---------------------------------------------------------------------------
# Locked bonds (on-chain claim status)
# ---------------------------------------------------------------------------

_REALITIO_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "question_id", "type": "bytes32"}],
        "name": "getHistoryHash",
        "outputs": [{"name": "", "type": "bytes32"}],
        "stateMutability": "view",
        "type": "function",
    },
]

_MULTICALL3_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"name": "target", "type": "address"},
                    {"name": "allowFailure", "type": "bool"},
                    {"name": "callData", "type": "bytes"},
                ],
                "name": "calls",
                "type": "tuple[]",
            }
        ],
        "name": "aggregate3",
        "outputs": [
            {
                "components": [
                    {"name": "success", "type": "bool"},
                    {"name": "returnData", "type": "bytes"},
                ],
                "name": "returnData",
                "type": "tuple[]",
            }
        ],
        "stateMutability": "payable",
        "type": "function",
    },
]


def _check_unclaimed_questions(question_ids: Iterable[str]) -> Set[str]:
    """Return the subset of question IDs whose Realitio bond is unclaimed.

    A question is *unclaimed* iff ``getHistoryHash(question_id) != 0``.
    Uses Multicall3 to batch the on-chain calls.

    :param question_ids: iterable of Realitio question IDs (hex strings).
    :return: set of question IDs (lowercased) that are still unclaimed.
    """
    qids = list({q.lower() for q in question_ids if q})
    if not qids:
        return set()

    w3 = Web3(Web3.HTTPProvider(_RPC_URL))
    realitio = w3.eth.contract(
        address=w3.to_checksum_address(REALITIO_CONTRACT), abi=_REALITIO_ABI
    )
    multicall = w3.eth.contract(
        address=w3.to_checksum_address(MULTICALL3), abi=_MULTICALL3_ABI
    )
    realitio_addr = w3.to_checksum_address(REALITIO_CONTRACT)

    unclaimed: Set[str] = set()
    batch_size = 500
    pbar = tqdm(total=len(qids), desc="Checking Realitio claim status", unit=" q")
    for i in range(0, len(qids), batch_size):
        batch = qids[i : i + batch_size]
        calls = []
        for qid in batch:
            qbytes = bytes.fromhex(qid[2:] if qid.startswith("0x") else qid)
            data = realitio.functions.getHistoryHash(qbytes)._encode_transaction_data()
            calls.append((realitio_addr, True, bytes.fromhex(data[2:])))
        results = multicall.functions.aggregate3(calls).call()
        for qid, (ok, ret) in zip(batch, results):
            if not ok or len(ret) < 32:
                continue
            if int.from_bytes(ret, "big") != 0:
                unclaimed.add(qid)
        pbar.update(len(batch))
    pbar.close()
    return unclaimed


def _simulate_claim_payouts(
    responses: List[Dict[str, Any]], best_answer: str
) -> Dict[str, int]:
    """Simulate ``Realitio.claimWinnings`` payouts per user.

    Implements the exact algorithm from RealitioERC20.sol — iterates the
    response history in **reverse chronological order**, accumulating
    queued funds and handling answer-takeover fees, then sums each
    payee's resulting balance.

    :param responses: list of responses for one question, in chronological
        order (as returned by the Realitio subgraph). Each response must
        have ``user``, ``answer``, ``bond`` keys.
    :param best_answer: the final accepted answer (hex string, lowercased).
    :return: mapping of user address (lowercased) -> payout in wei.
    """
    payouts: Dict[str, int] = {}
    if not responses:
        return payouts

    # Reverse: contract iterates from last (final) answer back to first
    history = list(reversed(responses))
    payee: str = ""
    queued_funds = 0
    last_bond = 0  # bond from the response that came AFTER the current one

    for entry in history:
        addr = (entry.get("user") or "").lower()
        try:
            bond = int(entry.get("bond") or 0)
        except (ValueError, TypeError):
            return {}  # bail out on bad data
        answer = (entry.get("answer") or "").lower()

        # Step 1: add the previous (newer) iteration's bond to queued funds
        queued_funds += last_bond

        # Step 2: process this history item (matches _processHistoryItem)
        if answer == best_answer:
            if not payee:
                # First winning answerer encountered (i.e. the LAST winning
                # response in chronological order — the one that "stuck")
                payee = addr
                # Note: we ignore question bounty (it's 0 for Omen markets)
            elif addr != payee:
                # Earlier same-answer responder takes over
                takeover_fee = bond if queued_funds >= bond else queued_funds
                # Pay the previous (newer) payee what's left after the fee
                payouts[payee] = payouts.get(payee, 0) + (queued_funds - takeover_fee)
                # Restart for the new (earlier) payee
                payee = addr
                queued_funds = takeover_fee

        # Step 3: lineup current bond for next iteration
        last_bond = bond

    # End of loop: pay the final payee queued_funds + last_bond
    if payee:
        payouts[payee] = payouts.get(payee, 0) + queued_funds + last_bond

    return payouts


def compute_locked_bonds(
    realitio_raw: Dict[str, Any],
    user_addresses: Iterable[str],
    question_ids: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Compute locked Realitio bonds per (user, question).

    For each question with at least one response from a tracked user, runs
    the exact ``claimWinnings`` simulation against the response history to
    compute the precise payout. Filtered to questions whose on-chain
    ``getHistoryHash`` is still non-zero (i.e. not yet claimed).

    Two flavours of "locked" amount are returned:

    - **actual_xdai**: precise payout from the claim simulation. 100%
      accurate when the question has a non-empty ``currentAnswer`` and the
      response history is complete.
    - **estimated_xdai**: fallback raw sum of the user's posted bonds for
      questions where the simulation can't be trusted (no response data,
      missing currentAnswer, etc.). This is an upper bound only.

    :param realitio_raw: dict of question_id -> question data (responses).
    :param user_addresses: iterable of user addresses (lowercased) to track.
    :param question_ids: optional whitelist of question IDs to consider.
        If None, all questions in ``realitio_raw`` are considered.
    :return: DataFrame with columns user, question_id, actual_xdai,
        estimated_xdai, kind.
    """
    user_set = {u.lower() for u in user_addresses}
    qid_filter = (
        {q.lower() for q in question_ids if q} if question_ids is not None else None
    )

    # Step 1: identify candidate (user, question, payout) tuples.
    candidate_rows: List[Dict[str, Any]] = []
    candidate_qids: Set[str] = set()

    for qid, q in realitio_raw.items():
        if qid_filter is not None and qid.lower() not in qid_filter:
            continue
        responses = q.get("responses") or []
        users_on_q = {(r.get("user") or "").lower() for r in responses} & user_set
        if not users_on_q:
            continue

        best_answer = (q.get("currentAnswer") or "").lower()
        # Run precise simulation only when we have a final answer
        sim_payouts: Dict[str, int] = {}
        if best_answer:
            sim_payouts = _simulate_claim_payouts(responses, best_answer)

        for user in users_on_q:
            actual_wei = sim_payouts.get(user, 0)

            # Estimated upper bound: sum of bonds the user posted
            estimated_wei = 0
            for r in responses:
                if (r.get("user") or "").lower() == user:
                    try:
                        estimated_wei += int(r.get("bond") or 0)
                    except (ValueError, TypeError):
                        pass

            if actual_wei == 0 and estimated_wei == 0:
                continue

            # Classify: "verified" if simulation produced a non-zero answer
            # for this user; "estimated" otherwise (we have to fall back to
            # the upper bound because we can't trust the simulation).
            if best_answer and actual_wei > 0:
                kind = "verified"
                actual_xdai = actual_wei / 1e18
                estimated_xdai = 0.0
            elif best_answer:
                # Simulation ran but user got nothing (their answers all lost).
                # This is also verified — they get nothing.
                kind = "verified"
                actual_xdai = 0.0
                estimated_xdai = 0.0
            else:
                # No final answer in subgraph data — fall back to raw sum.
                kind = "estimated"
                actual_xdai = 0.0
                estimated_xdai = estimated_wei / 1e18

            if actual_xdai == 0 and estimated_xdai == 0:
                continue

            candidate_rows.append(
                {
                    "user": user,
                    "question_id": qid.lower(),
                    "actual_xdai": actual_xdai,
                    "estimated_xdai": estimated_xdai,
                    "kind": kind,
                }
            )
            candidate_qids.add(qid.lower())

    if not candidate_rows:
        return pd.DataFrame(
            columns=["user", "question_id", "actual_xdai", "estimated_xdai", "kind"]
        )

    # Step 2: check on-chain which questions are still unclaimed
    unclaimed = _check_unclaimed_questions(candidate_qids)

    df = pd.DataFrame(candidate_rows)
    df = df[df["question_id"].isin(unclaimed)]
    df.reset_index(drop=True, inplace=True)
    return df

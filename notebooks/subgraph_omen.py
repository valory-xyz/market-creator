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

"""Script for retrieving Omen markets."""

import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Set

import pandas as pd
import requests as http_requests
from dotenv import load_dotenv
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport
from tqdm import tqdm
from web3 import Web3

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


answer_mapping = defaultdict(
    lambda: "Unknown",
    {
        "0x0000000000000000000000000000000000000000000000000000000000000000": "Yes",
        "0x0000000000000000000000000000000000000000000000000000000000000001": "No",
        "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff": "Invalid",
    },
)


TEXT_ALIGNMENT = 30
MINIMUM_WRITE_FILE_DELAY_SECONDS = 20
FPMMS_JSON_PATH = "fpmms.json"
INVALID_ANSWER_HEX = "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
INVALID_ANSWER = "Invalid"
NA_ANSWER = "N/A"
OMEN_SUBGRAPH_ID = "9fUVQpFwzpdWS9bq5WkAnmKbNNcoBwatMR4yZq81pbbz"
_API_KEY = os.getenv("THEGRAPH_API_KEY", "")
THEGRAPH_ENDPOINT = (
    f"https://gateway.thegraph.com/api/{_API_KEY}/subgraphs/id/{OMEN_SUBGRAPH_ID}"
)

# ConditionalTokens / redemption constants
CONDITIONAL_TOKENS = "0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce"
WXDAI = "0xe91D153E0b41518A2Ce8Dd3D7944Fa863463a97d"
MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"
CT_SUBGRAPH_URL = os.getenv(
    "CT_SUBGRAPH_URL", "https://conditional-tokens.subgraph.autonolas.tech"
)
_RPC_URL = os.getenv("GNOSIS_RPC", "https://gnosis-rpc.publicnode.com")
_CONDITION_ID_BATCH = 100
_SUBGRAPH_PAGE = 1000

FPMMS_QUERY = """
query fpmms_query($creator: Bytes, $creationTimestamp_gt: BigInt) {
    fixedProductMarketMakers(
        where: {creator: $creator, creationTimestamp_gt: $creationTimestamp_gt}
        orderBy: creationTimestamp
        orderDirection: asc
        first: 1000
    ) {
        question {
            id
            title
            outcomes
            currentAnswer
            currentAnswerBond
            currentAnswerTimestamp
        }
        id
        openingTimestamp
        resolutionTimestamp
        creationTimestamp
        isPendingArbitration
        answerFinalizedTimestamp
        currentAnswer
        currentAnswerBond
        collateralVolume
        outcomeTokenMarginalPrices
        outcomeTokenAmounts
    }
}
"""

TRADES_QUERY = """
query fpmms_query($fpmm: String, $id_gt: ID) {
    fpmmTrades(
        where: {fpmm: $fpmm, id_gt: $id_gt, type: Buy}
        orderBy: id
        orderDirection: asc
        first: 1000
    ) {
        collateralAmount
        outcomeIndex
        outcomeTokensTraded
        id
        oldOutcomeTokenMarginalPrice
        outcomeTokenMarginalPrice
        type
        collateralAmountUSD
        creationTimestamp
        feeAmount
  }
}
"""

LAST_TRADES_BATCH_QUERY = """
query last_trades($fpmm_ids: [String!]!, $id_gt: ID!) {
    fpmmTrades(
        where: {fpmm_in: $fpmm_ids, id_gt: $id_gt}
        orderBy: id
        orderDirection: asc
        first: 1000
    ) {
        id
        fpmm { id }
        outcomeIndex
        outcomeTokenMarginalPrice
        creationTimestamp
    }
}
"""


class MarketState(Enum):
    """Market state"""

    OPEN = 1
    PENDING = 2
    FINALIZING = 3
    ARBITRATING = 4
    CLOSED = 5
    UNKNOWN = 6

    def __str__(self) -> str:
        """Prints the market status."""
        return self.name.capitalize()

    def __lt__(self, other):  # noqa: D105
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented

    def __le__(self, other):  # noqa: D105
        if self.__class__ is other.__class__:
            return self.value <= other.value
        return NotImplemented

    def __gt__(self, other):  # noqa: D105
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented

    def __ge__(self, other):  # noqa: D105
        if self.__class__ is other.__class__:
            return self.value >= other.value
        return NotImplemented


def get_market_state(market: Dict[str, Any]) -> MarketState:
    """Get market state"""
    try:
        now = datetime.now(timezone.utc)

        market_status = MarketState.CLOSED
        if market["currentAnswer"] is None and now >= datetime.fromtimestamp(
            float(market.get("openingTimestamp", 0)), tz=timezone.utc
        ):
            market_status = MarketState.PENDING
        elif market["currentAnswer"] is None:
            market_status = MarketState.OPEN
        elif market["isPendingArbitration"]:
            market_status = MarketState.ARBITRATING
        elif now < datetime.fromtimestamp(
            float(market.get("answerFinalizedTimestamp", 0)), tz=timezone.utc
        ):
            market_status = MarketState.FINALIZING

        return market_status
    except Exception:  # pylint: disable=broad-except
        return MarketState.UNKNOWN


def get_market_current_answer(market: dict) -> str:
    """Get market current answer"""
    current_answer = market.get("currentAnswer", "")

    if not current_answer:
        return NA_ANSWER

    if current_answer.lower() == INVALID_ANSWER_HEX.lower():
        return INVALID_ANSWER

    answer_index = int(current_answer, 16)
    outcomes = market.get("question", {}).get("outcomes", [])
    return outcomes[answer_index]


def _populate_missing_buy_trades(fpmms: Dict[str, Any]) -> None:
    transport = RequestsHTTPTransport(url=THEGRAPH_ENDPOINT)
    client = Client(transport=transport, fetch_schema_from_transport=True)

    for _, fpmm in tqdm(
        fpmms.items(),
        desc=f"{'Fetching trades':>{TEXT_ALIGNMENT}}",
        miniters=1,
    ):
        state = get_market_state(fpmm)

        if state is not MarketState.CLOSED:
            continue

        if "trades" in fpmm:
            continue

        trades = fpmm.setdefault("trades", {})
        id_gt = "0x00"
        while True:
            variables = {
                "fpmm": fpmm["id"],
                "id_gt": id_gt,
            }
            response = client.execute(gql(TRADES_QUERY), variable_values=variables)
            items = response.get("fpmmTrades", [])

            if not items:
                break

            for trade in items:
                if trade["id"] not in trades:
                    trades[trade["id"]] = trade

            id_gt = items[-1]["id"]
            _write_db_to_file(fpmms)

    _write_db_to_file(fpmms, True)


last_write_time = 0.0


def _write_db_to_file(fpmms: Dict[str, Any], force_write: bool = False) -> None:
    global last_write_time  # pylint: disable=global-statement
    now = time.time()

    if force_write or (now - last_write_time) >= MINIMUM_WRITE_FILE_DELAY_SECONDS:
        with open(FPMMS_JSON_PATH, "w", encoding="utf-8") as file:
            json.dump(
                {"fixedProductMarketMakers": fpmms}, file, indent=2, sort_keys=True
            )
        last_write_time = now


_LAST_TRADE_BATCH_SIZE = 200


def _fetch_last_trades_batch(
    market_ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    """Fetch all trades for a batch of markets (paginated).

    Keeps only the latest trade per market (highest creationTimestamp).

    :param market_ids: list of market addresses (max ~200 per call).
    :return: mapping of market_id -> last trade dict (raw subgraph).
    """
    transport = RequestsHTTPTransport(url=THEGRAPH_ENDPOINT)
    client = Client(transport=transport, fetch_schema_from_transport=True)

    result: Dict[str, Dict[str, Any]] = {}
    id_gt = "0x00"
    while True:
        response = client.execute(
            gql(LAST_TRADES_BATCH_QUERY),
            variable_values={"fpmm_ids": market_ids, "id_gt": id_gt},
        )
        trades = response.get("fpmmTrades", [])
        if not trades:
            break
        for t in trades:
            mid = t["fpmm"]["id"]
            prev = result.get(mid)
            if not prev or t["creationTimestamp"] > prev["creationTimestamp"]:
                result[mid] = t
        id_gt = trades[-1]["id"]
        if len(trades) < 1000:
            break
    return result


def _fetch_last_trades(market_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Fetch the last trade for each market, batched and threaded.

    :param market_ids: list of market addresses to query.
    :return: mapping of market_id -> last trade dict (raw subgraph).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    batches = [
        market_ids[i : i + _LAST_TRADE_BATCH_SIZE]
        for i in range(0, len(market_ids), _LAST_TRADE_BATCH_SIZE)
    ]

    result: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(_fetch_last_trades_batch, batch): batch
            for batch in batches
        }
        for future in tqdm(
            as_completed(futures),
            total=len(futures),
            desc=f"{'Fetching last trades':>{TEXT_ALIGNMENT}}",
            miniters=1,
        ):
            result.update(future.result())
    return result


def get_fpmms(creator: str) -> dict:
    """Get Fixed Product Market Makers for one or more creators."""

    fpmms = {}

    transport = RequestsHTTPTransport(url=THEGRAPH_ENDPOINT)
    client = Client(transport=transport, fetch_schema_from_transport=True)

    spinner = tqdm(desc=f"Fetching fpmms for {creator[:10]}…", unit=" markets", bar_format="{desc}: {n}{unit} {elapsed}")
    creation_timestamp_gt = 0
    while True:
        variables = {
            "creator": creator,
            "creationTimestamp_gt": creation_timestamp_gt,
        }
        response = client.execute(gql(FPMMS_QUERY), variable_values=variables)
        items = response.get("fixedProductMarketMakers", [])

        if not items:
            break

        for fpmm in items:
            if fpmm["id"] not in fpmms:
                fpmms[fpmm["id"]] = fpmm

        spinner.n = len(fpmms)
        spinner.refresh()
        creation_timestamp_gt = items[-1]["creationTimestamp"]

    spinner.close()
    return {"fixedProductMarketMakers": fpmms}


def enrich_last_trades(fpmms: dict, market_ids: List[str]) -> None:
    """Fetch last trades only for the given market IDs and attach to fpmms.

    Call this from the notebook after filtering to only the markets that
    will be displayed (e.g. pending/finalizing).

    :param fpmms: mapping of market_id -> market dict (mutated in place).
    :param market_ids: list of market IDs to fetch last trades for.
    """
    need = [
        mid for mid in market_ids
        if mid in fpmms
        and not fpmms[mid].get("outcomeTokenMarginalPrices")
        and int(fpmms[mid].get("collateralVolume") or 0) > 0
    ]
    if not need:
        return
    last_trades = _fetch_last_trades(need)
    for mid, trade in last_trades.items():
        fpmms[mid]["lastTrade"] = trade


# ---------------------------------------------------------------------------
# DataFrame builder
# ---------------------------------------------------------------------------

def markets_to_dataframe(fpmms_dict: dict) -> pd.DataFrame:
    """Convert a dict of FPMM market dicts into a DataFrame.

    :param fpmms_dict: mapping of market_id -> market dict (the value of
        ``get_fpmms(...)["fixedProductMarketMakers"]``)
    :return: DataFrame with one row per market and pre-computed columns for
        state, answer info, etc.  Challenge fields (is_challenged,
        is_flipped, n_responses) come from ``realitio_questions.py``.
    """
    rows = []
    for market_id, m in fpmms_dict.items():
        question = m.get("question") or {}
        current_answer_hex = m.get("currentAnswer") or question.get("currentAnswer")
        bond = int(
            m.get("currentAnswerBond")
            or question.get("currentAnswerBond")
            or 0
        )

        is_invalid = (
            isinstance(current_answer_hex, str)
            and current_answer_hex.lower() == INVALID_ANSWER_HEX.lower()
        )

        rows.append(
            {
                "market_id": market_id,
                "question_id": question.get("id"),
                "title": question.get("title"),
                "outcomes": question.get("outcomes"),
                "creation_ts": _ts_to_datetime(m.get("creationTimestamp")),
                "opening_ts": _ts_to_datetime(m.get("openingTimestamp")),
                "resolution_ts": _ts_to_datetime(m.get("resolutionTimestamp")),
                "finalized_ts": _ts_to_datetime(m.get("answerFinalizedTimestamp")),
                "state": get_market_state(m),
                "current_answer": get_market_current_answer(m),
                "current_answer_hex": current_answer_hex,
                "is_invalid": is_invalid,
                "current_answer_bond": bond,
                "collateral_volume": float(m.get("collateralVolume") or 0) / 1e18,
                "outcome_prices": _calc_prices(m),
            }
        )

    return pd.DataFrame(rows)


def _calc_prices(m: dict) -> list:
    """Compute outcome prices from subgraph data.

    Priority:
      1. ``outcomeTokenMarginalPrices`` — live prices (active liquidity)
      2. ``outcomeTokenAmounts`` — CPMM formula (same as Presagio)
      3. ``lastTrade.outcomeTokenMarginalPrice`` — historical snapshot
         from the last trade before liquidity was removed

    :param m: raw market dict from the subgraph.
    :return: list of floats (one per outcome, summing to ~1), or [].
    """
    # 1. Prefer marginal prices when the subgraph provides them
    raw_prices = m.get("outcomeTokenMarginalPrices")
    if raw_prices and all(float(p) > 0 for p in raw_prices):
        return [float(p) for p in raw_prices]

    # 2. Fallback: CPMM formula from outcomeTokenAmounts
    raw_amounts = m.get("outcomeTokenAmounts") or []
    amounts = [int(a) for a in raw_amounts]
    if amounts and all(a > 0 for a in amounts):
        product = 1
        for a in amounts:
            product *= a
        inv = [product // a for a in amounts]
        denom = sum(inv)
        return [v / denom for v in inv]

    # 3. Fallback: last trade marginal price (binary markets only)
    last_trade = m.get("lastTrade")
    if last_trade and last_trade.get("outcomeTokenMarginalPrice"):
        n_outcomes = len(
            (m.get("question") or {}).get("outcomes") or []
        )
        if n_outcomes == 2:
            p = float(last_trade["outcomeTokenMarginalPrice"])
            idx = int(last_trade.get("outcomeIndex", 0))
            prices = [0.0, 0.0]
            prices[idx] = p
            prices[1 - idx] = 1.0 - p
            return prices

    return []


def _ts_to_datetime(ts) -> datetime | None:
    """Convert a subgraph timestamp string to a UTC datetime, or None."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Redeemable positions
# ---------------------------------------------------------------------------

_CT_ABI = [
    {"constant": True, "inputs": [{"name": "", "type": "bytes32"}],
     "name": "payoutDenominator", "outputs": [{"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [{"name": "", "type": "bytes32"}, {"name": "", "type": "uint256"}],
     "name": "payoutNumerators", "outputs": [{"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [{"name": "owner", "type": "address"}, {"name": "id", "type": "uint256"}],
     "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"constant": True,
     "inputs": [{"name": "parentCollectionId", "type": "bytes32"},
                {"name": "conditionId", "type": "bytes32"},
                {"name": "indexSet", "type": "uint256"}],
     "name": "getCollectionId", "outputs": [{"name": "", "type": "bytes32"}],
     "stateMutability": "view", "type": "function"},
]

_MC3_ABI = [
    {"inputs": [{"components": [
        {"name": "target", "type": "address"},
        {"name": "allowFailure", "type": "bool"},
        {"name": "callData", "type": "bytes"}],
        "name": "calls", "type": "tuple[]"}],
     "name": "aggregate3",
     "outputs": [{"components": [
         {"name": "success", "type": "bool"},
         {"name": "returnData", "type": "bytes"}],
         "name": "returnData", "type": "tuple[]"}],
     "stateMutability": "payable", "type": "function"},
]


def _sg_post(url: str, query: str) -> dict | None:
    """POST a GraphQL query, return parsed JSON data or None on error."""
    try:
        resp = http_requests.post(
            url, json={"query": query},
            headers={"Content-Type": "application/json"}, timeout=30,
        )
        if resp.status_code != 200:
            return None
        body = resp.json()
        return body.get("data") if "errors" not in body else None
    except Exception:
        return None


def _ct_held_positions(safe: str, pbar: tqdm | None = None) -> Dict[str, Set[int]]:
    """CT subgraph → {condition_id: {held index_sets}}."""
    held: Dict[str, Set[int]] = {}
    cursor = ""
    while True:
        q = """{
          user(id: "%s") {
            userPositions(first: %d, where: {balance_gt: "0", id_gt: "%s"}, orderBy: id) {
              id balance
              position { conditionIds indexSets }
            }
          }
        }""" % (safe.lower(), _SUBGRAPH_PAGE, cursor)
        data = _sg_post(CT_SUBGRAPH_URL, q)
        if not data:
            break
        positions = (data.get("user") or {}).get("userPositions", [])
        if not positions:
            break
        for p in positions:
            pos = p.get("position") or {}
            for cid in pos.get("conditionIds", []):
                s = held.setdefault(cid.lower(), set())
                for idx in pos.get("indexSets", []):
                    s.add(int(idx))
        if pbar is not None:
            pbar.set_postfix_str(f"{len(held)} conditions")
            pbar.update(len(positions))
        cursor = positions[-1]["id"]
        if len(positions) < _SUBGRAPH_PAGE:
            break
    return held


def _omen_markets_for_conditions(
    condition_ids: List[str], pbar: tqdm | None = None,
) -> List[Dict[str, Any]]:
    """Omen subgraph → finalized markets matching given conditions."""
    now = str(int(time.time()))
    markets: List[Dict[str, Any]] = []
    seen: set = set()
    for i in range(0, len(condition_ids), _CONDITION_ID_BATCH):
        batch = condition_ids[i : i + _CONDITION_ID_BATCH]
        ids_str = ", ".join(f'"{c}"' for c in batch)
        q = """{
          fixedProductMarketMakers(
            where: {conditions_: {id_in: [%s]}, answerFinalizedTimestamp_not: null, answerFinalizedTimestamp_lt: "%s"}
            first: %d, orderBy: id, orderDirection: asc
          ) { id payouts conditions { id outcomeSlotCount } }
        }""" % (ids_str, now, _SUBGRAPH_PAGE)
        data = _sg_post(THEGRAPH_ENDPOINT, q)
        if not data:
            if pbar is not None:
                pbar.update(1)
            continue
        for e in data.get("fixedProductMarketMakers", []):
            conds = e.get("conditions", [])
            if not conds or not conds[0].get("outcomeSlotCount"):
                continue
            payouts = e.get("payouts")
            if not payouts or not any(float(p) > 0 for p in payouts):
                continue
            addr = e["id"]
            if addr not in seen:
                seen.add(addr)
                markets.append({
                    "market_id": addr,
                    "condition_id": conds[0]["id"],
                    "outcome_slot_count": conds[0]["outcomeSlotCount"],
                    "payouts": payouts,
                })
        if pbar is not None:
            pbar.set_postfix_str(f"{len(markets)} markets")
            pbar.update(1)
    return markets


def _encode_call(fn_call: Any) -> bytes:
    return bytes.fromhex(fn_call._encode_transaction_data()[2:])


def _multicall(mc_contract: Any, calls: list, batch_size: int = 500) -> list:
    results = []
    for i in range(0, len(calls), batch_size):
        chunk = [(addr, True, data) for addr, data in calls[i : i + batch_size]]
        results.extend(mc_contract.functions.aggregate3(chunk).call())
    return results


def get_redeemable_positions(safe_address: str) -> pd.DataFrame:
    """Return a DataFrame of redeemable conditional-token positions for a safe.

    Strategy (subgraph-first, same as RedeemWinningsBehaviour):
      1. CT subgraph  → held positions (condition IDs + index sets)
      2. Omen subgraph → finalized markets for those conditions only
      3. Cross-reference  → filter to winning held positions
      4. On-chain (Multicall3) → estimate actual payout in xDAI

    :param safe_address: Gnosis Safe address (checksummed or lowercase).
    :return: DataFrame with columns: market_id, condition_id, payouts,
        winning_outcome, redeemable_xdai.  One row per redeemable market.
        Empty DataFrame if nothing to redeem.
    """
    w3 = Web3(Web3.HTTPProvider(_RPC_URL))
    ct = w3.eth.contract(address=w3.to_checksum_address(CONDITIONAL_TOKENS), abi=_CT_ABI)
    mc = w3.eth.contract(address=w3.to_checksum_address(MULTICALL3), abi=_MC3_ABI)
    ct_addr = w3.to_checksum_address(CONDITIONAL_TOKENS)
    wxdai_addr = w3.to_checksum_address(WXDAI)
    safe_cs = w3.to_checksum_address(safe_address)
    zero = bytes(32)

    safe_short = safe_address[:10]
    empty = pd.DataFrame(columns=[
        "market_id", "condition_id", "payouts", "winning_outcome", "redeemable_xdai",
    ])

    # Step 1: CT subgraph — held positions
    pbar1 = tqdm(desc=f"CT positions {safe_short}…", unit=" pos", bar_format="{desc}: {n}{unit} {elapsed} {postfix}")
    held = _ct_held_positions(safe_address, pbar=pbar1)
    pbar1.close()
    if not held:
        return empty

    # Step 2: Omen subgraph — markets for held conditions
    n_batches = (len(held) - 1) // _CONDITION_ID_BATCH + 1
    pbar2 = tqdm(total=n_batches, desc=f"Omen markets {safe_short}…", unit=" batch", bar_format="{desc}: {n}/{total}{unit} {elapsed} {postfix}")
    markets = _omen_markets_for_conditions(list(held.keys()), pbar=pbar2)
    pbar2.close()
    if not markets:
        return empty

    # Step 3: cross-reference — keep markets where held index set matches winning payout
    winning_markets = []
    for m in markets:
        cid = m["condition_id"].lower()
        held_sets = held.get(cid, set())
        payouts = m["payouts"]
        winning_outcome = None
        for idx_set in held_sets:
            for i in range(len(payouts)):
                if idx_set == (1 << i) and float(payouts[i]) > 0:
                    winning_outcome = i
                    break
            if winning_outcome is not None:
                break
        if winning_outcome is not None:
            m["winning_outcome"] = winning_outcome
            winning_markets.append(m)

    if not winning_markets:
        return empty

    # Step 4: on-chain payout estimation via Multicall3
    pbar3 = tqdm(total=3, desc=f"On-chain {safe_short}…", unit=" step", bar_format="{desc}: {n}/{total}{unit} {elapsed} {postfix}")

    # 4a: payoutDenominator
    pbar3.set_postfix_str("payoutDenominator")
    denom_calls = [
        (ct_addr, _encode_call(ct.functions.payoutDenominator(bytes.fromhex(m["condition_id"][2:]))))
        for m in winning_markets
    ]
    denom_results = _multicall(mc, denom_calls)
    pbar3.update(1)

    # 4b: getCollectionId for winning outcome
    pbar3.set_postfix_str("getCollectionId")
    col_calls = []
    for m in winning_markets:
        cid_bytes = bytes.fromhex(m["condition_id"][2:])
        idx_set = 1 << m["winning_outcome"]
        col_calls.append((ct_addr, _encode_call(ct.functions.getCollectionId(zero, cid_bytes, idx_set))))
    col_results = _multicall(mc, col_calls)
    pbar3.update(1)

    # 4c: balanceOf + payoutNumerators for winning outcome
    pbar3.set_postfix_str("balanceOf + numerators")
    detail_calls = []
    valid_indices = []
    for i, ((d_ok, d_ret), (c_ok, c_ret)) in enumerate(zip(denom_results, col_results)):
        if not d_ok or not c_ok or len(d_ret) < 32 or len(c_ret) < 32:
            continue
        denom = int.from_bytes(d_ret, "big")
        if denom == 0:
            continue
        position_id = int.from_bytes(
            w3.solidity_keccak(["address", "uint256"], [wxdai_addr, int.from_bytes(c_ret, "big")]),
            "big",
        )
        detail_calls.append((ct_addr, _encode_call(ct.functions.balanceOf(safe_cs, position_id))))
        cid_bytes = bytes.fromhex(winning_markets[i]["condition_id"][2:])
        detail_calls.append(
            (ct_addr, _encode_call(ct.functions.payoutNumerators(cid_bytes, winning_markets[i]["winning_outcome"])))
        )
        valid_indices.append((i, denom))

    detail_results = _multicall(mc, detail_calls)
    pbar3.update(1)
    pbar3.close()

    # Assemble rows
    rows = []
    for j, (idx, denom) in enumerate(valid_indices):
        bal_ok, bal_ret = detail_results[j * 2]
        num_ok, num_ret = detail_results[j * 2 + 1]
        if not bal_ok or not num_ok:
            continue
        balance = int.from_bytes(bal_ret, "big")
        numerator = int.from_bytes(num_ret, "big")
        payout_wei = balance * numerator // denom if denom else 0
        m = winning_markets[idx]
        rows.append({
            "market_id": m["market_id"],
            "condition_id": m["condition_id"],
            "payouts": m["payouts"],
            "winning_outcome": m["winning_outcome"],
            "redeemable_xdai": payout_wei / 1e18,
        })

    df = pd.DataFrame(rows) if rows else empty
    # Drop zero-payout rows (already redeemed)
    df = df[df["redeemable_xdai"] > 0]
    return df

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

import argparse
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict

import pandas as pd
from dotenv import load_dotenv
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport
from tqdm import tqdm

load_dotenv()


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
THEGRAPH_ENDPOINT = os.getenv(
    "OMEN_SUBGRAPH_URL", "https://api.thegraph.com/subgraphs/name/protofire/omen-xdai"
)

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
            answers {
            answer
            bondAggregate
            }
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

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            return self.value <= other.value
        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented

    def __ge__(self, other):
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


# ---------------------------------------------------------------------------
# DataFrame builder
# ---------------------------------------------------------------------------

INITIAL_BOND_WEI = 1_000_000_000_000_000  # 0.001 xDAI


def markets_to_dataframe(fpmms_dict: dict) -> pd.DataFrame:
    """Convert a dict of FPMM market dicts into a DataFrame.

    Args:
        fpmms_dict: mapping of market_id -> market dict (the value of
            ``get_fpmms(...)["fixedProductMarketMakers"]``)

    Returns:
        DataFrame with one row per market and pre-computed columns for
        state, challenge status, answer info, etc.
    """
    rows = []
    for market_id, m in fpmms_dict.items():
        question = m.get("question") or {}
        answers = question.get("answers") or []
        current_answer_hex = m.get("currentAnswer") or question.get("currentAnswer")
        bond = int(
            m.get("currentAnswerBond")
            or question.get("currentAnswerBond")
            or 0
        )

        n_answers = len(answers)
        first_answer_hex = answers[0]["answer"] if answers else None
        is_challenged = n_answers > 1 or bond > INITIAL_BOND_WEI
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
                "n_answers": n_answers,
                "first_answer_hex": first_answer_hex,
                "is_challenged": is_challenged,
                "is_flipped": (
                    is_challenged
                    and n_answers >= 2
                    and current_answer_hex is not None
                    and first_answer_hex is not None
                    and current_answer_hex != first_answer_hex
                ),
                "n_challenges": max(n_answers - 1, 1) if is_challenged else 0,
                "current_answer_bond": bond,
                "collateral_volume": float(m.get("collateralVolume") or 0) / 1e18,
            }
        )

    return pd.DataFrame(rows)


def _ts_to_datetime(ts) -> datetime | None:
    """Convert a subgraph timestamp string to a UTC datetime, or None."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None

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

"""Script for retrieving Omen markets."""

import json
import os
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict

from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport
from tqdm import tqdm


TEXT_ALIGNMENT = 30
MINIMUM_WRITE_FILE_DELAY_SECONDS = 20
FPMMS_JSON_PATH = "fpmms.json"
THEGRAPH_ENDPOINT = os.getenv(
    "OMEN_SUBGRAPH_URL", "https://api.thegraph.com/subgraphs/name/protofire/omen-xdai"
)

FPMMS_QUERY = """
query fpmms_query($creator: Bytes, $id_gt: ID) {
    fixedProductMarketMakers(
        where: {creator: $creator, id_gt: $id_gt}
        orderBy: id
        orderDirection: asc
        first: 1000
    ) {
        question {
            title
            outcomes
            currentAnswer
            currentAnswerTimestamp
            answers {
            answer
            }
        }
        id
        openingTimestamp
        resolutionTimestamp
        creationTimestamp
        isPendingArbitration
        answerFinalizedTimestamp
        currentAnswer
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


def _get_market_state(market: Dict[str, Any]) -> MarketState:
    try:
        now = datetime.utcnow()

        market_status = MarketState.CLOSED
        if market["currentAnswer"] is None and now >= datetime.utcfromtimestamp(
            float(market.get("openingTimestamp", 0))
        ):
            market_status = MarketState.PENDING
        elif market["currentAnswer"] is None:
            market_status = MarketState.OPEN
        elif market["isPendingArbitration"]:
            market_status = MarketState.ARBITRATING
        elif now < datetime.utcfromtimestamp(
            float(market.get("answerFinalizedTimestamp", 0))
        ):
            market_status = MarketState.FINALIZING

        return market_status
    except Exception:  # pylint: disable=broad-except
        return MarketState.UNKNOWN


def _populate_missing_fpmms(creator: str, fpmms: Dict[str, Any]) -> None:
    print(f"{'Fetching fpmms...':>{TEXT_ALIGNMENT}}")

    transport = RequestsHTTPTransport(url=THEGRAPH_ENDPOINT)
    client = Client(transport=transport, fetch_schema_from_transport=True)

    id_gt = "0x00"
    while True:
        variables = {
            "creator": creator,
            "id_gt": id_gt,
        }
        response = client.execute(gql(FPMMS_QUERY), variable_values=variables)
        items = response.get("fixedProductMarketMakers", [])

        if not items:
            break

        for fpmm in items:
            if fpmm["id"] not in fpmms:
                fpmms[fpmm["id"]] = fpmm

        id_gt = items[-1]["id"]
        _write_db_to_file(fpmms)

    _write_db_to_file(fpmms, True)


def _populate_missing_buy_trades(fpmms: Dict[str, Any]) -> None:
    transport = RequestsHTTPTransport(url=THEGRAPH_ENDPOINT)
    client = Client(transport=transport, fetch_schema_from_transport=True)

    for _, fpmm in tqdm(
        fpmms.items(),
        desc=f"{'Fetching trades':>{TEXT_ALIGNMENT}}",
        miniters=1,
    ):
        state = _get_market_state(fpmm)

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


def get_fpmms(creator: str) -> Dict[str, Any]:
    """Get Fixed Product Market Makers."""
    fpmms = {}
    try:
        with open(FPMMS_JSON_PATH, "r", encoding="UTF-8") as json_file:
            existing_data = json.load(json_file)
            fpmms = existing_data.get("fixedProductMarketMakers", {})
    except FileNotFoundError:
        pass  # File doesn't exist yet, so there are no existing requests

    _populate_missing_fpmms(creator.lower(), fpmms)
    _populate_missing_buy_trades(fpmms)
    return fpmms

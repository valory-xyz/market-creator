# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2024 Valory AG
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
"""This package contains collect proposed markets behaviours of MarketCreationManagerAbciApp."""


import json
import random
import time
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from string import Template
from typing import (
    Any,
    Dict,
    Generator,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    cast,
)

import packages.valory.skills.market_creation_manager_abci.propose_questions as mech_tool_propose_questions
import packages.valory.skills.mech_interact_abci.states.request as MechRequestStates
from packages.valory.contracts.conditional_tokens.contract import (
    ConditionalTokensContract,
)
from packages.valory.contracts.fpmm.contract import FPMMContract
from packages.valory.contracts.fpmm_deterministic_factory.contract import (
    FPMMDeterministicFactory,
)
from packages.valory.contracts.realitio.contract import RealitioContract
from packages.valory.contracts.wxdai.contract import WxDAIContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.protocols.ledger_api import LedgerApiMessage
from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)
from packages.valory.skills.abstract_round_abci.common import (
    SelectKeeperBehaviour,
)
from packages.valory.skills.market_creation_manager_abci import (
    PUBLIC_ID as MARKET_CREATION_MANAGER_PUBLIC_ID,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    CollectRandomnessBehaviour,
    ETHER_VALUE,
    MarketCreationManagerBaseBehaviour,
    SAFE_TX_GAS,
    get_callable_name, _ONE_DAY, HTTP_OK, FPMM_QUERY,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    CollectProposedMarketsPayload,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    CollectProposedMarketsRound,
)


class CollectProposedMarketsBehaviour(MarketCreationManagerBaseBehaviour):
    """CollectProposedMarketsBehaviour"""

    matching_round: Type[AbstractRound] = CollectProposedMarketsRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            current_timestamp = self.last_synced_timestamp
            self.context.logger.info(f"current_timestamp={current_timestamp}")

            openingTimestamp_gte = current_timestamp + _ONE_DAY
            self.context.logger.info(f"openingTimestamp_gte={openingTimestamp_gte}")

            openingTimestamp_lte = current_timestamp + (
                self.params.approve_market_event_days_offset * _ONE_DAY
            )
            self.context.logger.info(f"openingTimestamp_lte={openingTimestamp_lte}")

            # Compute required openingTimestamp (between now and now + approve_market_event_days_offset)
            # openingTimestamp refers to the time the market is closed for trades, and open for answer
            # in Realitio. We require "self.params.markets_to_approve_per_day" markets to close for trades every day.
            required_opening_ts = []
            current_day_start_timestamp = (
                openingTimestamp_gte - (openingTimestamp_gte % _ONE_DAY) + _ONE_DAY
            )
            while current_day_start_timestamp <= openingTimestamp_lte:
                required_opening_ts.append(current_day_start_timestamp)
                current_day_start_timestamp += _ONE_DAY

            self.context.logger.info(f"{required_opening_ts=}")

            # Get existing (open) markets count per openingTimestamp (between now and now + approve_market_event_days_offset)
            latest_open_markets = yield from self._collect_latest_open_markets(
                openingTimestamp_gte, openingTimestamp_lte
            )
            existing_market_count: Dict[int, int] = defaultdict(int)

            for market in latest_open_markets["fixedProductMarketMakers"]:
                ts = int(market.get("openingTimestamp"))
                existing_market_count[ts] += 1

            self.context.logger.info(f"existing_market_count={existing_market_count}")

            # Determine number of markets required to be approved per openingTimestamp (between now and now + approve_market_event_days_offset)
            required_markets_to_approve_per_opening_ts: Dict[int, int] = defaultdict(
                int
            )
            N = self.params.markets_to_approve_per_day

            for ts in required_opening_ts:
                required_markets_to_approve_per_opening_ts[ts] = max(
                    0, N - existing_market_count.get(ts, 0)
                )

            num_markets_to_approve = sum(
                required_markets_to_approve_per_opening_ts.values()
            )

            self.context.logger.info(f"{required_markets_to_approve_per_opening_ts=}")
            self.context.logger.info(f"{num_markets_to_approve=}")

            # Determine largest creation timestamp in markets with openingTimestamp between now and now + approve_market_event_days_offset
            creation_timestamps = [
                int(entry["creationTimestamp"])
                for entry in latest_open_markets.get("fixedProductMarketMakers", {})
            ]
            largest_creation_timestamp = max(creation_timestamps, default=0)
            self.context.logger.info(f"{largest_creation_timestamp=}")

            # Collect misc data related to market approval
            min_approve_markets_epoch_seconds = (
                self.params.min_approve_markets_epoch_seconds
            )
            self.context.logger.info(f"{min_approve_markets_epoch_seconds=}")
            approved_markets_count = self.synchronized_data.approved_markets_count
            self.context.logger.info(f"{approved_markets_count=}")

            latest_approve_market_timestamp = (
                self.synchronized_data.approved_markets_timestamp
            )
            self.context.logger.info(f"{latest_approve_market_timestamp=}")

            # Collect approved markets (not yet processed by the service)
            approved_markets = yield from self._collect_approved_markets()

            # Main logic of the behaviour
            if (
                self.params.max_approved_markets >= 0
                and approved_markets_count >= self.params.max_approved_markets
            ):
                self.context.logger.info("Max markets approved reached.")
                content = (
                    CollectProposedMarketsRound.MAX_APPROVED_MARKETS_REACHED_PAYLOAD
                )
            elif (
                current_timestamp - latest_approve_market_timestamp
                < min_approve_markets_epoch_seconds
            ):
                self.context.logger.info("Timeout to approve markets not reached (1).")
                content = CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD
            elif (
                current_timestamp - largest_creation_timestamp
                < min_approve_markets_epoch_seconds
            ):
                self.context.logger.info("Timeout to approve markets not reached (2).")
                content = CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD
            elif num_markets_to_approve <= 0:
                self.context.logger.info("No market approval required.")
                content = CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD
            elif len(approved_markets["approved_markets"]) > 0:
                self.context.logger.info("There are unprocessed approved markets.")
                content = CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD
            else:
                self.context.logger.info("Timeout to approve markets reached.")

                content_data = {}
                content_data.update(latest_open_markets)
                content_data.update(approved_markets)
                content_data[
                    "required_markets_to_approve_per_opening_ts"
                ] = required_markets_to_approve_per_opening_ts
                content_data["timestamp"] = current_timestamp
                content = json.dumps(content_data, sort_keys=True)

            payload = CollectProposedMarketsPayload(
                sender=sender,
                content=content,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _collect_approved_markets(self) -> Generator[None, None, Dict[str, Any]]:
        """Auxiliary method to collect approved and unprocessed markets from the endpoint."""
        self.context.logger.info("Collecting approved markets.")

        url = f"{self.params.market_approval_server_url}/approved_markets"
        headers = {
            "Authorization": self.params.market_approval_server_api_key,
            "Content-Type": "application/json",
        }
        http_response = yield from self.get_http_response(
            method="GET",
            url=url,
            headers=headers,
        )
        if http_response.status_code != HTTP_OK:
            self.context.logger.warning(
                f"Failed to retrieve approved markets: {http_response.status_code} {http_response}"
            )
            # TODO return error instead?
            return {"approved_markets": {}}

        body = json.loads(http_response.body.decode())
        self.context.logger.info(
            f"Successfully collected approved markets, received body {body}"
        )
        return body

    def _collect_latest_open_markets(
        self, openingTimestamp_gte: int, openingTimestamp_lte: int
    ) -> Generator[None, None, Dict[str, Any]]:
        """Collect FPMM from subgraph."""
        creator = self.synchronized_data.safe_contract_address.lower()

        self.context.logger.info(f"_collect_latest_open_markets for {creator=}")

        response = yield from self.get_subgraph_result(
            query=FPMM_QUERY.substitute(
                creator=creator,
                openingTimestamp_gte=openingTimestamp_gte,
                openingTimestamp_lte=openingTimestamp_lte,
            )
        )

        # TODO Handle retries
        if response is None:
            return {"fixedProductMarketMakers": []}
        return response.get("data", {})

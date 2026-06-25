# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2026 Valory AG
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

"""This module contains the CollectProposedMarketsBehaviour of the 'market_creation_manager_abci' skill."""

import json
from collections import defaultdict
from string import Template
from typing import Any, Dict, Generator, Type

from packages.valory.contracts.erc20.contract import ERC20TokenContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    HTTP_OK,
    MarketCreationManagerBaseBehaviour,
    _ONE_DAY,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    CollectProposedMarketsPayload,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    CollectProposedMarketsRound,
)

FPMM_QUERY = Template("""{
    fixedProductMarketMakers(
        where: {
            creator: "$creator"
            openingTimestamp_gte:"$openingTimestamp_gte"
            openingTimestamp_lte:"$openingTimestamp_lte"
        }
        first: 1000
        orderBy: creationTimestamp
        orderDirection: desc
    ) {
        currentAnswerTimestamp
        creator
        category
        creationTimestamp
        currentAnswer
        id
        openingTimestamp
        question {
        data
        }
        title
        timeout
    }
    }""")


class CollectProposedMarketsBehaviour(MarketCreationManagerBaseBehaviour):
    """CollectProposedMarketsBehaviour"""

    matching_round: Type[AbstractRound] = CollectProposedMarketsRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        sender = self.context.agent_address

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            # Guard: skip the entire propose -> Mech-request -> create cycle
            # when the safe cannot fund even one market (initial_funds). Creating
            # it would only revert on-chain (GS013) and waste the Mech request
            # fee, so branch out via INSUFFICIENT_FUNDS and reset/pause.
            if not (yield from self._have_funds_for_market()):
                content = CollectProposedMarketsRound.INSUFFICIENT_FUNDS_PAYLOAD
            else:
                content = yield from self._assess_market_approval()
            payload = CollectProposedMarketsPayload(sender=sender, content=content)

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _assess_market_approval(self) -> Generator[None, None, str]:
        """Assess market demand + throttles; return the round payload content."""
        current_timestamp = self.last_synced_timestamp
        self.context.logger.info(f"current_timestamp={current_timestamp}")

        openingTimestamp_gte = current_timestamp + _ONE_DAY
        self.context.logger.info(f"openingTimestamp_gte={openingTimestamp_gte}")

        openingTimestamp_lte = current_timestamp + (
            self.params.approve_market_event_days_offset * _ONE_DAY
        )
        self.context.logger.info(f"openingTimestamp_lte={openingTimestamp_lte}")

        # Compute required openingTimestamp (now .. now + offset). openingTimestamp
        # is when the market closes for trades and opens for answer in Realitio. We
        # require "markets_to_approve_per_day" markets to close for trades each day.
        required_opening_ts = []
        current_day_start_timestamp = (
            openingTimestamp_gte - (openingTimestamp_gte % _ONE_DAY) + _ONE_DAY
        )
        while current_day_start_timestamp <= openingTimestamp_lte:
            required_opening_ts.append(current_day_start_timestamp)
            current_day_start_timestamp += _ONE_DAY

        self.context.logger.info(f"{required_opening_ts=}")

        # Existing (open) markets count per openingTimestamp (now .. now + offset).
        latest_open_markets = yield from self._collect_latest_open_markets(
            openingTimestamp_gte, openingTimestamp_lte
        )
        existing_market_count: Dict[int, int] = defaultdict(int)

        for market in latest_open_markets["fixedProductMarketMakers"]:
            ts = int(market.get("openingTimestamp"))
            existing_market_count[ts] += 1

        self.context.logger.info(f"existing_market_count={existing_market_count}")

        # Markets still required to be approved per openingTimestamp.
        required_markets_to_approve_per_opening_ts: Dict[int, int] = defaultdict(int)
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

        # Largest creation timestamp among markets opening in the window.
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
            return CollectProposedMarketsRound.MAX_APPROVED_MARKETS_REACHED_PAYLOAD
        if (
            current_timestamp - latest_approve_market_timestamp
            < min_approve_markets_epoch_seconds
        ):
            self.context.logger.info("Timeout to approve markets not reached (1).")
            return CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD
        if (
            current_timestamp - largest_creation_timestamp
            < min_approve_markets_epoch_seconds
        ):
            self.context.logger.info("Timeout to approve markets not reached (2).")
            return CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD
        if num_markets_to_approve <= 0:
            self.context.logger.info("No market approval required.")
            return CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD
        if len(approved_markets["approved_markets"]) > 0:
            self.context.logger.info("There are unprocessed approved markets.")
            return CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD

        self.context.logger.info("Timeout to approve markets reached.")
        content_data: Dict[str, Any] = {}
        content_data.update(latest_open_markets)
        content_data.update(approved_markets)
        content_data["required_markets_to_approve_per_opening_ts"] = (
            required_markets_to_approve_per_opening_ts
        )
        content_data["timestamp"] = current_timestamp
        return json.dumps(content_data, sort_keys=True)

    def _have_funds_for_market(self) -> Generator[None, None, bool]:
        """Return True if the safe holds enough wxDAI to fund one market."""
        # Compare the safe's wxDAI (collateral) balance against the amount
        # ``createFPMM`` pulls -- ``to_wei(initial_funds / 100)``, i.e.
        # ``initial_funds * 10**16``. On a transient balance-read failure (or a
        # missing ``token`` key) the cycle is not blocked (returns True).
        required = int(self.params.initial_funds * 10**16)
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.collateral_tokens_contract,
            contract_id=str(ERC20TokenContract.contract_id),
            contract_callable="check_balance",
            account=self.synchronized_data.safe_contract_address,
            chain_id=self.params.default_chain_id,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(f"check_balance unsuccessful!: {response}")
            return True
        balance = response.state.body.get("token")
        if balance is None:
            self.context.logger.warning(
                "check_balance STATE response missing 'token' key; "
                "not blocking market creation this cycle."
            )
            return True
        balance = int(balance)
        if balance < required:
            self.context.logger.error(
                "Insufficient wxDAI to create a market: have "
                f"{balance / 10 ** 18} wxDAI, need {required / 10 ** 18} wxDAI "
                "(initial_funds per market). Skipping the Mech request and "
                "market creation this cycle."
            )
            return False
        return True

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

        try:
            body = json.loads(http_response.body.decode())
        except json.JSONDecodeError:
            self.context.logger.error("Invalid JSON response received.")
            return {"approved_markets": {}}

        if "approved_markets" not in body:
            self.context.logger.error("Missing 'approved_markets' key in response.")
            return {"approved_markets": {}}

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

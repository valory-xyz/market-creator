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

"""This module contains the sync markets behaviour."""

import json
from datetime import datetime
from typing import Any, Dict, Generator, List, Tuple, cast

from packages.valory.contracts.fpmm.contract import FPMMContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    MarketCreationManagerBaseBehaviour,
    ZERO_ADDRESS,
    FPMM_POOL_MEMBERSHIPS_QUERY,
    get_callable_name
)
from packages.valory.skills.market_creation_manager_abci.states.sync_markets_round import SyncMarketsRound
from packages.valory.skills.market_creation_manager_abci.payloads import SyncMarketsPayload


class SyncMarketsBehaviour(MarketCreationManagerBaseBehaviour):
    """SyncMarketsBehaviour"""

    matching_round = SyncMarketsRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            payload_content = yield from self.get_payload()
            payload = SyncMarketsPayload(sender=sender, content=payload_content)
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def get_payload(self) -> Generator[None, None, str]:
        """Get the payload."""
        market_removal = yield from self.get_markets()
        if market_removal is None:
            yield SyncMarketsRound.ERROR_PAYLOAD
            return

        markets, from_block = market_removal
        if len(markets) == 0:
            yield SyncMarketsRound.NO_UPDATE_PAYLOAD
            return

        payload = dict(markets=markets, from_block=from_block)
        yield json.dumps(payload, sort_keys=True)

    def get_markets(self) -> Generator[None, None, Tuple[List[Dict[str, Any]], int]]:
        """Collect FMPMM from subgraph."""
        creator = self.synchronized_data.safe_contract_address.lower()
        response = yield from self.get_subgraph_result(
            query=FPMM_POOL_MEMBERSHIPS_QUERY.substitute(creator=creator)
        )
        if response is None:
            yield [], 0
            return

        markets = []
        for entry in response["data"]["fpmmPoolMemberships"]:
            market = {}
            liquidity_measure = entry["pool"].get("liquidityMeasure")
            if liquidity_measure is None:
                continue

            liquidity_measure = int(liquidity_measure)
            if liquidity_measure == 0:
                continue

            if entry["pool"]["openingTimestamp"] is None:
                continue

            market["address"] = entry["pool"]["id"]
            market["amount"] = sum(map(int, entry["pool"]["outcomeTokenAmounts"]))
            market["opening_timestamp"] = int(entry["pool"]["openingTimestamp"])
            market["removal_timestamp"] = market["opening_timestamp"] - 86400

            # The markets created by the agent will only have one condition per market
            condition, *_ = entry["pool"]["conditions"]
            market["condition_id"] = condition["id"]
            market["outcome_slot_count"] = condition["outcomeSlotCount"]
            if condition["question"] is None:
                continue

            market["question_id"] = condition["question"]["id"]
            markets.append(market)

        market_addresses = [market["address"] for market in markets]
        market_addresses_with_funds = yield from self._get_markets_with_funds(
            market_addresses, self.synchronized_data.safe_contract_address
        )
        market_addresses_with_funds_str = [
            str(market).lower() for market in market_addresses_with_funds
        ]
        markets_with_funds = []
        for market in markets:
            if str(market["address"]).lower() not in market_addresses_with_funds_str:
                continue
            markets_with_funds.append(market)
            log_msg = "\n\t".join(
                [
                    "Adding market with",
                    "Address: " + market["address"],
                    "Liquidity: " + str(market["amount"]),
                    "Opening time: "
                    + str(datetime.fromtimestamp(market["opening_timestamp"])),
                    "Liquidity removal time: "
                    + str(datetime.fromtimestamp(market["removal_timestamp"])),
                ]
            )
            self.context.logger.info(log_msg)

        return markets_with_funds, 0

    def _get_markets_with_funds(
        self,
        market_addresses: List[str],
        safe_address: str,
    ) -> Generator[None, None, List[str]]:
        """Get markets with funds."""
        # no need to query the contract if there are no markets
        if len(market_addresses) == 0:
            return []

        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=ZERO_ADDRESS,  # NOT USED!
            contract_id=str(FPMMContract.contract_id),
            contract_callable=get_callable_name(FPMMContract.get_markets_with_funds),
            markets=market_addresses,
            safe_address=safe_address,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Couldn't get tx data for FPMMContract.get_markets_with_funds. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return []
        return cast(List[str], response.state.body["data"])
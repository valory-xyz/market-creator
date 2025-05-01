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

"""This module contains the approve markets behaviour of MarketCreationManagerAbciApp"""

import json
import random
import time
from typing import Any, Dict, Generator, Type

from packages.valory.skills.abstract_round_abci.base import AbstractRound
import packages.valory.skills.market_creation_manager_abci.propose_questions as mech_tool_propose_questions
from packages.valory.skills.market_creation_manager_abci import (
    PUBLIC_ID as MARKET_CREATION_MANAGER_PUBLIC_ID,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    MarketCreationManagerBaseBehaviour,
    HTTP_OK,
    _ONE_DAY,
)
from packages.valory.skills.market_creation_manager_abci.states.approve_markets_round import (
    ApproveMarketsRound,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    ApproveMarketsPayload,
)


class ApproveMarketsBehaviour(MarketCreationManagerBaseBehaviour):
    """ApproveMarketsBehaviour"""

    matching_round: Type[AbstractRound] = ApproveMarketsRound

    def _i_am_not_sending(self) -> bool:
        """Indicates if the current agent is the sender or not."""
        return (
            self.context.agent_address
            != self.synchronized_data.most_voted_keeper_address
        )

    def async_act(self) -> Generator[None, None, None]:
        """
        Do the action.

        Steps:
        - If the agent is the keeper, then prepare the transaction and send it.
        - Otherwise, wait until the next round.
        - If a timeout is hit, set exit A event, otherwise set done event.
        """
        if self._i_am_not_sending():
            yield from self._not_sender_act()
        else:
            yield from self._sender_act()

    def _not_sender_act(self) -> Generator:
        """Do the non-sender action."""
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            self.context.logger.info(
                f"Waiting for the keeper to do its keeping: {self.synchronized_data.most_voted_keeper_address}"
            )
            yield from self.wait_until_round_end()
        self.set_done()

    def _sender_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            random.seed(
                "ApproveMarketsBehaviour"
                + self.synchronized_data.most_voted_randomness,
                2,
            )  # nosec

            collected_proposed_markets_json = json.loads(
                self.synchronized_data.collected_proposed_markets_data
            )

            required_markets_to_approve_per_opening_ts = (
                collected_proposed_markets_json[
                    "required_markets_to_approve_per_opening_ts"
                ]
            )

            # Select an openingTimestamp with >0 markets to approve
            opening_ts = next(
                (
                    k
                    for k, v in required_markets_to_approve_per_opening_ts.items()
                    if v > 0
                ),
                None,
            )
            self.context.logger.info(f"{opening_ts=}")
            proposed_markets = {}
            approved_markets_count = 0

            if opening_ts:
                # TODO THIS EMULATES MECH INTERACT SENDING REQUEST TO A TOOL

                # This is very important, the resolution_time (i.e., the event day)
                # is one day less than the openingTimestamp
                resolution_time = int(opening_ts) - _ONE_DAY

                num_questions = min(
                    required_markets_to_approve_per_opening_ts[opening_ts],
                    self.params.max_markets_per_story,
                )

                keys = mech_tool_propose_questions.KeyChain(  # type: ignore
                    {
                        "openai": [self.params.openai_api_key],
                        "newsapi": [self.params.newsapi_api_key],
                        "serper": [self.params.serper_api_key],
                        "subgraph": [self.params.subgraph_api_key],
                    }
                )

                tool_kwargs = dict(
                    tool="propose-question",
                    api_keys=keys,
                    news_sources=self.params.news_sources,
                    topics=self.params.topics,
                    num_questions=num_questions,
                    resolution_time=resolution_time,
                )
                mech_tool_output = mech_tool_propose_questions.run(**tool_kwargs)[0]  # type: ignore
                mech_tool_output_json = json.loads(mech_tool_output)
                # END MECH INTERACT EMULATION

                self.context.logger.info(f"{mech_tool_output_json['reasoning']=}")

                proposed_markets = mech_tool_output_json["questions"]  # type: ignore

                if "error" in proposed_markets:
                    approved_markets_count = 0
                    self.context.logger.error(
                        f"An error occurred interacting with the Mech tool {proposed_markets=}"
                    )
                else:
                    for market in proposed_markets.values():
                        yield from self._propose_and_approve_market(market)

                    approved_markets_count = len(proposed_markets)

            sender = self.context.agent_address
            payload = ApproveMarketsPayload(
                sender=sender,
                content=json.dumps(proposed_markets, sort_keys=True),
                approved_markets_count=approved_markets_count
                + self.synchronized_data.approved_markets_count,
                timestamp=self.last_synced_timestamp,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _propose_and_approve_market(
        self, market: Dict[str, Any]
    ) -> Generator[None, None, str]:
        """Auxiliary method to approve markets on the endpoint."""

        headers = {
            "Authorization": self.params.market_approval_server_api_key,
            "Content-Type": "application/json",
        }

        market_id = market["id"]

        # Step 1: Propose market
        self.context.logger.info(f"proposing market {market_id=}")
        url = self.params.market_approval_server_url + "/propose_market"
        body = market
        http_response = yield from self.get_http_response(
            method="POST",
            url=url,
            headers=headers,
            content=json.dumps(body).encode("utf-8"),
        )
        if http_response.status_code != HTTP_OK:
            self.context.logger.warning(
                f"Failed to propose market: {http_response.status_code} {http_response}"
            )
            yield ApproveMarketsRound.ERROR_PAYLOAD
            return
        body = json.loads(http_response.body.decode())
        self.context.logger.info(f"Successfully proposed market, received body {body}")
        time.sleep(3)

        # Step 2: Approve market
        self.context.logger.info(f"Approving market {market_id=}")
        url = self.params.market_approval_server_url + "/approve_market"
        body = {"id": market_id}
        http_response = yield from self.get_http_response(
            method="POST",
            url=url,
            headers=headers,
            content=json.dumps(body).encode("utf-8"),
        )
        if http_response.status_code != HTTP_OK:
            self.context.logger.warning(
                f"Failed to approve market: {http_response.status_code} {http_response}"
            )
            yield ApproveMarketsRound.ERROR_PAYLOAD
            return
        body = json.loads(http_response.body.decode())
        self.context.logger.info(f"Successfully approved market, received body {body}")
        time.sleep(3)

        # Step 3: Update market data
        self.context.logger.info(f"Updating market {market_id=}")
        url = self.params.market_approval_server_url + "/update_market"
        body = {
            "id": market_id,
            "approved_by": f"{MARKET_CREATION_MANAGER_PUBLIC_ID}@{self.context.agent_address}",
        }
        http_response = yield from self.get_http_response(
            method="PUT",
            url=url,
            headers=headers,
            content=json.dumps(body).encode("utf-8"),
        )
        if http_response.status_code != HTTP_OK:
            self.context.logger.warning(
                f"Failed to update market: {http_response.status_code} {http_response}"
            )
            yield ApproveMarketsRound.ERROR_PAYLOAD
            return

        body = json.loads(http_response.body.decode())
        self.context.logger.info(f"Successfully updated market, received body {body}")
        time.sleep(3)

        yield json.dumps(body, sort_keys=True)

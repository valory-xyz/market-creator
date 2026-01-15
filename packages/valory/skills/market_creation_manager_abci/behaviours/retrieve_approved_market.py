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

"""This module contains the RetrieveApprovedMarketBehaviour of the 'market_creation_manager_abci' skill."""

import json
from typing import Generator, Type

from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    HTTP_NO_CONTENT,
    HTTP_OK,
    MAX_RETRIES,
    MarketCreationManagerBaseBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    RetrieveApprovedMarketPayload,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    RetrieveApprovedMarketRound,
)


class RetrieveApprovedMarketBehaviour(MarketCreationManagerBaseBehaviour):
    """RetrieveApprovedMarketBehaviour"""

    matching_round: Type[AbstractRound] = RetrieveApprovedMarketRound

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
            sender = self.context.agent_address
            response = yield from self._get_process_random_approved_market()
            payload = RetrieveApprovedMarketPayload(sender=sender, content=response)
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _get_process_random_approved_market(self) -> Generator[None, None, str]:
        """Auxiliary method to collect data from endpoint."""

        url = (
            self.params.market_approval_server_url
            + "/get_process_random_approved_market"
        )
        headers = {
            "Authorization": self.params.market_approval_server_api_key,
            "Content-Type": "application/json",
        }

        response = yield from self.get_http_response(
            method="POST",
            url=url,
            headers=headers,
        )

        if response.status_code == HTTP_NO_CONTENT:
            self.context.logger.info("No approved markets to retrieve.")
            return RetrieveApprovedMarketRound.NO_MARKETS_RETRIEVED_PAYLOAD

        if response.status_code != HTTP_OK:
            self.context.logger.error(
                f"Could not retrieve response from {url}."
                f"Received status code {response.status_code}.\n{response}"
            )
            retries = 3  # TODO: Make params
            if retries >= MAX_RETRIES:
                self.context.logger.error(f"Max retries reached ({MAX_RETRIES}).")
                return RetrieveApprovedMarketRound.MAX_RETRIES_PAYLOAD
            return RetrieveApprovedMarketRound.ERROR_PAYLOAD

        response_data = json.loads(response.body.decode())
        self.context.logger.info(f"Response received from {url}:\n {response_data}")

        return json.dumps(response_data, sort_keys=True)

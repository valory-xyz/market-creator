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

"""This module contains the post transaction behaviour."""

import json
from typing import Any, Dict, Generator, Optional, cast

from packages.valory.contracts.fpmm_deterministic_factory.contract import (
    FPMMDeterministicFactory,
)
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    HTTP_OK,
    MarketCreationManagerBaseBehaviour,
    get_callable_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import PostTxPayload
from packages.valory.skills.market_creation_manager_abci.rounds import (
    AnswerQuestionsRound,
    DepositDaiRound,
    PostTransactionRound,
    PrepareTransactionRound,
    RedeemBondRound,
    RemoveFundingRound,
)
from packages.valory.skills.mech_interact_abci.states import request as MechRequestStates


class PostTransactionBehaviour(MarketCreationManagerBaseBehaviour):
    """A behaviour that is called after a transaction has been settled."""

    matching_round = PostTransactionRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            content = yield from self.get_payload()
            payload = PostTxPayload(sender=sender, content=content)
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def get_payload(self) -> Generator[None, None, str]:
        """Get the transaction payload"""
        settled_tx_hash = self.synchronized_data.settled_tx_hash
        if settled_tx_hash is None:
            self.context.logger.info("No settled tx hash.")
            return PostTransactionRound.DONE_PAYLOAD

        if (
            self.synchronized_data.tx_sender
            == MechRequestStates.MechRequestRound.auto_round_id()
        ):
            return PostTransactionRound.MECH_REQUEST_DONE_PAYLOAD

        if self.synchronized_data.tx_sender == RedeemBondRound.auto_round_id():
            return PostTransactionRound.REDEEM_BOND_DONE_PAYLOAD

        if self.synchronized_data.tx_sender == DepositDaiRound.auto_round_id():
            return PostTransactionRound.DEPOSIT_DAI_DONE_PAYLOAD

        if self.synchronized_data.tx_sender == AnswerQuestionsRound.auto_round_id():
            return PostTransactionRound.ANSWER_QUESTION_DONE_PAYLOAD

        if self.synchronized_data.tx_sender == RemoveFundingRound.auto_round_id():
            return PostTransactionRound.REMOVE_FUNDING_DONE_PAYLOAD

        is_approved_question_data_set = (
            self.synchronized_data.is_approved_question_data_set
        )
        if not is_approved_question_data_set:
            self.context.logger.info("No approved question data.")
            return PostTransactionRound.DONE_PAYLOAD

        data = self.synchronized_data.approved_question_data
        market_id = data.get("id", None)
        if market_id is None:
            self.context.logger.info("No market id.")
            return PostTransactionRound.DONE_PAYLOAD

        self.context.logger.info(
            f"Handling settled tx hash {settled_tx_hash}. "
            f"For market with id {market_id}. "
        )

        if self.synchronized_data.tx_sender != PrepareTransactionRound.auto_round_id():
            # we only handle market creation txs atm, any other tx, we don't need to take action
            self.context.logger.info(
                f"No handling required for tx sender with round id {self.synchronized_data.tx_sender}. "
                f"Handling only required for {PrepareTransactionRound.auto_round_id()}."
            )
            return PostTransactionRound.DONE_PAYLOAD

        payload = yield from self._handle_market_creation(market_id, settled_tx_hash)
        return payload

    def _handle_market_creation(
        self, market_id: str, tx_hash: str
    ) -> Generator[None, None, str]:
        """Handle market creation tx settlement."""
        # get fpmm id from the events
        fpmm_id = yield from self._get_fpmm_id(tx_hash)
        if fpmm_id is None:
            # something went wrong
            return PostTransactionRound.ERROR_PAYLOAD

        self.context.logger.info(f"Got fpmm_id {fpmm_id} for market {market_id}")

        # mark as done on the market approval server
        err = yield from self._mark_market_as_done(market_id, fpmm_id)
        if err is not None:
            # something went wrong
            return PostTransactionRound.ERROR_PAYLOAD

        return PostTransactionRound.DONE_PAYLOAD

    def _get_fpmm_id(self, tx_hash: str) -> Generator[None, None, Optional[str]]:
        """Get the fpmm id from the events"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.fpmm_deterministic_factory_contract,
            tx_hash=tx_hash,
            contract_id=str(FPMMDeterministicFactory.contract_id),
            contract_callable=get_callable_name(
                FPMMDeterministicFactory.parse_market_creation_event
            ),
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{get_callable_name(FPMMDeterministicFactory.parse_market_creation_event)} unsuccessful!: {response}"
            )
            return None

        data = cast(Dict[str, Any], response.state.body["data"])
        fpmm_id = cast(str, data["fixed_product_market_maker"])
        return fpmm_id

    def _mark_market_as_done(
        self, id_: str, fpmm_id: str
    ) -> Generator[None, None, Optional[str]]:
        """Call the market approval server to signal that the provided market is created."""

        headers = {
            "Authorization": self.params.market_approval_server_api_key,
            "Content-Type": "application/json",
        }

        # Update the 'fpmm' field
        url = f"{self.params.market_approval_server_url}/update_market"
        body = {"id": id_, "fpmm_id": fpmm_id}
        http_response = yield from self.get_http_response(
            headers=headers,
            method="PUT",
            url=url,
            content=json.dumps(body).encode("utf-8"),
        )
        if http_response.status_code != HTTP_OK:
            self.context.logger.warning(
                f"Failed to update market: {http_response.status_code} {http_response}"
            )
            return str(http_response.body)

        body = json.loads(http_response.body.decode())
        self.context.logger.info(f"Successfully updated market, received body {body}")

        # Update the market id to match the 'fpmm' id
        url = f"{self.params.market_approval_server_url}/update_market_id"
        body = {"id": id_, "new_id": fpmm_id}
        http_response = yield from self.get_http_response(
            headers=headers,
            method="PUT",
            url=url,
            content=json.dumps(body).encode("utf-8"),
        )
        if http_response.status_code != HTTP_OK:
            self.context.logger.warning(
                f"Failed to update market id: {http_response.status_code} {http_response}"
            )
            return str(http_response.body)

        body = json.loads(http_response.body.decode())
        self.context.logger.info(
            f"Successfully updated market id, received body {body}"
        )

        return None
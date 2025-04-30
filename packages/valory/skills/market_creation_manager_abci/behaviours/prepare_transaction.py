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

"""This module contains the prepare transaction behaviour."""

from datetime import datetime
from typing import Dict, Generator, Optional, Tuple, cast

from packages.valory.contracts.conditional_tokens.contract import ConditionalTokensContract
from packages.valory.contracts.fpmm_deterministic_factory.contract import FPMMDeterministicFactory
from packages.valory.contracts.realitio.contract import RealitioContract
from packages.valory.contracts.wxdai.contract import WxDAIContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.base import MarketCreationManagerBaseBehaviour, ETHER_VALUE, _ONE_DAY, get_callable_name
from packages.valory.skills.market_creation_manager_abci.states.prepare_transaction_round import PrepareTransactionRound
from packages.valory.skills.market_creation_manager_abci.payloads import PrepareTransactionPayload


class PrepareTransactionBehaviour(MarketCreationManagerBaseBehaviour):
    """PrepareTransactionBehaviour"""

    matching_round = PrepareTransactionRound

    def _calculate_time_parameters(
        self,
        resolution_time: float,
        timeout: int,
    ) -> Tuple[int, int]:
        """Calculate time params."""
        days_to_opening = datetime.fromtimestamp(resolution_time + _ONE_DAY)
        opening_time = int(days_to_opening.timestamp())
        return opening_time, timeout * _ONE_DAY

    def _calculate_question_id(
        self,
        question_data: Dict,
        opening_timestamp: int,
        timeout: int,
        template_id: int = 2,
        question_nonce: int = 0,
    ) -> Generator[None, None, str]:
        """Calculate question ID."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.realitio_contract,
            contract_id=str(RealitioContract.contract_id),
            contract_callable="calculate_question_id",
            question_data=question_data,
            opening_timestamp=opening_timestamp,
            timeout=timeout,
            arbitrator_contract=self.params.arbitrator_contract,
            sender=self.synchronized_data.safe_contract_address,
            template_id=template_id,
            question_nonce=question_nonce,
        )
        return cast(str, response.state.body["question_id"])

    def _prepare_ask_question_mstx(
        self,
        question_data: Dict,
        opening_timestamp: int,
        timeout: int,
        template_id: int = 2,
        question_nonce: int = 0,
    ) -> Generator[None, None, Optional[Dict]]:
        """Prepare a multisend tx for `askQuestionMethod`"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.conditional_tokens_contract,
            contract_id=str(RealitioContract.contract_id),
            contract_callable="get_ask_question_tx_data",
            question_data=question_data,
            opening_timestamp=opening_timestamp,
            timeout=timeout,
            arbitrator_contract=self.params.arbitrator_contract,
            template_id=template_id,
            question_nonce=question_nonce,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"get_ask_question_tx_data unsuccessful!: {response}"
            )
            return None
        return {
            "to": self.params.realitio_contract,
            "data": response.state.body["data"],
            "value": self.params.realitio_answer_question_bounty,
        }

    def _prepare_prepare_condition_mstx(
        self,
        question_id: str,
        outcome_slot_count: int = 2,
    ) -> Generator[None, None, Optional[Dict]]:
        """Prepare a multisend tx for `askQuestionMethod`"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.conditional_tokens_contract,
            contract_id=str(ConditionalTokensContract.contract_id),
            contract_callable="get_prepare_condition_tx_data",
            question_id=question_id,
            oracle_contract=self.params.realitio_oracle_proxy_contract,
            outcome_slot_count=outcome_slot_count,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"get_prepare_condition_tx_data unsuccessful!: {response}"
            )
            return None
        return {
            "to": self.params.conditional_tokens_contract,
            "data": response.state.body["data"],
            "value": ETHER_VALUE,
        }

    def _prepare_create_fpmm_mstx(
        self,
        condition_id: str,
        initial_funds: float,
        market_fee: float,
    ) -> Generator[None, None, Optional[Dict]]:
        """Prepare a multisend tx for `askQuestionMethod`"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.fpmm_deterministic_factory_contract,
            contract_id=str(FPMMDeterministicFactory.contract_id),
            contract_callable="get_create_fpmm_tx_data",
            condition_id=condition_id,
            conditional_tokens=self.params.conditional_tokens_contract,
            collateral_token=self.params.collateral_tokens_contract,
            initial_funds=initial_funds,
            market_fee=market_fee,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"get_prepare_condition_tx_data unsuccessful!: {response}"
            )
            return None
        return {
            "to": self.params.fpmm_deterministic_factory_contract,
            "data": response.state.body["data"],
            "value": ETHER_VALUE,
            "approval_amount": response.state.body["value"],
        }

    def _get_approve_tx(self, amount: int) -> Generator[None, None, Optional[Dict]]:
        """Prepare a multisend tx for `askQuestionMethod`"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.collateral_tokens_contract,
            contract_id=str(WxDAIContract.contract_id),
            contract_callable="get_approve_tx_data",
            guy=self.params.fpmm_deterministic_factory_contract,
            amount=amount,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"get_approve_tx_data unsuccessful!: {response}"
            )
            return None
        return {
            "to": self.params.collateral_tokens_contract,
            "data": response.state.body["data"],
            "value": ETHER_VALUE,
        }

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            data = self.synchronized_data.approved_question_data
            question_data = {
                "question": data["question"],
                "answers": data["answers"],
                "topic": data["topic"],
                "language": data["language"],
            }
            self.context.logger.info(f"Preparing txs for {question_data=}")

            opening_timestamp, timeout = self._calculate_time_parameters(
                resolution_time=float(data["resolution_time"]),
                timeout=self.params.market_timeout,
            )
            self.context.logger.info(
                f"Opening time = {datetime.fromtimestamp(opening_timestamp)}"
            )
            self.context.logger.info(
                f"Closing time = {datetime.fromtimestamp(opening_timestamp + timeout)}"
            )

            question_id = yield from self._calculate_question_id(
                question_data=question_data,
                opening_timestamp=opening_timestamp,
                timeout=timeout,
            )
            self.context.logger.info(f"Calculated {question_id=}")

            ask_question_tx = yield from self._prepare_ask_question_mstx(
                question_data=question_data,
                opening_timestamp=opening_timestamp,
                timeout=timeout,
            )
            if ask_question_tx is None:
                yield
                return

            prepare_condition_tx = yield from self._prepare_prepare_condition_mstx(
                question_id=question_id,
            )
            if prepare_condition_tx is None:
                yield
                return

            condition_id = yield from self._calculate_condition_id(
                oracle_contract=self.params.realitio_oracle_proxy_contract,
                question_id=question_id,
            )
            self.context.logger.info(f"Calculated {condition_id=}")

            create_fpmm_tx = yield from self._prepare_create_fpmm_mstx(
                condition_id=condition_id,
                initial_funds=self.params.initial_funds,
                market_fee=self.params.market_fee,
            )
            if create_fpmm_tx is None:
                yield
                return

            amount = cast(int, create_fpmm_tx["approval_amount"])
            wxdai_approval_tx = yield from self._get_approve_tx(amount=amount)
            if wxdai_approval_tx is None:
                yield
                return

            self.context.logger.info(f"Added approval for {amount}")
            tx_hash = yield from self._to_multisend(
                transactions=[
                    wxdai_approval_tx,
                    ask_question_tx,
                    prepare_condition_tx,
                    create_fpmm_tx,
                ]
            )
            if tx_hash is None:
                yield
                return

            payload = PrepareTransactionPayload(
                sender=self.context.agent_address,
                content=tx_hash,
            )
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()
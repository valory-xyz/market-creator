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

"""This module contains the AnswerQuestionsBehaviour of the 'market_creation_manager_abci' skill."""

import json
from typing import Any, Dict, Generator, Optional, cast

from packages.valory.contracts.realitio.contract import RealitioContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    MarketCreationManagerBaseBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    MultisigTxPayload,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    AnswerQuestionsRound,
)
from packages.valory.skills.mech_interact_abci.states.base import (
    MechInteractionResponse,
)


ANSWER_YES, ANSWER_NO, ANSWER_INVALID = (
    "0x0000000000000000000000000000000000000000000000000000000000000000",
    "0x0000000000000000000000000000000000000000000000000000000000000001",
    "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
)

MAX_PREVIOUS = 0


class AnswerQuestionsBehaviour(MarketCreationManagerBaseBehaviour):
    """AnswerQuestionsBehaviour (to close markets)"""

    matching_round = AnswerQuestionsRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        self.context.logger.info("async_act")
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            agent = self.context.agent_address
            tx_hash = yield from self._get_payload()
            if tx_hash is None:
                tx_submitter = None
            else:
                tx_submitter = self.matching_round.auto_round_id()
            payload = MultisigTxPayload(
                sender=agent, tx_submitter=tx_submitter, tx_hash=tx_hash
            )
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def _parse_mech_response(self, response: MechInteractionResponse) -> Optional[str]:
        self.context.logger.info(f"_parse_mech_response: {response}")

        try:
            if response.result is None:
                return None

            data = json.loads(response.result)
            is_valid = data.get("is_valid", True)
            is_determinable = data.get("is_determinable", True)
            has_occurred = data.get("has_occurred", None)

            if not is_valid:
                return ANSWER_INVALID
            if not is_determinable:
                return None
            if has_occurred is False:
                return ANSWER_NO
            if has_occurred is True:
                return ANSWER_YES

            return None
        except json.JSONDecodeError:
            return None

    def _get_payload(self) -> Generator[None, None, Optional[str]]:
        self.context.logger.info("_get_payload")
        self.context.logger.info(
            f"mech_responses = {self.synchronized_data.mech_responses}"
        )

        question_to_answer = {}
        for response in self.synchronized_data.mech_responses:
            question_id = response.nonce
            self.context.logger.info(
                f"Received mech response: {response.nonce} {response.result}"
            )

            if question_id in self.shared_state.questions_responded:
                continue

            if question_id not in self.shared_state.questions_requested_mech:
                continue

            question = self.shared_state.questions_requested_mech[question_id][
                "question"
            ]
            retries = self.shared_state.questions_requested_mech[question_id]["retries"]
            answer = self._parse_mech_response(response)

            if answer is None and len(retries) >= len(
                self.params.answer_retry_intervals
            ):
                self.context.logger.info(
                    f"Question {question} has been retried at timestamps {retries} without success. Assuming question is invalid."
                )
                answer = ANSWER_INVALID

            self.context.logger.info(f"Got answer {answer} for question {question}")

            if answer is None:
                self.context.logger.warning(
                    f"Couldn't get answer for question {question}"
                )
                continue
            question_to_answer[question_id] = answer

            if len(question_to_answer) == self.params.questions_to_close_batch_size:
                break

        self.context.logger.info(
            f"Got answers for {len(question_to_answer)} questions. "
        )
        if len(question_to_answer) == 0:
            # we couldn't get any answers, no tx to be made
            self.context.logger.warning(
                "[AnswerQuestionsBehaviour] No answers to submit."
            )
            return None

        # prepare tx for all the answers
        txs = []
        for question_id, answer in question_to_answer.items():
            tx = yield from self._get_answer_tx(question_id, answer)
            if tx is None:
                # something went wrong, skip the current tx
                self.context.logger.warning(
                    f"Couldn't get tx for question {question_id} with answer {answer}"
                )
                continue
            txs.append(tx)
            # mark this question as processed. This is to avoid the situation where we
            # try to answer the same question multiple times due to a out-of-sync issue
            # between the subgraph and the realitio contract.
            self.shared_state.questions_responded.add(question_id)
            del self.shared_state.questions_requested_mech[question_id]

        if len(txs) == 0:
            # something went wrong, respond with ERROR payload for now
            self.context.logger.error(
                "[AnswerQuestionsBehaviour] Couldn't get any txs for questions that we have answers for."
            )
            return None

        multisend_tx_str = yield from self._to_multisend(txs)
        if multisend_tx_str is None:
            # something went wrong, respond with ERROR payload for now
            self.context.logger.error(
                "[AnswerQuestionsBehaviour] multisend_tx_str is None."
            )
            return None
        return multisend_tx_str

    def _get_answer_tx(
        self, question_id: str, answer: str
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Get an answer a tx."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.realitio_contract,
            contract_id=str(RealitioContract.contract_id),
            contract_callable="get_submit_answer_tx",
            question_id=bytes.fromhex(question_id[2:]),
            answer=bytes.fromhex(answer[2:]),
            max_previous=MAX_PREVIOUS,
        )

        # Handle error or missing response
        if (
            response is None
            or response.performative != ContractApiMessage.Performative.STATE
        ):
            self.context.logger.error(
                f"Couldn't get submitAnswer transaction. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return None

        data = cast(bytes, response.state.body["data"])
        return {
            "to": self.params.realitio_contract,
            "value": self.params.realitio_answer_question_bond,
            "data": data,
        }

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

"""This module contains the get pending questions behaviour."""

import json
import random
from dataclasses import asdict
from typing import Any, Dict, Generator, List, Optional, cast

from packages.valory.protocols.ledger_api import LedgerApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    MarketCreationManagerBaseBehaviour,
    OPEN_FPMM_QUERY
)
from packages.valory.skills.market_creation_manager_abci.states.get_pending_questions_round import GetPendingQuestionsRound
from packages.valory.skills.market_creation_manager_abci.payloads import GetPendingQuestionsPayload
from packages.valory.skills.mech_interact_abci.states.base import MechMetadata


class GetPendingQuestionsBehaviour(MarketCreationManagerBaseBehaviour):
    """Gets Omen pending questions to close markets"""

    matching_round = GetPendingQuestionsRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            content = yield from self.get_payload()
            payload = GetPendingQuestionsPayload(sender=sender, content=content)
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def _get_unanswered_questions(
        self,
    ) -> Generator[None, None, List[Dict[str, Any]]]:
        """Collect FPMM from subgraph."""
        creator = self.synchronized_data.safe_contract_address.lower()
        response = yield from self.get_subgraph_result(
            query=OPEN_FPMM_QUERY.substitute(
                creator=creator,
                current_timestamp=self.last_synced_timestamp,
            )
        )
        if response is None:
            yield []
            return
        questions = response.get("data", {}).get("fixedProductMarketMakers", [])
        self.context.logger.info(f"Collected questions: {questions}")

        if not questions:
            yield []
            return

        yield questions

    def _get_balance(self, account: str) -> Generator[None, None, Optional[int]]:
        """Get the balance of an account"""
        ledger_api_response = yield from self.get_ledger_api_response(
            performative=LedgerApiMessage.Performative.GET_STATE,
            ledger_callable="get_balance",
            account=account,
        )
        if ledger_api_response.performative != LedgerApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Couldn't get balance for account {account}. "
                f"Expected response performative {LedgerApiMessage.Performative.STATE.value}, "
                f"Received {ledger_api_response.performative.value}."
            )
            yield None
            return

        balance = cast(int, ledger_api_response.state.body.get("get_balance_result"))
        yield balance

    def _eligible_questions_to_answer(
        self, unanswered_questions: List[Dict[str, Any]]
    ) -> List[str]:
        """Determine the eligible questions to answer at this time"""
        now = self.last_synced_timestamp
        eligible_questions_id = []
        answer_retry_intervals = self.params.answer_retry_intervals

        self.context.logger.info(f"Answer retry intervals: {answer_retry_intervals}")

        for question in unanswered_questions:
            question_id = question["question"]["id"].lower()

            if question_id in self.shared_state.questions_responded:
                continue

            if question_id not in self.shared_state.questions_requested_mech:
                self.shared_state.questions_requested_mech[question_id] = {
                    "question": question,
                    "retries": [],
                }

            retries = self.shared_state.questions_requested_mech[question_id]["retries"]
            n_retries = len(retries)
            time_since_last_retry = now - retries[-1] if retries else 0
            retry_period = answer_retry_intervals[
                min(n_retries, len(answer_retry_intervals) - 1)
            ]
            if n_retries == 0 or time_since_last_retry > retry_period:
                eligible_questions_id.append(question_id)

        self.context.logger.info(
            f"Determined {len(eligible_questions_id)} eligible questions to answer."
        )

        num_questions = min(
            len(eligible_questions_id), self.params.multisend_batch_size
        )
        random.seed(self.last_synced_timestamp)
        random_questions_id = random.sample(eligible_questions_id, num_questions)

        self.context.logger.info(
            f"Chosen {len(random_questions_id)} eligible questions to answer."
        )
        return random_questions_id

    def get_payload(self) -> Generator[None, None, str]:
        """Get the transaction payload"""
        # get the questions to that need to be answered
        unanswered_questions = yield from self._get_unanswered_questions()

        if unanswered_questions is None:
            self.context.logger.info("Couldn't get the questions")
            yield GetPendingQuestionsRound.ERROR_PAYLOAD
            return

        eligible_questions_id = self._eligible_questions_to_answer(unanswered_questions)

        self.context.logger.info(f"{self.shared_state.questions_requested_mech=}")

        if len(eligible_questions_id) == 0:
            self.context.logger.info("No eligible questions to answer")
            yield GetPendingQuestionsRound.NO_TX_PAYLOAD
            return

        self.context.logger.info(
            f"Got {len(eligible_questions_id)} questions to close. "
            f"Questions ID: {eligible_questions_id}"
        )

        safe_address = self.synchronized_data.safe_contract_address
        balance = yield from self._get_balance(safe_address)
        if balance is None:
            self.context.logger.info("Couldn't get balance")
            yield GetPendingQuestionsRound.NO_TX_PAYLOAD
            return

        self.context.logger.info(f"Address {safe_address!r} has balance {balance}.")
        max_num_questions = min(
            len(eligible_questions_id), self.params.questions_to_close_batch_size
        )
        bond_required = self.params.realitio_answer_question_bond * max_num_questions

        # TODO uncomment
        if balance < bond_required:
            self.context.logger.info(
                f"Not enough balance to close {max_num_questions} questions. "
                f"Balance {balance}, required {bond_required}"
            )
            yield GetPendingQuestionsRound.NO_TX_PAYLOAD
            return

        # Prepare the Mech Requests for these questions
        new_mech_requests = []
        for question_id in eligible_questions_id:
            question = self.shared_state.questions_requested_mech[question_id][
                "question"
            ]
            retries = self.shared_state.questions_requested_mech[question_id]["retries"]
            retries.append(self.last_synced_timestamp)

            self.context.logger.info(
                f"Requesting mech answer for question {question_id} ({question['title']})."
            )
            self.context.logger.info(f"Question {question_id} retries: {retries}.")

            new_mech_requests.append(
                asdict(
                    MechMetadata(
                        nonce=question_id,
                        tool=self.params.mech_tool_resolve_market,
                        prompt=question["title"],
                    )
                )
            )

        self.context.logger.info(f"new_mech_requests: {new_mech_requests}")

        if len(new_mech_requests) == 0:
            self.context.logger.info("No mech requests")
            yield GetPendingQuestionsRound.NO_TX_PAYLOAD
            return

        yield json.dumps(new_mech_requests, sort_keys=True)
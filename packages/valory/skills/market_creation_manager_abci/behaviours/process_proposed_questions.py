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

"""This module contains the ProcessProposedQuestionsBehaviour."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Generator, Type

from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.market_creation_manager_abci import (
    PUBLIC_ID as MARKET_CREATION_MANAGER_PUBLIC_ID,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    HTTP_OK,
    MarketCreationManagerBaseBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    ProcessProposedQuestionsPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.process_proposed_questions import (
    ProcessProposedQuestionsRound,
)


class ProcessProposedQuestionsBehaviour(MarketCreationManagerBaseBehaviour):
    """Consume Mech response and approve markets via the approval server.

    Entered after MechInteract delivers question proposals (via
    FinishedMechResponseRound -> ProcessProposedQuestionsRound in
    the composed app).  Reads the delivered ``mech_responses`` from
    SynchronizedData, parses the tool JSON, and calls the approval server
    for each valid question.

    FAIL-CLOSED: any error (missing response, bad JSON, empty questions,
    server errors) results in an empty proposed_markets dict and the round
    still advances to RetrieveApprovedMarketRound -- the service never
    gets stuck here.
    """

    matching_round: Type[AbstractRound] = ProcessProposedQuestionsRound

    def async_act(self) -> Generator[None, None, None]:
        """Process Mech response and call approval server for each question."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            proposed_markets: Dict[str, Any] = {}
            approved_markets_count = 0

            questions = yield from self._parse_mech_response()
            if questions:
                for market in questions.values():
                    if not self._is_resolution_date_in_question(market):
                        self.context.logger.error(
                            "Resolution date wrong or not found in "
                            f"question {market=}"
                        )
                        continue
                    yield from self._propose_and_approve_market(market)
                    approved_markets_count += 1
                proposed_markets = questions

        sender = self.context.agent_address
        payload = ProcessProposedQuestionsPayload(
            sender=sender,
            content=json.dumps(proposed_markets, sort_keys=True),
            approved_markets_count=(
                approved_markets_count + self.synchronized_data.approved_markets_count
            ),
            timestamp=self.last_synced_timestamp,
        )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _parse_mech_response(
        self,
    ) -> Generator[None, None, Dict[str, Any]]:
        """Read the delivered mech_response and parse the tool JSON.

        :return: dict of questions from the tool output, or empty dict on
            any failure (missing response / bad JSON / no questions key).
        :yield: nothing -- no async I/O needed here.
        """
        # market-creator sends a single propose-question request per cycle, and
        # mech_interact_abci clears ``mech_requests`` once consumed -- so read
        # the delivered response directly rather than matching on the (now
        # cleared) request nonce. The response's ``error`` field also defaults
        # to "Unknown" even on success, so key off ``result`` instead.
        mech_responses = self.synchronized_data.mech_responses
        if not mech_responses:
            self.context.logger.warning(
                "ProcessProposedQuestions: no Mech responses in SynchronizedData. "
                "Treating as empty."
            )
            return {}

        matched = mech_responses[0]

        if not matched.result:
            self.context.logger.warning(
                "ProcessProposedQuestions: Mech result is empty. " "Treating as empty."
            )
            return {}

        try:
            parsed = json.loads(matched.result)
        except (json.JSONDecodeError, TypeError) as exc:
            self.context.logger.warning(
                f"ProcessProposedQuestions: could not parse Mech result as "
                f"JSON: {exc}. Result snippet: {str(matched.result)[:200]}"
            )
            return {}

        self.context.logger.info(
            f"ProcessProposedQuestions: reasoning={parsed.get('reasoning')!r}"
        )
        questions = parsed.get("questions", {})
        if not questions:
            self.context.logger.warning(
                "ProcessProposedQuestions: Mech result has no 'questions'. "
                "Treating as empty."
            )
            return {}

        # Generator protocol requirement -- yield nothing here.
        return questions
        yield  # pragma: no cover

    def _is_resolution_date_in_question(self, market: Dict) -> bool:
        """Check that the resolution date appears verbatim in the question text."""
        if not isinstance(market, dict) or "resolution_time" not in market:
            return False
        dt = datetime.fromtimestamp(market["resolution_time"], tz=timezone.utc)
        date_formats = [
            f"{dt.strftime('%B')} {dt.day}, {dt.year}",
            f"{dt.strftime('%B')} {dt.strftime('%d')}, {dt.year}",
        ]
        for formatted_date in date_formats:
            if formatted_date in market["question"]:
                return True
        return False

    def _propose_and_approve_market(
        self, market: Dict[str, Any]
    ) -> Generator[None, None, str]:
        """Call the market approval server: propose, approve, update."""
        headers = {
            "Authorization": self.params.market_approval_server_api_key,
            "Content-Type": "application/json",
        }
        market_id = market["id"]

        # Step 1: Propose market
        self.context.logger.info(f"proposing market {market_id=}")
        url = self.params.market_approval_server_url + "/propose_market"
        http_response = yield from self.get_http_response(
            method="POST",
            url=url,
            headers=headers,
            content=json.dumps(market).encode("utf-8"),
        )
        if http_response.status_code != HTTP_OK:
            self.context.logger.warning(
                f"Failed to propose market: "
                f"{http_response.status_code} {http_response}"
            )
            return ProcessProposedQuestionsRound.ERROR_PAYLOAD
        body = json.loads(http_response.body.decode())
        self.context.logger.info(f"Successfully proposed market, received body {body}")
        yield from self.sleep(3)

        # Step 2: Approve market
        self.context.logger.info(f"Approving market {market_id=}")
        url = self.params.market_approval_server_url + "/approve_market"
        http_response = yield from self.get_http_response(
            method="POST",
            url=url,
            headers=headers,
            content=json.dumps({"id": market_id}).encode("utf-8"),
        )
        if http_response.status_code != HTTP_OK:
            self.context.logger.warning(
                f"Failed to approve market: "
                f"{http_response.status_code} {http_response}"
            )
            return ProcessProposedQuestionsRound.ERROR_PAYLOAD
        body = json.loads(http_response.body.decode())
        self.context.logger.info(f"Successfully approved market, received body {body}")
        yield from self.sleep(3)

        # Step 3: Update market data
        self.context.logger.info(f"Updating market {market_id=}")
        url = self.params.market_approval_server_url + "/update_market"
        approved_by = (
            f"{MARKET_CREATION_MANAGER_PUBLIC_ID}@{self.context.agent_address}"
        )
        http_response = yield from self.get_http_response(
            method="PUT",
            url=url,
            headers=headers,
            content=json.dumps({"id": market_id, "approved_by": approved_by}).encode(
                "utf-8"
            ),
        )
        if http_response.status_code != HTTP_OK:
            self.context.logger.warning(
                f"Failed to update market: "
                f"{http_response.status_code} {http_response}"
            )
            return ProcessProposedQuestionsRound.ERROR_PAYLOAD

        body = json.loads(http_response.body.decode())
        self.context.logger.info(f"Successfully updated market, received body {body}")
        yield from self.sleep(3)

        return json.dumps(body, sort_keys=True)

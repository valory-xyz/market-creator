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
from typing import Any, Dict, Generator, Optional, Type

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

    FAIL-CLOSED: a missing/empty/unparseable Mech response yields no
    questions, and any individual market that fails validation or an
    approval-server step is skipped (not recorded in proposed_markets, not
    counted in approved_markets_count). The round always advances to
    RetrieveApprovedMarketRound -- the service never gets stuck here.
    """

    matching_round: Type[AbstractRound] = ProcessProposedQuestionsRound

    def async_act(self) -> Generator[None, None, None]:
        """Process Mech response and call approval server for each question."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            proposed_markets: Dict[str, Any] = {}
            approved_markets_count = 0

            questions = yield from self._parse_mech_response()
            if questions:
                for key, market in questions.items():
                    if not self._is_resolution_date_in_question(market):
                        self.context.logger.error(
                            "Resolution date wrong or not found in "
                            f"question {market=}"
                        )
                        continue
                    result = yield from self._propose_and_approve_market(market)
                    if result == ProcessProposedQuestionsRound.ERROR_PAYLOAD:
                        # Approval server failed -- do not record or count it.
                        continue
                    approved_markets_count += 1
                    proposed_markets[key] = market

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
        if (
            not isinstance(market, dict)
            or "resolution_time" not in market
            or "question" not in market
        ):
            return False
        dt = datetime.fromtimestamp(market["resolution_time"], tz=timezone.utc)
        month_name = dt.strftime("%B")
        date_formats = [
            f"{month_name} {dt.day}, {dt.year}",
            f"{month_name} {dt.strftime('%d')}, {dt.year}",
        ]
        for formatted_date in date_formats:
            if formatted_date in market["question"]:
                return True
        return False

    def _call_approval_server(
        self,
        method: str,
        endpoint: str,
        payload: Dict[str, Any],
        action: str,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Call the approval server and return the parsed JSON body.

        :param method: HTTP method (``POST``/``PUT``).
        :param endpoint: server path, e.g. ``/propose_market``.
        :param payload: JSON request body.
        :param action: verb used in log lines (``propose``/``approve``/``update``).
        :return: the parsed response body on a 200 with a JSON body, else None
            (non-200 status, or an empty/truncated/non-JSON 200 body).
        :yield: the HTTP request to the approval server.
        """
        http_response = yield from self.get_http_response(
            method=method,
            url=self.params.market_approval_server_url + endpoint,
            headers={
                "Authorization": self.params.market_approval_server_api_key,
                "Content-Type": "application/json",
            },
            content=json.dumps(payload).encode("utf-8"),
        )
        if http_response.status_code != HTTP_OK:
            self.context.logger.warning(
                f"Failed to {action} market: "
                f"{http_response.status_code} {http_response}"
            )
            return None
        try:
            body = json.loads(http_response.body.decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.context.logger.warning(
                f"Failed to {action} market: 200 with unparseable body ({exc})."
            )
            return None
        self.context.logger.info(f"Successfully {action}d market, received body {body}")
        return body

    def _propose_and_approve_market(
        self, market: Dict[str, Any]
    ) -> Generator[None, None, str]:
        """Propose, approve, then update a market on the approval server.

        :param market: the proposed market dict (must contain ``id``).
        :return: the final update body JSON on success, or ERROR_PAYLOAD when
            the market is malformed or any approval-server step fails.
        :yield: HTTP requests to the approval server.
        """
        if "id" not in market:
            self.context.logger.warning(
                f"Proposed market missing 'id'; skipping. market={market}"
            )
            return ProcessProposedQuestionsRound.ERROR_PAYLOAD
        market_id = market["id"]

        body = yield from self._call_approval_server(
            "POST", "/propose_market", market, "propose"
        )
        if body is None:
            return ProcessProposedQuestionsRound.ERROR_PAYLOAD
        yield from self.sleep(3)

        body = yield from self._call_approval_server(
            "POST", "/approve_market", {"id": market_id}, "approve"
        )
        if body is None:
            return ProcessProposedQuestionsRound.ERROR_PAYLOAD
        yield from self.sleep(3)

        approved_by = (
            f"{MARKET_CREATION_MANAGER_PUBLIC_ID}@{self.context.agent_address}"
        )
        body = yield from self._call_approval_server(
            "PUT",
            "/update_market",
            {"id": market_id, "approved_by": approved_by},
            "update",
        )
        if body is None:
            return ProcessProposedQuestionsRound.ERROR_PAYLOAD
        yield from self.sleep(3)

        return json.dumps(body, sort_keys=True)

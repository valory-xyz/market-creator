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

"""This module contains the RequestProposedQuestionsBehaviour of the 'market_creation_manager_abci' skill."""

import json
from dataclasses import asdict
from typing import Generator, Optional, Type
from uuid import uuid4

from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    MarketCreationManagerBaseBehaviour,
    _ONE_DAY,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    RequestProposedQuestionsPayload,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    RequestProposedQuestionsRound,
)
from packages.valory.skills.mech_interact_abci.states.base import MechMetadata


class RequestProposedQuestionsBehaviour(MarketCreationManagerBaseBehaviour):
    """RequestProposedQuestionsBehaviour -- build a Mech request for question generation.

    The keeper reads the next opening_ts that still needs markets, constructs
    a ``MechMetadata`` request, and serialises it into the payload's
    ``mech_requests`` field.  The round's custom ``end_block`` routes:
    - mech_requests set  -> MECH_REQUEST_DONE -> FinishedWithMechRequestRound
    - mech_requests None -> SKIP             -> RetrieveApprovedMarketRound
    """

    matching_round: Type[AbstractRound] = RequestProposedQuestionsRound

    def _i_am_not_sending(self) -> bool:
        """Indicates if the current agent is the sender or not."""
        return (
            self.context.agent_address
            != self.synchronized_data.most_voted_keeper_address
        )

    def async_act(self) -> Generator[None, None, None]:
        """Do the action.

        Steps:
        - If the agent is the keeper, build the Mech request and send it.
        - Otherwise, wait until the next round.
        """
        if self._i_am_not_sending():
            yield from self._not_sender_act()
        else:
            yield from self._sender_act()

    def _not_sender_act(self) -> Generator:
        """Do the non-sender action."""
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            self.context.logger.info(
                "Waiting for the keeper to do its keeping: "
                f"{self.synchronized_data.most_voted_keeper_address}"
            )
            yield from self.wait_until_round_end()
        self.set_done()

    def _sender_act(self) -> Generator:
        """Build a Mech request for question generation, or skip if no work."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            mech_requests_json: Optional[str] = yield from self._build_mech_request()

        sender = self.context.agent_address
        payload = RequestProposedQuestionsPayload(
            sender=sender,
            mech_requests=mech_requests_json,
        )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _build_mech_request(self) -> Generator[None, None, Optional[str]]:
        """Return a JSON-serialised list of MechMetadata, or None to skip."""
        collected_proposed_markets_json = json.loads(
            self.synchronized_data.collected_proposed_markets_data
        )
        required_markets_to_approve_per_opening_ts = (
            collected_proposed_markets_json.get(
                "required_markets_to_approve_per_opening_ts", {}
            )
        )

        # Select the first opening_ts with >0 markets still to approve.
        opening_ts = next(
            (k for k, v in required_markets_to_approve_per_opening_ts.items() if v > 0),
            None,
        )
        self.context.logger.info(f"{opening_ts=}")

        if opening_ts is None:
            self.context.logger.info(
                "No opening_ts with pending approvals -- skipping Mech request."
            )
            return None

        # resolution_time is one day before the market opening timestamp.
        resolution_time = int(opening_ts) - _ONE_DAY
        num_questions = min(
            required_markets_to_approve_per_opening_ts[opening_ts],
            self.params.max_markets_per_story,
        )

        nonce = str(uuid4())
        # The propose-question tool reads its inputs from top-level run(**kwargs).
        # The mech executor spreads the request JSON, and mech_interact_abci
        # merges ``extra_attributes`` into that JSON top-level -- so operator
        # params travel there and reach the tool as kwargs (the prompt stays a
        # plain description; ``request_context`` is reserved for analysis data).
        mech_request = MechMetadata(
            nonce=nonce,
            tool=self.params.mech_tool_propose_question,
            prompt="Propose prediction-market questions from recent news.",
            extra_attributes={
                "topics": self.params.topics,
                "news_sources": self.params.news_sources,
                "num_questions": num_questions,
                "resolution_time": resolution_time,
            },
        )

        self.context.logger.info(
            f"Building Mech request for question generation: "
            f"tool={self.params.mech_tool_propose_question}, "
            f"nonce={nonce}, resolution_time={resolution_time}, "
            f"num_questions={num_questions}"
        )

        # Return a 1-element list to match mech_interact_abci convention.
        mech_requests_json = json.dumps([asdict(mech_request)], sort_keys=True)
        return mech_requests_json

        # Satisfy the Generator return type; never actually reached.
        yield  # pragma: no cover

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

"""Tests for RequestProposedQuestionsBehaviour."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from packages.valory.skills.market_creation_manager_abci.behaviours.request_proposed_questions import (
    RequestProposedQuestionsBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    RequestProposedQuestionsRound,
)

CURRENT_FILE_PATH = Path(__file__).resolve()
PACKAGE_DIR = CURRENT_FILE_PATH.parents[2]

AGENT_ADDRESS = "0x1234567890123456789012345678901234567890"
KEEPER_ADDRESS = "0xaaaa567890123456789012345678901234567890"


def _exhaust_gen(gen: Any) -> Any:
    """Exhaust a generator and return its StopIteration value."""
    try:
        while True:
            next(gen)
    except StopIteration as exc:
        return exc.value


class TestRequestProposedQuestionsBehaviour:
    """Tests for RequestProposedQuestionsBehaviour."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.mech_tool_propose_question = "propose-question"
        context_mock.params.max_markets_per_story = 5
        context_mock.params.topics = ["business", "science"]
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.synchronized_data = MagicMock()
        context_mock.benchmark_tool = MagicMock()
        context_mock.benchmark_tool.measure.return_value.__enter__ = MagicMock(
            return_value=None
        )
        context_mock.benchmark_tool.measure.return_value.__exit__ = MagicMock(
            return_value=False
        )
        context_mock.agent_address = AGENT_ADDRESS
        self.context_mock = context_mock
        self.behaviour = RequestProposedQuestionsBehaviour(
            name="test", skill_context=context_mock
        )

    def _synced(self) -> MagicMock:
        """Return the underlying synchronized_data mock."""
        return self.context_mock.state.synchronized_data

    def test_matching_round(self) -> None:
        """Test matching_round is correctly set."""
        assert self.behaviour.matching_round == RequestProposedQuestionsRound

    def test_i_am_not_sending_true(self) -> None:
        """Test returns True when this agent is NOT the keeper."""
        self._synced().most_voted_keeper_address = KEEPER_ADDRESS
        assert self.behaviour._i_am_not_sending() is True

    def test_i_am_not_sending_false(self) -> None:
        """Test returns False when this agent IS the keeper."""
        self._synced().most_voted_keeper_address = AGENT_ADDRESS
        assert self.behaviour._i_am_not_sending() is False

    def test_build_mech_request_no_opening_ts(self) -> None:
        """Test returns None when no opening_ts has pending approvals."""
        self._synced().collected_proposed_markets_data = json.dumps(
            {"required_markets_to_approve_per_opening_ts": {}}
        )

        result = _exhaust_gen(self.behaviour._build_mech_request())
        assert result is None

    def test_build_mech_request_all_zero_counts(self) -> None:
        """Test returns None when all opening_ts counts are 0."""
        self._synced().collected_proposed_markets_data = json.dumps(
            {
                "required_markets_to_approve_per_opening_ts": {
                    "1700000000": 0,
                    "1700086400": 0,
                }
            }
        )

        result = _exhaust_gen(self.behaviour._build_mech_request())
        assert result is None

    def test_build_mech_request_returns_mech_metadata_json(self) -> None:
        """Test returns JSON list with one MechMetadata when work is pending."""
        opening_ts = "1700000000"
        num_pending = 3
        self._synced().collected_proposed_markets_data = json.dumps(
            {
                "required_markets_to_approve_per_opening_ts": {
                    opening_ts: num_pending,
                }
            }
        )

        result = _exhaust_gen(self.behaviour._build_mech_request())
        assert result is not None
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        item = parsed[0]
        assert item["tool"] == "propose-question"
        assert "nonce" in item
        assert len(item["nonce"]) > 0
        prompt = json.loads(item["prompt"])
        # resolution time is the opening timestamp minus one day (86400s)
        assert prompt["resolution_time"] == int(opening_ts) - 86400
        assert prompt["num_questions"] == num_pending
        # operator-configured params travel via request_context (the dedicated
        # params dict the Mech executor spreads as top-level tool kwargs)
        ctx = item["request_context"]
        assert ctx["topics"] == ["business", "science"]
        assert ctx["num_questions"] == num_pending
        assert ctx["resolution_time"] == int(opening_ts) - 86400

    def test_build_mech_request_caps_num_questions_at_max(self) -> None:
        """Test num_questions is capped at max_markets_per_story."""
        self.context_mock.params.max_markets_per_story = 2
        opening_ts = "1700000000"
        self._synced().collected_proposed_markets_data = json.dumps(
            {
                "required_markets_to_approve_per_opening_ts": {
                    opening_ts: 10,  # more than max
                }
            }
        )

        result = _exhaust_gen(self.behaviour._build_mech_request())
        assert result is not None
        prompt = json.loads(json.loads(result)[0]["prompt"])
        assert prompt["num_questions"] == 2

    def test_build_mech_request_picks_first_nonzero_opening_ts(self) -> None:
        """Test selects the first opening_ts dict entry with >0 approvals."""
        self._synced().collected_proposed_markets_data = json.dumps(
            {
                "required_markets_to_approve_per_opening_ts": {
                    "1700000000": 0,
                    "1700086400": 2,
                    "1700172800": 3,
                }
            }
        )

        result = _exhaust_gen(self.behaviour._build_mech_request())
        assert result is not None
        prompt = json.loads(json.loads(result)[0]["prompt"])
        # Should pick 1700086400 (first non-zero)
        assert prompt["resolution_time"] == 1700086400 - 86400

    def test_not_sender_act_waits(self) -> None:
        """Test _not_sender_act yields to wait_until_round_end and sets done."""
        self._synced().most_voted_keeper_address = KEEPER_ADDRESS

        with patch.object(
            self.behaviour, "wait_until_round_end", return_value=iter([])
        ):
            with patch.object(self.behaviour, "set_done") as set_done_mock:
                gen = self.behaviour._not_sender_act()
                try:
                    while True:
                        next(gen)
                except StopIteration:
                    pass
                set_done_mock.assert_called_once()

    def test_sender_act_calls_build_and_sends(self) -> None:
        """Test _sender_act builds the mech request and sends via transaction."""

        def _fake_build() -> Any:
            return '[{"nonce":"n","tool":"t","prompt":"{}"}]'
            yield  # noqa: unreachable

        with patch.object(
            self.behaviour, "_build_mech_request", return_value=_fake_build()
        ):
            with patch.object(
                self.behaviour, "send_a2a_transaction", return_value=iter([])
            ):
                with patch.object(
                    self.behaviour, "wait_until_round_end", return_value=iter([])
                ):
                    with patch.object(self.behaviour, "set_done") as set_done_mock:
                        gen = self.behaviour._sender_act()
                        try:
                            while True:
                                next(gen)
                        except StopIteration:
                            pass
                        set_done_mock.assert_called_once()

    def test_async_act_not_sender_path(self) -> None:
        """Test async_act dispatches to _not_sender_act when not keeper."""
        self._synced().most_voted_keeper_address = KEEPER_ADDRESS

        with patch.object(
            self.behaviour, "_not_sender_act", return_value=iter([])
        ) as mock_not_sender:
            gen = self.behaviour.async_act()
            try:
                while True:
                    next(gen)
            except StopIteration:
                pass
            mock_not_sender.assert_called_once()

    def test_async_act_sender_path(self) -> None:
        """Test async_act dispatches to _sender_act when this agent is keeper."""
        self._synced().most_voted_keeper_address = AGENT_ADDRESS

        with patch.object(
            self.behaviour, "_sender_act", return_value=iter([])
        ) as mock_sender:
            gen = self.behaviour.async_act()
            try:
                while True:
                    next(gen)
            except StopIteration:
                pass
            mock_sender.assert_called_once()

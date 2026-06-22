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

"""Tests for ProcessProposedQuestionsBehaviour."""

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from packages.valory.skills.market_creation_manager_abci.behaviours.process_proposed_questions import (
    ProcessProposedQuestionsBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.states.process_proposed_questions import (
    ProcessProposedQuestionsRound,
)

CURRENT_FILE_PATH = Path(__file__).resolve()
PACKAGE_DIR = CURRENT_FILE_PATH.parents[2]

AGENT_ADDRESS = "0x1234567890123456789012345678901234567890"

# resolution_time = 2025-09-05 00:00:00 UTC
_TS_SEP_5_2025 = 1757030400


def _exhaust_gen(gen: Any) -> Any:
    """Exhaust a generator and return its StopIteration value."""
    try:
        while True:
            next(gen)
    except StopIteration as exc:
        return exc.value


def _make_mech_response(nonce: str, result: Any, error: Any = None) -> MagicMock:
    """Make a MechInteractionResponse mock."""
    r = MagicMock()
    r.nonce = nonce
    r.result = result
    r.error = error
    return r


class TestProcessProposedQuestionsBehaviourAttributes:
    """Test class attributes."""

    def test_matching_round(self) -> None:
        """Test matching_round."""
        assert (
            ProcessProposedQuestionsBehaviour.matching_round
            is ProcessProposedQuestionsRound
        )


class TestIsResolutionDateInQuestion:
    """Tests for _is_resolution_date_in_question."""

    def setup_method(self) -> None:
        """Setup behaviour."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.synchronized_data = MagicMock()
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = AGENT_ADDRESS
        self.behaviour = ProcessProposedQuestionsBehaviour(
            name="test", skill_context=context_mock
        )

    @pytest.mark.parametrize(
        "market, expected",
        [
            # Date present in standard format "September 5, 2025"
            (
                {
                    "question": "Will X happen on or before September 5, 2025?",
                    "resolution_time": _TS_SEP_5_2025,
                },
                True,
            ),
            # Date present with zero-padded day "September 05, 2025"
            (
                {
                    "question": "Will X happen on or before September 05, 2025?",
                    "resolution_time": _TS_SEP_5_2025,
                },
                True,
            ),
            # Date absent -- resolution_time doesn't match text
            (
                {
                    "question": "Will X happen on or before October 31, 2024?",
                    "resolution_time": _TS_SEP_5_2025,
                },
                False,
            ),
            # No resolution_time key
            (
                {"question": "Will X happen?"},
                False,
            ),
            # Missing question key (has resolution_time)
            (
                {"resolution_time": _TS_SEP_5_2025},
                False,
            ),
            # Non-dict market
            (
                "not_a_dict",
                False,
            ),
        ],
    )
    def test_is_resolution_date_in_question(self, market: Any, expected: bool) -> None:
        """Test _is_resolution_date_in_question."""
        assert self.behaviour._is_resolution_date_in_question(market) == expected


class TestParseMechResponse:
    """Tests for _parse_mech_response (fail-closed)."""

    def setup_method(self) -> None:
        """Setup behaviour with a real synchronized_data mock on context."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.synchronized_data = MagicMock()
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = AGENT_ADDRESS
        self.context_mock = context_mock
        self.behaviour = ProcessProposedQuestionsBehaviour(
            name="test", skill_context=context_mock
        )

    def _synced(self) -> MagicMock:
        """Return the underlying synchronized_data mock."""
        return self.context_mock.state.synchronized_data

    def _run(self) -> Dict:
        """Exhaust the _parse_mech_response generator."""
        return _exhaust_gen(self.behaviour._parse_mech_response())

    def test_empty_when_no_mech_responses(self) -> None:
        """Returns empty dict when there are no Mech responses."""
        self._synced().mech_responses = []
        assert self._run() == {}

    def test_empty_when_result_is_none(self) -> None:
        """Returns empty dict when the delivered result is None."""
        self._synced().mech_responses = [_make_mech_response("nonce-abc", result=None)]
        assert self._run() == {}

    def test_empty_when_result_is_invalid_json(self) -> None:
        """Returns empty dict when result is not valid JSON."""
        self._synced().mech_responses = [
            _make_mech_response("nonce-abc", result="not-json")
        ]
        assert self._run() == {}

    def test_empty_when_result_is_non_string(self) -> None:
        """Returns empty dict when result is non-string (json.loads TypeError)."""
        self._synced().mech_responses = [_make_mech_response("nonce-abc", result=42)]
        assert self._run() == {}

    def test_empty_when_no_questions_key(self) -> None:
        """Returns empty dict when JSON has no 'questions' key."""
        self._synced().mech_responses = [
            _make_mech_response("nonce-abc", result='{"reasoning": "..."}')
        ]
        assert self._run() == {}

    def test_empty_when_questions_is_empty_dict(self) -> None:
        """Returns empty dict when 'questions' key is empty."""
        self._synced().mech_responses = [
            _make_mech_response("nonce-abc", result='{"questions": {}}')
        ]
        assert self._run() == {}

    def test_returns_questions_despite_unknown_error_default(self) -> None:
        """Parse questions from the result despite the default error='Unknown'."""
        questions = {
            "q1": {
                "question": "Will X happen on September 5, 2025?",
                "resolution_time": _TS_SEP_5_2025,
                "id": "market-1",
            }
        }
        result_json = json.dumps({"reasoning": "...", "questions": questions})
        self._synced().mech_responses = [
            _make_mech_response("nonce-abc", result=result_json, error="Unknown")
        ]
        assert self._run() == questions


def _make_http_response(status_code: int, body: Any = None) -> MagicMock:
    """Make an HTTP response mock."""
    resp = MagicMock()
    resp.status_code = status_code
    if body is not None:
        resp.body = json.dumps(body).encode()
    return resp


def _make_gen(return_value: Any) -> Any:
    """Create a no-yield generator function returning the given value."""

    def gen(*args: Any, **kwargs: Any) -> Any:
        return return_value
        yield  # noqa: unreachable - makes this a generator function

    return gen


class TestProposeAndApproveMarket:
    """Tests for _propose_and_approve_market HTTP flow."""

    def setup_method(self) -> None:
        """Setup behaviour."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.market_approval_server_url = "http://example.com"
        context_mock.params.market_approval_server_api_key = "key"
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.synchronized_data = MagicMock()
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = AGENT_ADDRESS
        self.context_mock = context_mock
        self.behaviour = ProcessProposedQuestionsBehaviour(
            name="test", skill_context=context_mock
        )

    def _run_propose(self, market: Any, *http_responses: Any) -> Any:
        """Exhaust _propose_and_approve_market with the given HTTP responses."""
        response_iter = iter(http_responses)

        def _http_gen(*args: Any, **kwargs: Any) -> Any:
            return next(response_iter)
            yield  # noqa: unreachable

        with patch.object(self.behaviour, "get_http_response", new=_http_gen):
            with patch.object(self.behaviour, "sleep", new=_make_gen(None)):
                return _exhaust_gen(self.behaviour._propose_and_approve_market(market))

    def test_propose_fails(self) -> None:
        """Returns ERROR_PAYLOAD when propose step returns non-200."""
        from packages.valory.skills.market_creation_manager_abci.states.process_proposed_questions import (  # noqa
            ProcessProposedQuestionsRound,
        )

        market = {"id": "m1", "question": "Q?"}
        result = self._run_propose(market, _make_http_response(500))
        assert result == ProcessProposedQuestionsRound.ERROR_PAYLOAD

    def test_approve_fails(self) -> None:
        """Returns ERROR_PAYLOAD when approve step returns non-200."""
        from packages.valory.skills.market_creation_manager_abci.states.process_proposed_questions import (  # noqa
            ProcessProposedQuestionsRound,
        )

        market = {"id": "m1", "question": "Q?"}
        result = self._run_propose(
            market,
            _make_http_response(200, {"id": "m1"}),
            _make_http_response(500),
        )
        assert result == ProcessProposedQuestionsRound.ERROR_PAYLOAD

    def test_update_fails(self) -> None:
        """Returns ERROR_PAYLOAD when update step returns non-200."""
        from packages.valory.skills.market_creation_manager_abci.states.process_proposed_questions import (  # noqa
            ProcessProposedQuestionsRound,
        )

        market = {"id": "m1", "question": "Q?"}
        result = self._run_propose(
            market,
            _make_http_response(200, {"id": "m1"}),
            _make_http_response(200, {"id": "m1"}),
            _make_http_response(500),
        )
        assert result == ProcessProposedQuestionsRound.ERROR_PAYLOAD

    def test_all_steps_succeed(self) -> None:
        """Returns JSON body when all three HTTP steps succeed."""
        market = {"id": "m1", "question": "Q?"}
        body = {"id": "m1", "status": "approved"}
        result = self._run_propose(
            market,
            _make_http_response(200, {"id": "m1"}),
            _make_http_response(200, {"id": "m1"}),
            _make_http_response(200, body),
        )
        assert json.loads(result) == body

    def test_missing_id_returns_error(self) -> None:
        """Returns ERROR_PAYLOAD when the market has no 'id' (no HTTP call)."""
        result = self._run_propose({"question": "Q?"})
        assert result == ProcessProposedQuestionsRound.ERROR_PAYLOAD

    def test_unparseable_200_body_returns_error(self) -> None:
        """Returns ERROR_PAYLOAD when a 200 response carries a non-JSON body."""
        bad = MagicMock()
        bad.status_code = 200
        bad.body = b"not-json"
        result = self._run_propose({"id": "m1", "question": "Q?"}, bad)
        assert result == ProcessProposedQuestionsRound.ERROR_PAYLOAD


class TestAsyncAct:
    """Tests for ProcessProposedQuestionsBehaviour.async_act."""

    def setup_method(self) -> None:
        """Setup behaviour."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.market_approval_server_url = "http://example.com"
        context_mock.params.market_approval_server_api_key = "key"
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.synchronized_data = MagicMock()
        context_mock.state.synchronized_data.approved_markets_count = 0
        context_mock.state.synchronized_data.last_synced_timestamp = 0
        context_mock.benchmark_tool = MagicMock()
        context_mock.benchmark_tool.measure.return_value.__enter__ = MagicMock(
            return_value=None
        )
        context_mock.benchmark_tool.measure.return_value.__exit__ = MagicMock(
            return_value=False
        )
        context_mock.agent_address = AGENT_ADDRESS
        self.context_mock = context_mock
        self.behaviour = ProcessProposedQuestionsBehaviour(
            name="test", skill_context=context_mock
        )

    def _synced(self) -> MagicMock:
        return self.context_mock.state.synchronized_data

    def _run_async_act(self) -> Any:
        """Exhaust async_act and return the emitted payload."""
        captured: Dict[str, Any] = {}

        def _capture(payload: Any, *args: Any, **kwargs: Any) -> Any:
            captured["payload"] = payload
            return None
            yield  # noqa: unreachable

        with patch.object(self.behaviour, "send_a2a_transaction", new=_capture):
            with patch.object(
                self.behaviour, "wait_until_round_end", new=_make_gen(None)
            ):
                with patch.object(self.behaviour, "set_done"):
                    gen = self.behaviour.async_act()
                    try:
                        while True:
                            next(gen)
                    except StopIteration:
                        pass
        return captured.get("payload")

    @staticmethod
    def _patched_propose(called: list, return_value: Any) -> Any:
        """A fake _propose_and_approve_market that records its calls."""

        def _fake(market_arg: Any) -> Any:
            called.append(market_arg)
            return return_value
            yield  # noqa: unreachable

        return _fake

    _VALID_MARKET = {
        "id": "m1",
        "question": "Will X happen on September 5, 2025?",
        "resolution_time": _TS_SEP_5_2025,
    }

    def _set_questions(self, market: Dict) -> None:
        """Put a single-question Mech response into synchronized_data."""
        result_json = json.dumps({"reasoning": "...", "questions": {"q1": market}})
        self._synced().mech_responses = [
            _make_mech_response("nonce-abc", result=result_json)
        ]

    def test_async_act_empty_questions(self) -> None:
        """No mech responses -> empty proposed_markets, count unchanged."""
        self._synced().mech_responses = []
        payload = self._run_async_act()
        assert payload.approved_markets_count == 0
        assert payload.content == "{}"

    def test_async_act_with_valid_question_and_date_mismatch(self) -> None:
        """Date not in question text -> skipped, not attempted, not counted."""
        market = {
            "id": "m1",
            "question": "No date here?",
            "resolution_time": _TS_SEP_5_2025,
        }
        self._set_questions(market)
        called: list = []
        with patch.object(
            self.behaviour,
            "_propose_and_approve_market",
            new=self._patched_propose(called, "{}"),
        ):
            payload = self._run_async_act()
        assert called == []
        assert payload.approved_markets_count == 0
        assert payload.content == "{}"

    def test_async_act_with_valid_question_approves(self) -> None:
        """Valid market that approves -> attempted, counted, and recorded."""
        self._set_questions(self._VALID_MARKET)
        called: list = []
        with patch.object(
            self.behaviour,
            "_propose_and_approve_market",
            new=self._patched_propose(called, '{"ok": 1}'),
        ):
            payload = self._run_async_act()
        assert called == [self._VALID_MARKET]
        assert payload.approved_markets_count == 1
        assert json.loads(payload.content) == {"q1": self._VALID_MARKET}

    def test_async_act_approval_failure_not_counted(self) -> None:
        """C1: an approval-server failure is attempted but never counted/recorded."""
        self._set_questions(self._VALID_MARKET)
        called: list = []
        with patch.object(
            self.behaviour,
            "_propose_and_approve_market",
            new=self._patched_propose(
                called, ProcessProposedQuestionsRound.ERROR_PAYLOAD
            ),
        ):
            payload = self._run_async_act()
        assert called == [self._VALID_MARKET]
        assert payload.approved_markets_count == 0
        assert payload.content == "{}"

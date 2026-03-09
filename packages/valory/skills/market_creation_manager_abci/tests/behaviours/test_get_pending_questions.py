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

"""Tests for GetPendingQuestionsBehaviour."""

from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

from packages.valory.protocols.ledger_api import LedgerApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.get_pending_questions import (
    GetPendingQuestionsBehaviour,
    OPEN_FPMM_QUERY,
)
from packages.valory.skills.market_creation_manager_abci.states.get_pending_questions import (
    GetPendingQuestionsRound,
)


def _make_gen(return_value: Any) -> Any:
    """Create a no-yield generator returning the given value."""

    def gen(*args: Any, **kwargs: Any) -> Any:
        return return_value
        yield  # noqa: unreachable - makes this a generator function

    return gen


def _exhaust_gen(gen: Any) -> Any:
    """Exhaust a generator and return its value."""
    try:
        while True:
            next(gen)
    except StopIteration as e:
        return e.value


def _make_question(question_id: str, title: str = "Will X happen?") -> Any:
    """Create a sample question dict."""
    return {
        "id": f"0x{question_id}",
        "title": title,
        "question": {"id": question_id, "data": "some data", "currentAnswerBond": None},
        "openingTimestamp": "1700000000",
        "currentAnswer": None,
        "currentAnswerTimestamp": None,
        "timeout": "86400",
    }


class TestGetPendingQuestionsBehaviour:
    """Tests for GetPendingQuestionsBehaviour."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.answer_retry_intervals = [0, 300, 600]
        context_mock.params.multisend_batch_size = 10
        context_mock.params.questions_to_close_batch_size = 5
        context_mock.params.realitio_answer_question_bond = 100
        context_mock.params.mech_tool_resolve_market = "resolve_market"
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
            1700000100
        )
        context_mock.state.questions_responded = {}
        context_mock.state.questions_requested_mech = {}
        context_mock.state.synchronized_data.safe_contract_address = "0xSafeAddress"
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        self.behaviour = GetPendingQuestionsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_get_unanswered_questions_success(self) -> None:
        """Test _get_unanswered_questions with valid subgraph data."""
        questions = [_make_question("q1"), _make_question("q2")]
        subgraph_response = {"data": {"fixedProductMarketMakers": questions}}

        with patch.object(
            self.behaviour,
            "get_subgraph_result",
            new=_make_gen(subgraph_response),
        ):
            gen = self.behaviour._get_unanswered_questions()
            result = _exhaust_gen(gen)

        assert len(result) == 2

    def test_get_unanswered_questions_none(self) -> None:
        """Test _get_unanswered_questions when subgraph returns None."""
        with patch.object(
            self.behaviour,
            "get_subgraph_result",
            new=_make_gen(None),
        ):
            gen = self.behaviour._get_unanswered_questions()
            result = _exhaust_gen(gen)

        assert result == []

    def test_get_unanswered_questions_empty(self) -> None:
        """Test _get_unanswered_questions when subgraph returns empty list."""
        subgraph_response: Any = {"data": {"fixedProductMarketMakers": []}}

        with patch.object(
            self.behaviour,
            "get_subgraph_result",
            new=_make_gen(subgraph_response),
        ):
            gen = self.behaviour._get_unanswered_questions()
            result = _exhaust_gen(gen)

        assert result == []

    def test_get_balance_success(self) -> None:
        """Test _get_balance with correct performative and balance result."""
        mock_resp = MagicMock()
        mock_resp.performative = LedgerApiMessage.Performative.STATE
        mock_resp.state.body = {"get_balance_result": 1000}

        with patch.object(
            self.behaviour,
            "get_ledger_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_balance("0xAccount")
            result = _exhaust_gen(gen)

        assert result == 1000

    def test_get_balance_error(self) -> None:
        """Test _get_balance when performative is wrong."""
        mock_resp = MagicMock()
        mock_resp.performative = LedgerApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour,
            "get_ledger_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_balance("0xAccount")
            result = _exhaust_gen(gen)

        assert result is None

    def test_eligible_questions_new_question(self) -> None:
        """Test _eligible_questions_to_answer with a new, unseen question."""
        questions = [_make_question("q1")]

        with patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=PropertyMock,
            return_value=1700000100,
        ), patch.object(
            type(self.behaviour),
            "shared_state",
            new_callable=PropertyMock,
        ) as mock_shared:
            state = MagicMock()
            state.questions_responded = {}
            state.questions_requested_mech = {}
            mock_shared.return_value = state

            result = self.behaviour._eligible_questions_to_answer(questions)

        assert "q1" in result

    def test_eligible_questions_already_responded(self) -> None:
        """Test _eligible_questions_to_answer when question already responded."""
        questions = [_make_question("q1")]

        with patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=PropertyMock,
            return_value=1700000100,
        ), patch.object(
            type(self.behaviour),
            "shared_state",
            new_callable=PropertyMock,
        ) as mock_shared:
            state = MagicMock()
            state.questions_responded = {"q1": True}
            state.questions_requested_mech = {}
            mock_shared.return_value = state

            result = self.behaviour._eligible_questions_to_answer(questions)

        assert "q1" not in result

    def test_eligible_questions_retry_not_ready(self) -> None:
        """Test _eligible_questions_to_answer when retry interval not elapsed."""
        questions = [_make_question("q1")]

        with patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=PropertyMock,
            return_value=1700000100,
        ), patch.object(
            type(self.behaviour),
            "shared_state",
            new_callable=PropertyMock,
        ) as mock_shared:
            state = MagicMock()
            state.questions_responded = {}
            # Last retry was very recent (1 second ago)
            state.questions_requested_mech = {
                "q1": {
                    "question": questions[0],
                    "retries": [1700000099],
                }
            }
            mock_shared.return_value = state

            result = self.behaviour._eligible_questions_to_answer(questions)

        assert "q1" not in result

    def test_eligible_questions_retry_ready(self) -> None:
        """Test _eligible_questions_to_answer when retry interval has elapsed."""
        questions = [_make_question("q1")]

        with patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=PropertyMock,
            return_value=1700001000,
        ), patch.object(
            type(self.behaviour),
            "shared_state",
            new_callable=PropertyMock,
        ) as mock_shared:
            state = MagicMock()
            state.questions_responded = {}
            # Last retry was long ago (900+ seconds ago, interval[1]=300)
            state.questions_requested_mech = {
                "q1": {
                    "question": questions[0],
                    "retries": [1700000000],
                }
            }
            mock_shared.return_value = state

            result = self.behaviour._eligible_questions_to_answer(questions)

        assert "q1" in result

    def test_get_payload_no_questions(self) -> None:
        """Test get_payload when _get_unanswered_questions returns None."""
        with patch.object(
            self.behaviour,
            "_get_unanswered_questions",
            new=_make_gen(None),
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result == GetPendingQuestionsRound.ERROR_PAYLOAD

    def test_get_payload_no_eligible(self) -> None:
        """Test get_payload when all questions are already responded."""
        questions = [_make_question("q1")]

        with patch.object(
            self.behaviour,
            "_get_unanswered_questions",
            new=_make_gen(questions),
        ), patch.object(
            self.behaviour,
            "_eligible_questions_to_answer",
            return_value=[],
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result == GetPendingQuestionsRound.NO_TX_PAYLOAD

    def test_get_payload_insufficient_balance(self) -> None:
        """Test get_payload when balance is less than bond_required."""
        questions = [_make_question("q1")]

        with patch.object(
            self.behaviour,
            "_get_unanswered_questions",
            new=_make_gen(questions),
        ), patch.object(
            self.behaviour,
            "_eligible_questions_to_answer",
            return_value=["q1"],
        ), patch.object(
            self.behaviour,
            "_get_balance",
            new=_make_gen(10),
        ):
            # bond_required = 100 * 1 = 100, balance = 10
            self.behaviour.params.realitio_answer_question_bond = 100
            self.behaviour.params.questions_to_close_batch_size = 5
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result == GetPendingQuestionsRound.NO_TX_PAYLOAD

    def test_open_fpmm_query_template(self) -> None:
        """Test that OPEN_FPMM_QUERY template contains expected fields."""
        template_str = OPEN_FPMM_QUERY.template
        assert "fixedProductMarketMakers" in template_str
        assert "$creator" in template_str
        assert "$current_timestamp" in template_str
        assert "answerFinalizedTimestamp" in template_str
        assert "currentAnswerBond" in template_str
        assert "question" in template_str

    def test_get_payload_balance_none(self) -> None:
        """Test get_payload when _get_balance returns None."""
        questions = [_make_question("q1")]

        with patch.object(
            self.behaviour,
            "_get_unanswered_questions",
            new=_make_gen(questions),
        ), patch.object(
            self.behaviour,
            "_eligible_questions_to_answer",
            return_value=["q1"],
        ), patch.object(
            self.behaviour,
            "_get_balance",
            new=_make_gen(None),
        ):
            self.behaviour.params.questions_to_close_batch_size = 5
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result == GetPendingQuestionsRound.NO_TX_PAYLOAD

    def test_get_payload_success_with_mech_requests(self) -> None:
        """Test get_payload happy path returning JSON mech requests."""
        import json

        questions = [_make_question("q1")]

        with patch.object(
            self.behaviour,
            "_get_unanswered_questions",
            new=_make_gen(questions),
        ), patch.object(
            self.behaviour,
            "_eligible_questions_to_answer",
            return_value=["q1"],
        ), patch.object(
            self.behaviour,
            "_get_balance",
            new=_make_gen(10000),
        ), patch.object(
            type(self.behaviour),
            "shared_state",
            new_callable=PropertyMock,
        ) as mock_shared, patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=PropertyMock,
            return_value=1700000100,
        ):
            state = MagicMock()
            state.questions_requested_mech = {
                "q1": {
                    "question": questions[0],
                    "retries": [],
                }
            }
            mock_shared.return_value = state

            self.behaviour.params.realitio_answer_question_bond = 100
            self.behaviour.params.questions_to_close_batch_size = 5
            self.behaviour.params.mech_tool_resolve_market = "resolve_market"

            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["nonce"] == "q1"

    def test_async_act(self) -> None:
        """Test async_act wraps get_payload correctly."""
        with patch.object(
            self.behaviour,
            "get_payload",
            new=_make_gen(GetPendingQuestionsRound.NO_TX_PAYLOAD),
        ), patch.object(
            self.behaviour, "send_a2a_transaction", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "wait_until_round_end", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "set_done"
        ) as mock_set_done:
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)
            mock_set_done.assert_called_once()

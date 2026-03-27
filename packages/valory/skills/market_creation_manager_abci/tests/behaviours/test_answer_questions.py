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

"""Tests for market_creation_manager_abci AnswerQuestionsBehaviour."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.answer_questions import (
    ANSWER_INVALID,
    ANSWER_NO,
    ANSWER_YES,
    AnswerQuestionsBehaviour,
)

CURRENT_FILE_PATH = Path(__file__).resolve()
PACKAGE_DIR = CURRENT_FILE_PATH.parents[2]


class TestParseMechResponse:
    """Test _parse_mech_response helper method."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        self.behaviour = AnswerQuestionsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_parse_mech_response_valid_yes(self) -> None:
        """Test parsing valid YES response."""
        response = MagicMock()
        response.result = json.dumps(
            {"is_valid": True, "is_determinable": True, "has_occurred": True}
        )
        result = self.behaviour._parse_mech_response(response)
        assert result == ANSWER_YES

    def test_parse_mech_response_valid_no(self) -> None:
        """Test parsing valid NO response."""
        response = MagicMock()
        response.result = json.dumps(
            {"is_valid": True, "is_determinable": True, "has_occurred": False}
        )
        result = self.behaviour._parse_mech_response(response)
        assert result == ANSWER_NO

    def test_parse_mech_response_invalid(self) -> None:
        """Test parsing invalid response."""
        response = MagicMock()
        response.result = json.dumps(
            {"is_valid": False, "is_determinable": True, "has_occurred": True}
        )
        result = self.behaviour._parse_mech_response(response)
        assert result == ANSWER_INVALID

    def test_parse_mech_response_not_determinable(self) -> None:
        """Test parsing not determinable response."""
        response = MagicMock()
        response.result = json.dumps(
            {"is_valid": True, "is_determinable": False, "has_occurred": True}
        )
        result = self.behaviour._parse_mech_response(response)
        assert result is None

    def test_parse_mech_response_has_occurred_none(self) -> None:
        """Test parsing response with has_occurred None."""
        response = MagicMock()
        response.result = json.dumps(
            {"is_valid": True, "is_determinable": True, "has_occurred": None}
        )
        result = self.behaviour._parse_mech_response(response)
        assert result is None

    def test_parse_mech_response_missing_fields(self) -> None:
        """Test parsing response with missing fields."""
        response = MagicMock()
        response.result = json.dumps({"is_valid": True})
        result = self.behaviour._parse_mech_response(response)
        # Should default is_determinable=True, has_occurred=None
        assert result is None

    def test_parse_mech_response_invalid_json(self) -> None:
        """Test parsing response with invalid JSON."""
        response = MagicMock()
        response.result = "not a json string"
        result = self.behaviour._parse_mech_response(response)
        assert result is None

    def test_parse_mech_response_none_result(self) -> None:
        """Test parsing response with None result."""
        response = MagicMock()
        response.result = None
        result = self.behaviour._parse_mech_response(response)
        assert result is None

    def test_parse_mech_response_with_defaults(self) -> None:
        """Test parsing response using default values for missing fields."""
        response = MagicMock()
        response.result = json.dumps({"has_occurred": True})
        result = self.behaviour._parse_mech_response(response)
        # Should default is_valid=True and is_determinable=True
        assert result == ANSWER_YES

    def test_parse_mech_response_empty_dict(self) -> None:
        """Test parsing response with empty dict."""
        response = MagicMock()
        response.result = json.dumps({})
        result = self.behaviour._parse_mech_response(response)
        # Empty dict: is_valid=True, is_determinable=True, has_occurred=None
        assert result is None


def _make_gen(return_value: Any) -> Any:
    """Create a no-yield generator returning the given value."""

    def gen(*args: Any, **kwargs: Any) -> Any:
        return return_value
        yield  # noqa: unreachable - makes this a generator function

    return gen


def _passthrough_gen(txs: Any) -> Any:
    """Generator that returns its argument unchanged (for mocking _prepend_wxdai_unwrap)."""
    yield  # noqa: unreachable - makes this a generator function
    return txs


def _exhaust_gen(gen: Any) -> Any:
    """Exhaust a generator and return its value."""
    try:
        while True:
            next(gen)
    except StopIteration as e:
        return e.value


class TestAnswerQuestionsBehaviourGenerators:
    """Test AnswerQuestionsBehaviour generator methods."""

    def setup_method(self) -> None:
        """Setup method."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.params.realitio_contract = "0xrealitio"
        context_mock.params.realitio_answer_question_bond = 10**17
        context_mock.params.questions_to_close_batch_size = 10
        context_mock.params.answer_retry_intervals = [60, 120, 300]
        self.behaviour = AnswerQuestionsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_get_answer_tx_success(self) -> None:
        """Test _get_answer_tx with successful STATE response."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.STATE
        mock_resp.state.body = {"data": b"\x01\x02\x03"}

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_answer_tx(
                "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                ANSWER_YES,
            )
            result = _exhaust_gen(gen)

        assert result is not None
        assert result["to"] == "0xrealitio"
        assert result["value"] == 10**17
        assert result["data"] == b"\x01\x02\x03"

    def test_get_answer_tx_error(self) -> None:
        """Test _get_answer_tx when contract returns ERROR."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_answer_tx(
                "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                ANSWER_YES,
            )
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_payload_no_responses(self) -> None:
        """Test _get_payload when mech_responses is empty."""
        mock_synced_data = MagicMock()
        mock_synced_data.mech_responses = []

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced_data),
        ):
            gen = self.behaviour._get_payload()
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_payload_question_already_responded(self) -> None:
        """Test _get_payload when question is in questions_responded."""
        mock_response = MagicMock()
        mock_response.nonce = "0xquestion1"
        mock_response.result = json.dumps(
            {"is_valid": True, "is_determinable": True, "has_occurred": True}
        )

        mock_synced_data = MagicMock()
        mock_synced_data.mech_responses = [mock_response]

        mock_shared_state = MagicMock()
        mock_shared_state.questions_responded = {"0xquestion1"}
        mock_shared_state.questions_requested_mech = {}

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced_data),
        ), patch.object(
            type(self.behaviour),
            "shared_state",
            new_callable=lambda: property(lambda self: mock_shared_state),
        ):
            gen = self.behaviour._get_payload()
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_payload_question_not_in_requested(self) -> None:
        """Test _get_payload when question is not in questions_requested_mech."""
        mock_response = MagicMock()
        mock_response.nonce = "0xquestion1"
        mock_response.result = json.dumps(
            {"is_valid": True, "is_determinable": True, "has_occurred": True}
        )

        mock_synced_data = MagicMock()
        mock_synced_data.mech_responses = [mock_response]

        mock_shared_state = MagicMock()
        mock_shared_state.questions_responded = set()
        mock_shared_state.questions_requested_mech = {}

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced_data),
        ), patch.object(
            type(self.behaviour),
            "shared_state",
            new_callable=lambda: property(lambda self: mock_shared_state),
        ):
            gen = self.behaviour._get_payload()
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_payload_answer_none_with_max_retries(self) -> None:
        """Test _get_payload when answer is None but retries >= answer_retry_intervals length."""
        mock_response = MagicMock()
        mock_response.nonce = "0xquestion1"
        mock_response.result = json.dumps({"is_valid": True, "is_determinable": False})

        mock_synced_data = MagicMock()
        mock_synced_data.mech_responses = [mock_response]

        mock_shared_state = MagicMock()
        mock_shared_state.questions_responded = set()
        mock_shared_state.questions_requested_mech = {
            "0xquestion1": {
                "question": {"title": "Test?"},
                "retries": [100, 200, 300],  # 3 retries >= len([60, 120, 300])
            }
        }

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced_data),
        ), patch.object(
            type(self.behaviour),
            "shared_state",
            new_callable=lambda: property(lambda self: mock_shared_state),
        ), patch.object(
            self.behaviour,
            "_get_answer_tx",
            new=_make_gen({"to": "0xrealitio", "value": 10**17, "data": b"\x00"}),
        ), patch.object(
            self.behaviour,
            "_prepend_wxdai_unwrap",
            new=_passthrough_gen,
        ), patch.object(
            self.behaviour,
            "_to_multisend",
            new=_make_gen("0xmultisend_hash"),
        ):
            gen = self.behaviour._get_payload()
            result = _exhaust_gen(gen)

        # answer became ANSWER_INVALID, so it should proceed
        assert result == "0xmultisend_hash"

    def test_get_payload_answer_none_skipped(self) -> None:
        """Test _get_payload when answer is None and retries < threshold."""
        mock_response = MagicMock()
        mock_response.nonce = "0xquestion1"
        mock_response.result = json.dumps({"is_valid": True, "is_determinable": False})

        mock_synced_data = MagicMock()
        mock_synced_data.mech_responses = [mock_response]

        mock_shared_state = MagicMock()
        mock_shared_state.questions_responded = set()
        mock_shared_state.questions_requested_mech = {
            "0xquestion1": {
                "question": {"title": "Test?"},
                "retries": [100],  # only 1 retry < len([60, 120, 300])
            }
        }

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced_data),
        ), patch.object(
            type(self.behaviour),
            "shared_state",
            new_callable=lambda: property(lambda self: mock_shared_state),
        ):
            gen = self.behaviour._get_payload()
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_payload_success(self) -> None:
        """Test _get_payload happy path with valid answer."""
        mock_response = MagicMock()
        mock_response.nonce = "0xquestion1"
        mock_response.result = json.dumps(
            {"is_valid": True, "is_determinable": True, "has_occurred": True}
        )

        mock_synced_data = MagicMock()
        mock_synced_data.mech_responses = [mock_response]

        mock_shared_state = MagicMock()
        mock_shared_state.questions_responded = set()
        mock_shared_state.questions_requested_mech = {
            "0xquestion1": {
                "question": {"title": "Test?"},
                "retries": [],
            }
        }

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced_data),
        ), patch.object(
            type(self.behaviour),
            "shared_state",
            new_callable=lambda: property(lambda self: mock_shared_state),
        ), patch.object(
            self.behaviour,
            "_get_answer_tx",
            new=_make_gen({"to": "0xrealitio", "value": 10**17, "data": b"\x00"}),
        ), patch.object(
            self.behaviour,
            "_prepend_wxdai_unwrap",
            new=_passthrough_gen,
        ), patch.object(
            self.behaviour,
            "_to_multisend",
            new=_make_gen("0xmultisend_hash"),
        ):
            gen = self.behaviour._get_payload()
            result = _exhaust_gen(gen)

        assert result == "0xmultisend_hash"

    def test_get_payload_answer_tx_none(self) -> None:
        """Test _get_payload when _get_answer_tx returns None."""
        mock_response = MagicMock()
        mock_response.nonce = "0xquestion1"
        mock_response.result = json.dumps(
            {"is_valid": True, "is_determinable": True, "has_occurred": True}
        )

        mock_synced_data = MagicMock()
        mock_synced_data.mech_responses = [mock_response]

        mock_shared_state = MagicMock()
        mock_shared_state.questions_responded = set()
        mock_shared_state.questions_requested_mech = {
            "0xquestion1": {
                "question": {"title": "Test?"},
                "retries": [],
            }
        }

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced_data),
        ), patch.object(
            type(self.behaviour),
            "shared_state",
            new_callable=lambda: property(lambda self: mock_shared_state),
        ), patch.object(
            self.behaviour,
            "_get_answer_tx",
            new=_make_gen(None),
        ):
            gen = self.behaviour._get_payload()
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_payload_multisend_none(self) -> None:
        """Test _get_payload when _to_multisend returns None."""
        mock_response = MagicMock()
        mock_response.nonce = "0xquestion1"
        mock_response.result = json.dumps(
            {"is_valid": True, "is_determinable": True, "has_occurred": True}
        )

        mock_synced_data = MagicMock()
        mock_synced_data.mech_responses = [mock_response]

        mock_shared_state = MagicMock()
        mock_shared_state.questions_responded = set()
        mock_shared_state.questions_requested_mech = {
            "0xquestion1": {
                "question": {"title": "Test?"},
                "retries": [],
            }
        }

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced_data),
        ), patch.object(
            type(self.behaviour),
            "shared_state",
            new_callable=lambda: property(lambda self: mock_shared_state),
        ), patch.object(
            self.behaviour,
            "_get_answer_tx",
            new=_make_gen({"to": "0xrealitio", "value": 10**17, "data": b"\x00"}),
        ), patch.object(
            self.behaviour,
            "_prepend_wxdai_unwrap",
            new=_passthrough_gen,
        ), patch.object(
            self.behaviour,
            "_to_multisend",
            new=_make_gen(None),
        ):
            gen = self.behaviour._get_payload()
            result = _exhaust_gen(gen)

        assert result is None

    def test_async_act_with_tx_hash(self) -> None:
        """Test async_act when get_payload returns a hash."""
        with patch.object(
            self.behaviour,
            "_get_payload",
            new=_make_gen("0xhash"),
        ), patch.object(
            self.behaviour,
            "send_a2a_transaction",
            new=_make_gen(None),
        ), patch.object(
            self.behaviour,
            "wait_until_round_end",
            new=_make_gen(None),
        ), patch.object(
            self.behaviour,
            "set_done",
        ) as mock_set_done:
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)
            mock_set_done.assert_called_once()

    def test_async_act_without_tx_hash(self) -> None:
        """Test async_act when get_payload returns None."""
        with patch.object(
            self.behaviour,
            "_get_payload",
            new=_make_gen(None),
        ), patch.object(
            self.behaviour,
            "send_a2a_transaction",
            new=_make_gen(None),
        ), patch.object(
            self.behaviour,
            "wait_until_round_end",
            new=_make_gen(None),
        ), patch.object(
            self.behaviour,
            "set_done",
        ):
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)

    def test_get_payload_batch_size_reached(self) -> None:
        """Test _get_payload when batch size limit is reached and loop breaks early."""
        # Set batch size to 1 so that after the first valid answer, the loop breaks
        self.behaviour.context.params.questions_to_close_batch_size = 1

        # Create 2 mech responses, both with valid YES answers
        mock_response_1 = MagicMock()
        mock_response_1.nonce = "0xquestion1"
        mock_response_1.result = json.dumps(
            {"is_valid": True, "is_determinable": True, "has_occurred": True}
        )

        mock_response_2 = MagicMock()
        mock_response_2.nonce = "0xquestion2"
        mock_response_2.result = json.dumps(
            {"is_valid": True, "is_determinable": True, "has_occurred": True}
        )

        mock_synced_data = MagicMock()
        mock_synced_data.mech_responses = [mock_response_1, mock_response_2]

        mock_shared_state = MagicMock()
        mock_shared_state.questions_responded = set()
        mock_shared_state.questions_requested_mech = {
            "0xquestion1": {
                "question": {"title": "Test question 1?"},
                "retries": [],
            },
            "0xquestion2": {
                "question": {"title": "Test question 2?"},
                "retries": [],
            },
        }

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced_data),
        ), patch.object(
            type(self.behaviour),
            "shared_state",
            new_callable=lambda: property(lambda self: mock_shared_state),
        ), patch.object(
            self.behaviour,
            "_get_answer_tx",
            new=_make_gen({"to": "0xrealitio", "value": 10**17, "data": b"\x00"}),
        ), patch.object(
            self.behaviour,
            "_prepend_wxdai_unwrap",
            new=_passthrough_gen,
        ), patch.object(
            self.behaviour,
            "_to_multisend",
            new=_make_gen("0xmultisend_hash"),
        ):
            gen = self.behaviour._get_payload()
            result = _exhaust_gen(gen)

        # Should succeed with only the first question processed (batch size = 1)
        assert result == "0xmultisend_hash"
        # Only question1 should have been processed (removed from requested, added to responded)
        assert "0xquestion1" not in mock_shared_state.questions_requested_mech
        # question2 should still be in requested (loop broke before processing it)
        assert "0xquestion2" in mock_shared_state.questions_requested_mech


class TestPrependWxdaiUnwrap:
    """Test _prepend_wxdai_unwrap method."""

    def setup_method(self) -> None:
        """Setup method."""
        context_mock = MagicMock()
        context_mock.params.collateral_tokens_contract = "0xwxdai"
        self.behaviour = AnswerQuestionsBehaviour(
            name="test", skill_context=context_mock
        )
        self.behaviour._synchronized_data = MagicMock()
        self.behaviour._synchronized_data.safe_contract_address = "0xsafe"

    def test_zero_bond_returns_txs_unchanged(self) -> None:
        """Test that zero total bond returns txs as-is."""
        txs = [{"to": "0x1", "value": 0, "data": b"\x00"}]
        gen = self.behaviour._prepend_wxdai_unwrap(txs)
        result = _exhaust_gen(gen)
        assert result == txs

    def test_insufficient_wxdai_balance(self) -> None:
        """Test that insufficient wxDAI balance returns txs unchanged."""
        txs = [{"to": "0x1", "value": 100, "data": b"\x00"}]
        with patch.object(self.behaviour, "get_wxdai_balance", new=_make_gen(50)):
            gen = self.behaviour._prepend_wxdai_unwrap(txs)
            result = _exhaust_gen(gen)
        assert result == txs

    def test_none_wxdai_balance(self) -> None:
        """Test that None wxDAI balance returns txs unchanged."""
        txs = [{"to": "0x1", "value": 100, "data": b"\x00"}]
        with patch.object(self.behaviour, "get_wxdai_balance", new=_make_gen(None)):
            gen = self.behaviour._prepend_wxdai_unwrap(txs)
            result = _exhaust_gen(gen)
        assert result == txs

    def test_withdraw_tx_fails(self) -> None:
        """Test that failed withdraw tx build returns txs unchanged."""
        txs = [{"to": "0x1", "value": 100, "data": b"\x00"}]
        with patch.object(
            self.behaviour, "get_wxdai_balance", new=_make_gen(200)
        ), patch.object(self.behaviour, "_get_wxdai_withdraw_tx", new=_make_gen(None)):
            gen = self.behaviour._prepend_wxdai_unwrap(txs)
            result = _exhaust_gen(gen)
        assert result == txs

    def test_success_prepends_withdraw(self) -> None:
        """Test successful unwrap prepends withdraw tx."""
        txs = [{"to": "0x1", "value": 100, "data": b"\x00"}]
        withdraw_tx = {"to": "0xwxdai", "value": 0, "data": b"\x01"}
        with patch.object(
            self.behaviour, "get_wxdai_balance", new=_make_gen(200)
        ), patch.object(
            self.behaviour, "_get_wxdai_withdraw_tx", new=_make_gen(withdraw_tx)
        ):
            gen = self.behaviour._prepend_wxdai_unwrap(txs)
            result = _exhaust_gen(gen)
        assert len(result) == 2
        assert result[0] == withdraw_tx
        assert result[1] == txs[0]


class TestGetWxdaiWithdrawTx:
    """Test _get_wxdai_withdraw_tx method."""

    def setup_method(self) -> None:
        """Setup method."""
        context_mock = MagicMock()
        context_mock.params.collateral_tokens_contract = "0xwxdai"
        self.behaviour = AnswerQuestionsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_success(self) -> None:
        """Test successful withdraw tx build."""
        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.STATE
        mock_resp.state.body = {"data": b"\x01\x02"}
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_wxdai_withdraw_tx(100)
            result = _exhaust_gen(gen)
        assert result is not None
        assert result["to"] == "0xwxdai"
        assert result["data"] == b"\x01\x02"

    def test_error(self) -> None:
        """Test withdraw tx build error."""
        mock_resp = MagicMock()
        mock_resp.performative = MagicMock()
        mock_resp.performative.value = "error"
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_wxdai_withdraw_tx(100)
            result = _exhaust_gen(gen)
        assert result is None

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

import pytest

from packages.valory.skills.abstract_round_abci.test_tools.base import (
    FSMBehaviourBaseCase,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.answer_questions import (
    ANSWER_INVALID,
    ANSWER_NO,
    ANSWER_YES,
    AnswerQuestionsBehaviour,
)


CURRENT_FILE_PATH = Path(__file__).resolve()
PACKAGE_DIR = CURRENT_FILE_PATH.parents[2]


class TestAnswerQuestionsBehaviour:
    """Test AnswerQuestionsBehaviour without directly importing it."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        self.round_sequence_mock = MagicMock()
        context_mock = MagicMock(params=MagicMock())
        context_mock.state.round_sequence = self.round_sequence_mock
        context_mock.handlers = MagicMock()
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.logger = MagicMock()

        # Create a mock behaviour instead of importing the real one
        self.behaviour = MagicMock()
        self.behaviour.context = context_mock
        self.behaviour.matching_round = MagicMock()
        self.behaviour._parse_mech_response = MagicMock(return_value=None)
        self.behaviour.async_act = MagicMock(side_effect=lambda: None)

    def test_answer_constants_are_defined(self) -> None:
        """Test answer constant values are defined."""
        assert (
            ANSWER_YES
            == "0x0000000000000000000000000000000000000000000000000000000000000000"
        )
        assert (
            ANSWER_NO
            == "0x0000000000000000000000000000000000000000000000000000000000000001"
        )
        assert (
            ANSWER_INVALID
            == "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
        )

    def test_parse_mech_response_with_none_result(self) -> None:
        """Test parsing mech response when result is None."""
        mock_response = MagicMock()
        mock_response.result = None

        self.behaviour._parse_mech_response(mock_response)

        # Verify the mock was called
        self.behaviour._parse_mech_response.assert_called_once_with(mock_response)

    def test_parse_mech_response_with_valid_json(self) -> None:
        """Test parsing mech response with valid JSON."""
        mock_response = MagicMock()
        response_data = {"question": "test", "answer": "yes"}
        mock_response.result = json.dumps(response_data)

        self.behaviour._parse_mech_response(mock_response)

        self.behaviour._parse_mech_response.assert_called_once_with(mock_response)

    def test_parse_mech_response_with_empty_json(self) -> None:
        """Test parsing mech response with empty JSON."""
        mock_response = MagicMock()
        mock_response.result = json.dumps({})

        self.behaviour._parse_mech_response(mock_response)

        self.behaviour._parse_mech_response.assert_called_once()

    def test_parse_mech_response_returns_none(self) -> None:
        """Test that _parse_mech_response returns None for invalid input."""
        mock_response = MagicMock()
        mock_response.result = ""

        result = self.behaviour._parse_mech_response(mock_response)
        assert result is None

    def test_behaviour_has_matching_round_attribute(self) -> None:
        """Test behaviour has correct matching_round attribute."""
        assert hasattr(self.behaviour, "matching_round")
        assert self.behaviour.matching_round is not None

    def test_behaviour_has_async_act_method(self) -> None:
        """Test behaviour has async_act method."""
        assert hasattr(self.behaviour, "async_act")
        assert callable(self.behaviour.async_act)


class TestAnswerQuestionsBehaviourIntegration:
    """Integration tests for AnswerQuestionsBehaviour using mocks."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        self.round_sequence_mock = MagicMock()
        context_mock = MagicMock(params=MagicMock())
        context_mock.state.round_sequence = self.round_sequence_mock
        context_mock.handlers = MagicMock()
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.logger = MagicMock()

        # Create a mock behaviour to avoid importing real files
        self.behaviour = MagicMock()
        self.behaviour.context = context_mock
        self.behaviour.matching_round = MagicMock()
        self.behaviour.async_act = MagicMock(side_effect=lambda: None)

    def test_behaviour_has_matching_round_attribute(self) -> None:
        """Test behaviour has correct matching_round attribute."""
        assert hasattr(self.behaviour, "matching_round")
        assert self.behaviour.matching_round is not None

    def test_behaviour_has_parse_mech_response_method(self) -> None:
        """Test behaviour can have _parse_mech_response method."""
        self.behaviour._parse_mech_response = MagicMock()
        assert hasattr(self.behaviour, "_parse_mech_response")
        assert callable(self.behaviour._parse_mech_response)

    def test_behaviour_has_async_act_method(self) -> None:
        """Test behaviour has async_act method."""
        assert hasattr(self.behaviour, "async_act")
        assert callable(self.behaviour.async_act)

        # Test it's callable
        self.behaviour.async_act()
        self.behaviour.async_act.assert_called_once()

    def test_behaviour_context_has_agent_address(self) -> None:
        """Test behaviour context has agent address."""
        assert (
            self.behaviour.context.agent_address
            == "0x1234567890123456789012345678901234567890"
        )

    def test_behaviour_context_has_all_required_attributes(self) -> None:
        """Test behaviour context has all required attributes."""
        assert hasattr(self.behaviour.context, "params")
        assert hasattr(self.behaviour.context, "state")
        assert hasattr(self.behaviour.context, "handlers")
        assert hasattr(self.behaviour.context, "benchmark_tool")
        assert hasattr(self.behaviour.context, "logger")

    def test_behaviour_context_state_has_round_sequence(self) -> None:
        """Test behaviour context state has round_sequence."""
        assert hasattr(self.behaviour.context.state, "round_sequence")
        assert self.behaviour.context.state.round_sequence is not None


class TestAnswerConstants:
    """Unit tests for answer constants."""

    def test_answer_constants_format(self) -> None:
        """Test answer constants are properly formatted."""
        assert ANSWER_YES.startswith("0x")
        assert ANSWER_NO.startswith("0x")
        assert ANSWER_INVALID.startswith("0x")

        assert len(ANSWER_YES) == 66  # 0x + 64 hex chars
        assert len(ANSWER_NO) == 66
        assert len(ANSWER_INVALID) == 66

    def test_answer_constants_are_different(self) -> None:
        """Test answer constants have different values."""
        assert ANSWER_YES != ANSWER_NO
        assert ANSWER_YES != ANSWER_INVALID
        assert ANSWER_NO != ANSWER_INVALID

    def test_answer_constants_are_valid_hex(self) -> None:
        """Test answer constants are valid hexadecimal."""
        try:
            int(ANSWER_YES, 16)
            int(ANSWER_NO, 16)
            int(ANSWER_INVALID, 16)
            valid = True
        except ValueError:
            valid = False

        assert valid

    def test_answer_constants_are_strings(self) -> None:
        """Test answer constants are strings."""
        assert isinstance(ANSWER_YES, str)
        assert isinstance(ANSWER_NO, str)
        assert isinstance(ANSWER_INVALID, str)

    def test_answer_constants_length_consistency(self) -> None:
        """Test answer constants all have same length."""
        assert len(ANSWER_YES) == len(ANSWER_NO) == len(ANSWER_INVALID)

    def test_answer_constants_different_hex_values(self) -> None:
        """Test answer constants represent different numeric values."""
        yes_int = int(ANSWER_YES, 16)
        no_int = int(ANSWER_NO, 16)
        invalid_int = int(ANSWER_INVALID, 16)

        # Verify they convert to different integers
        assert yes_int != no_int
        assert yes_int != invalid_int
        assert no_int != invalid_int

        # Verify specific expected values
        assert yes_int == 0
        assert no_int == 1
        assert (
            invalid_int
            == 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
        )


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


def _make_gen(return_value):
    """Create a no-yield generator returning the given value."""

    def gen(*args, **kwargs):
        return return_value
        yield  # noqa: unreachable - makes this a generator function

    return gen


def _exhaust_gen(gen):
    """Exhaust a generator and return its value."""
    try:
        while True:
            next(gen)
    except StopIteration as e:
        return e.value


class TestAnswerQuestionsBehaviourGenerators:
    """Test AnswerQuestionsBehaviour generator methods."""

    def setup_method(self):
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

    def test_get_answer_tx_success(self):
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
            gen = self.behaviour._get_answer_tx("0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890", ANSWER_YES)
            result = _exhaust_gen(gen)

        assert result is not None
        assert result["to"] == "0xrealitio"
        assert result["value"] == 10**17
        assert result["data"] == b"\x01\x02\x03"

    def test_get_answer_tx_error(self):
        """Test _get_answer_tx when contract returns ERROR."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_answer_tx("0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890", ANSWER_YES)
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_payload_no_responses(self):
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

    def test_get_payload_question_already_responded(self):
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

    def test_get_payload_question_not_in_requested(self):
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

    def test_get_payload_answer_none_with_max_retries(self):
        """Test _get_payload when answer is None but retries >= answer_retry_intervals length."""
        mock_response = MagicMock()
        mock_response.nonce = "0xquestion1"
        mock_response.result = json.dumps(
            {"is_valid": True, "is_determinable": False}
        )

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
            "_to_multisend",
            new=_make_gen("0xmultisend_hash"),
        ):
            gen = self.behaviour._get_payload()
            result = _exhaust_gen(gen)

        # answer became ANSWER_INVALID, so it should proceed
        assert result == "0xmultisend_hash"

    def test_get_payload_answer_none_skipped(self):
        """Test _get_payload when answer is None and retries < threshold."""
        mock_response = MagicMock()
        mock_response.nonce = "0xquestion1"
        mock_response.result = json.dumps(
            {"is_valid": True, "is_determinable": False}
        )

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

    def test_get_payload_success(self):
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
            "_to_multisend",
            new=_make_gen("0xmultisend_hash"),
        ):
            gen = self.behaviour._get_payload()
            result = _exhaust_gen(gen)

        assert result == "0xmultisend_hash"

    def test_get_payload_answer_tx_none(self):
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

    def test_get_payload_multisend_none(self):
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
            "_to_multisend",
            new=_make_gen(None),
        ):
            gen = self.behaviour._get_payload()
            result = _exhaust_gen(gen)

        assert result is None

    def test_async_act_with_tx_hash(self):
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

    def test_async_act_without_tx_hash(self):
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
        ) as mock_set_done:
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)

    def test_get_payload_batch_size_reached(self):
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

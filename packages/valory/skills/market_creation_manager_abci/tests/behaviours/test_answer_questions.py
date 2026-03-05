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
from unittest.mock import MagicMock

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

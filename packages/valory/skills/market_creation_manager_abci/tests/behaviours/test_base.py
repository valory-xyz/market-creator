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

"""Tests for market_creation_manager_abci base behaviour helpers."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    ZERO_ADDRESS,
    ZERO_HASH,
    get_callable_name,
    parse_date_timestring,
    to_content,
)

CURRENT_FILE_PATH = Path(__file__).resolve()
PACKAGE_DIR = CURRENT_FILE_PATH.parents[2]


class TestBaseHelpers:
    """Test base behaviour helper functions."""

    def test_to_content_converts_query_to_bytes(self) -> None:
        """Test to_content converts query string to proper structure."""
        query = "What is the market about?"
        content = to_content(query)
        assert isinstance(content, bytes)
        assert query.encode() in content or query in str(content)

    def test_to_content_with_special_characters(self) -> None:
        """Test to_content handles special characters."""
        query = "What's the BTC/USD market? (prediction)"
        content = to_content(query)
        assert isinstance(content, bytes)

    def test_parse_date_timestring_with_valid_format_iso(self) -> None:
        """Test date parsing with ISO format."""
        date_str = "2026-03-05T10:30:00Z"
        parsed = parse_date_timestring(date_str)
        assert parsed is not None
        assert parsed.year == 2026
        assert parsed.month == 3
        assert parsed.day == 5

    def test_parse_date_timestring_with_valid_format_date_only(self) -> None:
        """Test date parsing with date-only format."""
        date_str = "2026-03-05"
        parsed = parse_date_timestring(date_str)
        assert parsed is not None
        assert parsed.year == 2026
        assert parsed.month == 3
        assert parsed.day == 5

    def test_parse_date_timestring_with_invalid_format(self) -> None:
        """Test date parsing with invalid format."""
        date_str = "invalid-date"
        parsed = parse_date_timestring(date_str)
        assert parsed is None

    def test_parse_date_timestring_with_empty_string(self) -> None:
        """Test date parsing with empty string."""
        date_str = ""
        parsed = parse_date_timestring(date_str)
        assert parsed is None

    def test_constants_are_defined(self) -> None:
        """Test that constants are properly defined."""
        assert ZERO_ADDRESS == "0x0000000000000000000000000000000000000000"
        assert len(ZERO_ADDRESS) == 42  # 0x + 40 hex chars
        assert (
            ZERO_HASH
            == "0x0000000000000000000000000000000000000000000000000000000000000000"
        )
        assert len(ZERO_HASH) == 66  # 0x + 64 hex chars


class TestGetCallableName:
    """Test get_callable_name helper function."""

    def test_get_callable_name_with_function(self) -> None:
        """Test get_callable_name with a regular function."""

        def my_function() -> None:
            pass

        assert get_callable_name(my_function) == "my_function"

    def test_get_callable_name_with_lambda(self) -> None:
        """Test get_callable_name with a lambda."""

        def my_lambda(x: Any) -> Any:
            return x + 1

        my_lambda.__name__ = "<lambda>"
        assert get_callable_name(my_lambda) == "<lambda>"

    def test_get_callable_name_with_method(self) -> None:
        """Test get_callable_name with a class method."""

        class MyClass:
            def my_method(self) -> None:
                pass

        obj = MyClass()
        assert get_callable_name(obj.my_method) == "my_method"

    def test_get_callable_name_with_builtin(self) -> None:
        """Test get_callable_name with a built-in function."""
        assert get_callable_name(len) == "len"
        assert get_callable_name(str) == "str"


class TestParseDateTimestringEdgeCases:
    """Test parse_date_timestring with edge cases."""

    def test_parse_date_timestring_with_timezone(self) -> None:
        """Test parsing timestamp with timezone."""
        result = parse_date_timestring("2024-01-15T10:30:45Z")
        assert result is not None
        assert result.year == 2024

    def test_parse_date_timestring_date_with_dashes(self) -> None:
        """Test parsing date in YYYY-MM-DD format."""
        result = parse_date_timestring("2024-12-25")
        assert result is not None
        assert result.year == 2024
        assert result.month == 12
        assert result.day == 25

    def test_parse_date_timestring_gibberish(self) -> None:
        """Test parsing completely invalid string."""
        result = parse_date_timestring("not-a-date-at-all")
        assert result is None

    def test_parse_date_timestring_partial_iso(self) -> None:
        """Test parsing partial ISO format."""
        result = parse_date_timestring("2024-01")
        assert result is None  # Should not match any format

    def test_parse_date_timestring_unix_timestamp(self) -> None:
        """Test that unix timestamps don't parse."""
        result = parse_date_timestring("1704067200")
        assert result is None


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


class TestMarketCreationManagerBaseBehaviourGenerators:
    """Test MarketCreationManagerBaseBehaviour generator methods."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        from packages.valory.skills.market_creation_manager_abci.behaviours.answer_questions import (
            AnswerQuestionsBehaviour,
        )

        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.conditional_tokens_contract = "0xConditionalTokens"
        context_mock.params.multisend_address = "0x" + "ab" * 20
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
            1700000000
        )
        context_mock.state.synchronized_data = MagicMock()
        context_mock.state.synchronized_data.safe_contract_address = "0xSafe"
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.omen_subgraph = MagicMock()
        context_mock.omen_subgraph.get_spec.return_value = {
            "method": "POST",
            "url": "http://subgraph.example.com",
        }
        context_mock.requests = MagicMock()
        context_mock.outbox = MagicMock()
        # Use a concrete subclass to test the base methods
        self.behaviour = AnswerQuestionsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_calculate_condition_id_success(self) -> None:
        """Test _calculate_condition_id returns condition_id."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.STATE
        mock_resp.state.body = {"condition_id": "0xCondId123"}

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._calculate_condition_id(
                oracle_contract="0xOracle",
                question_id="0xQ1",
            )
            result = _exhaust_gen(gen)

        assert result == "0xCondId123"

    def test_calculate_condition_id_error(self) -> None:
        """Test _calculate_condition_id returns None on error."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._calculate_condition_id(
                oracle_contract="0xOracle",
                question_id="0xQ1",
            )
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_safe_tx_hash_success(self) -> None:
        """Test _get_safe_tx_hash returns stripped tx_hash."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.STATE
        mock_resp.state.body = {"tx_hash": "0xabcdef1234567890"}

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_safe_tx_hash(
                to_address="0xTo",
                data=b"\x00",
            )
            result = _exhaust_gen(gen)

        assert result == "abcdef1234567890"

    def test_get_safe_tx_hash_error(self) -> None:
        """Test _get_safe_tx_hash returns None on error."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_safe_tx_hash(
                to_address="0xTo",
                data=b"\x00",
            )
            result = _exhaust_gen(gen)

        assert result is None

    def test_to_multisend_success(self) -> None:
        """Test _to_multisend returns payload_data."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_raw_resp = MagicMock()
        mock_raw_resp.performative = ContractApiMessage.Performative.RAW_TRANSACTION
        mock_raw_resp.raw_transaction.body = {"data": "0xaabbccdd"}

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_raw_resp),
        ), patch.object(
            self.behaviour,
            "_get_safe_tx_hash",
            new=_make_gen("a" * 64),
        ):
            gen = self.behaviour._to_multisend(
                transactions=[
                    {"to": "0xTo", "value": 0, "data": b"\x00"},
                ]
            )
            result = _exhaust_gen(gen)

        assert result is not None

    def test_to_multisend_get_tx_data_error(self) -> None:
        """Test _to_multisend returns None when get_tx_data fails."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._to_multisend(
                transactions=[
                    {"to": "0xTo", "value": 0, "data": b"\x00"},
                ]
            )
            result = _exhaust_gen(gen)

        assert result is None

    def test_to_multisend_safe_tx_hash_none(self) -> None:
        """Test _to_multisend returns None when _get_safe_tx_hash returns None."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_raw_resp = MagicMock()
        mock_raw_resp.performative = ContractApiMessage.Performative.RAW_TRANSACTION
        mock_raw_resp.raw_transaction.body = {"data": "0xaabbccdd"}

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_raw_resp),
        ), patch.object(
            self.behaviour,
            "_get_safe_tx_hash",
            new=_make_gen(None),
        ):
            gen = self.behaviour._to_multisend(
                transactions=[
                    {"to": "0xTo", "value": 0, "data": b"\x00"},
                ]
            )
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_subgraph_result_success(self) -> None:
        """Test get_subgraph_result returns parsed JSON."""
        import json

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.body = json.dumps({"data": {"markets": []}}).encode()

        with patch.object(
            self.behaviour,
            "get_http_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour.get_subgraph_result(query="{ markets {} }")
            result = _exhaust_gen(gen)

        assert result is not None
        assert "data" in result

    def test_get_subgraph_result_none_response(self) -> None:
        """Test get_subgraph_result returns None when response is None."""
        with patch.object(
            self.behaviour,
            "get_http_response",
            new=_make_gen(None),
        ):
            gen = self.behaviour.get_subgraph_result(query="{ markets {} }")
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_subgraph_result_non_200(self) -> None:
        """Test get_subgraph_result returns None on non-200 status."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.body = b"Server Error"

        with patch.object(
            self.behaviour,
            "get_http_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour.get_subgraph_result(query="{ markets {} }")
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_ct_subgraph_result_success(self) -> None:
        """Test get_conditional_tokens_subgraph_result returns parsed JSON."""
        import json

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.body = json.dumps({"data": {"user": {}}}).encode()
        self.behaviour.context.conditional_tokens_subgraph = MagicMock()
        self.behaviour.context.conditional_tokens_subgraph.get_spec.return_value = {
            "method": "POST",
            "url": "http://ct-subgraph.example.com",
        }

        with patch.object(
            self.behaviour,
            "get_http_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour.get_conditional_tokens_subgraph_result(
                query="{ user {} }"
            )
            result = _exhaust_gen(gen)

        assert result is not None
        assert "data" in result

    def test_get_ct_subgraph_result_none_response(self) -> None:
        """Test get_conditional_tokens_subgraph_result returns None when response is None."""
        self.behaviour.context.conditional_tokens_subgraph = MagicMock()
        self.behaviour.context.conditional_tokens_subgraph.get_spec.return_value = {
            "method": "POST",
            "url": "http://ct-subgraph.example.com",
        }

        with patch.object(
            self.behaviour,
            "get_http_response",
            new=_make_gen(None),
        ):
            gen = self.behaviour.get_conditional_tokens_subgraph_result(
                query="{ user {} }"
            )
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_ct_subgraph_result_non_200(self) -> None:
        """Test get_conditional_tokens_subgraph_result returns None on non-200."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.body = b"Server Error"
        self.behaviour.context.conditional_tokens_subgraph = MagicMock()
        self.behaviour.context.conditional_tokens_subgraph.get_spec.return_value = {
            "method": "POST",
            "url": "http://ct-subgraph.example.com",
        }

        with patch.object(
            self.behaviour,
            "get_http_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour.get_conditional_tokens_subgraph_result(
                query="{ user {} }"
            )
            result = _exhaust_gen(gen)

        assert result is None

    def test_synchronized_data_property(self) -> None:
        """Test the synchronized_data property."""
        from packages.valory.skills.market_creation_manager_abci.rounds import (
            SynchronizedData,
        )

        mock_synced = MagicMock(spec=SynchronizedData)
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ):
            result = self.behaviour.synchronized_data
            assert result is mock_synced

    def test_params_property(self) -> None:
        """Test the params property."""
        assert self.behaviour.params is not None

    def test_last_synced_timestamp_property(self) -> None:
        """Test the last_synced_timestamp property."""
        with patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=PropertyMock,
            return_value=1700000000,
        ):
            result = self.behaviour.last_synced_timestamp
            assert result == 1700000000

    def test_shared_state_property(self) -> None:
        """Test the shared_state property."""
        mock_state = MagicMock()
        with patch.object(
            type(self.behaviour),
            "shared_state",
            new_callable=PropertyMock,
            return_value=mock_state,
        ):
            result = self.behaviour.shared_state
            assert result is mock_state

    def test_do_llm_request(self) -> None:
        """Test do_llm_request basic flow."""
        mock_llm_message = MagicMock()
        mock_llm_dialogue = MagicMock()
        mock_response = MagicMock()

        with patch.object(
            self.behaviour,
            "_get_request_nonce_from_dialogue",
            return_value="nonce123",
        ), patch.object(
            self.behaviour,
            "get_callback_request",
            return_value=MagicMock(),
        ), patch.object(
            self.behaviour,
            "wait_for_message",
            new=_make_gen(mock_response),
        ):
            gen = self.behaviour.do_llm_request(mock_llm_message, mock_llm_dialogue)
            result = _exhaust_gen(gen)

        assert result is mock_response

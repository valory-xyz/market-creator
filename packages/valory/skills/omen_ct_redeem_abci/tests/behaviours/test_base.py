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

"""Tests for CtRedeemBaseBehaviour and base helpers."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from packages.valory.skills.omen_ct_redeem_abci.behaviours.base import (
    get_callable_name,
    to_content,
)
from packages.valory.skills.omen_ct_redeem_abci.behaviours.ct_redeem import (
    CtRedeemBehaviour,
)
from packages.valory.skills.omen_ct_redeem_abci.tests.behaviours.conftest import (
    exhaust_gen,
    make_contract_error_response,
    make_contract_state_response,
    make_gen,
    make_http_response,
    make_raw_tx_response,
)


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_to_content(self) -> None:
        """Test to_content encodes query to JSON bytes."""
        query = "{ users { id } }"
        result = to_content(query)
        parsed = json.loads(result.decode("utf-8"))
        assert parsed == {"query": "{ users { id } }"}

    def test_get_callable_name(self) -> None:
        """Test get_callable_name returns function name."""

        def my_function() -> None:
            """Local helper for the test."""

        assert get_callable_name(my_function) == "my_function"


class TestCtRedeemBaseBehaviour:
    """Tests for CtRedeemBaseBehaviour using a concrete subclass."""

    def setup_method(self) -> None:
        """Set up test fixtures using CtRedeemBehaviour as a concrete subclass."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.multisend_address = "0x" + "A0" * 20
        context_mock.params.conditional_tokens_contract = "0xConditionalTokens"
        context_mock.params.collateral_tokens_contract = "0xCollateral"
        context_mock.params.realitio_oracle_proxy_contract = "0xRealitioProxy"
        context_mock.params.ct_redeem_batch_size = 5
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
            1700100000
        )
        context_mock.state.synchronized_data = MagicMock()
        context_mock.state.synchronized_data.safe_contract_address = "0xSafe"
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0xAgent"
        context_mock.omen_subgraph = MagicMock()
        context_mock.omen_subgraph.get_spec.return_value = {
            "method": "POST",
            "url": "https://omen.example.com",
        }
        context_mock.conditional_tokens_subgraph = MagicMock()
        context_mock.conditional_tokens_subgraph.get_spec.return_value = {
            "method": "POST",
            "url": "https://ct.example.com",
        }
        self.behaviour: Any = CtRedeemBehaviour(name="test", skill_context=context_mock)

    # -- Properties --

    def test_synchronized_data(self) -> None:
        """Test synchronized_data property returns cast SynchronizedData."""
        sd = self.behaviour.synchronized_data
        assert sd is not None

    def test_params(self) -> None:
        """Test params property returns cast CtRedeemParams."""
        p = self.behaviour.params
        assert p is not None

    def test_last_synced_timestamp(self) -> None:
        """Test last_synced_timestamp property returns integer timestamp."""
        ts = self.behaviour.last_synced_timestamp
        assert ts == 1700100000

    def test_shared_state(self) -> None:
        """Test shared_state property returns cast SharedState."""
        ss = self.behaviour.shared_state
        assert ss is not None

    # -- _get_safe_tx_hash --

    def test_get_safe_tx_hash_success(self) -> None:
        """Test _get_safe_tx_hash returns tx_hash on success."""
        resp = make_contract_state_response({"tx_hash": "0xabcdef1234567890"})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._get_safe_tx_hash("0xTo", b"\x01")
            result = exhaust_gen(gen)
        assert result == "abcdef1234567890"

    def test_get_safe_tx_hash_failure(self) -> None:
        """Test _get_safe_tx_hash returns None on error."""
        resp = make_contract_error_response()
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._get_safe_tx_hash("0xTo", b"\x01")
            result = exhaust_gen(gen)
        assert result is None

    # -- _to_multisend --

    def test_to_multisend_success(self) -> None:
        """Test _to_multisend returns payload_data on success."""
        # tx_hash must be 0x + 64 hex chars (32 bytes) for hash_payload_to_hex
        tx_hash_64 = "ab" * 32
        raw_resp = make_raw_tx_response({"data": "0xabcd1234"})
        safe_resp = make_contract_state_response({"tx_hash": "0x" + tx_hash_64})

        call_count = 0

        def mock_contract_gen(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return raw_resp
            return safe_resp
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=mock_contract_gen,
        ):
            gen = self.behaviour._to_multisend([{"to": "0xA", "value": 0}])
            result = exhaust_gen(gen)
        assert result is not None
        assert isinstance(result, str)

    def test_to_multisend_multisend_fails(self) -> None:
        """Test _to_multisend returns None when multisend compilation fails."""
        resp = make_contract_error_response()
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._to_multisend([{"to": "0xA", "value": 0}])
            result = exhaust_gen(gen)
        assert result is None

    def test_to_multisend_safe_hash_fails(self) -> None:
        """Test _to_multisend returns None when safe hash fails."""
        raw_resp = make_raw_tx_response({"data": "0xabcd1234"})
        error_resp = make_contract_error_response()

        call_count = 0

        def mock_contract_gen(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return raw_resp
            return error_resp
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=mock_contract_gen,
        ):
            gen = self.behaviour._to_multisend([{"to": "0xA", "value": 0}])
            result = exhaust_gen(gen)
        assert result is None

    # -- Subgraph result methods (parametrized) --

    @pytest.mark.parametrize(
        "method_name,subgraph_attr",
        [
            ("get_omen_subgraph_result", "omen_subgraph"),
            (
                "get_conditional_tokens_subgraph_result",
                "conditional_tokens_subgraph",
            ),
        ],
    )
    def test_subgraph_result_success(
        self, method_name: str, subgraph_attr: str
    ) -> None:
        """Test subgraph result method returns parsed JSON on 200 OK."""
        body = json.dumps({"data": {"items": []}}).encode()
        resp = make_http_response(200, body)
        with patch.object(
            self.behaviour,
            "get_http_response",
            new=make_gen(resp),
        ):
            gen = getattr(self.behaviour, method_name)("{ q }")
            result = exhaust_gen(gen)
        assert result == {"data": {"items": []}}

    @pytest.mark.parametrize(
        "method_name,subgraph_attr",
        [
            ("get_omen_subgraph_result", "omen_subgraph"),
            (
                "get_conditional_tokens_subgraph_result",
                "conditional_tokens_subgraph",
            ),
        ],
    )
    def test_subgraph_result_none_response(
        self, method_name: str, subgraph_attr: str
    ) -> None:
        """Test subgraph result method returns None when response is None."""
        with patch.object(
            self.behaviour,
            "get_http_response",
            new=make_gen(None),
        ):
            gen = getattr(self.behaviour, method_name)("{ q }")
            result = exhaust_gen(gen)
        assert result is None

    @pytest.mark.parametrize(
        "method_name,subgraph_attr",
        [
            ("get_omen_subgraph_result", "omen_subgraph"),
            (
                "get_conditional_tokens_subgraph_result",
                "conditional_tokens_subgraph",
            ),
        ],
    )
    def test_subgraph_result_non_200(
        self, method_name: str, subgraph_attr: str
    ) -> None:
        """Test subgraph result method returns None on non-200 status."""
        resp = make_http_response(500, b"error")
        with patch.object(
            self.behaviour,
            "get_http_response",
            new=make_gen(resp),
        ):
            gen = getattr(self.behaviour, method_name)("{ q }")
            result = exhaust_gen(gen)
        assert result is None

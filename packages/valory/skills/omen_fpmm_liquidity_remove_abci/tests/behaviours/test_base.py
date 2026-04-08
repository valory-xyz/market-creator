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

"""Tests for FpmmLiquidityRemoveBaseBehaviour utility methods."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

from packages.valory.skills.omen_fpmm_liquidity_remove_abci.behaviours.base import (
    FpmmLiquidityRemoveBaseBehaviour,
    HTTP_OK,
    get_callable_name,
    to_content,
)
from packages.valory.skills.omen_fpmm_liquidity_remove_abci.behaviours.behaviour import (
    FpmmLiquidityRemoveBehaviour,
)
from packages.valory.skills.omen_fpmm_liquidity_remove_abci.tests.behaviours.conftest import (
    exhaust_gen,
    make_contract_error_response,
    make_contract_state_response,
    make_gen,
    make_http_response,
    make_raw_tx_response,
)


def _make_behaviour(context: MagicMock) -> FpmmLiquidityRemoveBehaviour:
    """Instantiate the concrete behaviour with a mocked context."""
    return FpmmLiquidityRemoveBehaviour(name="test", skill_context=context)


class TestModuleLevelHelpers:
    """Tests for module-level helper utilities."""

    def test_to_content_is_json(self) -> None:
        """to_content wraps the query string in a JSON object."""
        result = to_content("{ test }")
        assert json.loads(result) == {"query": "{ test }"}

    def test_get_callable_name(self) -> None:
        """get_callable_name returns the __name__ attribute."""

        def my_func() -> None:
            pass  # pragma: no cover

        assert get_callable_name(my_func) == "my_func"


class TestFpmmLiquidityRemoveBaseBehaviourProperties:
    """Tests for property accessors on FpmmLiquidityRemoveBaseBehaviour."""

    def setup_method(self) -> None:
        """Set up a fresh mock context."""
        ctx = MagicMock()
        ctx.logger = MagicMock()
        ctx.params = MagicMock()
        ctx.params.liquidity_removal_lead_time = 86400
        ctx.params.fpmm_remove_batch_size = 3
        ctx.params.conditional_tokens_contract = "0xCT"
        ctx.params.collateral_tokens_contract = "0xCollateral"
        # 42-char address required by hash_payload_to_hex
        ctx.params.multisend_address = "0x" + "A0" * 20
        ctx.state = MagicMock()
        ctx.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
            1700100000
        )
        ctx.state.synchronized_data.safe_contract_address = "0xSafe"
        ctx.benchmark_tool = MagicMock()
        ctx.agent_address = "0xAgent"
        ctx.omen_subgraph = MagicMock()
        ctx.omen_subgraph.get_spec.return_value = {
            "method": "POST",
            "url": "https://omen.example.com",
        }
        self.ctx = ctx
        self.behaviour: Any = _make_behaviour(ctx)

    def test_last_synced_timestamp(self) -> None:
        """last_synced_timestamp casts the timestamp float to int."""
        assert self.behaviour.last_synced_timestamp == 1700100000

    def test_params_property(self) -> None:
        """params returns ctx.params."""
        assert self.behaviour.params is self.ctx.params

    def test_shared_state_property(self) -> None:
        """shared_state returns ctx.state."""
        assert self.behaviour.shared_state is self.ctx.state


class TestGetOmenSubgraphResult:
    """Tests for get_omen_subgraph_result."""

    def setup_method(self) -> None:
        """Set up behaviour."""
        ctx = MagicMock()
        ctx.logger = MagicMock()
        ctx.params = MagicMock()
        # 42-char address required by hash_payload_to_hex
        ctx.params.multisend_address = "0x" + "A0" * 20
        ctx.params.liquidity_removal_lead_time = 86400
        ctx.params.fpmm_remove_batch_size = 3
        ctx.params.conditional_tokens_contract = "0xCT"
        ctx.params.collateral_tokens_contract = "0xCollateral"
        ctx.state = MagicMock()
        ctx.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
            1700100000
        )
        ctx.state.synchronized_data.safe_contract_address = "0xSafe"
        ctx.benchmark_tool = MagicMock()
        ctx.agent_address = "0xAgent"
        ctx.omen_subgraph = MagicMock()
        ctx.omen_subgraph.get_spec.return_value = {
            "method": "POST",
            "url": "https://omen.example.com",
        }
        self.behaviour: Any = _make_behaviour(ctx)

    def _mock_http(self, response: Any) -> Any:
        """Return a make_gen wrapping the response."""

        def gen(*args: Any, **kwargs: Any) -> Any:
            return response
            yield  # noqa

        return gen

    def test_returns_none_when_response_is_none(self) -> None:
        """Returns None when get_http_response returns None."""
        with patch.object(self.behaviour, "get_http_response", self._mock_http(None)):
            gen = self.behaviour.get_omen_subgraph_result("{ test }")
            result = exhaust_gen(gen)
        assert result is None

    def test_returns_none_on_bad_status_code(self) -> None:
        """Returns None when HTTP status code is not 200."""
        resp = make_http_response(500, b"server error")
        with patch.object(self.behaviour, "get_http_response", self._mock_http(resp)):
            gen = self.behaviour.get_omen_subgraph_result("{ test }")
            result = exhaust_gen(gen)
        assert result is None

    def test_returns_parsed_json_on_success(self) -> None:
        """Returns parsed JSON dict on HTTP 200."""
        body = json.dumps({"data": {"fpmmPoolMemberships": []}}).encode()
        resp = make_http_response(HTTP_OK, body)
        with patch.object(self.behaviour, "get_http_response", self._mock_http(resp)):
            gen = self.behaviour.get_omen_subgraph_result("{ test }")
            result = exhaust_gen(gen)
        assert result == {"data": {"fpmmPoolMemberships": []}}


class TestGetSafeTxHash:
    """Tests for _get_safe_tx_hash."""

    def setup_method(self) -> None:
        """Set up behaviour."""
        ctx = MagicMock()
        ctx.logger = MagicMock()
        ctx.params = MagicMock()
        # 42-char address required by hash_payload_to_hex
        ctx.params.multisend_address = "0x" + "A0" * 20
        ctx.params.liquidity_removal_lead_time = 86400
        ctx.params.fpmm_remove_batch_size = 3
        ctx.params.conditional_tokens_contract = "0xCT"
        ctx.params.collateral_tokens_contract = "0xCollateral"
        ctx.state = MagicMock()
        ctx.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
            1700100000
        )
        ctx.state.synchronized_data.safe_contract_address = "0xSafe"
        ctx.benchmark_tool = MagicMock()
        ctx.agent_address = "0xAgent"
        ctx.omen_subgraph = MagicMock()
        self.behaviour: Any = _make_behaviour(ctx)

    def test_returns_none_on_failure(self) -> None:
        """Returns None when contract call fails."""
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            make_gen(make_contract_error_response()),
        ):
            gen = self.behaviour._get_safe_tx_hash("0xTo", b"data")
            result = exhaust_gen(gen)
        assert result is None

    def test_returns_tx_hash_on_success(self) -> None:
        """Returns tx_hash (stripped 0x prefix) on success."""
        resp = make_contract_state_response({"tx_hash": "0xdeadbeef"})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            make_gen(resp),
        ):
            gen = self.behaviour._get_safe_tx_hash("0xTo", b"data")
            result = exhaust_gen(gen)
        assert result == "deadbeef"


class TestToMultisend:
    """Tests for _to_multisend."""

    def setup_method(self) -> None:
        """Set up behaviour."""
        ctx = MagicMock()
        ctx.logger = MagicMock()
        ctx.params = MagicMock()
        # 42-char address required by hash_payload_to_hex
        ctx.params.multisend_address = "0x" + "A0" * 20
        ctx.params.liquidity_removal_lead_time = 86400
        ctx.params.fpmm_remove_batch_size = 3
        ctx.params.conditional_tokens_contract = "0xCT"
        ctx.params.collateral_tokens_contract = "0xCollateral"
        ctx.state = MagicMock()
        ctx.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
            1700100000
        )
        ctx.state.synchronized_data.safe_contract_address = "0xSafe"
        ctx.benchmark_tool = MagicMock()
        ctx.agent_address = "0xAgent"
        ctx.omen_subgraph = MagicMock()
        self.behaviour: Any = _make_behaviour(ctx)

    def test_returns_none_when_multisend_fails(self) -> None:
        """Returns None when get_tx_data call fails."""
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            make_gen(make_contract_error_response()),
        ):
            txs = [{"to": "0xA", "value": 0, "data": b""}]
            gen = self.behaviour._to_multisend(txs)
            result = exhaust_gen(gen)
        assert result is None

    def test_returns_none_when_safe_hash_fails(self) -> None:
        """Returns None when _get_safe_tx_hash returns None."""
        raw_resp = make_raw_tx_response({"data": "0x" + "ab" * 32})

        with (
            patch.object(
                self.behaviour, "get_contract_api_response", make_gen(raw_resp)
            ),
            patch.object(
                self.behaviour, "_get_safe_tx_hash", lambda *a, **k: (x for x in [None])
            ),
        ):
            txs = [{"to": "0xA", "value": 0, "data": b""}]
            gen = self.behaviour._to_multisend(txs)
            result = exhaust_gen(gen)
        assert result is None

    def test_returns_payload_on_success(self) -> None:
        """Returns payload hash when all steps succeed."""
        raw_resp = make_raw_tx_response({"data": "0x" + "ab" * 32})

        def mock_safe_hash(*a: Any, **k: Any) -> Any:
            return "a" * 64
            yield  # noqa

        with (
            patch.object(
                self.behaviour, "get_contract_api_response", make_gen(raw_resp)
            ),
            patch.object(self.behaviour, "_get_safe_tx_hash", mock_safe_hash),
        ):
            txs = [{"to": "0xA", "value": 0, "data": b""}]
            gen = self.behaviour._to_multisend(txs)
            result = exhaust_gen(gen)
        assert result is not None
        assert isinstance(result, str)

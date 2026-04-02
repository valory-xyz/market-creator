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

"""Tests for ClaimBondsBehaviour."""

import contextlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from packages.valory.skills.omen_funds_recoverer_abci.behaviours.base import ETHER_VALUE
from packages.valory.skills.omen_funds_recoverer_abci.behaviours.claim_bonds import (
    ClaimBondsBehaviour,
    SUBGRAPH_PAGE_SIZE,
    ZERO_BYTES32,
)
from packages.valory.skills.omen_funds_recoverer_abci.tests.behaviours.conftest import (
    exhaust_gen,
    make_contract_error_response,
    make_contract_state_response,
    make_gen,
)


class TestClaimBondsBehaviour:
    """Tests for ClaimBondsBehaviour."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.realitio_contract = "0xRealitio"
        context_mock.params.realitio_start_block = 0
        context_mock.params.claim_bonds_batch_size = 10
        context_mock.params.min_balance_withdraw_realitio = 10000000000000000000
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
            1700100000
        )
        context_mock.state.synchronized_data = MagicMock()
        context_mock.state.synchronized_data.safe_contract_address = "0xSafe"
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.realitio_subgraph = MagicMock()
        context_mock.realitio_subgraph.get_spec.return_value = {
            "method": "POST",
            "url": "https://realitio.example.com",
        }
        self.behaviour: Any = ClaimBondsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_is_unclaimed_true_bytes(self) -> None:
        """Test _is_unclaimed returns True for non-zero bytes hash."""
        non_zero_hash = b"\x01" + b"\x00" * 31
        resp = make_contract_state_response({"data": non_zero_hash})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._is_unclaimed(b"\x00" * 32)
            result = exhaust_gen(gen)
        assert result is True

    def test_is_unclaimed_false_bytes(self) -> None:
        """Test _is_unclaimed returns False for zero bytes hash."""
        resp = make_contract_state_response({"data": ZERO_BYTES32})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._is_unclaimed(b"\x00" * 32)
            result = exhaust_gen(gen)
        assert result is False

    def test_is_unclaimed_true_hex_string(self) -> None:
        """Test _is_unclaimed returns True for non-zero hex string hash."""
        resp = make_contract_state_response({"data": "0x" + "ab" * 32})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._is_unclaimed(b"\x00" * 32)
            result = exhaust_gen(gen)
        assert result is True

    def test_is_unclaimed_false_hex_string(self) -> None:
        """Test _is_unclaimed returns False for zero hex string hash."""
        resp = make_contract_state_response({"data": "0x" + "0" * 64})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._is_unclaimed(b"\x00" * 32)
            result = exhaust_gen(gen)
        assert result is False

    def test_is_unclaimed_error(self) -> None:
        """Test _is_unclaimed returns False on contract error."""
        resp = make_contract_error_response()
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._is_unclaimed(b"\x00" * 32)
            result = exhaust_gen(gen)
        assert result is False

    def test_is_unclaimed_unexpected_type(self) -> None:
        """Test _is_unclaimed returns False for unexpected data type."""
        resp = make_contract_state_response({"data": 12345})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._is_unclaimed(b"\x00" * 32)
            result = exhaust_gen(gen)
        assert result is False

    def test_get_claim_params_success(self) -> None:
        """Test _get_claim_params returns answered data on success."""
        answered = [{"some": "params"}]
        resp = make_contract_state_response({"answered": answered})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._get_claim_params(b"\x01" * 32)
            result = exhaust_gen(gen)
        assert result == answered

    @pytest.mark.parametrize(
        "description,response_body",
        [
            ("contract error", None),
            ("body contains error key", {"error": "something went wrong"}),
            ("empty answers list", {"answered": []}),
            ("answered is None", {"answered": None}),
        ],
    )
    def test_get_claim_params_returns_none(
        self, description: str, response_body: Any
    ) -> None:
        """Test _get_claim_params returns None on various failure modes."""
        if response_body is None:
            resp = make_contract_error_response()
        else:
            resp = make_contract_state_response(response_body)
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._get_claim_params(b"\x01" * 32)
            result = exhaust_gen(gen)
        assert result is None

    def test_simulate_claim_success(self) -> None:
        """Test _simulate_claim returns True when simulation succeeds."""
        resp = make_contract_state_response({"data": True})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._simulate_claim(b"\x01" * 32, [{"p": "v"}])
            result = exhaust_gen(gen)
        assert result is True

    def test_simulate_claim_failure(self) -> None:
        """Test _simulate_claim returns False when simulation fails."""
        resp = make_contract_state_response({"data": False})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._simulate_claim(b"\x01" * 32, [{"p": "v"}])
            result = exhaust_gen(gen)
        assert result is False

    def test_simulate_claim_error(self) -> None:
        """Test _simulate_claim returns False on contract error."""
        resp = make_contract_error_response()
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._simulate_claim(b"\x01" * 32, [{"p": "v"}])
            result = exhaust_gen(gen)
        assert result is False

    def test_build_claim_tx_success(self) -> None:
        """Test _build_claim_tx builds tx dict on success."""
        resp = make_contract_state_response({"data": "0xClaimData"})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._build_claim_tx(b"\x01" * 32, [{"p": "v"}])
            result = exhaust_gen(gen)
        assert result is not None
        assert result["to"] == "0xRealitio"
        assert result["data"] == "0xClaimData"
        assert result["value"] == ETHER_VALUE

    def test_build_claim_tx_with_bytes_data(self) -> None:
        """Test _build_claim_tx when contract returns bytes data."""
        resp = make_contract_state_response({"data": b"\xef\x01"})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._build_claim_tx(b"\x01" * 32, [{"p": "v"}])
            result = exhaust_gen(gen)
        assert result is not None
        assert result["data"] == "ef01"

    def test_build_claim_tx_error(self) -> None:
        """Test _build_claim_tx returns None on error."""
        resp = make_contract_error_response()
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._build_claim_tx(b"\x01" * 32, [{"p": "v"}])
            result = exhaust_gen(gen)
        assert result is None

    def test_maybe_build_withdraw_tx_below_threshold(self) -> None:
        """Test _maybe_build_withdraw_tx returns None when balance below threshold."""
        # balance of 100 wei is below min_balance_withdraw_realitio threshold
        resp = make_contract_state_response({"data": 100})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._maybe_build_withdraw_tx()
            result = exhaust_gen(gen)
        assert result is None

    def test_maybe_build_withdraw_tx_above_threshold(self) -> None:
        """Test _maybe_build_withdraw_tx builds withdraw tx when above threshold."""
        balance_resp = make_contract_state_response({"data": 20000000000000000000})
        withdraw_resp = make_contract_state_response({"data": "0xWithdrawData"})

        call_count = 0

        def mock_contract_gen(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return balance_resp
            return withdraw_resp
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=mock_contract_gen,
        ):
            gen = self.behaviour._maybe_build_withdraw_tx()
            result = exhaust_gen(gen)

        assert result is not None
        assert result["to"] == "0xRealitio"
        assert result["data"] == "0xWithdrawData"

    def test_maybe_build_withdraw_tx_balance_error(self) -> None:
        """Test _maybe_build_withdraw_tx returns None on balance query error."""
        resp = make_contract_error_response()
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._maybe_build_withdraw_tx()
            result = exhaust_gen(gen)
        assert result is None

    def test_maybe_build_withdraw_tx_withdraw_error(self) -> None:
        """Test _maybe_build_withdraw_tx returns None when withdraw tx build fails."""
        balance_resp = make_contract_state_response({"data": 20000000000000000000})
        error_resp = make_contract_error_response()

        call_count = 0

        def mock_contract_gen(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return balance_resp
            return error_resp
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=mock_contract_gen,
        ):
            gen = self.behaviour._maybe_build_withdraw_tx()
            result = exhaust_gen(gen)
        assert result is None

    def test_async_act(self) -> None:
        """Test async_act wraps _build_claim_bonds_txs correctly."""
        self.behaviour.synchronized_data.funds_recovery_txs = []
        with (
            patch.object(
                self.behaviour,
                "_build_claim_bonds_txs",
                new=make_gen([]),
            ),
            patch.object(self.behaviour, "send_a2a_transaction", new=make_gen(None)),
            patch.object(self.behaviour, "wait_until_round_end", new=make_gen(None)),
            patch.object(self.behaviour, "set_done") as mock_set_done,
        ):
            gen = self.behaviour.async_act()
            exhaust_gen(gen)
            mock_set_done.assert_called_once()

    def test_build_claim_bonds_txs_no_responses_no_withdraw(self) -> None:
        """Test _build_claim_bonds_txs with no claimable responses and no withdraw."""
        with (
            patch.object(self.behaviour, "_get_claimable_responses", new=make_gen([])),
            patch.object(
                self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(None)
            ),
        ):
            gen = self.behaviour._build_claim_bonds_txs()
            result = exhaust_gen(gen)
        assert not result

    def test_build_claim_bonds_txs_no_responses_with_withdraw(self) -> None:
        """Test _build_claim_bonds_txs with no claims but a withdraw tx."""
        withdraw_tx = {"to": "0xR", "data": "0xw", "value": 0}
        with (
            patch.object(self.behaviour, "_get_claimable_responses", new=make_gen([])),
            patch.object(
                self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(withdraw_tx)
            ),
        ):
            gen = self.behaviour._build_claim_bonds_txs()
            result = exhaust_gen(gen)
        assert len(result) == 1
        assert result[0] == withdraw_tx

    def test_build_claim_bonds_txs_claim_and_withdraw(self) -> None:
        """Test _build_claim_bonds_txs with one claim and a withdraw tx."""
        responses = [{"question": {"id": "0xabcd"}, "bond": "100"}]
        claim_tx = {"to": "0xR", "data": "0xclaim", "value": 0}
        withdraw_tx = {"to": "0xR", "data": "0xw", "value": 0}

        with (
            patch.object(
                self.behaviour, "_get_claimable_responses", new=make_gen(responses)
            ),
            patch.object(self.behaviour, "_is_unclaimed", new=make_gen(True)),
            patch.object(
                self.behaviour, "_get_claim_params", new=make_gen([{"p": "v"}])
            ),
            patch.object(self.behaviour, "_simulate_claim", new=make_gen(True)),
            patch.object(self.behaviour, "_build_claim_tx", new=make_gen(claim_tx)),
            patch.object(
                self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(withdraw_tx)
            ),
        ):
            gen = self.behaviour._build_claim_bonds_txs()
            result = exhaust_gen(gen)
        assert len(result) == 2
        assert result[0] == claim_tx
        assert result[1] == withdraw_tx

    @pytest.mark.parametrize(
        "description,is_unclaimed,claim_params,simulate_ok,build_tx",
        [
            ("already claimed", False, None, None, None),
            ("claim params fail", True, None, None, None),
            ("simulation fail", True, [{"p": "v"}], False, None),
            ("build claim tx fail", True, [{"p": "v"}], True, None),
        ],
    )
    def test_build_claim_bonds_txs_single_claim_failure(
        self,
        description: str,
        is_unclaimed: bool,
        claim_params: Any,
        simulate_ok: Any,
        build_tx: Any,
    ) -> None:
        """Test _build_claim_bonds_txs skips when a step in the claim chain fails."""
        responses = [{"question": {"id": "0xabcd"}, "bond": "100"}]

        patches = [
            patch.object(
                self.behaviour, "_get_claimable_responses", new=make_gen(responses)
            ),
            patch.object(self.behaviour, "_is_unclaimed", new=make_gen(is_unclaimed)),
            patch.object(
                self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(None)
            ),
        ]
        # Only add patches for steps that are reached
        if is_unclaimed:
            patches.append(
                patch.object(
                    self.behaviour, "_get_claim_params", new=make_gen(claim_params)
                )
            )
        if claim_params is not None:
            patches.append(
                patch.object(
                    self.behaviour, "_simulate_claim", new=make_gen(simulate_ok)
                )
            )
        if simulate_ok:
            patches.append(
                patch.object(self.behaviour, "_build_claim_tx", new=make_gen(build_tx))
            )

        with patches[0]:
            with contextlib.ExitStack() as stack:
                for p in patches[1:]:
                    stack.enter_context(p)
                gen = self.behaviour._build_claim_bonds_txs()
                result = exhaust_gen(gen)
        assert not result

    def test_build_claim_txs_batch_size_limit(self) -> None:
        """Test _build_claim_txs stops after reaching batch_size."""
        self.behaviour.context.params.claim_bonds_batch_size = 1
        responses = [
            {"question": {"id": "0xaaaa"}, "bond": "100"},
            {"question": {"id": "0xbbbb"}, "bond": "200"},
        ]
        claim_tx = {"to": "0xR", "data": "0xclaim", "value": 0}

        with (
            patch.object(
                self.behaviour, "_get_claimable_responses", new=make_gen(responses)
            ),
            patch.object(self.behaviour, "_is_unclaimed", new=make_gen(True)),
            patch.object(
                self.behaviour, "_get_claim_params", new=make_gen([{"p": "v"}])
            ),
            patch.object(self.behaviour, "_simulate_claim", new=make_gen(True)),
            patch.object(self.behaviour, "_build_claim_tx", new=make_gen(claim_tx)),
        ):
            gen = self.behaviour._build_claim_txs()
            result = exhaust_gen(gen)
        # Only 1 tx even though there are 2 responses
        assert len(result) == 1

    def test_get_claimable_responses_empty(self) -> None:
        """Test _get_claimable_responses returns empty list when subgraph returns no data."""
        subgraph_response: dict = {"data": {"responses": []}}
        with patch.object(
            self.behaviour,
            "get_realitio_subgraph_result",
            new=make_gen(subgraph_response),
        ):
            gen = self.behaviour._get_claimable_responses()
            result = exhaust_gen(gen)
        assert result == []

    def test_get_claimable_responses_single_page(self) -> None:
        """Test _get_claimable_responses returns results from a single page."""
        responses_data = [
            {
                "id": "resp1",
                "question": {"id": "0xq1"},
                "bond": "100",
                "answer": "0x01",
            },
        ]
        subgraph_response = {"data": {"responses": responses_data}}
        with patch.object(
            self.behaviour,
            "get_realitio_subgraph_result",
            new=make_gen(subgraph_response),
        ):
            gen = self.behaviour._get_claimable_responses()
            result = exhaust_gen(gen)
        assert len(result) == 1
        assert result[0]["id"] == "resp1"

    def test_get_claimable_responses_pagination(self) -> None:
        """Test _get_claimable_responses paginates through multiple pages."""
        # First page: exactly SUBGRAPH_PAGE_SIZE items to trigger pagination
        page1 = [
            {"id": f"r{i}", "question": {"id": f"0xq{i}"}}
            for i in range(SUBGRAPH_PAGE_SIZE)
        ]
        page2 = [{"id": "final", "question": {"id": "0xfinal"}}]

        call_count = 0

        def mock_subgraph(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"data": {"responses": page1}}
            return {"data": {"responses": page2}}
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_realitio_subgraph_result",
            new=mock_subgraph,
        ):
            gen = self.behaviour._get_claimable_responses()
            result = exhaust_gen(gen)
        assert len(result) == SUBGRAPH_PAGE_SIZE + 1
        assert result[-1]["id"] == "final"

    def test_get_claimable_responses_subgraph_failure(self) -> None:
        """Test _get_claimable_responses returns empty on subgraph failure."""
        with patch.object(
            self.behaviour,
            "get_realitio_subgraph_result",
            new=make_gen(None),
        ):
            gen = self.behaviour._get_claimable_responses()
            result = exhaust_gen(gen)
        assert result == []

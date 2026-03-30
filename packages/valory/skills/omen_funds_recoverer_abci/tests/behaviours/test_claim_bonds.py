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

from typing import Any
from unittest.mock import MagicMock, patch

from packages.valory.skills.omen_funds_recoverer_abci.behaviours.base import ETHER_VALUE
from packages.valory.skills.omen_funds_recoverer_abci.behaviours.claim_bonds import (
    ClaimBondsBehaviour,
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

    def test_get_claim_params_error(self) -> None:
        """Test _get_claim_params returns None on contract error."""
        resp = make_contract_error_response()
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._get_claim_params(b"\x01" * 32)
            result = exhaust_gen(gen)
        assert result is None

    def test_get_claim_params_body_error(self) -> None:
        """Test _get_claim_params returns None when body contains error key."""
        resp = make_contract_state_response({"error": "something went wrong"})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._get_claim_params(b"\x01" * 32)
            result = exhaust_gen(gen)
        assert result is None

    def test_get_claim_params_no_answers(self) -> None:
        """Test _get_claim_params returns None when no answers found."""
        resp = make_contract_state_response({"answered": []})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._get_claim_params(b"\x01" * 32)
            result = exhaust_gen(gen)
        assert result is None

    def test_get_claim_params_answered_none(self) -> None:
        """Test _get_claim_params returns None when answered is None."""
        resp = make_contract_state_response({"answered": None})
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
        """Test async_act wraps _get_recovery_txs correctly."""
        self.behaviour.synchronized_data.funds_recovery_txs = []
        with patch.object(
            self.behaviour,
            "_get_recovery_txs",
            new=make_gen([]),
        ), patch.object(
            self.behaviour, "send_a2a_transaction", new=make_gen(None)
        ), patch.object(
            self.behaviour, "wait_until_round_end", new=make_gen(None)
        ), patch.object(
            self.behaviour, "set_done"
        ) as mock_set_done:
            gen = self.behaviour.async_act()
            exhaust_gen(gen)
            mock_set_done.assert_called_once()

    def test_get_recovery_txs_no_responses_no_withdraw(self) -> None:
        """Test _get_recovery_txs with no claimable responses and no withdraw."""
        with patch.object(
            self.behaviour, "_get_claimable_responses", new=make_gen([])
        ), patch.object(self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(None)):
            gen = self.behaviour._get_recovery_txs()
            result = exhaust_gen(gen)
        assert not result

    def test_get_recovery_txs_no_responses_with_withdraw(self) -> None:
        """Test _get_recovery_txs with no claims but a withdraw tx."""
        withdraw_tx = {"to": "0xR", "data": "0xw", "value": 0}
        with patch.object(
            self.behaviour, "_get_claimable_responses", new=make_gen([])
        ), patch.object(
            self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(withdraw_tx)
        ):
            gen = self.behaviour._get_recovery_txs()
            result = exhaust_gen(gen)
        assert len(result) == 1
        assert result[0] == withdraw_tx

    def test_get_recovery_txs_claim_and_withdraw(self) -> None:
        """Test _get_recovery_txs with one claim and a withdraw tx."""
        responses = [{"question": {"id": "0xabcd"}, "bond": "100"}]
        claim_tx = {"to": "0xR", "data": "0xclaim", "value": 0}
        withdraw_tx = {"to": "0xR", "data": "0xw", "value": 0}

        with patch.object(
            self.behaviour, "_get_claimable_responses", new=make_gen(responses)
        ), patch.object(
            self.behaviour, "_is_unclaimed", new=make_gen(True)
        ), patch.object(
            self.behaviour, "_get_claim_params", new=make_gen([{"p": "v"}])
        ), patch.object(
            self.behaviour, "_simulate_claim", new=make_gen(True)
        ), patch.object(
            self.behaviour, "_build_claim_tx", new=make_gen(claim_tx)
        ), patch.object(
            self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(withdraw_tx)
        ):
            gen = self.behaviour._get_recovery_txs()
            result = exhaust_gen(gen)
        assert len(result) == 2
        assert result[0] == claim_tx
        assert result[1] == withdraw_tx

    def test_get_recovery_txs_already_claimed(self) -> None:
        """Test _get_recovery_txs skips already-claimed questions."""
        responses = [{"question": {"id": "0xabcd"}, "bond": "100"}]

        with patch.object(
            self.behaviour, "_get_claimable_responses", new=make_gen(responses)
        ), patch.object(
            self.behaviour, "_is_unclaimed", new=make_gen(False)
        ), patch.object(
            self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(None)
        ):
            gen = self.behaviour._get_recovery_txs()
            result = exhaust_gen(gen)
        assert not result

    def test_get_recovery_txs_claim_params_fail(self) -> None:
        """Test _get_recovery_txs skips when claim params fail."""
        responses = [{"question": {"id": "0xabcd"}, "bond": "100"}]

        with patch.object(
            self.behaviour, "_get_claimable_responses", new=make_gen(responses)
        ), patch.object(
            self.behaviour, "_is_unclaimed", new=make_gen(True)
        ), patch.object(
            self.behaviour, "_get_claim_params", new=make_gen(None)
        ), patch.object(
            self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(None)
        ):
            gen = self.behaviour._get_recovery_txs()
            result = exhaust_gen(gen)
        assert not result

    def test_get_recovery_txs_simulation_fail(self) -> None:
        """Test _get_recovery_txs skips when simulation fails."""
        responses = [{"question": {"id": "0xabcd"}, "bond": "100"}]

        with patch.object(
            self.behaviour, "_get_claimable_responses", new=make_gen(responses)
        ), patch.object(
            self.behaviour, "_is_unclaimed", new=make_gen(True)
        ), patch.object(
            self.behaviour, "_get_claim_params", new=make_gen([{"p": "v"}])
        ), patch.object(
            self.behaviour, "_simulate_claim", new=make_gen(False)
        ), patch.object(
            self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(None)
        ):
            gen = self.behaviour._get_recovery_txs()
            result = exhaust_gen(gen)
        assert not result

    def test_get_recovery_txs_build_claim_tx_fail(self) -> None:
        """Test _get_recovery_txs skips when build claim tx fails."""
        responses = [{"question": {"id": "0xabcd"}, "bond": "100"}]

        with patch.object(
            self.behaviour, "_get_claimable_responses", new=make_gen(responses)
        ), patch.object(
            self.behaviour, "_is_unclaimed", new=make_gen(True)
        ), patch.object(
            self.behaviour, "_get_claim_params", new=make_gen([{"p": "v"}])
        ), patch.object(
            self.behaviour, "_simulate_claim", new=make_gen(True)
        ), patch.object(
            self.behaviour, "_build_claim_tx", new=make_gen(None)
        ), patch.object(
            self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(None)
        ):
            gen = self.behaviour._get_recovery_txs()
            result = exhaust_gen(gen)
        assert not result

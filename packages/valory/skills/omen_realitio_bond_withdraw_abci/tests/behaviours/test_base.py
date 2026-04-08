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

"""Tests for RealitioBondWithdrawBaseBehaviour and base helpers."""

# pylint: disable=protected-access,attribute-defined-outside-init
# pylint: disable=unused-argument,import-outside-toplevel

import json
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from packages.valory.skills.omen_realitio_bond_withdraw_abci.behaviours.base import (
    ZERO_BYTES32,
    assemble_claim_params,
    get_callable_name,
    to_content,
    wei_to_str,
)
from packages.valory.skills.omen_realitio_bond_withdraw_abci.behaviours.behaviour import (
    RealitioBondWithdrawBehaviour,
)
from packages.valory.skills.omen_realitio_bond_withdraw_abci.tests.behaviours.conftest import (
    exhaust_gen,
    make_contract_error_response,
    make_contract_state_response,
    make_gen,
    make_http_response,
    make_raw_tx_response,
)


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_wei_to_str_default_unit(self) -> None:
        """Test wei_to_str with default unit."""
        result = wei_to_str(1000000000000000000)
        assert result == "1.0000 xDAI"

    def test_wei_to_str_custom_unit(self) -> None:
        """Test wei_to_str with custom unit."""
        result = wei_to_str(500000000000000000, unit="ETH")
        assert result == "0.5000 ETH"

    def test_to_content(self) -> None:
        """Test to_content encodes query to JSON bytes."""
        query = "{ users { id } }"
        result = to_content(query)
        parsed = json.loads(result.decode("utf-8"))
        assert parsed == {"query": "{ users { id } }"}

    def test_get_callable_name(self) -> None:
        """Test get_callable_name returns function name."""

        def my_function() -> None:
            pass

        assert get_callable_name(my_function) == "my_function"


class TestAssembleClaimParams:
    """Tests for the module-level assemble_claim_params helper.

    These exercise the calldata-shape requirement of
    Realitio.claimWinnings: arrays must be in REVERSE chronological
    order (newest first), parallel and equal length, with
    history_hashes[i] holding the stored hash of the previous (older)
    chronological entry, or ZERO_BYTES32 for the very first entry.
    """

    @staticmethod
    def _entry(
        user: str, bond: int, answer: bytes, history_hash: bytes
    ) -> Dict[str, Any]:
        return {
            "args": {
                "user": user,
                "bond": bond,
                "answer": answer,
                "history_hash": history_hash,
            }
        }

    def test_single_entry(self) -> None:
        """A 1-entry history yields a 1-element 4-tuple with ZERO_BYTES32."""
        ans = b"\x01" + b"\x00" * 31
        hh = b"\xaa" * 32
        result = assemble_claim_params([self._entry("0xUserA", 100, ans, hh)])
        history_hashes, addrs, bonds, answers = result
        assert addrs == ["0xUserA"]
        assert bonds == [100]
        assert answers == [ans]
        # Only one entry → its prior hash is the zero-bytes32 sentinel.
        assert history_hashes == [ZERO_BYTES32]

    def test_two_entries_reverse_order_and_hash_chain(self) -> None:
        """Two chronological entries → reversed arrays + correct hash chain."""
        e1 = self._entry("0xUserOld", 100, b"\x00" * 32, b"\xaa" * 32)
        e2 = self._entry("0xUserNew", 200, b"\x01" + b"\x00" * 31, b"\xbb" * 32)
        history_hashes, addrs, bonds, answers = assemble_claim_params([e1, e2])
        # Reverse-chronological: e2 (newest) first, e1 (oldest) last.
        assert addrs == ["0xUserNew", "0xUserOld"]
        assert bonds == [200, 100]
        assert answers == [b"\x01" + b"\x00" * 31, b"\x00" * 32]
        assert history_hashes == [b"\xaa" * 32, ZERO_BYTES32]

    def test_three_entries_reverse_order_and_hash_chain(self) -> None:
        """Three chronological entries → reversed arrays + correct hash chain."""
        e1 = self._entry("0xUser1", 100, b"\x00" * 32, b"\x11" * 32)
        e2 = self._entry("0xUser2", 200, b"\x01" + b"\x00" * 31, b"\x22" * 32)
        e3 = self._entry("0xUser3", 400, b"\x00" * 32, b"\x33" * 32)
        history_hashes, addrs, bonds, answers = assemble_claim_params([e1, e2, e3])
        # Reverse-chronological: newest (e3) at index 0, oldest (e1) at index 2.
        assert addrs == ["0xUser3", "0xUser2", "0xUser1"]
        assert bonds == [400, 200, 100]
        assert answers == [
            b"\x00" * 32,
            b"\x01" + b"\x00" * 31,
            b"\x00" * 32,
        ]
        # history_hashes[i] is the stored hash of the entry one older
        # than entry i (in reverse order), or ZERO_BYTES32 for the
        # oldest entry.
        assert history_hashes == [
            b"\x22" * 32,  # before e3 was posted, the chain ended at e2.history_hash
            b"\x11" * 32,  # before e2 was posted, the chain ended at e1.history_hash
            ZERO_BYTES32,  # before e1 was posted, the chain was empty
        ]

    def test_bond_coerced_to_int(self) -> None:
        """A string bond from JSON deserialization is coerced to int."""
        e = self._entry("0xUser", 0, b"\x00" * 32, b"\x11" * 32)
        e["args"]["bond"] = "1234567890"  # subgraph/JSON path returns strings
        _, _, bonds, _ = assemble_claim_params([e])
        assert bonds == [1234567890]
        assert isinstance(bonds[0], int)


class TestRealitioBondWithdrawBaseBehaviour:
    """Tests for RealitioBondWithdrawBaseBehaviour using a concrete subclass."""

    def setup_method(self) -> None:
        """Set up test fixtures using RealitioBondWithdrawBehaviour as a concrete subclass."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.multisend_address = "0x" + "A0" * 20
        context_mock.params.realitio_contract = "0xRealitio"
        context_mock.params.realitio_bond_withdraw_batch_size = 10
        context_mock.params.min_balance_withdraw_realitio = 10**19
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
            1700100000
        )
        context_mock.state.synchronized_data = MagicMock()
        context_mock.state.synchronized_data.safe_contract_address = "0xSafe"
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0xAgent"
        context_mock.realitio_subgraph = MagicMock()
        context_mock.realitio_subgraph.get_spec.return_value = {
            "method": "POST",
            "url": "https://realitio.example.com",
        }
        self.behaviour: Any = RealitioBondWithdrawBehaviour(
            name="test", skill_context=context_mock
        )

    # -- Properties --

    def test_synchronized_data(self) -> None:
        """Test synchronized_data property returns cast SynchronizedData."""
        sd = self.behaviour.synchronized_data
        assert sd is not None

    def test_params(self) -> None:
        """Test params property returns cast RealitioBondWithdrawParams."""
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

    # -- get_realitio_subgraph_result --

    def test_get_realitio_subgraph_result_success(self) -> None:
        """Test get_realitio_subgraph_result returns parsed JSON on 200 OK."""
        body = json.dumps({"data": {"items": []}}).encode()
        resp = make_http_response(200, body)
        with patch.object(
            self.behaviour,
            "get_http_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour.get_realitio_subgraph_result("{ q }")
            result = exhaust_gen(gen)
        assert result == {"data": {"items": []}}

    def test_get_realitio_subgraph_result_none_response(self) -> None:
        """Test get_realitio_subgraph_result returns None when response is None."""
        with patch.object(
            self.behaviour,
            "get_http_response",
            new=make_gen(None),
        ):
            gen = self.behaviour.get_realitio_subgraph_result("{ q }")
            result = exhaust_gen(gen)
        assert result is None

    def test_get_realitio_subgraph_result_non_200(self) -> None:
        """Test get_realitio_subgraph_result returns None on non-200 status."""
        resp = make_http_response(500, b"error")
        with patch.object(
            self.behaviour,
            "get_http_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour.get_realitio_subgraph_result("{ q }")
            result = exhaust_gen(gen)
        assert result is None

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

"""Tests for BuildMultisendBehaviour."""

from typing import Any
from unittest.mock import MagicMock, patch

from packages.valory.skills.omen_funds_recoverer_abci.behaviours.build_multisend import (
    BuildMultisendBehaviour,
)
from packages.valory.skills.omen_funds_recoverer_abci.tests.behaviours.conftest import (
    exhaust_gen,
    make_gen,
)


class TestBuildMultisendBehaviour:
    """Tests for BuildMultisendBehaviour."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.multisend_address = "0xMultisend"
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.synchronized_data = MagicMock()
        context_mock.state.synchronized_data.safe_contract_address = "0xSafe"
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        self.behaviour: Any = BuildMultisendBehaviour(
            name="test", skill_context=context_mock
        )

    def test_build_multisend_no_txs(self) -> None:
        """Test _build_multisend returns None when funds_recovery_txs is empty."""
        self.behaviour.synchronized_data.funds_recovery_txs = []
        gen = self.behaviour._build_multisend()
        result = exhaust_gen(gen)
        assert result is None

    def test_build_multisend_success_with_hex_data(self) -> None:
        """Test _build_multisend converts hex string data to bytes and calls _to_multisend."""
        self.behaviour.synchronized_data.funds_recovery_txs = [
            {"to": "0xAddr", "data": "abcd", "value": 0},
        ]
        with patch.object(
            self.behaviour, "_to_multisend", new=make_gen("0xMultisendHash")
        ):
            gen = self.behaviour._build_multisend()
            result = exhaust_gen(gen)
        assert result == "0xMultisendHash"

    def test_build_multisend_success_with_0x_prefix(self) -> None:
        """Test _build_multisend strips 0x prefix from hex data."""
        self.behaviour.synchronized_data.funds_recovery_txs = [
            {"to": "0xAddr", "data": "0xabcd", "value": 0},
        ]
        with patch.object(self.behaviour, "_to_multisend", new=make_gen("0xHash123")):
            gen = self.behaviour._build_multisend()
            result = exhaust_gen(gen)
        assert result == "0xHash123"

    def test_build_multisend_success_with_bytes_data(self) -> None:
        """Test _build_multisend leaves bytes data as-is."""
        self.behaviour.synchronized_data.funds_recovery_txs = [
            {"to": "0xAddr", "data": b"\xab\xcd", "value": 0},
        ]
        with patch.object(self.behaviour, "_to_multisend", new=make_gen("0xHash456")):
            gen = self.behaviour._build_multisend()
            result = exhaust_gen(gen)
        assert result == "0xHash456"

    def test_build_multisend_multiple_txs(self) -> None:
        """Test _build_multisend with multiple transactions."""
        self.behaviour.synchronized_data.funds_recovery_txs = [
            {"to": "0xA", "data": "aa", "value": 0},
            {"to": "0xB", "data": "bb", "value": 0},
            {"to": "0xC", "data": "cc", "value": 0},
        ]
        with patch.object(self.behaviour, "_to_multisend", new=make_gen("0xMultiHash")):
            gen = self.behaviour._build_multisend()
            result = exhaust_gen(gen)
        assert result == "0xMultiHash"

    def test_build_multisend_to_multisend_fails(self) -> None:
        """Test _build_multisend returns None when _to_multisend fails."""
        self.behaviour.synchronized_data.funds_recovery_txs = [
            {"to": "0xAddr", "data": "abcd", "value": 0},
        ]
        with patch.object(self.behaviour, "_to_multisend", new=make_gen(None)):
            gen = self.behaviour._build_multisend()
            result = exhaust_gen(gen)
        assert result is None

    def test_async_act_with_tx(self) -> None:
        """Test async_act when there is a multisend hash."""
        with patch.object(
            self.behaviour, "_build_multisend", new=make_gen("0xHash")
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

    def test_async_act_without_tx(self) -> None:
        """Test async_act when there is no multisend hash (no txs)."""
        with patch.object(
            self.behaviour, "_build_multisend", new=make_gen(None)
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

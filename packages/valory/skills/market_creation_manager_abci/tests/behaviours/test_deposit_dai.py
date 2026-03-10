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

"""Tests for DepositDaiBehaviour."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.protocols.ledger_api import LedgerApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.deposit_dai import (
    DepositDaiBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.rounds import DepositDaiRound

CURRENT_FILE_PATH = Path(__file__).resolve()
PACKAGE_DIR = CURRENT_FILE_PATH.parents[2]


def _make_gen(return_value: Any) -> Any:
    """Create a no-yield generator returning the given value."""

    def gen(*args: Any, **kwargs: Any) -> Any:
        return return_value
        yield  # noqa: unreachable

    return gen


def _exhaust_gen(gen: Any) -> Any:
    """Exhaust a generator and return its value."""
    try:
        while True:
            next(gen)
    except StopIteration as e:
        return e.value


class TestDepositDaiBehaviour:
    """Test DepositDaiBehaviour."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.params.xdai_threshold = 10**18  # 1 xDAI
        context_mock.params.collateral_tokens_contract = (
            "0xaaaa567890123456789012345678901234567890"
        )
        self.behaviour = DepositDaiBehaviour(name="test", skill_context=context_mock)

    def test_matching_round(self) -> None:
        """Test matching_round is correctly set."""
        assert self.behaviour.matching_round == DepositDaiRound

    def test_get_balance_success(self) -> None:
        """Test get_balance with successful ledger API response."""
        mock_response = MagicMock()
        mock_response.performative = LedgerApiMessage.Performative.STATE
        mock_response.state.body = {"get_balance_result": 5 * 10**18}

        with patch.object(
            self.behaviour, "get_ledger_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour.get_balance("0xaddr")
            result = _exhaust_gen(gen)

        assert result == 5 * 10**18

    def test_get_balance_error(self) -> None:
        """Test get_balance with wrong performative."""
        mock_response = MagicMock()
        mock_response.performative = LedgerApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour, "get_ledger_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour.get_balance("0xaddr")
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_deposit_tx_success(self) -> None:
        """Test _get_deposit_tx with successful contract API response."""
        mock_response = MagicMock()
        mock_response.performative = ContractApiMessage.Performative.STATE
        mock_response.state.body = {"data": b"\x01\x02\x03"}

        with patch.object(
            self.behaviour, "get_contract_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._get_deposit_tx("0xwxdai")
            result = _exhaust_gen(gen)

        assert result == b"\x01\x02\x03"

    def test_get_deposit_tx_error(self) -> None:
        """Test _get_deposit_tx with wrong performative."""
        mock_response = MagicMock()
        mock_response.performative = ContractApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour, "get_contract_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._get_deposit_tx("0xwxdai")
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_tx_hash_balance_none(self) -> None:
        """Test get_tx_hash when balance is None."""
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xsafe")
            ),
        ), patch.object(self.behaviour, "get_balance", new=_make_gen(None)):
            gen = self.behaviour.get_tx_hash()
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_tx_hash_balance_below_threshold(self) -> None:
        """Test get_tx_hash when balance is below threshold."""
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xsafe")
            ),
        ), patch.object(
            self.behaviour,
            "get_balance",
            new=_make_gen(10**17),  # 0.1 xDAI < 1 xDAI threshold
        ):
            gen = self.behaviour.get_tx_hash()
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_tx_hash_deposit_tx_none(self) -> None:
        """Test get_tx_hash when _get_deposit_tx returns None."""
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xsafe")
            ),
        ), patch.object(
            self.behaviour, "get_balance", new=_make_gen(5 * 10**18)
        ), patch.object(
            self.behaviour, "_get_deposit_tx", new=_make_gen(None)
        ):
            gen = self.behaviour.get_tx_hash()
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_tx_hash_safe_tx_hash_none(self) -> None:
        """Test get_tx_hash when _get_safe_tx_hash returns None."""
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xsafe")
            ),
        ), patch.object(
            self.behaviour, "get_balance", new=_make_gen(5 * 10**18)
        ), patch.object(
            self.behaviour, "_get_deposit_tx", new=_make_gen(b"\x01\x02")
        ), patch.object(
            self.behaviour, "_get_safe_tx_hash", new=_make_gen(None)
        ):
            gen = self.behaviour.get_tx_hash()
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_tx_hash_success(self) -> None:
        """Test get_tx_hash happy path."""
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xsafe")
            ),
        ), patch.object(
            self.behaviour, "get_balance", new=_make_gen(5 * 10**18)
        ), patch.object(
            self.behaviour, "_get_deposit_tx", new=_make_gen(b"\x01\x02")
        ), patch.object(
            self.behaviour, "_get_safe_tx_hash", new=_make_gen("abcdef1234567890")
        ), patch(
            "packages.valory.skills.market_creation_manager_abci.behaviours.deposit_dai.hash_payload_to_hex",
            return_value="0xpayloadhex",
        ):
            gen = self.behaviour.get_tx_hash()
            result = _exhaust_gen(gen)

        assert result == "0xpayloadhex"

    def test_async_act_with_tx_hash(self) -> None:
        """Test async_act when tx_hash is not None."""
        with patch.object(
            self.behaviour, "get_tx_hash", new=_make_gen("0xtxhash")
        ), patch.object(
            self.behaviour, "send_a2a_transaction", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "wait_until_round_end", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "set_done"
        ) as mock_set_done:
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)
            mock_set_done.assert_called_once()

    def test_async_act_without_tx_hash(self) -> None:
        """Test async_act when tx_hash is None."""
        with patch.object(
            self.behaviour, "get_tx_hash", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "send_a2a_transaction", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "wait_until_round_end", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "set_done"
        ) as mock_set_done:
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)
            mock_set_done.assert_called_once()

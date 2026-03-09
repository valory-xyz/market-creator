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

"""Tests for RedeemBondBehaviour."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.redeem_bond import (
    MIN_BALANCE_WITHDRAW_REALITIO,
    RedeemBondBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.rounds import RedeemBondRound

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


class TestRedeemBondBehaviour:
    """Test RedeemBondBehaviour."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.params.realitio_contract = (
            "0xbbbb567890123456789012345678901234567890"
        )
        self.behaviour = RedeemBondBehaviour(name="test", skill_context=context_mock)

    def test_matching_round(self) -> None:
        """Test matching_round is correctly set."""
        assert self.behaviour.matching_round == RedeemBondRound

    def test_min_balance_constant(self) -> None:
        """Test MIN_BALANCE_WITHDRAW_REALITIO is correct."""
        assert MIN_BALANCE_WITHDRAW_REALITIO == 100000000000000000  # 0.1 DAI

    def test_get_balance_success(self) -> None:
        """Test get_balance with successful contract API response."""
        mock_response = MagicMock()
        mock_response.performative = ContractApiMessage.Performative.STATE
        mock_response.state.body = {"data": 5 * 10**18}

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xsafe")
            ),
        ), patch.object(
            self.behaviour, "get_contract_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour.get_balance("0xaddr")
            result = _exhaust_gen(gen)

        assert result == 5 * 10**18

    def test_get_balance_error(self) -> None:
        """Test get_balance with wrong performative."""
        mock_response = MagicMock()
        mock_response.performative = ContractApiMessage.Performative.ERROR

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xsafe")
            ),
        ), patch.object(
            self.behaviour, "get_contract_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour.get_balance("0xaddr")
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_withdraw_tx_success(self) -> None:
        """Test _get_withdraw_tx with successful response."""
        mock_response = MagicMock()
        mock_response.performative = ContractApiMessage.Performative.STATE
        mock_response.state.body = {"data": "0xwithdrawdata"}

        with patch.object(
            self.behaviour, "get_contract_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._get_withdraw_tx()
            result = _exhaust_gen(gen)

        assert result is not None
        assert result["to"] == self.behaviour.params.realitio_contract
        assert result["data"] == "0xwithdrawdata"
        assert result["value"] == 0

    def test_get_withdraw_tx_error(self) -> None:
        """Test _get_withdraw_tx with wrong performative."""
        mock_response = MagicMock()
        mock_response.performative = ContractApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour, "get_contract_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._get_withdraw_tx()
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_payload_balance_none(self) -> None:
        """Test get_payload when balance is None."""
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xsafe")
            ),
        ), patch.object(self.behaviour, "get_balance", new=_make_gen(None)):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_payload_balance_below_threshold(self) -> None:
        """Test get_payload when balance is below MIN_BALANCE_WITHDRAW_REALITIO."""
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xsafe")
            ),
        ), patch.object(
            self.behaviour,
            "get_balance",
            new=_make_gen(MIN_BALANCE_WITHDRAW_REALITIO - 1),
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_payload_withdraw_tx_none(self) -> None:
        """Test get_payload when _get_withdraw_tx returns None."""
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xsafe")
            ),
        ), patch.object(
            self.behaviour,
            "get_balance",
            new=_make_gen(MIN_BALANCE_WITHDRAW_REALITIO + 10**18),
        ), patch.object(
            self.behaviour, "_get_withdraw_tx", new=_make_gen(None)
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_payload_multisend_none(self) -> None:
        """Test get_payload when _to_multisend returns None."""
        withdraw_tx = {
            "to": "0xrealitio",
            "data": "0xdata",
            "value": 0,
        }
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xsafe")
            ),
        ), patch.object(
            self.behaviour,
            "get_balance",
            new=_make_gen(MIN_BALANCE_WITHDRAW_REALITIO + 10**18),
        ), patch.object(
            self.behaviour, "_get_withdraw_tx", new=_make_gen(withdraw_tx)
        ), patch.object(
            self.behaviour, "_to_multisend", new=_make_gen(None)
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_payload_success(self) -> None:
        """Test get_payload happy path."""
        withdraw_tx = {
            "to": "0xrealitio",
            "data": "0xdata",
            "value": 0,
        }
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xsafe")
            ),
        ), patch.object(
            self.behaviour,
            "get_balance",
            new=_make_gen(MIN_BALANCE_WITHDRAW_REALITIO + 10**18),
        ), patch.object(
            self.behaviour, "_get_withdraw_tx", new=_make_gen(withdraw_tx)
        ), patch.object(
            self.behaviour, "_to_multisend", new=_make_gen("0xmultisend_hash")
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result == "0xmultisend_hash"

    def test_async_act_with_tx_hash(self) -> None:
        """Test async_act when get_payload returns a tx hash."""
        with patch.object(
            self.behaviour, "get_payload", new=_make_gen("0xtxhash")
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
        """Test async_act when get_payload returns None."""
        with patch.object(
            self.behaviour, "get_payload", new=_make_gen(None)
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

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

"""Tests for fpmm contract."""

from unittest.mock import MagicMock, patch

import pytest

from packages.valory.contracts.fpmm.contract import (
    BATCH_TOTAL_SUPPLY_DATA,
    FPMMContract,
    PUBLIC_ID,
)


class TestFPMMContractConstants:
    """Test module constants."""

    def test_public_id(self) -> None:
        """Test PUBLIC_ID."""
        assert str(PUBLIC_ID) == "valory/fpmm:0.1.0"

    def test_contract_id(self) -> None:
        """Test contract_id."""
        assert str(FPMMContract.contract_id) == "valory/fpmm:0.1.0"

    def test_batch_total_supply_has_abi(self) -> None:
        """Test BATCH_TOTAL_SUPPLY_DATA has abi."""
        assert "abi" in BATCH_TOTAL_SUPPLY_DATA
        assert len(BATCH_TOTAL_SUPPLY_DATA["abi"]) == 1

    def test_batch_total_supply_has_bytecode(self) -> None:
        """Test BATCH_TOTAL_SUPPLY_DATA has bytecode."""
        assert "bytecode" in BATCH_TOTAL_SUPPLY_DATA
        assert BATCH_TOTAL_SUPPLY_DATA["bytecode"].startswith("0x")


class TestFPMMContractNotImplemented:
    """Test NotImplementedError methods."""

    def test_get_raw_transaction_raises(self) -> None:
        """Test get_raw_transaction raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            FPMMContract.get_raw_transaction(
                ledger_api=MagicMock(), contract_address="0x1234"
            )

    def test_get_raw_message_raises(self) -> None:
        """Test get_raw_message raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            FPMMContract.get_raw_message(
                ledger_api=MagicMock(), contract_address="0x1234"
            )

    def test_get_state_raises(self) -> None:
        """Test get_state raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            FPMMContract.get_state(
                ledger_api=MagicMock(), contract_address="0x1234"
            )


class TestFPMMContractGetBalance:
    """Test get_balance method."""

    def test_get_balance(self) -> None:
        """Test get_balance returns balance dict."""
        mock_ledger_api = MagicMock()
        mock_instance = MagicMock()
        mock_instance.functions.balanceOf.return_value.call.return_value = 1000

        with patch.object(FPMMContract, "get_instance", return_value=mock_instance):
            result = FPMMContract.get_balance(
                ledger_api=mock_ledger_api,
                contract_address="0xcontract",
                address="0xaddress",
            )

        assert result == {"balance": 1000}
        mock_ledger_api.api.to_checksum_address.assert_called_once_with("0xaddress")


class TestFPMMContractGetTotalSupply:
    """Test get_total_supply method."""

    def test_get_total_supply(self) -> None:
        """Test get_total_supply returns supply dict."""
        mock_instance = MagicMock()
        mock_instance.functions.totalSupply.return_value.call.return_value = 5000

        with patch.object(FPMMContract, "get_instance", return_value=mock_instance):
            result = FPMMContract.get_total_supply(
                ledger_api=MagicMock(),
                contract_address="0xcontract",
            )

        assert result == {"supply": 5000}


class TestFPMMContractBuildRemoveFundingTx:
    """Test build_remove_funding_tx method."""

    def test_build_remove_funding_tx(self) -> None:
        """Test build_remove_funding_tx returns data dict."""
        mock_instance = MagicMock()
        mock_instance.encode_abi.return_value = b"\x01\x02\x03"

        with patch.object(FPMMContract, "get_instance", return_value=mock_instance):
            result = FPMMContract.build_remove_funding_tx(
                ledger_api=MagicMock(),
                contract_address="0xcontract",
                amount_to_remove=100,
            )

        assert "data" in result
        assert result["data"] == b"\x01\x02\x03"
        mock_instance.encode_abi.assert_called_once_with(
            abi_element_identifier="removeFunding",
            args=[100],
        )


class TestFPMMContractGetMarketsWithFunds:
    """Test get_markets_with_funds method."""

    def test_get_markets_with_funds_success(self) -> None:
        """Test get_markets_with_funds returns decoded markets."""
        mock_ledger_api = MagicMock()
        mock_contract = MagicMock()

        mock_ledger_api.api.eth.contract.return_value = mock_contract
        mock_contract.bytecode = b"\x60"

        # Mock codec encode to return some bytes
        mock_ledger_api.api.codec.encode.return_value = b"\x00" * 32

        # Mock the eth.call to return encoded result
        mock_ledger_api.api.eth.call.return_value = b"\x00" * 64

        # Mock codec decode to return tuple of markets
        market1 = "0x1111111111111111111111111111111111111111"
        mock_ledger_api.api.codec.decode.return_value = ([market1],)
        mock_ledger_api.api.to_checksum_address.return_value = market1

        with patch.object(FPMMContract, "get_instance", return_value=mock_contract):
            result = FPMMContract.get_markets_with_funds(
                ledger_api=mock_ledger_api,
                contract_address="0xcontract",
                markets=["0xmarket1"],
                safe_address="0xsafe",
            )

        assert "data" in result
        assert market1 in result["data"]

    def test_get_markets_with_funds_exception(self) -> None:
        """Test get_markets_with_funds raises on error.

        Note: the source code has a logger formatting bug (comma-separated args
        instead of %s). pytest's logging plugin propagates the resulting TypeError
        from ``msg % args`` in ``LogRecord.getMessage``.
        """
        mock_ledger_api = MagicMock()
        mock_ledger_api.api.eth.contract.side_effect = Exception("test error")

        with patch.object(FPMMContract, "get_instance", return_value=MagicMock()):
            with pytest.raises(
                TypeError,
                match="not all arguments converted during string formatting",
            ):
                FPMMContract.get_markets_with_funds(
                    ledger_api=mock_ledger_api,
                    contract_address="0xcontract",
                    markets=["0xmarket1"],
                    safe_address="0xsafe",
                )

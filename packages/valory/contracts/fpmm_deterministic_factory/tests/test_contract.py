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

"""Tests for fpmm_deterministic_factory contract."""

from unittest.mock import MagicMock, patch

import pytest

from packages.valory.contracts.fpmm_deterministic_factory.contract import (
    FPMMDeterministicFactory,
    get_logs,
)


class TestGetLogs:
    """Test get_logs helper function."""

    def test_get_logs(self) -> None:
        """Test get_logs calls eth.get_logs with correct filter params."""
        mock_eth = MagicMock()
        mock_eth.get_logs.return_value = []

        mock_contract = MagicMock()
        mock_contract.address = "0xcontract"

        event_abi = {"name": "SomeEvent", "type": "event", "inputs": []}

        with patch(
            "packages.valory.contracts.fpmm_deterministic_factory.contract.event_abi_to_log_topic",
            return_value=b"\x01" * 32,
        ):
            result = get_logs(
                eth=mock_eth,
                contract_instance=mock_contract,
                event_abi=event_abi,
                topics=["some_topic"],
                from_block=100,
                to_block=200,
            )

        assert result == []
        mock_eth.get_logs.assert_called_once()
        call_args = mock_eth.get_logs.call_args[0][0]
        assert call_args["fromBlock"] == 100
        assert call_args["toBlock"] == 200
        assert call_args["address"] == "0xcontract"


class TestFPMMDeterministicFactoryNotImplemented:
    """Test NotImplementedError methods."""

    def test_get_raw_transaction_raises(self) -> None:
        """Test get_raw_transaction raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            FPMMDeterministicFactory.get_raw_transaction(
                ledger_api=MagicMock(), contract_address="0x1234"
            )

    def test_get_raw_message_raises(self) -> None:
        """Test get_raw_message raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            FPMMDeterministicFactory.get_raw_message(
                ledger_api=MagicMock(), contract_address="0x1234"
            )

    def test_get_state_raises(self) -> None:
        """Test get_state raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            FPMMDeterministicFactory.get_state(
                ledger_api=MagicMock(), contract_address="0x1234"
            )


class TestGetCreateFpmmTx:
    """Test get_create_fpmm_tx method."""

    def test_get_create_fpmm_tx(self) -> None:
        """Test get_create_fpmm_tx calls build_transaction."""
        mock_ledger_api = MagicMock()
        mock_instance = MagicMock()
        mock_ledger_api.build_transaction.return_value = {"data": "0x123"}

        with patch.object(
            FPMMDeterministicFactory, "get_instance", return_value=mock_instance
        ):
            _ = FPMMDeterministicFactory.get_create_fpmm_tx(
                ledger_api=mock_ledger_api,
                contract_address="0xfactory",
                condition_id="0xcondition",
                conditional_tokens="0xctokens",
                collateral_token="0xcollateral",  # nosec - placeholder address, not secret
                initial_funds=100.0,
                market_fee=2.0,
            )

        mock_ledger_api.build_transaction.assert_called_once()
        call_kwargs = mock_ledger_api.build_transaction.call_args
        assert call_kwargs.kwargs["method_name"] == "create2FixedProductMarketMaker"

    def test_get_create_fpmm_tx_default_fee(self) -> None:
        """Test get_create_fpmm_tx uses default fee."""
        mock_ledger_api = MagicMock()
        mock_instance = MagicMock()
        mock_ledger_api.build_transaction.return_value = {}

        with patch.object(
            FPMMDeterministicFactory, "get_instance", return_value=mock_instance
        ):
            FPMMDeterministicFactory.get_create_fpmm_tx(
                ledger_api=mock_ledger_api,
                contract_address="0xfactory",
                condition_id="0xcondition",
                conditional_tokens="0xctokens",
                collateral_token="0xcollateral",  # nosec - placeholder address, not secret
                initial_funds=100.0,
            )

        mock_ledger_api.build_transaction.assert_called_once()


class TestGetCreateFpmmTxData:
    """Test get_create_fpmm_tx_data method."""

    def test_get_create_fpmm_tx_data(self) -> None:
        """Test get_create_fpmm_tx_data returns data and value."""
        mock_ledger_api = MagicMock()
        mock_instance = MagicMock()
        mock_instance.encode_abi.return_value = "0xaabbccdd"
        mock_ledger_api.api.to_wei.return_value = 1000000

        with patch.object(
            FPMMDeterministicFactory, "get_instance", return_value=mock_instance
        ):
            result = FPMMDeterministicFactory.get_create_fpmm_tx_data(
                ledger_api=mock_ledger_api,
                contract_address="0xfactory",
                condition_id="0xcondition",
                conditional_tokens="0xctokens",
                collateral_token="0xcollateral",  # nosec - placeholder address, not secret
                initial_funds=100.0,
                market_fee=2.0,
            )

        assert "data" in result
        assert "value" in result
        assert result["data"] == bytes.fromhex("aabbccdd")
        mock_instance.encode_abi.assert_called_once()


class TestGetMarketCreationEvents:
    """Test get_market_creation_events method."""

    def test_get_market_creation_events(self) -> None:
        """Test get_market_creation_events."""
        mock_ledger_api = MagicMock()
        mock_instance = MagicMock()

        # Mock event abi
        mock_event = MagicMock()
        mock_event.abi = {
            "name": "FixedProductMarketMakerCreation",
            "type": "event",
            "inputs": [],
        }
        mock_instance.events.FixedProductMarketMakerCreation.return_value = mock_event

        with patch.object(
            FPMMDeterministicFactory, "get_instance", return_value=mock_instance
        ), patch(
            "packages.valory.contracts.fpmm_deterministic_factory.contract.get_logs",
            return_value=[],
        ):
            result = FPMMDeterministicFactory.get_market_creation_events(
                ledger_api=mock_ledger_api,
                contract_address="0xfactory",
                creator_address="0xABCDef1234567890abcdef1234567890ABCDEF12",
                from_block=100,
                to_block=200,
            )

        assert "data" in result
        assert result["data"] == []


class TestParseMarketCreationEvent:
    """Test parse_market_creation_event method."""

    def test_parse_market_creation_event(self) -> None:
        """Test parse_market_creation_event."""
        mock_ledger_api = MagicMock()
        mock_instance = MagicMock()

        # Mock event log
        mock_event = MagicMock()
        mock_event.blockNumber = 12345
        mock_event.__getitem__ = lambda self, key: {
            "args": {
                "conditionIds": ["0xcondition1"],
                "collateralToken": "0xcollateral",
                "conditionalTokens": "0xctokens",
                "fixedProductMarketMaker": "0xfpmm",
                "fee": 20000,
            }
        }[key]

        mock_process = MagicMock(return_value=[mock_event])
        mock_instance.events.FixedProductMarketMakerCreation.return_value.process_receipt = (
            mock_process
        )

        mock_receipt = MagicMock()
        mock_ledger_api.api.eth.get_transaction_receipt.return_value = mock_receipt

        with patch.object(
            FPMMDeterministicFactory, "get_instance", return_value=mock_instance
        ):
            result = FPMMDeterministicFactory.parse_market_creation_event(
                ledger_api=mock_ledger_api,
                contract_address="0xfactory",
                tx_hash="0xtxhash",
            )

        assert "data" in result
        data = result["data"]
        assert data["tx_hash"] == "0xtxhash"
        assert data["block_number"] == 12345

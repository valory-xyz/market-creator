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

"""Tests for RedeemWinningsBehaviour."""

from typing import Any
from unittest.mock import MagicMock, patch

from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.redeem_winnings import (
    RedeemWinningsBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.states.redeem_winnings import (
    RedeemWinningsRound,
)


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


class TestRedeemWinningsBehaviour:
    """Test RedeemWinningsBehaviour."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.params.conditional_tokens_contract = "0xcondtokens"
        context_mock.params.collateral_tokens_contract = "0xcollateral"
        context_mock.params.redeem_winnings_batch_size = 5
        self.behaviour = RedeemWinningsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_matching_round(self) -> None:
        """Test matching_round is correctly set."""
        assert self.behaviour.matching_round == RedeemWinningsRound

    def test_get_payload_no_markets(self) -> None:
        """Test get_payload when no resolved markets are found."""
        with patch.object(self.behaviour, "_get_resolved_markets", new=_make_gen(None)):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)
        assert result is None

    def test_get_payload_empty_markets(self) -> None:
        """Test get_payload when resolved markets list is empty."""
        with patch.object(self.behaviour, "_get_resolved_markets", new=_make_gen([])):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)
        assert result is None

    def test_get_payload_no_redeemable_positions(self) -> None:
        """Test get_payload when markets exist but none are redeemable."""
        markets = [
            {
                "address": "0xmarket1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
            }
        ]
        with patch.object(
            self.behaviour, "_get_resolved_markets", new=_make_gen(markets)
        ), patch.object(
            self.behaviour, "_build_redeem_txs_for_market", new=_make_gen(None)
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)
        assert result is None

    def test_get_payload_multisend_fails(self) -> None:
        """Test get_payload when _to_multisend returns None."""
        markets = [
            {
                "address": "0xmarket1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
            }
        ]
        redeem_txs = [{"to": "0xcondtokens", "data": "0xdata", "value": 0}]
        with patch.object(
            self.behaviour, "_get_resolved_markets", new=_make_gen(markets)
        ), patch.object(
            self.behaviour, "_build_redeem_txs_for_market", new=_make_gen(redeem_txs)
        ), patch.object(
            self.behaviour, "_to_multisend", new=_make_gen(None)
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)
        assert result is None

    def test_get_payload_success(self) -> None:
        """Test get_payload happy path."""
        markets = [
            {
                "address": "0xmarket1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
            }
        ]
        redeem_txs = [{"to": "0xcondtokens", "data": "0xdata", "value": 0}]
        with patch.object(
            self.behaviour, "_get_resolved_markets", new=_make_gen(markets)
        ), patch.object(
            self.behaviour, "_build_redeem_txs_for_market", new=_make_gen(redeem_txs)
        ), patch.object(
            self.behaviour, "_to_multisend", new=_make_gen("0xmultisend_hash")
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)
        assert result == "0xmultisend_hash"

    def test_get_resolved_markets_subgraph_error(self) -> None:
        """Test _get_resolved_markets when subgraph returns None."""
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xSafe")
            ),
        ), patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=lambda: property(lambda self: 1000000),
        ), patch.object(
            self.behaviour, "get_subgraph_result", new=_make_gen(None)
        ):
            gen = self.behaviour._get_resolved_markets()
            result = _exhaust_gen(gen)
        assert result is None

    def test_get_resolved_markets_success(self) -> None:
        """Test _get_resolved_markets with valid data."""
        subgraph_response = {
            "data": {
                "fixedProductMarketMakers": [
                    {
                        "id": "0xmarket1",
                        "openingTimestamp": "1000000",
                        "conditions": [
                            {
                                "id": "0xcond1",
                                "question": {"id": "0xq1"},
                                "outcomeSlotCount": 2,
                            }
                        ],
                    },
                    {
                        "id": "0xmarket2",
                        "openingTimestamp": "2000000",
                        "conditions": [],
                    },
                    {
                        "id": "0xmarket3",
                        "openingTimestamp": "1500000",
                        "conditions": [
                            {
                                "id": "0xcond3",
                                "question": {"id": "0xq3"},
                                "outcomeSlotCount": None,
                            }
                        ],
                    },
                ]
            }
        }
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xSafe")
            ),
        ), patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=lambda: property(lambda self: 3000000),
        ), patch.object(
            self.behaviour, "get_subgraph_result", new=_make_gen(subgraph_response)
        ):
            gen = self.behaviour._get_resolved_markets()
            result = _exhaust_gen(gen)
        assert result is not None
        assert len(result) == 1
        assert result[0]["address"] == "0xmarket1"

    def test_check_resolved_success(self) -> None:
        """Test _check_resolved with successful response."""
        mock_response = MagicMock()
        mock_response.performative = ContractApiMessage.Performative.STATE
        mock_response.state.body = {"resolved": True}

        with patch.object(
            self.behaviour, "get_contract_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._check_resolved("0xcond1")
            result = _exhaust_gen(gen)
        assert result is True

    def test_check_resolved_not_resolved(self) -> None:
        """Test _check_resolved when condition is not resolved."""
        mock_response = MagicMock()
        mock_response.performative = ContractApiMessage.Performative.STATE
        mock_response.state.body = {"resolved": False}

        with patch.object(
            self.behaviour, "get_contract_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._check_resolved("0xcond1")
            result = _exhaust_gen(gen)
        assert result is False

    def test_check_resolved_error(self) -> None:
        """Test _check_resolved with error response."""
        mock_response = MagicMock()
        mock_response.performative = ContractApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour, "get_contract_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._check_resolved("0xcond1")
            result = _exhaust_gen(gen)
        assert result is None

    def test_check_holdings_has_shares(self) -> None:
        """Test _check_holdings when safe holds conditional tokens."""
        mock_response = MagicMock()
        mock_response.performative = ContractApiMessage.Performative.STATE
        mock_response.state.body = {
            "shares": [100, 200],
            "holdings": [50, 50],
        }

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xsafe")
            ),
        ), patch.object(
            self.behaviour, "get_contract_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._check_holdings("0xmarket1", "0xcond1", 2)
            result = _exhaust_gen(gen)
        assert result is True

    def test_check_holdings_no_shares(self) -> None:
        """Test _check_holdings when safe has no conditional tokens."""
        mock_response = MagicMock()
        mock_response.performative = ContractApiMessage.Performative.STATE
        mock_response.state.body = {
            "shares": [0, 0],
            "holdings": [50, 50],
        }

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xsafe")
            ),
        ), patch.object(
            self.behaviour, "get_contract_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._check_holdings("0xmarket1", "0xcond1", 2)
            result = _exhaust_gen(gen)
        assert result is False

    def test_check_holdings_error(self) -> None:
        """Test _check_holdings with error response."""
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
            gen = self.behaviour._check_holdings("0xmarket1", "0xcond1", 2)
            result = _exhaust_gen(gen)
        assert result is False

    def test_get_redeem_positions_tx_success(self) -> None:
        """Test _get_redeem_positions_tx with successful response."""
        mock_response = MagicMock()
        mock_response.performative = ContractApiMessage.Performative.STATE
        mock_response.state.body = {"data": "0xredeemdata"}

        with patch.object(
            self.behaviour, "get_contract_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._get_redeem_positions_tx("0xcond1", [1, 2])
            result = _exhaust_gen(gen)
        assert result is not None
        assert result["to"] == "0xcondtokens"
        assert result["data"] == "0xredeemdata"
        assert result["value"] == 0

    def test_get_redeem_positions_tx_error(self) -> None:
        """Test _get_redeem_positions_tx with error response."""
        mock_response = MagicMock()
        mock_response.performative = ContractApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour, "get_contract_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._get_redeem_positions_tx("0xcond1", [1, 2])
            result = _exhaust_gen(gen)
        assert result is None

    def test_build_redeem_txs_not_resolved(self) -> None:
        """Test _build_redeem_txs_for_market when condition is not resolved."""
        market = {
            "address": "0xmarket1",
            "condition_id": "0xcond1",
            "outcome_slot_count": 2,
        }
        with patch.object(self.behaviour, "_check_resolved", new=_make_gen(False)):
            gen = self.behaviour._build_redeem_txs_for_market(market)
            result = _exhaust_gen(gen)
        assert result is None

    def test_build_redeem_txs_no_holdings(self) -> None:
        """Test _build_redeem_txs_for_market when no holdings."""
        market = {
            "address": "0xmarket1",
            "condition_id": "0xcond1",
            "outcome_slot_count": 2,
        }
        with patch.object(
            self.behaviour, "_check_resolved", new=_make_gen(True)
        ), patch.object(self.behaviour, "_check_holdings", new=_make_gen(False)):
            gen = self.behaviour._build_redeem_txs_for_market(market)
            result = _exhaust_gen(gen)
        assert result is None

    def test_build_redeem_txs_success(self) -> None:
        """Test _build_redeem_txs_for_market happy path."""
        market = {
            "address": "0xmarket1",
            "condition_id": "0xcond1",
            "outcome_slot_count": 2,
        }
        redeem_tx = {"to": "0xcondtokens", "data": "0xdata", "value": 0}
        with patch.object(
            self.behaviour, "_check_resolved", new=_make_gen(True)
        ), patch.object(
            self.behaviour, "_check_holdings", new=_make_gen(True)
        ), patch.object(
            self.behaviour, "_get_redeem_positions_tx", new=_make_gen(redeem_tx)
        ):
            gen = self.behaviour._build_redeem_txs_for_market(market)
            result = _exhaust_gen(gen)
        assert result is not None
        assert len(result) == 1
        assert result[0] == redeem_tx

    def test_build_redeem_txs_redeem_tx_fails(self) -> None:
        """Test _build_redeem_txs_for_market when redeem tx build fails."""
        market = {
            "address": "0xmarket1",
            "condition_id": "0xcond1",
            "outcome_slot_count": 2,
        }
        with patch.object(
            self.behaviour, "_check_resolved", new=_make_gen(True)
        ), patch.object(
            self.behaviour, "_check_holdings", new=_make_gen(True)
        ), patch.object(
            self.behaviour, "_get_redeem_positions_tx", new=_make_gen(None)
        ):
            gen = self.behaviour._build_redeem_txs_for_market(market)
            result = _exhaust_gen(gen)
        assert result is None

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

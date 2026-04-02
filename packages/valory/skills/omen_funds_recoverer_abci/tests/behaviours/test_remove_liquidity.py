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

"""Tests for RemoveLiquidityBehaviour."""

from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from packages.valory.skills.omen_funds_recoverer_abci.behaviours.base import ETHER_VALUE
from packages.valory.skills.omen_funds_recoverer_abci.behaviours.remove_liquidity import (
    RemoveLiquidityBehaviour,
)
from packages.valory.skills.omen_funds_recoverer_abci.tests.behaviours.conftest import (
    exhaust_gen,
    make_contract_error_response,
    make_contract_state_response,
    make_gen,
)


class TestRemoveLiquidityBehaviour:
    """Tests for RemoveLiquidityBehaviour."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.conditional_tokens_contract = "0xConditionalTokens"
        context_mock.params.collateral_tokens_contract = "0xCollateral"
        context_mock.params.liquidity_removal_lead_time = 86400
        context_mock.params.remove_liquidity_batch_size = 3
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
            1700100000
        )
        context_mock.state.synchronized_data = MagicMock()
        context_mock.state.synchronized_data.safe_contract_address = "0xSafe"
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.omen_subgraph = MagicMock()
        context_mock.omen_subgraph.get_spec.return_value = {
            "method": "POST",
            "url": "https://omen.example.com",
        }
        self.behaviour: Any = RemoveLiquidityBehaviour(
            name="test", skill_context=context_mock
        )

    def test_calculate_amounts_success(self) -> None:
        """Test _calculate_amounts when all 3 contract calls succeed."""
        resp_holdings = make_contract_state_response(
            {"shares": [100, 200], "holdings": [300, 400]}
        )
        resp_balance = make_contract_state_response({"balance": 500})
        resp_supply = make_contract_state_response({"supply": 1000})

        call_count = 0

        def mock_contract_gen(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return resp_holdings
            elif call_count == 2:
                return resp_balance
            return resp_supply
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=mock_contract_gen,
        ):
            gen = self.behaviour._calculate_amounts("0xMarket", "0xCond", 2)
            result = exhaust_gen(gen)

        assert result is not None
        amount_to_remove, amount_to_merge = result
        assert amount_to_remove == 500

    @pytest.mark.parametrize(
        "description,fail_at_call",
        [
            ("holdings fail", 1),
            ("balance fail", 2),
            ("supply fail", 3),
        ],
    )
    def test_calculate_amounts_contract_call_fail(
        self, description: str, fail_at_call: int
    ) -> None:
        """Test _calculate_amounts returns None when a contract call fails."""
        resp_holdings = make_contract_state_response(
            {"shares": [100, 200], "holdings": [300, 400]}
        )
        resp_balance = make_contract_state_response({"balance": 500})
        resp_error = make_contract_error_response()

        responses = {
            1: resp_holdings,
            2: resp_balance,
            3: make_contract_state_response({"supply": 1000}),
        }
        # Replace the failing call with an error
        responses[fail_at_call] = resp_error

        call_count = 0

        def mock_contract_gen(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            return responses[call_count]
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=mock_contract_gen,
        ):
            gen = self.behaviour._calculate_amounts("0xMarket", "0xCond", 2)
            result = exhaust_gen(gen)

        assert result is None

    def test_calculate_amounts_full_removal(self) -> None:
        """Test _calculate_amounts when amount_to_remove == total_pool_shares."""
        resp_holdings = make_contract_state_response(
            {"shares": [10, 20], "holdings": [300, 400]}
        )
        resp_balance = make_contract_state_response({"balance": 1000})
        resp_supply = make_contract_state_response({"supply": 1000})

        call_count = 0

        def mock_contract_gen(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return resp_holdings
            elif call_count == 2:
                return resp_balance
            return resp_supply
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=mock_contract_gen,
        ):
            gen = self.behaviour._calculate_amounts("0xMarket", "0xCond", 2)
            result = exhaust_gen(gen)

        assert result is not None
        amount_to_remove, amount_to_merge = result
        assert amount_to_remove == 1000
        # Full removal: send_amounts = holdings = [300, 400]
        # amount_to_merge = min(300+10, 400+20) = min(310, 420) = 310
        assert amount_to_merge == 310

    def test_calculate_amounts_partial_removal(self) -> None:
        """Test _calculate_amounts when amount_to_remove < total_pool_shares."""
        resp_holdings = make_contract_state_response(
            {"shares": [10, 20], "holdings": [300, 400]}
        )
        resp_balance = make_contract_state_response({"balance": 500})
        resp_supply = make_contract_state_response({"supply": 1000})

        call_count = 0

        def mock_contract_gen(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return resp_holdings
            elif call_count == 2:
                return resp_balance
            return resp_supply
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=mock_contract_gen,
        ):
            gen = self.behaviour._calculate_amounts("0xMarket", "0xCond", 2)
            result = exhaust_gen(gen)

        assert result is not None
        amount_to_remove, amount_to_merge = result
        assert amount_to_remove == 500
        # Partial: send_amounts = [int(300*500/1000), int(400*500/1000)] = [150, 200]
        # amount_to_merge = min(150+10, 200+20) = min(160, 220) = 160
        assert amount_to_merge == 160

    def test_get_remove_funding_tx_success(self) -> None:
        """Test _get_remove_funding_tx with successful contract response."""
        mock_resp = make_contract_state_response({"data": "0xEncodedData"})

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(mock_resp),
        ):
            gen = self.behaviour._get_remove_funding_tx(
                address="0xMarket", amount_to_remove=100
            )
            result = exhaust_gen(gen)

        assert result is not None
        assert result["to"] == "0xMarket"
        assert result["data"] == "0xEncodedData"
        assert result["value"] == ETHER_VALUE

    def test_get_remove_funding_tx_with_bytes_data(self) -> None:
        """Test _get_remove_funding_tx when contract returns bytes data."""
        mock_resp = make_contract_state_response({"data": b"\xab\xcd"})

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(mock_resp),
        ):
            gen = self.behaviour._get_remove_funding_tx(
                address="0xMarket", amount_to_remove=100
            )
            result = exhaust_gen(gen)

        assert result is not None
        assert result["data"] == "abcd"

    def test_get_remove_funding_tx_fail(self) -> None:
        """Test _get_remove_funding_tx with wrong performative."""
        mock_resp = make_contract_error_response()

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(mock_resp),
        ):
            gen = self.behaviour._get_remove_funding_tx(
                address="0xMarket", amount_to_remove=100
            )
            result = exhaust_gen(gen)

        assert result is None

    def test_get_merge_positions_tx_success(self) -> None:
        """Test _get_merge_positions_tx with successful response."""
        mock_resp = make_contract_state_response({"data": "0xMergeData"})

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(mock_resp),
        ):
            gen = self.behaviour._get_merge_positions_tx(
                collateral_token="0xCollateral",  # nosec
                parent_collection_id="0x0",
                condition_id="0xCond",
                outcome_slot_count=2,
                amount=100,
            )
            result = exhaust_gen(gen)

        assert result is not None
        assert result["to"] == "0xConditionalTokens"
        assert result["data"] == "0xMergeData"
        assert result["value"] == ETHER_VALUE

    def test_get_merge_positions_tx_fail(self) -> None:
        """Test _get_merge_positions_tx with wrong performative."""
        mock_resp = make_contract_error_response()

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(mock_resp),
        ):
            gen = self.behaviour._get_merge_positions_tx(
                collateral_token="0xCollateral",  # nosec
                parent_collection_id="0x0",
                condition_id="0xCond",
                outcome_slot_count=2,
                amount=100,
            )
            result = exhaust_gen(gen)

        assert result is None


class TestRemoveLiquidityBehaviourFlow:
    """Tests for RemoveLiquidityBehaviour flow and integration."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.conditional_tokens_contract = "0xConditionalTokens"
        context_mock.params.collateral_tokens_contract = "0xCollateral"
        context_mock.params.liquidity_removal_lead_time = 86400
        context_mock.params.remove_liquidity_batch_size = 3
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
            1700100000
        )
        context_mock.state.synchronized_data = MagicMock()
        context_mock.state.synchronized_data.safe_contract_address = "0xSafe"
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.omen_subgraph = MagicMock()
        context_mock.omen_subgraph.get_spec.return_value = {
            "method": "POST",
            "url": "https://omen.example.com",
        }
        self.behaviour: Any = RemoveLiquidityBehaviour(
            name="test", skill_context=context_mock
        )

    def test_async_act(self) -> None:
        """Test async_act wraps _build_remove_liquidity_txs correctly."""
        self.behaviour.synchronized_data.funds_recovery_txs = []
        with (
            patch.object(
                self.behaviour,
                "_build_remove_liquidity_txs",
                new=make_gen([]),
            ),
            patch.object(self.behaviour, "send_a2a_transaction", new=make_gen(None)),
            patch.object(self.behaviour, "wait_until_round_end", new=make_gen(None)),
            patch.object(self.behaviour, "set_done") as mock_set_done,
        ):
            gen = self.behaviour.async_act()
            exhaust_gen(gen)
            mock_set_done.assert_called_once()

    def test_build_remove_liquidity_txs_no_markets(self) -> None:
        """Test _build_remove_liquidity_txs when _get_markets returns empty list."""
        with patch.object(self.behaviour, "_get_markets", new=make_gen([])):
            gen = self.behaviour._build_remove_liquidity_txs()
            result = exhaust_gen(gen)

        assert not result

    def test_build_remove_liquidity_txs_no_eligible(self) -> None:
        """Test _build_remove_liquidity_txs when no market is eligible (future timestamp)."""
        markets = [
            {
                "address": "0xMarket1",
                "removal_timestamp": 1800000000,
                "condition_id": "0xCond",
                "outcome_slot_count": 2,
            }
        ]
        with (
            patch.object(self.behaviour, "_get_markets", new=make_gen(markets)),
            patch.object(
                type(self.behaviour),
                "last_synced_timestamp",
                new_callable=PropertyMock,
                return_value=1700100000,
            ),
        ):
            gen = self.behaviour._build_remove_liquidity_txs()
            result = exhaust_gen(gen)

        assert not result

    def test_build_remove_liquidity_txs_amounts_none(self) -> None:
        """Test _build_remove_liquidity_txs when _calculate_amounts returns None."""
        markets = [
            {
                "address": "0xMarket1",
                "removal_timestamp": 1700000000,
                "condition_id": "0xCond",
                "outcome_slot_count": 2,
            }
        ]
        with (
            patch.object(self.behaviour, "_get_markets", new=make_gen(markets)),
            patch.object(
                type(self.behaviour),
                "last_synced_timestamp",
                new_callable=PropertyMock,
                return_value=1700100000,
            ),
            patch.object(self.behaviour, "_calculate_amounts", new=make_gen(None)),
        ):
            gen = self.behaviour._build_remove_liquidity_txs()
            result = exhaust_gen(gen)

        assert not result

    def test_build_remove_liquidity_txs_remove_funding_none(self) -> None:
        """Test _build_remove_liquidity_txs when _get_remove_funding_tx returns None."""
        markets = [
            {
                "address": "0xMarket1",
                "removal_timestamp": 1700000000,
                "condition_id": "0xCond",
                "outcome_slot_count": 2,
            }
        ]
        with (
            patch.object(self.behaviour, "_get_markets", new=make_gen(markets)),
            patch.object(
                type(self.behaviour),
                "last_synced_timestamp",
                new_callable=PropertyMock,
                return_value=1700100000,
            ),
            patch.object(
                self.behaviour, "_calculate_amounts", new=make_gen((500, 160))
            ),
            patch.object(self.behaviour, "_get_remove_funding_tx", new=make_gen(None)),
        ):
            gen = self.behaviour._build_remove_liquidity_txs()
            result = exhaust_gen(gen)

        assert not result

    def test_build_remove_liquidity_txs_merge_positions_none(self) -> None:
        """Test _build_remove_liquidity_txs when _get_merge_positions_tx returns None."""
        markets = [
            {
                "address": "0xMarket1",
                "removal_timestamp": 1700000000,
                "condition_id": "0xCond",
                "outcome_slot_count": 2,
            }
        ]
        with (
            patch.object(self.behaviour, "_get_markets", new=make_gen(markets)),
            patch.object(
                type(self.behaviour),
                "last_synced_timestamp",
                new_callable=PropertyMock,
                return_value=1700100000,
            ),
            patch.object(
                self.behaviour, "_calculate_amounts", new=make_gen((500, 160))
            ),
            patch.object(
                self.behaviour,
                "_get_remove_funding_tx",
                new=make_gen({"to": "0xM", "data": "0x01", "value": 0}),
            ),
            patch.object(self.behaviour, "_get_merge_positions_tx", new=make_gen(None)),
        ):
            gen = self.behaviour._build_remove_liquidity_txs()
            result = exhaust_gen(gen)

        assert not result

    def test_build_remove_liquidity_txs_success(self) -> None:
        """Test _build_remove_liquidity_txs happy path with one eligible market."""
        markets = [
            {
                "address": "0xMarket1",
                "removal_timestamp": 1700000000,
                "condition_id": "0xCond",
                "outcome_slot_count": 2,
            }
        ]
        remove_tx = {"to": "0xM", "data": "0x01", "value": 0}
        merge_tx = {"to": "0xCT", "data": "0x02", "value": 0}

        with (
            patch.object(self.behaviour, "_get_markets", new=make_gen(markets)),
            patch.object(
                type(self.behaviour),
                "last_synced_timestamp",
                new_callable=PropertyMock,
                return_value=1700100000,
            ),
            patch.object(
                self.behaviour, "_calculate_amounts", new=make_gen((500, 160))
            ),
            patch.object(
                self.behaviour,
                "_get_remove_funding_tx",
                new=make_gen(remove_tx),
            ),
            patch.object(
                self.behaviour,
                "_get_merge_positions_tx",
                new=make_gen(merge_tx),
            ),
        ):
            gen = self.behaviour._build_remove_liquidity_txs()
            result = exhaust_gen(gen)

        assert len(result) == 2
        assert result[0] == remove_tx
        assert result[1] == merge_tx

    def test_get_markets_with_funds_empty(self) -> None:
        """Test _get_markets_with_funds with no addresses."""
        gen = self.behaviour._get_markets_with_funds([], "0xSafe")
        result = exhaust_gen(gen)
        assert not result

    def test_get_markets_with_funds_error(self) -> None:
        """Test _get_markets_with_funds with contract error."""
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(make_contract_error_response()),
        ):
            gen = self.behaviour._get_markets_with_funds(["0xM1"], "0xSafe")
            result = exhaust_gen(gen)
        assert not result

    def test_get_markets_with_funds_success(self) -> None:
        """Test _get_markets_with_funds with successful response."""
        resp = make_contract_state_response({"data": ["0xM1"]})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._get_markets_with_funds(["0xM1", "0xM2"], "0xSafe")
            result = exhaust_gen(gen)
        assert result == ["0xM1"]


def _make_pool_membership(overrides: dict) -> dict:
    """Build a valid pool membership dict, then apply overrides to the pool."""
    pool = {
        "id": "0xMarket1",
        "openingTimestamp": "1700200000",
        "creator": "0xSafe",
        "liquidityMeasure": "5000",
        "outcomeTokenAmounts": ["2000", "3000"],
        "conditions": [
            {
                "id": "0xC1",
                "outcomeSlotCount": 2,
                "question": {"id": "0xQ1"},
            }
        ],
    }
    pool.update(overrides)
    return {
        "amount": "1000",
        "id": "m1",
        "pool": pool,
    }


class TestGetMarkets:
    """Tests for _get_markets subgraph query and on-chain verification."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.conditional_tokens_contract = "0xConditionalTokens"
        context_mock.params.collateral_tokens_contract = "0xCollateral"
        context_mock.params.liquidity_removal_lead_time = 86400
        context_mock.params.remove_liquidity_batch_size = 3
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
            1700100000
        )
        context_mock.state.synchronized_data = MagicMock()
        context_mock.state.synchronized_data.safe_contract_address = "0xSafe"
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0xAgent"
        context_mock.omen_subgraph = MagicMock()
        context_mock.omen_subgraph.get_spec.return_value = {
            "method": "POST",
            "url": "https://omen.example.com",
        }
        self.behaviour: Any = RemoveLiquidityBehaviour(
            name="test", skill_context=context_mock
        )

    def test_get_markets_subgraph_failure(self) -> None:
        """Test _get_markets returns empty on subgraph failure."""
        with patch.object(
            self.behaviour,
            "get_subgraph_result",
            new=make_gen(None),
        ):
            gen = self.behaviour._get_markets()
            result = exhaust_gen(gen)
        assert result == []

    def test_get_markets_no_memberships(self) -> None:
        """Test _get_markets returns empty when no pool memberships found."""
        response: dict = {"data": {"fpmmPoolMemberships": []}}
        with patch.object(
            self.behaviour,
            "get_subgraph_result",
            new=make_gen(response),
        ):
            gen = self.behaviour._get_markets()
            result = exhaust_gen(gen)
        assert result == []

    def test_get_markets_success(self) -> None:
        """Test _get_markets returns markets with valid data and on-chain funds."""
        response = {
            "data": {
                "fpmmPoolMemberships": [
                    {
                        "amount": "1000",
                        "id": "membership1",
                        "pool": {
                            "id": "0xMarket1",
                            "openingTimestamp": "1700200000",
                            "creator": "0xSafe",
                            "liquidityMeasure": "5000",
                            "outcomeTokenAmounts": ["2000", "3000"],
                            "conditions": [
                                {
                                    "id": "0xCond1",
                                    "outcomeSlotCount": 2,
                                    "question": {"id": "0xQ1"},
                                }
                            ],
                        },
                    }
                ]
            }
        }
        funds_resp = make_contract_state_response({"data": ["0xMarket1"]})

        with (
            patch.object(
                self.behaviour,
                "get_subgraph_result",
                new=make_gen(response),
            ),
            patch.object(
                self.behaviour,
                "get_contract_api_response",
                new=make_gen(funds_resp),
            ),
        ):
            gen = self.behaviour._get_markets()
            result = exhaust_gen(gen)
        assert len(result) == 1
        assert result[0]["address"] == "0xMarket1"
        assert result[0]["condition_id"] == "0xCond1"

    @pytest.mark.parametrize(
        "description,pool_overrides",
        [
            ("zero liquidity", {"liquidityMeasure": "0"}),
            ("None liquidity", {"liquidityMeasure": None}),
            ("None openingTimestamp", {"openingTimestamp": None}),
            (
                "None question",
                {
                    "conditions": [
                        {
                            "id": "0xC1",
                            "outcomeSlotCount": 2,
                            "question": None,
                        }
                    ]
                },
            ),
        ],
    )
    def test_get_markets_filtered(self, description: str, pool_overrides: dict) -> None:
        """Test _get_markets filters out markets with invalid pool data."""
        membership = _make_pool_membership(pool_overrides)
        response = {"data": {"fpmmPoolMemberships": [membership]}}
        with patch.object(
            self.behaviour,
            "get_subgraph_result",
            new=make_gen(response),
        ):
            gen = self.behaviour._get_markets()
            result = exhaust_gen(gen)
        assert result == []

    def test_get_markets_no_on_chain_funds(self) -> None:
        """Test _get_markets filters markets that have no on-chain funds."""
        response = {
            "data": {
                "fpmmPoolMemberships": [
                    {
                        "amount": "1000",
                        "id": "m1",
                        "pool": {
                            "id": "0xMarket1",
                            "openingTimestamp": "1700200000",
                            "creator": "0xSafe",
                            "liquidityMeasure": "5000",
                            "outcomeTokenAmounts": ["2000", "3000"],
                            "conditions": [
                                {
                                    "id": "0xC1",
                                    "outcomeSlotCount": 2,
                                    "question": {"id": "0xQ1"},
                                }
                            ],
                        },
                    }
                ]
            }
        }
        # On-chain verification returns empty list -- market has no funds
        funds_resp = make_contract_state_response({"data": []})

        with (
            patch.object(
                self.behaviour,
                "get_subgraph_result",
                new=make_gen(response),
            ),
            patch.object(
                self.behaviour,
                "get_contract_api_response",
                new=make_gen(funds_resp),
            ),
        ):
            gen = self.behaviour._get_markets()
            result = exhaust_gen(gen)
        assert result == []

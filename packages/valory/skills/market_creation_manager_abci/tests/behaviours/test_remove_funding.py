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

"""Tests for RemoveFundingBehaviour."""

from unittest.mock import MagicMock, PropertyMock, patch

from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    ETHER_VALUE,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.remove_funding import (
    RemoveFundingBehaviour,
)


def _make_gen(return_value):
    """Create a no-yield generator returning the given value."""

    def gen(*args, **kwargs):
        return return_value
        yield  # noqa: unreachable - makes this a generator function

    return gen


def _exhaust_gen(gen):
    """Exhaust a generator and return its value."""
    try:
        while True:
            next(gen)
    except StopIteration as e:
        return e.value


def _make_contract_state_response(body_data):
    """Create a mock contract API STATE response."""
    mock_resp = MagicMock()
    mock_resp.performative = ContractApiMessage.Performative.STATE
    mock_resp.state.body = body_data
    return mock_resp


def _make_contract_error_response():
    """Create a mock contract API ERROR response."""
    mock_resp = MagicMock()
    mock_resp.performative = ContractApiMessage.Performative.ERROR
    return mock_resp


class TestRemoveFundingBehaviour:
    """Tests for RemoveFundingBehaviour."""

    def setup_method(self):
        """Set up test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.conditional_tokens_contract = "0xConditionalTokens"
        context_mock.params.collateral_tokens_contract = "0xCollateral"
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
            1700100000
        )
        context_mock.state.synchronized_data = MagicMock()
        context_mock.state.synchronized_data.safe_contract_address = "0xSafe"
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        self.behaviour = RemoveFundingBehaviour(name="test", skill_context=context_mock)

    def test_get_market_to_close_found(self):
        """Test _get_market_to_close when a market with old removal_timestamp exists."""
        markets = [
            {
                "address": "0xMarket1",
                "removal_timestamp": 1700000000,
                "condition_id": "0xCond",
                "outcome_slot_count": 2,
            }
        ]
        self.behaviour.synchronized_data.markets_to_remove_liquidity = markets

        with patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=PropertyMock,
            return_value=1700100000,
        ):
            result = self.behaviour._get_market_to_close()

        assert result is not None
        assert result["address"] == "0xMarket1"

    def test_get_market_to_close_none(self):
        """Test _get_market_to_close when no market has old enough timestamp."""
        markets = [
            {
                "address": "0xMarket1",
                "removal_timestamp": 1800000000,
                "condition_id": "0xCond",
                "outcome_slot_count": 2,
            }
        ]
        self.behaviour.synchronized_data.markets_to_remove_liquidity = markets

        with patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=PropertyMock,
            return_value=1700100000,
        ):
            result = self.behaviour._get_market_to_close()

        assert result is None

    def test_calculate_amounts_success(self):
        """Test _calculate_amounts when all 3 contract calls succeed."""
        resp_holdings = _make_contract_state_response(
            {"shares": [100, 200], "holdings": [300, 400]}
        )
        resp_balance = _make_contract_state_response({"balance": 500})
        resp_supply = _make_contract_state_response({"supply": 1000})

        call_count = 0

        def mock_contract_gen(*args, **kwargs):
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
            result = _exhaust_gen(gen)

        assert result is not None
        amount_to_remove, amount_to_merge = result
        assert amount_to_remove == 500

    def test_calculate_amounts_holdings_fail(self):
        """Test _calculate_amounts when first contract call (holdings) fails."""
        resp_error = _make_contract_error_response()

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(resp_error),
        ):
            gen = self.behaviour._calculate_amounts("0xMarket", "0xCond", 2)
            result = _exhaust_gen(gen)

        assert result is None

    def test_calculate_amounts_balance_fail(self):
        """Test _calculate_amounts when second contract call (balance) fails."""
        resp_holdings = _make_contract_state_response(
            {"shares": [100, 200], "holdings": [300, 400]}
        )
        resp_error = _make_contract_error_response()

        call_count = 0

        def mock_contract_gen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return resp_holdings
            return resp_error
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=mock_contract_gen,
        ):
            gen = self.behaviour._calculate_amounts("0xMarket", "0xCond", 2)
            result = _exhaust_gen(gen)

        assert result is None

    def test_calculate_amounts_supply_fail(self):
        """Test _calculate_amounts when third contract call (supply) fails."""
        resp_holdings = _make_contract_state_response(
            {"shares": [100, 200], "holdings": [300, 400]}
        )
        resp_balance = _make_contract_state_response({"balance": 500})
        resp_error = _make_contract_error_response()

        call_count = 0

        def mock_contract_gen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return resp_holdings
            elif call_count == 2:
                return resp_balance
            return resp_error
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=mock_contract_gen,
        ):
            gen = self.behaviour._calculate_amounts("0xMarket", "0xCond", 2)
            result = _exhaust_gen(gen)

        assert result is None

    def test_calculate_amounts_full_removal(self):
        """Test _calculate_amounts when amount_to_remove == total_pool_shares."""
        resp_holdings = _make_contract_state_response(
            {"shares": [10, 20], "holdings": [300, 400]}
        )
        resp_balance = _make_contract_state_response({"balance": 1000})
        resp_supply = _make_contract_state_response({"supply": 1000})

        call_count = 0

        def mock_contract_gen(*args, **kwargs):
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
            result = _exhaust_gen(gen)

        assert result is not None
        amount_to_remove, amount_to_merge = result
        assert amount_to_remove == 1000
        # Full removal: send_amounts = holdings = [300, 400]
        # amount_to_merge = min(300+10, 400+20) = min(310, 420) = 310
        assert amount_to_merge == 310

    def test_calculate_amounts_partial_removal(self):
        """Test _calculate_amounts when amount_to_remove < total_pool_shares."""
        resp_holdings = _make_contract_state_response(
            {"shares": [10, 20], "holdings": [300, 400]}
        )
        resp_balance = _make_contract_state_response({"balance": 500})
        resp_supply = _make_contract_state_response({"supply": 1000})

        call_count = 0

        def mock_contract_gen(*args, **kwargs):
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
            result = _exhaust_gen(gen)

        assert result is not None
        amount_to_remove, amount_to_merge = result
        assert amount_to_remove == 500
        # Partial: send_amounts = [int(300*500/1000), int(400*500/1000)] = [150, 200]
        # amount_to_merge = min(150+10, 200+20) = min(160, 220) = 160
        assert amount_to_merge == 160

    def test_get_remove_funding_tx_success(self):
        """Test _get_remove_funding_tx with successful contract response."""
        mock_resp = _make_contract_state_response({"data": "0xEncodedData"})

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_remove_funding_tx(
                address="0xMarket", amount_to_remove=100
            )
            result = _exhaust_gen(gen)

        assert result is not None
        assert result["to"] == "0xMarket"
        assert result["data"] == "0xEncodedData"
        assert result["value"] == ETHER_VALUE

    def test_get_remove_funding_tx_fail(self):
        """Test _get_remove_funding_tx with wrong performative."""
        mock_resp = _make_contract_error_response()

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_remove_funding_tx(
                address="0xMarket", amount_to_remove=100
            )
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_merge_positions_tx_success(self):
        """Test _get_merge_positions_tx with successful response."""
        mock_resp = _make_contract_state_response({"data": "0xMergeData"})

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_merge_positions_tx(
                collateral_token="0xCollateral",
                parent_collection_id="0x0",
                condition_id="0xCond",
                outcome_slot_count=2,
                amount=100,
            )
            result = _exhaust_gen(gen)

        assert result is not None
        assert result["to"] == "0xConditionalTokens"
        assert result["data"] == "0xMergeData"
        assert result["value"] == ETHER_VALUE

    def test_get_merge_positions_tx_fail(self):
        """Test _get_merge_positions_tx with wrong performative."""
        mock_resp = _make_contract_error_response()

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_merge_positions_tx(
                collateral_token="0xCollateral",
                parent_collection_id="0x0",
                condition_id="0xCond",
                outcome_slot_count=2,
                amount=100,
            )
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_withdraw_tx_success(self):
        """Test _get_withdraw_tx with successful response."""
        mock_resp = _make_contract_state_response({"data": "0xWithdrawData"})

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_withdraw_tx(amount=100)
            result = _exhaust_gen(gen)

        assert result is not None
        assert result["to"] == "0xCollateral"
        assert result["data"] == "0xWithdrawData"
        assert result["value"] == ETHER_VALUE

    def test_get_withdraw_tx_fail(self):
        """Test _get_withdraw_tx with wrong performative."""
        mock_resp = _make_contract_error_response()

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_withdraw_tx(amount=100)
            result = _exhaust_gen(gen)

        assert result is None

    def test_async_act(self):
        """Test async_act wraps get_payload correctly."""
        from packages.valory.skills.market_creation_manager_abci.states.remove_funding import (
            RemoveFundingRound,
        )

        with patch.object(
            self.behaviour,
            "get_payload",
            new=_make_gen(RemoveFundingRound.NO_UPDATE_PAYLOAD),
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

    def test_get_payload_no_market(self):
        """Test get_payload when _get_market_to_close returns None."""
        from packages.valory.skills.market_creation_manager_abci.states.remove_funding import (
            RemoveFundingRound,
        )

        with patch.object(self.behaviour, "_get_market_to_close", return_value=None):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result == RemoveFundingRound.NO_UPDATE_PAYLOAD

    def test_get_payload_amounts_none(self):
        """Test get_payload when _calculate_amounts returns None."""
        from packages.valory.skills.market_creation_manager_abci.states.remove_funding import (
            RemoveFundingRound,
        )

        market = {
            "address": "0xMarket1",
            "condition_id": "0xCond",
            "outcome_slot_count": 2,
        }
        with patch.object(
            self.behaviour, "_get_market_to_close", return_value=market
        ), patch.object(self.behaviour, "_calculate_amounts", new=_make_gen(None)):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result == RemoveFundingRound.NO_UPDATE_PAYLOAD

    def test_get_payload_remove_funding_tx_none(self):
        """Test get_payload when _get_remove_funding_tx returns None."""
        from packages.valory.skills.market_creation_manager_abci.states.remove_funding import (
            RemoveFundingRound,
        )

        market = {
            "address": "0xMarket1",
            "condition_id": "0xCond",
            "outcome_slot_count": 2,
        }
        with patch.object(
            self.behaviour, "_get_market_to_close", return_value=market
        ), patch.object(
            self.behaviour, "_calculate_amounts", new=_make_gen((500, 160))
        ), patch.object(
            self.behaviour, "_get_remove_funding_tx", new=_make_gen(None)
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result == RemoveFundingRound.ERROR_PAYLOAD

    def test_get_payload_merge_positions_none(self):
        """Test get_payload when _get_merge_positions_tx returns None."""
        from packages.valory.skills.market_creation_manager_abci.states.remove_funding import (
            RemoveFundingRound,
        )

        market = {
            "address": "0xMarket1",
            "condition_id": "0xCond",
            "outcome_slot_count": 2,
        }
        with patch.object(
            self.behaviour, "_get_market_to_close", return_value=market
        ), patch.object(
            self.behaviour, "_calculate_amounts", new=_make_gen((500, 160))
        ), patch.object(
            self.behaviour,
            "_get_remove_funding_tx",
            new=_make_gen({"to": "0xM", "data": b"\x01", "value": 0}),
        ), patch.object(
            self.behaviour, "_get_merge_positions_tx", new=_make_gen(None)
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result == RemoveFundingRound.ERROR_PAYLOAD

    def test_get_payload_withdraw_tx_none(self):
        """Test get_payload when _get_withdraw_tx returns None."""
        from packages.valory.skills.market_creation_manager_abci.states.remove_funding import (
            RemoveFundingRound,
        )

        market = {
            "address": "0xMarket1",
            "condition_id": "0xCond",
            "outcome_slot_count": 2,
        }
        with patch.object(
            self.behaviour, "_get_market_to_close", return_value=market
        ), patch.object(
            self.behaviour, "_calculate_amounts", new=_make_gen((500, 160))
        ), patch.object(
            self.behaviour,
            "_get_remove_funding_tx",
            new=_make_gen({"to": "0xM", "data": b"\x01", "value": 0}),
        ), patch.object(
            self.behaviour,
            "_get_merge_positions_tx",
            new=_make_gen({"to": "0xCT", "data": b"\x02", "value": 0}),
        ), patch.object(
            self.behaviour, "_get_withdraw_tx", new=_make_gen(None)
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result == RemoveFundingRound.ERROR_PAYLOAD

    def test_get_payload_multisend_none(self):
        """Test get_payload when _to_multisend returns None."""
        from packages.valory.skills.market_creation_manager_abci.states.remove_funding import (
            RemoveFundingRound,
        )

        market = {
            "address": "0xMarket1",
            "condition_id": "0xCond",
            "outcome_slot_count": 2,
        }
        with patch.object(
            self.behaviour, "_get_market_to_close", return_value=market
        ), patch.object(
            self.behaviour, "_calculate_amounts", new=_make_gen((500, 160))
        ), patch.object(
            self.behaviour,
            "_get_remove_funding_tx",
            new=_make_gen({"to": "0xM", "data": b"\x01", "value": 0}),
        ), patch.object(
            self.behaviour,
            "_get_merge_positions_tx",
            new=_make_gen({"to": "0xCT", "data": b"\x02", "value": 0}),
        ), patch.object(
            self.behaviour,
            "_get_withdraw_tx",
            new=_make_gen({"to": "0xC", "data": b"\x03", "value": 0}),
        ), patch.object(
            self.behaviour, "_to_multisend", new=_make_gen(None)
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result == RemoveFundingRound.ERROR_PAYLOAD

    def test_get_payload_success(self):
        """Test get_payload happy path returning JSON with tx and market."""
        import json

        market = {
            "address": "0xMarket1",
            "condition_id": "0xCond",
            "outcome_slot_count": 2,
        }
        with patch.object(
            self.behaviour, "_get_market_to_close", return_value=market
        ), patch.object(
            self.behaviour, "_calculate_amounts", new=_make_gen((500, 160))
        ), patch.object(
            self.behaviour,
            "_get_remove_funding_tx",
            new=_make_gen({"to": "0xM", "data": b"\x01", "value": 0}),
        ), patch.object(
            self.behaviour,
            "_get_merge_positions_tx",
            new=_make_gen({"to": "0xCT", "data": b"\x02", "value": 0}),
        ), patch.object(
            self.behaviour,
            "_get_withdraw_tx",
            new=_make_gen({"to": "0xC", "data": b"\x03", "value": 0}),
        ), patch.object(
            self.behaviour, "_to_multisend", new=_make_gen("0xMultisendHash")
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        parsed = json.loads(result)
        assert parsed["tx"] == "0xMultisendHash"
        assert parsed["market"]["address"] == "0xMarket1"

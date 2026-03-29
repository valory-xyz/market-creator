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

"""Tests for RedeemPositionsBehaviour."""

from typing import Any
from unittest.mock import MagicMock, patch

from packages.valory.skills.omen_funds_recoverer_abci.behaviours.base import (
    ETHER_VALUE,
)
from packages.valory.skills.omen_funds_recoverer_abci.behaviours.redeem_positions import (
    RedeemPositionsBehaviour,
)
from packages.valory.skills.omen_funds_recoverer_abci.tests.behaviours.conftest import (
    exhaust_gen,
    make_contract_error_response,
    make_contract_state_response,
    make_gen,
)


class TestRedeemPositionsBehaviour:
    """Tests for RedeemPositionsBehaviour."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.conditional_tokens_contract = "0xConditionalTokens"
        context_mock.params.collateral_tokens_contract = "0xCollateral"
        context_mock.params.realitio_oracle_proxy_contract = "0xRealitioProxy"
        context_mock.params.redeem_positions_batch_size = 5
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
        context_mock.conditional_tokens_subgraph = MagicMock()
        context_mock.conditional_tokens_subgraph.get_spec.return_value = {
            "method": "POST",
            "url": "https://ct.example.com",
        }
        self.behaviour: Any = RedeemPositionsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_has_winning_position_true(self) -> None:
        """Test _has_winning_position when a winning position exists."""
        payouts = ["1", "0"]
        held_index_sets = {1, 2}
        assert RedeemPositionsBehaviour._has_winning_position(payouts, held_index_sets)

    def test_has_winning_position_false(self) -> None:
        """Test _has_winning_position when no winning position exists."""
        payouts = ["0", "1"]
        held_index_sets = {1}  # index_set 1 = (1 << 0), payout[0] = "0"
        assert not RedeemPositionsBehaviour._has_winning_position(
            payouts, held_index_sets
        )

    def test_has_winning_position_empty_payouts(self) -> None:
        """Test _has_winning_position with empty payouts."""
        assert not RedeemPositionsBehaviour._has_winning_position([], {1, 2})

    def test_has_winning_position_empty_held(self) -> None:
        """Test _has_winning_position with empty held set."""
        assert not RedeemPositionsBehaviour._has_winning_position(["1", "0"], set())

    def test_check_resolved_true(self) -> None:
        """Test _check_resolved returns True when resolved."""
        resp = make_contract_state_response({"resolved": True})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._check_resolved("0xCondId")
            result = exhaust_gen(gen)
        assert result is True

    def test_check_resolved_false(self) -> None:
        """Test _check_resolved returns False when not resolved."""
        resp = make_contract_state_response({"resolved": False})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._check_resolved("0xCondId")
            result = exhaust_gen(gen)
        assert result is False

    def test_check_resolved_error(self) -> None:
        """Test _check_resolved returns False on contract error."""
        resp = make_contract_error_response()
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._check_resolved("0xCondId")
            result = exhaust_gen(gen)
        assert result is False

    def test_get_resolve_tx_success(self) -> None:
        """Test _get_resolve_tx with successful response."""
        market = {
            "address": "0xMarket",
            "question_id": "0xabcd1234",
            "question_data": "some question",
            "template_id": 2,
            "outcome_slot_count": 2,
        }
        resp = make_contract_state_response({"data": "0xResolveData"})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._get_resolve_tx(market)
            result = exhaust_gen(gen)

        assert result is not None
        assert result["to"] == "0xRealitioProxy"
        assert result["data"] == "0xResolveData"
        assert result["value"] == ETHER_VALUE

    def test_get_resolve_tx_no_question_id(self) -> None:
        """Test _get_resolve_tx with missing question_id."""
        market = {
            "address": "0xMarket",
            "question_id": "",
            "question_data": "some question",
        }
        gen = self.behaviour._get_resolve_tx(market)
        result = exhaust_gen(gen)
        assert result is None

    def test_get_resolve_tx_error(self) -> None:
        """Test _get_resolve_tx with contract error."""
        market = {
            "address": "0xMarket",
            "question_id": "0xabcd1234",
            "question_data": "q",
            "template_id": 2,
            "outcome_slot_count": 2,
        }
        resp = make_contract_error_response()
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._get_resolve_tx(market)
            result = exhaust_gen(gen)
        assert result is None

    def test_get_redeem_positions_tx_success(self) -> None:
        """Test _get_redeem_positions_tx with successful response."""
        resp = make_contract_state_response({"data": "0xRedeemData"})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._get_redeem_positions_tx("0xCond", [1, 2])
            result = exhaust_gen(gen)

        assert result is not None
        assert result["to"] == "0xConditionalTokens"
        assert result["data"] == "0xRedeemData"
        assert result["value"] == ETHER_VALUE

    def test_get_redeem_positions_tx_fail(self) -> None:
        """Test _get_redeem_positions_tx with error response."""
        resp = make_contract_error_response()
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._get_redeem_positions_tx("0xCond", [1, 2])
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

    def test_get_recovery_txs_no_held_positions(self) -> None:
        """Test _get_recovery_txs when no held positions found."""
        with patch.object(self.behaviour, "_get_held_positions", new=make_gen({})):
            gen = self.behaviour._get_recovery_txs()
            result = exhaust_gen(gen)
        assert result == []

    def test_get_recovery_txs_no_finalized_markets(self) -> None:
        """Test _get_recovery_txs when no finalized markets match conditions."""
        held = {"0xcond1": {1, 2}}
        with patch.object(
            self.behaviour, "_get_held_positions", new=make_gen(held)
        ), patch.object(
            self.behaviour, "_get_markets_for_conditions", new=make_gen([])
        ):
            gen = self.behaviour._get_recovery_txs()
            result = exhaust_gen(gen)
        assert result == []

    def test_get_recovery_txs_no_winning_positions(self) -> None:
        """Test _get_recovery_txs when cross-reference yields no winners."""
        held = {"0xcond1": {1}}
        markets = [
            {
                "address": "0xM1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["0", "1"],  # index_set=1 -> payout[0]=0 -> no win
            }
        ]
        with patch.object(
            self.behaviour, "_get_held_positions", new=make_gen(held)
        ), patch.object(
            self.behaviour, "_get_markets_for_conditions", new=make_gen(markets)
        ):
            gen = self.behaviour._get_recovery_txs()
            result = exhaust_gen(gen)
        assert result == []

    def test_get_recovery_txs_success_resolved(self) -> None:
        """Test _get_recovery_txs happy path with already-resolved condition."""
        held = {"0xcond1": {1}}
        markets = [
            {
                "address": "0xM1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["1", "0"],  # index_set=1 -> payout[0]=1 -> winning
            }
        ]
        redeem_tx = {"to": "0xCT", "data": "0xredeem", "value": 0}
        with patch.object(
            self.behaviour, "_get_held_positions", new=make_gen(held)
        ), patch.object(
            self.behaviour, "_get_markets_for_conditions", new=make_gen(markets)
        ), patch.object(
            self.behaviour, "_check_resolved", new=make_gen(True)
        ), patch.object(
            self.behaviour, "_get_redeem_positions_tx", new=make_gen(redeem_tx)
        ):
            gen = self.behaviour._get_recovery_txs()
            result = exhaust_gen(gen)
        assert len(result) == 1
        assert result[0] == redeem_tx

    def test_get_recovery_txs_success_not_resolved(self) -> None:
        """Test _get_recovery_txs when condition needs resolve first."""
        held = {"0xcond1": {1}}
        markets = [
            {
                "address": "0xM1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["1", "0"],
                "question_id": "0xqid",
                "question_data": "q",
                "template_id": 2,
            }
        ]
        resolve_tx = {"to": "0xProxy", "data": "0xresolve", "value": 0}
        redeem_tx = {"to": "0xCT", "data": "0xredeem", "value": 0}
        with patch.object(
            self.behaviour, "_get_held_positions", new=make_gen(held)
        ), patch.object(
            self.behaviour, "_get_markets_for_conditions", new=make_gen(markets)
        ), patch.object(
            self.behaviour, "_check_resolved", new=make_gen(False)
        ), patch.object(
            self.behaviour, "_get_resolve_tx", new=make_gen(resolve_tx)
        ), patch.object(
            self.behaviour, "_get_redeem_positions_tx", new=make_gen(redeem_tx)
        ):
            gen = self.behaviour._get_recovery_txs()
            result = exhaust_gen(gen)
        assert len(result) == 2
        assert result[0] == resolve_tx
        assert result[1] == redeem_tx

    def test_get_recovery_txs_resolve_tx_fails_skips(self) -> None:
        """Test _get_recovery_txs skips market when resolve tx fails."""
        held = {"0xcond1": {1}}
        markets = [
            {
                "address": "0xM1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["1", "0"],
                "question_id": "0xqid",
            }
        ]
        with patch.object(
            self.behaviour, "_get_held_positions", new=make_gen(held)
        ), patch.object(
            self.behaviour, "_get_markets_for_conditions", new=make_gen(markets)
        ), patch.object(
            self.behaviour, "_check_resolved", new=make_gen(False)
        ), patch.object(
            self.behaviour, "_get_resolve_tx", new=make_gen(None)
        ):
            gen = self.behaviour._get_recovery_txs()
            result = exhaust_gen(gen)
        assert result == []

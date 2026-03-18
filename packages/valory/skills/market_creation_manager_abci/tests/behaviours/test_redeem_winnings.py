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
        context_mock.params.realitio_oracle_proxy_contract = "0xproxy"
        self.behaviour = RedeemWinningsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_matching_round(self) -> None:
        """Test matching_round is correctly set."""
        assert self.behaviour.matching_round == RedeemWinningsRound

    # --- _has_winning_position tests ---

    def test_has_winning_position_true(self) -> None:
        """Test _has_winning_position when held index set matches winning payout."""
        # indexSet 1 = outcome 0, payouts[0] = "1" → winning
        assert RedeemWinningsBehaviour._has_winning_position(["1", "0"], {1}) is True

    def test_has_winning_position_false(self) -> None:
        """Test _has_winning_position when held index set is on losing side."""
        # indexSet 2 = outcome 1, payouts[1] = "0" → losing
        assert RedeemWinningsBehaviour._has_winning_position(["1", "0"], {2}) is False

    def test_has_winning_position_outcome1_wins(self) -> None:
        """Test _has_winning_position when outcome 1 wins and safe holds it."""
        # indexSet 2 = outcome 1, payouts[1] = "1" → winning
        assert RedeemWinningsBehaviour._has_winning_position(["0", "1"], {2}) is True

    def test_has_winning_position_both_held(self) -> None:
        """Test _has_winning_position when both outcomes held, one winning."""
        assert RedeemWinningsBehaviour._has_winning_position(["1", "0"], {1, 2}) is True

    def test_has_winning_position_empty_held(self) -> None:
        """Test _has_winning_position with empty held set."""
        assert RedeemWinningsBehaviour._has_winning_position(["1", "0"], set()) is False

    # --- _get_held_positions tests ---

    def test_get_held_positions_empty(self) -> None:
        """Test _get_held_positions when CT subgraph returns no positions."""
        ct_response: Any = {"data": {"user": {"userPositions": []}}}
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xSafe")
            ),
        ), patch.object(
            self.behaviour,
            "get_conditional_tokens_subgraph_result",
            new=_make_gen(ct_response),
        ):
            gen = self.behaviour._get_held_positions()
            result = _exhaust_gen(gen)
        assert result == {}

    def test_get_held_positions_subgraph_error(self) -> None:
        """Test _get_held_positions when CT subgraph returns None."""
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xSafe")
            ),
        ), patch.object(
            self.behaviour,
            "get_conditional_tokens_subgraph_result",
            new=_make_gen(None),
        ):
            gen = self.behaviour._get_held_positions()
            result = _exhaust_gen(gen)
        assert result == {}

    def test_get_held_positions_pagination(self) -> None:
        """Test _get_held_positions paginates when a full page is returned."""
        from packages.valory.skills.market_creation_manager_abci.behaviours.redeem_winnings import (
            SUBGRAPH_PAGE_SIZE,
        )

        # First page: full page triggers pagination
        page1_positions = [
            {
                "id": f"0xpos{i}",
                "balance": "100",
                "position": {"conditionIds": [f"0xcond{i}"], "indexSets": ["1"]},
            }
            for i in range(SUBGRAPH_PAGE_SIZE)
        ]
        page1 = {"data": {"user": {"userPositions": page1_positions}}}
        # Second page: partial → stops
        page2 = {
            "data": {
                "user": {
                    "userPositions": [
                        {
                            "id": "0xpos_extra",
                            "balance": "50",
                            "position": {
                                "conditionIds": ["0xcond_extra"],
                                "indexSets": ["2"],
                            },
                        }
                    ]
                }
            }
        }
        call_count = 0

        def _mock_ct_subgraph(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            return page1 if call_count == 1 else page2
            yield  # noqa: unreachable

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xSafe")
            ),
        ), patch.object(
            self.behaviour,
            "get_conditional_tokens_subgraph_result",
            new=_mock_ct_subgraph,
        ):
            gen = self.behaviour._get_held_positions()
            result = _exhaust_gen(gen)
        assert call_count == 2
        assert "0xcond_extra" in result

    def test_get_held_positions_success(self) -> None:
        """Test _get_held_positions with valid data."""
        ct_response = {
            "data": {
                "user": {
                    "userPositions": [
                        {
                            "id": "0xpos1",
                            "balance": "100",
                            "position": {
                                "conditionIds": ["0xcond1"],
                                "indexSets": ["1"],
                            },
                        },
                        {
                            "id": "0xpos2",
                            "balance": "200",
                            "position": {
                                "conditionIds": ["0xcond1"],
                                "indexSets": ["2"],
                            },
                        },
                        {
                            "id": "0xpos3",
                            "balance": "50",
                            "position": {
                                "conditionIds": ["0xcond2"],
                                "indexSets": ["1"],
                            },
                        },
                    ]
                }
            }
        }
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(safe_contract_address="0xSafe")
            ),
        ), patch.object(
            self.behaviour,
            "get_conditional_tokens_subgraph_result",
            new=_make_gen(ct_response),
        ):
            gen = self.behaviour._get_held_positions()
            result = _exhaust_gen(gen)
        assert len(result) == 2
        assert result["0xcond1"] == {1, 2}
        assert result["0xcond2"] == {1}

    # --- _get_markets_for_conditions tests ---

    def test_get_markets_for_conditions_empty(self) -> None:
        """Test _get_markets_for_conditions with empty condition list."""
        with patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=lambda: property(lambda self: 1000000),
        ):
            gen = self.behaviour._get_markets_for_conditions([])
            result = _exhaust_gen(gen)
        assert result == []

    def test_get_markets_for_conditions_subgraph_error(self) -> None:
        """Test _get_markets_for_conditions when subgraph returns None."""
        with patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=lambda: property(lambda self: 1000000),
        ), patch.object(self.behaviour, "get_subgraph_result", new=_make_gen(None)):
            gen = self.behaviour._get_markets_for_conditions(["0xcond1"])
            result = _exhaust_gen(gen)
        assert result == []

    def test_get_markets_for_conditions_success(self) -> None:
        """Test _get_markets_for_conditions with valid data and edge cases."""
        omen_response = {
            "data": {
                "fixedProductMarketMakers": [
                    {
                        "id": "0xmarket1",
                        "payouts": ["1", "0"],
                        "conditions": [{"id": "0xcond1", "outcomeSlotCount": 2}],
                    },
                    {
                        "id": "0xmarket2",
                        "payouts": None,
                        "conditions": [{"id": "0xcond2", "outcomeSlotCount": 2}],
                    },
                    {
                        "id": "0xmarket3",
                        "payouts": ["0", "1"],
                        "conditions": [],
                    },
                    {
                        "id": "0xmarket4",
                        "payouts": ["1", "0"],
                        "conditions": [{"id": "0xcond4", "outcomeSlotCount": None}],
                    },
                    {
                        "id": "0xmarket1",
                        "payouts": ["1", "0"],
                        "conditions": [{"id": "0xcond1", "outcomeSlotCount": 2}],
                    },
                ]
            }
        }
        with patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=lambda: property(lambda self: 3000000),
        ), patch.object(
            self.behaviour, "get_subgraph_result", new=_make_gen(omen_response)
        ):
            gen = self.behaviour._get_markets_for_conditions(["0xcond1", "0xcond2"])
            result = _exhaust_gen(gen)
        # market1 passes; market2 has None payouts; market3 has no conditions;
        # market4 has None outcomeSlotCount; duplicate market1 is deduplicated
        assert len(result) == 1
        assert result[0]["address"] == "0xmarket1"
        assert result[0]["payouts"] == ["1", "0"]

    # --- _check_resolved tests ---

    def test_check_resolved_true(self) -> None:
        """Test _check_resolved when condition is resolved."""
        mock_response = MagicMock()
        mock_response.performative = ContractApiMessage.Performative.STATE
        mock_response.state.body = {"resolved": True}
        with patch.object(
            self.behaviour, "get_contract_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._check_resolved("0xcond1")
            result = _exhaust_gen(gen)
        assert result is True

    def test_check_resolved_false(self) -> None:
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
        assert result is False

    # --- _get_resolve_tx tests ---

    def test_get_resolve_tx_success(self) -> None:
        """Test _get_resolve_tx with successful response."""
        market = {
            "address": "0xmarket1",
            "condition_id": "0xcond1",
            "outcome_slot_count": 2,
            "question_id": "0xabcd",
            "question_data": "Will X happen?",
            "template_id": 2,
        }
        mock_response = MagicMock()
        mock_response.performative = ContractApiMessage.Performative.STATE
        mock_response.state.body = {"data": "0xresolvedata"}
        with patch.object(
            self.behaviour, "get_contract_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._get_resolve_tx(market)
            result = _exhaust_gen(gen)
        assert result is not None
        assert result["to"] == "0xproxy"
        assert result["data"] == "0xresolvedata"

    def test_get_resolve_tx_no_question_id(self) -> None:
        """Test _get_resolve_tx when question_id is missing."""
        market = {
            "address": "0xmarket1",
            "condition_id": "0xcond1",
            "outcome_slot_count": 2,
            "question_id": "",
            "question_data": "Will X?",
            "template_id": 2,
        }
        gen = self.behaviour._get_resolve_tx(market)
        result = _exhaust_gen(gen)
        assert result is None

    def test_get_resolve_tx_error(self) -> None:
        """Test _get_resolve_tx with error response."""
        market = {
            "address": "0xmarket1",
            "condition_id": "0xcond1",
            "outcome_slot_count": 2,
            "question_id": "0xabcd",
            "question_data": "Will X?",
            "template_id": 2,
        }
        mock_response = MagicMock()
        mock_response.performative = ContractApiMessage.Performative.ERROR
        with patch.object(
            self.behaviour, "get_contract_api_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._get_resolve_tx(market)
            result = _exhaust_gen(gen)
        assert result is None

    # --- _get_redeem_positions_tx tests ---

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

    # --- get_payload tests ---

    def test_get_payload_no_held_positions(self) -> None:
        """Test get_payload when CT subgraph returns no held positions."""
        with patch.object(self.behaviour, "_get_held_positions", new=_make_gen({})):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)
        assert result is None

    def test_get_payload_no_finalized_markets(self) -> None:
        """Test get_payload when Omen subgraph returns no markets for held conditions."""
        held = {"0xcond1": {1}}
        with patch.object(
            self.behaviour, "_get_held_positions", new=_make_gen(held)
        ), patch.object(
            self.behaviour, "_get_markets_for_conditions", new=_make_gen([])
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)
        assert result is None

    def test_get_payload_no_winning_positions(self) -> None:
        """Test get_payload when markets exist but all held positions are losing."""
        held = {"0xcond1": {2}}  # holds outcome 1
        markets = [
            {
                "address": "0xmarket1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["1", "0"],  # outcome 0 won → losing
            }
        ]
        with patch.object(
            self.behaviour, "_get_held_positions", new=_make_gen(held)
        ), patch.object(
            self.behaviour, "_get_markets_for_conditions", new=_make_gen(markets)
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)
        assert result is None

    def test_get_payload_redeem_tx_build_fails(self) -> None:
        """Test get_payload when all redeem tx builds fail."""
        held = {"0xcond1": {1}}  # holds outcome 0
        markets = [
            {
                "address": "0xmarket1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["1", "0"],  # outcome 0 won → winning
            }
        ]
        with patch.object(
            self.behaviour, "_get_held_positions", new=_make_gen(held)
        ), patch.object(
            self.behaviour, "_get_markets_for_conditions", new=_make_gen(markets)
        ), patch.object(
            self.behaviour, "_check_resolved", new=_make_gen(True)
        ), patch.object(
            self.behaviour, "_get_redeem_positions_tx", new=_make_gen(None)
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)
        assert result is None

    def test_get_payload_resolve_needed_and_fails(self) -> None:
        """Test get_payload when resolve is needed but build_resolve_tx fails."""
        held = {"0xcond1": {1}}
        markets = [
            {
                "address": "0xmarket1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["1", "0"],
                "question_id": "0xq1",
                "question_data": "Will X?",
                "template_id": 2,
            }
        ]
        with patch.object(
            self.behaviour, "_get_held_positions", new=_make_gen(held)
        ), patch.object(
            self.behaviour, "_get_markets_for_conditions", new=_make_gen(markets)
        ), patch.object(
            self.behaviour, "_check_resolved", new=_make_gen(False)
        ), patch.object(
            self.behaviour, "_get_resolve_tx", new=_make_gen(None)
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)
        assert result is None

    def test_get_payload_resolve_needed_success(self) -> None:
        """Test get_payload when resolve is needed and succeeds."""
        held = {"0xcond1": {1}}
        markets = [
            {
                "address": "0xmarket1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["1", "0"],
                "question_id": "0xq1",
                "question_data": "Will X?",
                "template_id": 2,
            }
        ]
        resolve_tx = {"to": "0xproxy", "data": "0xresolve", "value": 0}
        redeem_tx = {"to": "0xcondtokens", "data": "0xredeem", "value": 0}
        with patch.object(
            self.behaviour, "_get_held_positions", new=_make_gen(held)
        ), patch.object(
            self.behaviour, "_get_markets_for_conditions", new=_make_gen(markets)
        ), patch.object(
            self.behaviour, "_check_resolved", new=_make_gen(False)
        ), patch.object(
            self.behaviour, "_get_resolve_tx", new=_make_gen(resolve_tx)
        ), patch.object(
            self.behaviour, "_get_redeem_positions_tx", new=_make_gen(redeem_tx)
        ), patch.object(
            self.behaviour, "_to_multisend", new=_make_gen("0xmultisend_hash")
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)
        assert result == "0xmultisend_hash"

    def test_get_payload_multisend_fails(self) -> None:
        """Test get_payload when _to_multisend returns None."""
        held = {"0xcond1": {1}}
        markets = [
            {
                "address": "0xmarket1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["1", "0"],
            }
        ]
        redeem_tx = {"to": "0xcondtokens", "data": "0xdata", "value": 0}
        with patch.object(
            self.behaviour, "_get_held_positions", new=_make_gen(held)
        ), patch.object(
            self.behaviour, "_get_markets_for_conditions", new=_make_gen(markets)
        ), patch.object(
            self.behaviour, "_check_resolved", new=_make_gen(True)
        ), patch.object(
            self.behaviour, "_get_redeem_positions_tx", new=_make_gen(redeem_tx)
        ), patch.object(
            self.behaviour, "_to_multisend", new=_make_gen(None)
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)
        assert result is None

    def test_get_payload_success(self) -> None:
        """Test get_payload happy path."""
        held = {"0xcond1": {1}}
        markets = [
            {
                "address": "0xmarket1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["1", "0"],
            }
        ]
        redeem_tx = {"to": "0xcondtokens", "data": "0xdata", "value": 0}
        with patch.object(
            self.behaviour, "_get_held_positions", new=_make_gen(held)
        ), patch.object(
            self.behaviour, "_get_markets_for_conditions", new=_make_gen(markets)
        ), patch.object(
            self.behaviour, "_check_resolved", new=_make_gen(True)
        ), patch.object(
            self.behaviour, "_get_redeem_positions_tx", new=_make_gen(redeem_tx)
        ), patch.object(
            self.behaviour, "_to_multisend", new=_make_gen("0xmultisend_hash")
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)
        assert result == "0xmultisend_hash"

    # --- async_act tests ---

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

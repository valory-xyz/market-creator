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

"""Tests for CtRedeemTokensBehaviour."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from packages.valory.skills.omen_ct_redeem_tokens_abci.behaviours.base import (
    ETHER_VALUE,
)
from packages.valory.skills.omen_ct_redeem_tokens_abci.behaviours.redeem_tokens import (
    CONDITION_ID_BATCH_SIZE,
    CT_REDEEM_TX_SUBMITTER,
    CtRedeemTokensBehaviour,
    SUBGRAPH_PAGE_SIZE,
)
from packages.valory.skills.omen_ct_redeem_tokens_abci.tests.behaviours.conftest import (
    exhaust_gen,
    make_contract_error_response,
    make_contract_state_response,
    make_gen,
)


def _build_behaviour() -> Any:
    """Build a CtRedeemTokensBehaviour with a fully mocked context."""
    context_mock = MagicMock()
    context_mock.logger = MagicMock()
    context_mock.params = MagicMock()
    context_mock.params.conditional_tokens_contract = "0xConditionalTokens"
    context_mock.params.collateral_tokens_contract = "0xCollateral"
    context_mock.params.realitio_oracle_proxy_contract = "0xRealitioProxy"
    context_mock.params.ct_redeem_tokens_batch_size = 5
    context_mock.params.ct_redeem_tokens_min_payout = 0
    context_mock.params.multisend_address = "0xMultisend"
    context_mock.state.ignored_ct_positions = set()
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
    return CtRedeemTokensBehaviour(name="test", skill_context=context_mock)


class TestCtRedeemTokensBehaviourSimpleHelpers:
    """Tests for the small static and contract-call helpers on CtRedeemTokensBehaviour."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.behaviour: Any = _build_behaviour()

    def test_has_winning_position_true(self) -> None:
        """Test _has_winning_position when a winning position exists."""
        payouts = ["1", "0"]
        held_index_sets = {1, 2}
        assert CtRedeemTokensBehaviour._has_winning_position(payouts, held_index_sets)

    def test_has_winning_position_false(self) -> None:
        """Test _has_winning_position when no winning position exists."""
        payouts = ["0", "1"]
        held_index_sets = {1}  # index_set 1 = (1 << 0), payout[0] = "0"
        assert not CtRedeemTokensBehaviour._has_winning_position(
            payouts, held_index_sets
        )

    def test_has_winning_position_empty_payouts(self) -> None:
        """Test _has_winning_position with empty payouts."""
        assert not CtRedeemTokensBehaviour._has_winning_position([], {1, 2})

    def test_has_winning_position_empty_held(self) -> None:
        """Test _has_winning_position with empty held set."""
        assert not CtRedeemTokensBehaviour._has_winning_position(["1", "0"], set())

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


class TestCtRedeemTokensBehaviourBuildRedeemTxs:
    """Tests for the _build_redeem_txs helper that walks the redeemable list."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.behaviour: Any = _build_behaviour()

    def test_build_redeem_txs_empty_input(self) -> None:
        """Test _build_redeem_txs with no redeemable markets returns empty list."""
        gen = self.behaviour._build_redeem_txs([])
        result = exhaust_gen(gen)
        assert not result

    def test_build_redeem_txs_already_resolved(self) -> None:
        """Test _build_redeem_txs happy path with already-resolved condition."""
        markets = [
            {
                "address": "0xM1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["1", "0"],
            }
        ]
        redeem_tx = {"to": "0xCT", "data": "0xredeem", "value": 0}
        with (
            patch.object(self.behaviour, "_check_resolved", new=make_gen(True)),
            patch.object(
                self.behaviour, "_get_redeem_positions_tx", new=make_gen(redeem_tx)
            ),
        ):
            gen = self.behaviour._build_redeem_txs(markets)
            result = exhaust_gen(gen)
        assert len(result) == 1
        assert result[0] == redeem_tx

    def test_build_redeem_txs_not_resolved_resolve_then_redeem(self) -> None:
        """Test _build_redeem_txs when condition needs resolve first."""
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
        with (
            patch.object(self.behaviour, "_check_resolved", new=make_gen(False)),
            patch.object(self.behaviour, "_get_resolve_tx", new=make_gen(resolve_tx)),
            patch.object(
                self.behaviour, "_get_redeem_positions_tx", new=make_gen(redeem_tx)
            ),
        ):
            gen = self.behaviour._build_redeem_txs(markets)
            result = exhaust_gen(gen)
        assert len(result) == 2
        assert result[0] == resolve_tx
        assert result[1] == redeem_tx

    def test_build_redeem_txs_resolve_tx_fails_skips(self) -> None:
        """Test _build_redeem_txs skips market when resolve tx fails."""
        markets = [
            {
                "address": "0xM1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["1", "0"],
                "question_id": "0xqid",
            }
        ]
        with (
            patch.object(self.behaviour, "_check_resolved", new=make_gen(False)),
            patch.object(self.behaviour, "_get_resolve_tx", new=make_gen(None)),
        ):
            gen = self.behaviour._build_redeem_txs(markets)
            result = exhaust_gen(gen)
        assert not result

    def test_build_redeem_txs_redeem_tx_fails(self) -> None:
        """Test _build_redeem_txs when redeem tx fails (already resolved)."""
        markets = [
            {
                "address": "0xM1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["1", "0"],
            }
        ]
        with (
            patch.object(self.behaviour, "_check_resolved", new=make_gen(True)),
            patch.object(
                self.behaviour, "_get_redeem_positions_tx", new=make_gen(None)
            ),
        ):
            gen = self.behaviour._build_redeem_txs(markets)
            result = exhaust_gen(gen)
        # No txs appended since redeem returned None
        assert not result

    def test_build_redeem_txs_respects_batch_size(self) -> None:
        """Test _build_redeem_txs caps the iteration at batch_size."""
        # Configure batch_size = 1, send 3 markets, expect only 1 redeem tx
        self.behaviour.context.params.ct_redeem_tokens_batch_size = 1
        markets = [
            {
                "address": f"0xM{i}",
                "condition_id": f"0xcond{i}",
                "outcome_slot_count": 2,
                "payouts": ["1", "0"],
            }
            for i in range(3)
        ]
        redeem_tx = {"to": "0xCT", "data": "0xredeem", "value": 0}
        with (
            patch.object(self.behaviour, "_check_resolved", new=make_gen(True)),
            patch.object(
                self.behaviour, "_get_redeem_positions_tx", new=make_gen(redeem_tx)
            ),
        ):
            gen = self.behaviour._build_redeem_txs(markets)
            result = exhaust_gen(gen)
        assert len(result) == 1


class TestCtRedeemTokensBehaviourRedeemableMarkets:
    """Tests for _get_redeemable_markets cross-referencing held positions and finalized markets."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.behaviour: Any = _build_behaviour()

    def test_get_redeemable_markets_no_finalized(self) -> None:
        """Test returns empty when no finalized markets match conditions."""
        held = {"0xcond1": {1, 2}}
        with patch.object(
            self.behaviour, "_get_markets_for_conditions", new=make_gen([])
        ):
            gen = self.behaviour._get_redeemable_markets(held)
            result = exhaust_gen(gen)
        assert not result

    def test_get_redeemable_markets_no_winning_ct_redeem_tokens_min_payout_nonzero(
        self,
    ) -> None:
        """Test losers are added to ignored set when ct_redeem_tokens_min_payout > 0."""
        self.behaviour.context.params.ct_redeem_tokens_min_payout = 1000
        held = {"0xcond1": {1}}
        markets = [
            {
                "address": "0xM1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["0", "1"],
            }
        ]
        with patch.object(
            self.behaviour, "_get_markets_for_conditions", new=make_gen(markets)
        ):
            gen = self.behaviour._get_redeemable_markets(held)
            result = exhaust_gen(gen)
        assert not result
        assert "0xcond1" in self.behaviour.context.state.ignored_ct_positions

    def test_get_redeemable_markets_no_winning_burn_losers(self) -> None:
        """Test losers are included for burning when ct_redeem_tokens_min_payout == 0."""
        self.behaviour.context.params.ct_redeem_tokens_min_payout = 0
        held = {"0xcond1": {1}}
        markets = [
            {
                "address": "0xM1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["0", "1"],
            }
        ]
        with patch.object(
            self.behaviour, "_get_markets_for_conditions", new=make_gen(markets)
        ):
            gen = self.behaviour._get_redeemable_markets(held)
            result = exhaust_gen(gen)
        assert len(result) == 1
        assert result[0]["address"] == "0xM1"

    def test_get_redeemable_markets_with_winners_only(self) -> None:
        """Test returns only winners when min_payout > 0."""
        self.behaviour.context.params.ct_redeem_tokens_min_payout = 1
        held = {"0xcond1": {1}, "0xcond2": {1}}
        markets = [
            {
                "address": "0xM1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["1", "0"],  # winning
            },
            {
                "address": "0xM2",
                "condition_id": "0xcond2",
                "outcome_slot_count": 2,
                "payouts": ["0", "1"],  # not winning for index_set=1
            },
        ]
        with patch.object(
            self.behaviour, "_get_markets_for_conditions", new=make_gen(markets)
        ):
            gen = self.behaviour._get_redeemable_markets(held)
            result = exhaust_gen(gen)
        assert len(result) == 1
        assert result[0]["address"] == "0xM1"

    def test_get_redeemable_markets_burn_all_when_min_zero(self) -> None:
        """Test returns both winners and losers when min_payout == 0."""
        self.behaviour.context.params.ct_redeem_tokens_min_payout = 0
        held = {"0xcond1": {1}, "0xcond2": {1}}
        markets = [
            {
                "address": "0xM1",
                "condition_id": "0xcond1",
                "outcome_slot_count": 2,
                "payouts": ["1", "0"],  # winning
            },
            {
                "address": "0xM2",
                "condition_id": "0xcond2",
                "outcome_slot_count": 2,
                "payouts": ["0", "1"],  # losing but included for burn
            },
        ]
        with patch.object(
            self.behaviour, "_get_markets_for_conditions", new=make_gen(markets)
        ):
            gen = self.behaviour._get_redeemable_markets(held)
            result = exhaust_gen(gen)
        assert len(result) == 2


class TestCtRedeemTokensBehaviourPrepareMultisend:
    """Tests for the _prepare_multisend pipeline orchestration."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.behaviour: Any = _build_behaviour()

    def test_prepare_multisend_no_held(self) -> None:
        """Test _prepare_multisend returns None when safe holds no positions."""
        with patch.object(self.behaviour, "_get_held_positions", new=make_gen({})):
            gen = self.behaviour._prepare_multisend()
            result = exhaust_gen(gen)
        assert result is None

    def test_prepare_multisend_all_ignored(self) -> None:
        """Test _prepare_multisend returns None when all held positions are ignored."""
        held = {"0xcond1": {1}, "0xcond2": {2}}
        self.behaviour.context.state.ignored_ct_positions = {"0xcond1", "0xcond2"}
        with patch.object(self.behaviour, "_get_held_positions", new=make_gen(held)):
            gen = self.behaviour._prepare_multisend()
            result = exhaust_gen(gen)
        assert result is None

    def test_prepare_multisend_partial_ignored(self) -> None:
        """Test _prepare_multisend filters out ignored positions."""
        held = {"0xcond1": {1}, "0xcond2": {2}}
        self.behaviour.context.state.ignored_ct_positions = {"0xcond1"}
        markets = [{"address": "0xM2", "condition_id": "0xcond2"}]
        txs = [{"to": "0xCT", "data": "0xredeem", "value": 0}]
        with (
            patch.object(self.behaviour, "_get_held_positions", new=make_gen(held)),
            patch.object(
                self.behaviour, "_get_redeemable_markets", new=make_gen(markets)
            ),
            patch.object(self.behaviour, "_build_redeem_txs", new=make_gen(txs)),
            patch.object(self.behaviour, "_to_multisend", new=make_gen("0xhash")),
        ):
            gen = self.behaviour._prepare_multisend()
            result = exhaust_gen(gen)
        assert result == "0xhash"

    def test_prepare_multisend_no_redeemable(self) -> None:
        """Test _prepare_multisend returns None when no markets are redeemable."""
        held = {"0xcond1": {1}}
        with (
            patch.object(self.behaviour, "_get_held_positions", new=make_gen(held)),
            patch.object(self.behaviour, "_get_redeemable_markets", new=make_gen([])),
        ):
            gen = self.behaviour._prepare_multisend()
            result = exhaust_gen(gen)
        assert result is None

    def test_prepare_multisend_no_built_txs(self) -> None:
        """Test _prepare_multisend returns None when no per-market txs are built."""
        held = {"0xcond1": {1}}
        markets = [{"address": "0xM1", "condition_id": "0xcond1"}]
        with (
            patch.object(self.behaviour, "_get_held_positions", new=make_gen(held)),
            patch.object(
                self.behaviour, "_get_redeemable_markets", new=make_gen(markets)
            ),
            patch.object(self.behaviour, "_build_redeem_txs", new=make_gen([])),
        ):
            gen = self.behaviour._prepare_multisend()
            result = exhaust_gen(gen)
        assert result is None

    def test_prepare_multisend_multisend_fails(self) -> None:
        """Test _prepare_multisend returns None when _to_multisend fails."""
        held = {"0xcond1": {1}}
        markets = [{"address": "0xM1", "condition_id": "0xcond1"}]
        txs = [{"to": "0xCT", "data": "0xredeem", "value": 0}]
        with (
            patch.object(self.behaviour, "_get_held_positions", new=make_gen(held)),
            patch.object(
                self.behaviour, "_get_redeemable_markets", new=make_gen(markets)
            ),
            patch.object(self.behaviour, "_build_redeem_txs", new=make_gen(txs)),
            patch.object(self.behaviour, "_to_multisend", new=make_gen(None)),
        ):
            gen = self.behaviour._prepare_multisend()
            result = exhaust_gen(gen)
        assert result is None

    def test_prepare_multisend_success(self) -> None:
        """Test _prepare_multisend returns the multisend hash on the happy path."""
        held = {"0xcond1": {1}}
        markets = [{"address": "0xM1", "condition_id": "0xcond1"}]
        txs = [{"to": "0xCT", "data": "0xredeem", "value": 0}]
        with (
            patch.object(self.behaviour, "_get_held_positions", new=make_gen(held)),
            patch.object(
                self.behaviour, "_get_redeemable_markets", new=make_gen(markets)
            ),
            patch.object(self.behaviour, "_build_redeem_txs", new=make_gen(txs)),
            patch.object(self.behaviour, "_to_multisend", new=make_gen("0xfinalhash")),
        ):
            gen = self.behaviour._prepare_multisend()
            result = exhaust_gen(gen)
        assert result == "0xfinalhash"


class TestCtRedeemTokensBehaviourAsyncAct:
    """Tests for the async_act entry point that wraps _prepare_multisend in a payload."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.behaviour: Any = _build_behaviour()

    def test_async_act_with_tx(self) -> None:
        """Test async_act sets a non-None tx_submitter when a tx is built."""
        sent_payloads: list = []

        def fake_send(payload: Any) -> Any:
            sent_payloads.append(payload)
            return None
            yield  # noqa

        with (
            patch.object(
                self.behaviour, "_prepare_multisend", new=make_gen("0xtxhash")
            ),
            patch.object(self.behaviour, "send_a2a_transaction", new=fake_send),
            patch.object(self.behaviour, "wait_until_round_end", new=make_gen(None)),
            patch.object(self.behaviour, "set_done") as mock_set_done,
        ):
            gen = self.behaviour.async_act()
            exhaust_gen(gen)
            mock_set_done.assert_called_once()
        assert len(sent_payloads) == 1
        assert sent_payloads[0].tx_hash == "0xtxhash"
        assert sent_payloads[0].tx_submitter == CT_REDEEM_TX_SUBMITTER

    def test_async_act_without_tx(self) -> None:
        """Test async_act sets None tx_submitter when no tx is built."""
        sent_payloads: list = []

        def fake_send(payload: Any) -> Any:
            sent_payloads.append(payload)
            return None
            yield  # noqa

        with (
            patch.object(self.behaviour, "_prepare_multisend", new=make_gen(None)),
            patch.object(self.behaviour, "send_a2a_transaction", new=fake_send),
            patch.object(self.behaviour, "wait_until_round_end", new=make_gen(None)),
            patch.object(self.behaviour, "set_done") as mock_set_done,
        ):
            gen = self.behaviour.async_act()
            exhaust_gen(gen)
            mock_set_done.assert_called_once()
        assert len(sent_payloads) == 1
        assert sent_payloads[0].tx_hash is None
        assert sent_payloads[0].tx_submitter is None


class TestGetHeldPositions:
    """Tests for _get_held_positions subgraph pagination."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.behaviour: Any = _build_behaviour()

    def test_get_held_positions_empty(self) -> None:
        """Test _get_held_positions when CT subgraph returns no user positions."""
        response: dict = {"data": {"user": {"userPositions": []}}}
        with patch.object(
            self.behaviour,
            "get_conditional_tokens_subgraph_result",
            new=make_gen(response),
        ):
            gen = self.behaviour._get_held_positions()
            result = exhaust_gen(gen)
        assert result == {}

    def test_get_held_positions_user_none(self) -> None:
        """Test _get_held_positions when user is None (no user found)."""
        response = {"data": {"user": None}}
        with patch.object(
            self.behaviour,
            "get_conditional_tokens_subgraph_result",
            new=make_gen(response),
        ):
            gen = self.behaviour._get_held_positions()
            result = exhaust_gen(gen)
        assert result == {}

    def test_get_held_positions_single_page(self) -> None:
        """Test _get_held_positions with a single page of results."""
        response = {
            "data": {
                "user": {
                    "userPositions": [
                        {
                            "id": "pos1",
                            "balance": "100",
                            "position": {
                                "conditionIds": ["0xCond1"],
                                "indexSets": ["1", "2"],
                            },
                        }
                    ]
                }
            }
        }
        with patch.object(
            self.behaviour,
            "get_conditional_tokens_subgraph_result",
            new=make_gen(response),
        ):
            gen = self.behaviour._get_held_positions()
            result = exhaust_gen(gen)
        assert "0xcond1" in result
        assert result["0xcond1"] == {1, 2}

    def test_get_held_positions_pagination(self) -> None:
        """Test _get_held_positions paginates through multiple pages."""
        page1 = [
            {
                "id": f"pos{i}",
                "balance": "100",
                "position": {
                    "conditionIds": [f"0xCond{i}"],
                    "indexSets": ["1"],
                },
            }
            for i in range(SUBGRAPH_PAGE_SIZE)
        ]
        page2 = [
            {
                "id": "posFinal",
                "balance": "50",
                "position": {
                    "conditionIds": ["0xCondFinal"],
                    "indexSets": ["2"],
                },
            }
        ]

        call_count = 0

        def mock_subgraph(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"data": {"user": {"userPositions": page1}}}
            return {"data": {"user": {"userPositions": page2}}}
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_conditional_tokens_subgraph_result",
            new=mock_subgraph,
        ):
            gen = self.behaviour._get_held_positions()
            result = exhaust_gen(gen)
        assert "0xcondfinal" in result
        assert len(result) == SUBGRAPH_PAGE_SIZE + 1

    def test_get_held_positions_duplicate_condition_id(self) -> None:
        """Test _get_held_positions merges index sets for duplicate condition IDs."""
        response = {
            "data": {
                "user": {
                    "userPositions": [
                        {
                            "id": "pos1",
                            "balance": "100",
                            "position": {
                                "conditionIds": ["0xCond1"],
                                "indexSets": ["1"],
                            },
                        },
                        {
                            "id": "pos2",
                            "balance": "200",
                            "position": {
                                "conditionIds": ["0xCond1"],
                                "indexSets": ["2"],
                            },
                        },
                    ]
                }
            }
        }
        with patch.object(
            self.behaviour,
            "get_conditional_tokens_subgraph_result",
            new=make_gen(response),
        ):
            gen = self.behaviour._get_held_positions()
            result = exhaust_gen(gen)
        assert "0xcond1" in result
        assert result["0xcond1"] == {1, 2}

    def test_get_held_positions_subgraph_failure(self) -> None:
        """Test _get_held_positions returns empty on subgraph failure."""
        with patch.object(
            self.behaviour,
            "get_conditional_tokens_subgraph_result",
            new=make_gen(None),
        ):
            gen = self.behaviour._get_held_positions()
            result = exhaust_gen(gen)
        assert result == {}


class TestGetMarketsForConditions:
    """Tests for _get_markets_for_conditions Omen subgraph queries."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.behaviour: Any = _build_behaviour()

    def test_get_markets_for_conditions_empty(self) -> None:
        """Test _get_markets_for_conditions with no condition_ids."""
        gen = self.behaviour._get_markets_for_conditions([])
        result = exhaust_gen(gen)
        assert result == []

    def test_get_markets_for_conditions_success(self) -> None:
        """Test _get_markets_for_conditions returns markets for valid conditions."""
        response = {
            "data": {
                "fixedProductMarketMakers": [
                    {
                        "id": "0xMarket1",
                        "payouts": ["1", "0"],
                        "templateId": "2",
                        "question": {"id": "0xq1", "data": "question?"},
                        "conditions": [{"id": "0xCond1", "outcomeSlotCount": 2}],
                    }
                ]
            }
        }
        with patch.object(
            self.behaviour,
            "get_omen_subgraph_result",
            new=make_gen(response),
        ):
            gen = self.behaviour._get_markets_for_conditions(["0xCond1"])
            result = exhaust_gen(gen)
        assert len(result) == 1
        assert result[0]["address"] == "0xMarket1"
        assert result[0]["condition_id"] == "0xCond1"

    def test_get_markets_for_conditions_dedup(self) -> None:
        """Test _get_markets_for_conditions deduplicates market addresses."""
        entry = {
            "id": "0xMarket1",
            "payouts": ["1", "0"],
            "templateId": "2",
            "question": {"id": "0xq1", "data": "q"},
            "conditions": [{"id": "0xCond1", "outcomeSlotCount": 2}],
        }
        response = {"data": {"fixedProductMarketMakers": [entry, entry]}}
        with patch.object(
            self.behaviour,
            "get_omen_subgraph_result",
            new=make_gen(response),
        ):
            gen = self.behaviour._get_markets_for_conditions(["0xCond1"])
            result = exhaust_gen(gen)
        assert len(result) == 1

    @pytest.mark.parametrize(
        "description,market_entry",
        [
            (
                "no positive payouts",
                {
                    "id": "0xM1",
                    "payouts": ["0", "0"],
                    "templateId": None,
                    "question": {"id": "0xq1", "data": "q"},
                    "conditions": [{"id": "0xC1", "outcomeSlotCount": 2}],
                },
            ),
            (
                "null payouts",
                {
                    "id": "0xM1",
                    "payouts": None,
                    "templateId": "0",
                    "question": None,
                    "conditions": [{"id": "0xC1", "outcomeSlotCount": 2}],
                },
            ),
            (
                "empty conditions",
                {
                    "id": "0xM1",
                    "payouts": ["1", "0"],
                    "templateId": "2",
                    "question": {"id": "0xq1", "data": "q"},
                    "conditions": [],
                },
            ),
            (
                "null outcomeSlotCount",
                {
                    "id": "0xM1",
                    "payouts": ["1", "0"],
                    "templateId": "2",
                    "question": {"id": "0xq1", "data": "q"},
                    "conditions": [{"id": "0xC1", "outcomeSlotCount": None}],
                },
            ),
        ],
    )
    def test_get_markets_for_conditions_filtered(
        self, description: str, market_entry: dict
    ) -> None:
        """Test _get_markets_for_conditions filters out invalid entries."""
        response = {"data": {"fixedProductMarketMakers": [market_entry]}}
        with patch.object(
            self.behaviour,
            "get_omen_subgraph_result",
            new=make_gen(response),
        ):
            gen = self.behaviour._get_markets_for_conditions(["0xC1"])
            result = exhaust_gen(gen)
        assert result == []

    def test_get_markets_for_conditions_subgraph_failure(self) -> None:
        """Test _get_markets_for_conditions continues on subgraph failure."""
        with patch.object(
            self.behaviour,
            "get_omen_subgraph_result",
            new=make_gen(None),
        ):
            gen = self.behaviour._get_markets_for_conditions(["0xC1"])
            result = exhaust_gen(gen)
        assert result == []

    def test_get_markets_for_conditions_batching(self) -> None:
        """Test _get_markets_for_conditions batches condition IDs."""
        # Create more than CONDITION_ID_BATCH_SIZE condition IDs to trigger batching
        condition_ids = [f"0xCond{i}" for i in range(CONDITION_ID_BATCH_SIZE + 1)]

        call_count = 0

        def mock_subgraph(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "data": {
                        "fixedProductMarketMakers": [
                            {
                                "id": "0xM1",
                                "payouts": ["1", "0"],
                                "templateId": "2",
                                "question": {"id": "0xq1", "data": "q"},
                                "conditions": [
                                    {"id": "0xCond0", "outcomeSlotCount": 2}
                                ],
                            }
                        ]
                    }
                }
            return {"data": {"fixedProductMarketMakers": []}}
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_omen_subgraph_result",
            new=mock_subgraph,
        ):
            gen = self.behaviour._get_markets_for_conditions(condition_ids)
            result = exhaust_gen(gen)
        assert call_count == 2  # Two batches
        assert len(result) == 1

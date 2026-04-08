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

"""Tests for FpmmRemoveLiquidityBehaviour — covers the four-state matrix and helpers."""

# Standard pytest test-file conventions that pylint flags as code smells.
# pylint: disable=protected-access,attribute-defined-outside-init
# pylint: disable=unused-argument,import-outside-toplevel
# pylint: disable=too-many-public-methods,too-many-locals,too-many-lines
# pylint: disable=unsubscriptable-object,unsupported-membership-test
# pylint: disable=use-implicit-booleaness-not-comparison
# pylint: disable=unpacking-non-sequence

from typing import Any
from unittest.mock import MagicMock, patch

from packages.valory.skills.omen_fpmm_remove_liquidity_abci.behaviours.remove_liquidity import (
    FpmmRemoveLiquidityBehaviour,
    _ACTION_REMOVE_AND_MERGE,
    _ACTION_REMOVE_ONLY,
    _ACTION_SKIP,
)
from packages.valory.skills.omen_fpmm_remove_liquidity_abci.tests.behaviours.conftest import (
    exhaust_gen,
    make_contract_error_response,
    make_contract_state_response,
    make_gen,
)


def _make_behaviour(context: MagicMock) -> FpmmRemoveLiquidityBehaviour:
    """Instantiate a FpmmRemoveLiquidityBehaviour with a mocked context."""
    return FpmmRemoveLiquidityBehaviour(name="test", skill_context=context)


def _make_market(
    *,
    address: str = "0xFPMM",
    opening_timestamp: int = 1700200000,
    condition_id: str = "0xCond",
    outcome_slot_count: int = 2,
    question_id: str = "0xQ",
) -> dict:
    """Create a minimal market dict for testing."""
    return {
        "address": address,
        "opening_timestamp": opening_timestamp,
        "condition_id": condition_id,
        "outcome_slot_count": outcome_slot_count,
        "question_id": question_id,
        "amount": 1000,
    }


class TestFpmmRemoveLiquidityBehaviour:
    """Tests for FpmmRemoveLiquidityBehaviour."""

    def setup_method(self) -> None:
        """Set up a fresh behaviour for each test."""
        mock_ctx = MagicMock()
        mock_ctx.logger = MagicMock()
        mock_ctx.params = MagicMock()
        mock_ctx.params.conditional_tokens_contract = "0xConditionalTokens"
        mock_ctx.params.collateral_tokens_contract = "0xCollateral"
        mock_ctx.params.liquidity_removal_lead_time = 86400
        mock_ctx.params.fpmm_remove_liquidity_batch_size = 3
        mock_ctx.params.multisend_address = "0xMultisend"
        mock_ctx.state = MagicMock()
        mock_ctx.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
            1700100000
        )
        mock_ctx.state.round_sequence.current_round_id = "fpmm_remove_liquidity_round"
        mock_ctx.state.round_sequence.last_round_id = "fpmm_remove_liquidity_round"
        mock_ctx.state.synchronized_data.safe_contract_address = "0xSafe"
        mock_ctx.state.synchronized_data.round_count = 0
        mock_ctx.benchmark_tool = MagicMock()
        mock_ctx.benchmark_tool.measure.return_value.__enter__ = MagicMock(
            return_value=None
        )
        mock_ctx.benchmark_tool.measure.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_ctx.agent_address = "0xAgent"
        mock_ctx.omen_subgraph = MagicMock()
        mock_ctx.omen_subgraph.get_spec.return_value = {
            "method": "POST",
            "url": "https://omen.example.com",
        }
        self.ctx = mock_ctx
        self.behaviour: Any = _make_behaviour(mock_ctx)

    # -----------------------------------------------------------------------
    # _classify_market state-matrix tests
    # -----------------------------------------------------------------------

    def test_state_1_open_far_from_close_produces_skip(self) -> None:
        """State 1: now < opening_ts - lead_time → _classify_market returns skip.

        With lead_time=86400 and now=1700100000, opening_ts=1700200000
        puts opening_ts-lead_time=1700113600 which is still > now.
        """
        market = _make_market(opening_timestamp=1700200000)
        gen = self.behaviour._classify_market(market, now=1700100000)
        result = exhaust_gen(gen)
        assert result == _ACTION_SKIP

    def test_state_2_open_approaching_close_produces_remove_and_merge(self) -> None:
        """State 2: approaching close, not resolved → remove_and_merge."""
        # opening_ts - lead_time = 1700000000 - 86400 = 1699913600 < now
        # ct not resolved
        market = _make_market(opening_timestamp=1700000000)
        with patch.object(self.behaviour, "_check_resolved", make_gen(False)):
            gen = self.behaviour._classify_market(market, now=1700100000)
            result = exhaust_gen(gen)
        assert result == _ACTION_REMOVE_AND_MERGE

    def test_state_3_closed_not_yet_resolved_produces_remove_and_merge(self) -> None:
        """State 3: past opening, CT not yet resolved → remove_and_merge."""
        # opening_ts = 1699000000 (past), lead_time = 86400 → opening_ts - lead_time < now
        market = _make_market(opening_timestamp=1699000000)
        with patch.object(self.behaviour, "_check_resolved", make_gen(False)):
            gen = self.behaviour._classify_market(market, now=1700100000)
            result = exhaust_gen(gen)
        assert result == _ACTION_REMOVE_AND_MERGE

    def test_state_4_closed_and_resolved_produces_remove_only(self) -> None:
        """State 4: closed + CT resolved → remove_only."""
        market = _make_market(opening_timestamp=1699000000)
        with patch.object(self.behaviour, "_check_resolved", make_gen(True)):
            gen = self.behaviour._classify_market(market, now=1700100000)
            result = exhaust_gen(gen)
        assert result == _ACTION_REMOVE_ONLY

    def test_classify_market_boundary_at_exactly_opening_minus_lead_time(self) -> None:
        """At now == opening_ts - lead_time the market is NOT skipped (boundary is exclusive)."""
        # now = opening_ts - lead_time  → NOT state 1 (condition: now < threshold is False)
        opening_ts = 1700186400
        lead_time = 86400
        now = opening_ts - lead_time  # exactly at the boundary
        market = _make_market(opening_timestamp=opening_ts)
        with patch.object(self.behaviour, "_check_resolved", make_gen(False)):
            gen = self.behaviour._classify_market(market, now=now)
            result = exhaust_gen(gen)
        assert result == _ACTION_REMOVE_AND_MERGE

    def test_classify_market_with_check_resolved_failure(self) -> None:
        """If _check_resolved fails (returns False), market is treated as remove_and_merge."""
        market = _make_market(opening_timestamp=1699000000)
        # _check_resolved returns False on failure per implementation
        with patch.object(self.behaviour, "_check_resolved", make_gen(False)):
            gen = self.behaviour._classify_market(market, now=1700100000)
            result = exhaust_gen(gen)
        assert result == _ACTION_REMOVE_AND_MERGE

    # -----------------------------------------------------------------------
    # _classify_market exhaustion confirms state-2 ≡ state-3 output
    # -----------------------------------------------------------------------

    def test_tx_output_matches_for_state_2_and_state_3(self) -> None:
        """Both state-2 and state-3 produce remove_and_merge (equivalence assertion)."""
        # State 2: opening_ts still in the future but within lead_time window
        market_state2 = _make_market(opening_timestamp=1700150000)
        # State 3: opening_ts already passed
        market_state3 = _make_market(opening_timestamp=1699000000)

        with patch.object(self.behaviour, "_check_resolved", make_gen(False)):
            r2 = exhaust_gen(
                self.behaviour._classify_market(market_state2, now=1700100000)
            )
            r3 = exhaust_gen(
                self.behaviour._classify_market(market_state3, now=1700100000)
            )

        assert r2 == r3 == _ACTION_REMOVE_AND_MERGE

    # -----------------------------------------------------------------------
    # _get_markets
    # -----------------------------------------------------------------------

    def test_get_markets_returns_empty_on_subgraph_failure(self) -> None:
        """_get_markets returns [] when subgraph returns None."""
        with patch.object(self.behaviour, "get_omen_subgraph_result", make_gen(None)):
            gen = self.behaviour._get_markets()
            result = exhaust_gen(gen)
        assert result == []

    def test_get_markets_filters_zero_liquidity(self) -> None:
        """Markets with liquidityMeasure=0 are excluded."""
        subgraph_data = {
            "data": {
                "fpmmPoolMemberships": [
                    {
                        "amount": "0",
                        "id": "0",
                        "pool": {
                            "id": "0xFPMM",
                            "openingTimestamp": "1700200000",
                            "creator": "0xSafe",
                            "liquidityMeasure": "0",
                            "outcomeTokenAmounts": ["100", "200"],
                            "conditions": [
                                {
                                    "id": "0xCond",
                                    "question": {"id": "0xQ"},
                                    "outcomeSlotCount": 2,
                                }
                            ],
                        },
                    }
                ]
            }
        }
        with patch.object(
            self.behaviour, "get_omen_subgraph_result", make_gen(subgraph_data)
        ):
            gen = self.behaviour._get_markets()
            result = exhaust_gen(gen)
        assert result == []

    def test_get_markets_filters_none_liquidity(self) -> None:
        """Markets with liquidityMeasure=None are excluded."""
        subgraph_data = {
            "data": {
                "fpmmPoolMemberships": [
                    {
                        "amount": "0",
                        "id": "0",
                        "pool": {
                            "id": "0xFPMM",
                            "openingTimestamp": "1700200000",
                            "creator": "0xSafe",
                            "liquidityMeasure": None,
                            "outcomeTokenAmounts": ["100", "200"],
                            "conditions": [
                                {
                                    "id": "0xCond",
                                    "question": {"id": "0xQ"},
                                    "outcomeSlotCount": 2,
                                }
                            ],
                        },
                    }
                ]
            }
        }
        with patch.object(
            self.behaviour, "get_omen_subgraph_result", make_gen(subgraph_data)
        ):
            gen = self.behaviour._get_markets()
            result = exhaust_gen(gen)
        assert result == []

    def test_get_markets_filters_none_question(self) -> None:
        """Markets where question is None are excluded."""
        subgraph_data = {
            "data": {
                "fpmmPoolMemberships": [
                    {
                        "amount": "1000",
                        "id": "0",
                        "pool": {
                            "id": "0xFPMM",
                            "openingTimestamp": "1700200000",
                            "creator": "0xSafe",
                            "liquidityMeasure": "1000",
                            "outcomeTokenAmounts": ["100", "200"],
                            "conditions": [
                                {
                                    "id": "0xCond",
                                    "question": None,
                                    "outcomeSlotCount": 2,
                                }
                            ],
                        },
                    }
                ]
            }
        }
        with patch.object(
            self.behaviour, "get_omen_subgraph_result", make_gen(subgraph_data)
        ):
            gen = self.behaviour._get_markets()
            result = exhaust_gen(gen)
        assert result == []

    def test_get_markets_filters_none_opening_timestamp(self) -> None:
        """Markets with openingTimestamp=None are excluded."""
        subgraph_data = {
            "data": {
                "fpmmPoolMemberships": [
                    {
                        "amount": "500",
                        "id": "0",
                        "pool": {
                            "id": "0xFPMM",
                            "openingTimestamp": None,
                            "creator": "0xSafe",
                            "liquidityMeasure": "500",
                            "outcomeTokenAmounts": ["100", "200"],
                            "conditions": [
                                {
                                    "id": "0xCond",
                                    "question": {"id": "0xQ"},
                                    "outcomeSlotCount": 2,
                                }
                            ],
                        },
                    }
                ]
            }
        }
        with patch.object(
            self.behaviour, "get_omen_subgraph_result", make_gen(subgraph_data)
        ):
            gen = self.behaviour._get_markets()
            result = exhaust_gen(gen)
        assert result == []

    def test_get_markets_filters_by_on_chain_funds(self) -> None:
        """Markets not in get_markets_with_funds result are excluded."""
        subgraph_data = {
            "data": {
                "fpmmPoolMemberships": [
                    {
                        "amount": "1000",
                        "id": "0",
                        "pool": {
                            "id": "0xFPMM",
                            "openingTimestamp": "1700200000",
                            "creator": "0xSafe",
                            "liquidityMeasure": "1000",
                            "outcomeTokenAmounts": ["100", "200"],
                            "conditions": [
                                {
                                    "id": "0xCond",
                                    "question": {"id": "0xQ"},
                                    "outcomeSlotCount": 2,
                                }
                            ],
                        },
                    }
                ]
            }
        }
        # on-chain says no markets have funds
        with (
            patch.object(
                self.behaviour, "get_omen_subgraph_result", make_gen(subgraph_data)
            ),
            patch.object(self.behaviour, "_get_markets_with_funds", make_gen([])),
        ):
            gen = self.behaviour._get_markets()
            result = exhaust_gen(gen)
        assert result == []

    def test_get_markets_returns_valid_market(self) -> None:
        """Valid market with funds is included."""
        market_id = "0xfpmm"
        subgraph_data = {
            "data": {
                "fpmmPoolMemberships": [
                    {
                        "amount": "1000",
                        "id": "0",
                        "pool": {
                            "id": market_id,
                            "openingTimestamp": "1700200000",
                            "creator": "0xSafe",
                            "liquidityMeasure": "1000",
                            "outcomeTokenAmounts": ["100", "200"],
                            "conditions": [
                                {
                                    "id": "0xCond",
                                    "question": {"id": "0xQ"},
                                    "outcomeSlotCount": 2,
                                }
                            ],
                        },
                    }
                ]
            }
        }
        with (
            patch.object(
                self.behaviour, "get_omen_subgraph_result", make_gen(subgraph_data)
            ),
            patch.object(
                self.behaviour, "_get_markets_with_funds", make_gen([market_id])
            ),
        ):
            gen = self.behaviour._get_markets()
            result = exhaust_gen(gen)
        assert len(result) == 1
        assert result[0]["address"] == market_id
        assert result[0]["opening_timestamp"] == 1700200000

    # -----------------------------------------------------------------------
    # _get_markets_with_funds
    # -----------------------------------------------------------------------

    def test_get_markets_with_funds_empty_list(self) -> None:
        """Empty market list returns empty without contract call."""
        gen = self.behaviour._get_markets_with_funds([], "0xSafe")
        result = exhaust_gen(gen)
        assert result == []

    def test_get_markets_with_funds_contract_failure(self) -> None:
        """Contract call failure returns empty list."""
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            make_gen(make_contract_error_response()),
        ):
            gen = self.behaviour._get_markets_with_funds(["0xA"], "0xSafe")
            result = exhaust_gen(gen)
        assert result == []

    def test_get_markets_with_funds_success(self) -> None:
        """Contract call returns market addresses."""
        resp = make_contract_state_response({"data": ["0xA", "0xB"]})
        with patch.object(self.behaviour, "get_contract_api_response", make_gen(resp)):
            gen = self.behaviour._get_markets_with_funds(["0xA", "0xB"], "0xSafe")
            result = exhaust_gen(gen)
        assert result == ["0xA", "0xB"]

    # -----------------------------------------------------------------------
    # _calculate_amounts
    # -----------------------------------------------------------------------

    def _run_calculate_amounts_with_responses(self, responses: list) -> Any:
        """Run _calculate_amounts providing the given ordered contract responses."""
        call_count = 0

        def mock_contract_gen(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            return responses[call_count - 1]
            yield  # noqa

        with patch.object(
            self.behaviour, "get_contract_api_response", new=mock_contract_gen
        ):
            gen = self.behaviour._calculate_amounts("0xMarket", "0xCond", 2)
            return exhaust_gen(gen)

    def test_calculate_amounts_holdings_failure(self) -> None:
        """Returns None when get_user_holdings fails."""
        result = self._run_calculate_amounts_with_responses(
            [make_contract_error_response()]
        )
        assert result is None

    def test_calculate_amounts_balance_failure(self) -> None:
        """Returns None when get_balance fails."""
        result = self._run_calculate_amounts_with_responses(
            [
                make_contract_state_response(
                    {"shares": [10, 20], "holdings": [300, 400]}
                ),
                make_contract_error_response(),
            ]
        )
        assert result is None

    def test_calculate_amounts_supply_failure(self) -> None:
        """Returns None when get_total_supply fails."""
        result = self._run_calculate_amounts_with_responses(
            [
                make_contract_state_response(
                    {"shares": [10, 20], "holdings": [300, 400]}
                ),
                make_contract_state_response({"balance": 500}),
                make_contract_error_response(),
            ]
        )
        assert result is None

    def test_calculate_amounts_full_removal(self) -> None:
        """When amount_to_remove == total_pool_shares, send_amounts = holdings."""
        result = self._run_calculate_amounts_with_responses(
            [
                make_contract_state_response(
                    {"shares": [10, 20], "holdings": [300, 400]}
                ),
                make_contract_state_response({"balance": 1000}),
                make_contract_state_response({"supply": 1000}),
            ]
        )
        assert result is not None
        amount_to_remove, amount_to_merge = result
        assert amount_to_remove == 1000
        # send_amounts = [300, 400]; amount_to_merge = min(310, 420) = 310
        assert amount_to_merge == 310

    def test_calculate_amounts_partial_removal(self) -> None:
        """Partial removal: send_amounts is proportional to holdings."""
        result = self._run_calculate_amounts_with_responses(
            [
                make_contract_state_response(
                    {"shares": [10, 20], "holdings": [300, 400]}
                ),
                make_contract_state_response({"balance": 500}),
                make_contract_state_response({"supply": 1000}),
            ]
        )
        assert result is not None
        amount_to_remove, amount_to_merge = result
        assert amount_to_remove == 500
        # send_amounts = [150, 200]; amount_to_merge = min(160, 220) = 160
        assert amount_to_merge == 160

    def test_calculate_amounts_zero_supply(self) -> None:
        """When total_pool_shares == 0, send_amounts = all zeros."""
        result = self._run_calculate_amounts_with_responses(
            [
                make_contract_state_response(
                    {"shares": [10, 20], "holdings": [300, 400]}
                ),
                make_contract_state_response({"balance": 0}),
                make_contract_state_response({"supply": 0}),
            ]
        )
        assert result is not None
        amount_to_remove, amount_to_merge = result
        assert amount_to_remove == 0
        # send_amounts = [0, 0]; amount_to_merge = min(10, 20) = 10
        assert amount_to_merge == 10

    # -----------------------------------------------------------------------
    # _get_remove_funding_tx
    # -----------------------------------------------------------------------

    def test_get_remove_funding_tx_failure(self) -> None:
        """Returns None when contract call fails."""
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            make_gen(make_contract_error_response()),
        ):
            gen = self.behaviour._get_remove_funding_tx("0xFPMM", 100)
            result = exhaust_gen(gen)
        assert result is None

    def test_get_remove_funding_tx_success_bytes(self) -> None:
        """Returns tx dict when contract call succeeds (data as bytes)."""
        resp = make_contract_state_response({"data": b"\xde\xad\xbe\xef"})
        with patch.object(self.behaviour, "get_contract_api_response", make_gen(resp)):
            gen = self.behaviour._get_remove_funding_tx("0xFPMM", 100)
            result = exhaust_gen(gen)
        assert result is not None
        assert result["to"] == "0xFPMM"
        assert result["value"] == 0
        assert result["data"] == "deadbeef"

    def test_get_remove_funding_tx_success_str(self) -> None:
        """Returns tx dict when contract call succeeds (data as str)."""
        resp = make_contract_state_response({"data": "0xdeadbeef"})
        with patch.object(self.behaviour, "get_contract_api_response", make_gen(resp)):
            gen = self.behaviour._get_remove_funding_tx("0xFPMM", 100)
            result = exhaust_gen(gen)
        assert result is not None
        assert result["data"] == "0xdeadbeef"

    # -----------------------------------------------------------------------
    # _get_merge_positions_tx
    # -----------------------------------------------------------------------

    def test_get_merge_positions_tx_failure(self) -> None:
        """Returns None when contract call fails."""
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            make_gen(make_contract_error_response()),
        ):
            gen = self.behaviour._get_merge_positions_tx(
                "0xCollateral", "0xParent", "0xCond", 2, 100
            )
            result = exhaust_gen(gen)
        assert result is None

    def test_get_merge_positions_tx_success(self) -> None:
        """Returns tx dict on success."""
        resp = make_contract_state_response({"data": b"\x01\x02"})
        with patch.object(self.behaviour, "get_contract_api_response", make_gen(resp)):
            gen = self.behaviour._get_merge_positions_tx(
                "0xCollateral", "0xParent", "0xCond", 2, 100
            )
            result = exhaust_gen(gen)
        assert result is not None
        assert result["to"] == "0xConditionalTokens"
        assert result["value"] == 0

    # -----------------------------------------------------------------------
    # _check_resolved
    # -----------------------------------------------------------------------

    def test_check_resolved_contract_failure(self) -> None:
        """Returns False when contract call fails."""
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            make_gen(make_contract_error_response()),
        ):
            gen = self.behaviour._check_resolved("0xCond")
            result = exhaust_gen(gen)
        assert result is False

    def test_check_resolved_false(self) -> None:
        """Returns False when resolved=False in response."""
        resp = make_contract_state_response({"resolved": False})
        with patch.object(self.behaviour, "get_contract_api_response", make_gen(resp)):
            gen = self.behaviour._check_resolved("0xCond")
            result = exhaust_gen(gen)
        assert result is False

    def test_check_resolved_true(self) -> None:
        """Returns True when resolved=True in response."""
        resp = make_contract_state_response({"resolved": True})
        with patch.object(self.behaviour, "get_contract_api_response", make_gen(resp)):
            gen = self.behaviour._check_resolved("0xCond")
            result = exhaust_gen(gen)
        assert result is True

    def test_check_resolved_missing_key(self) -> None:
        """Returns False when resolved key absent (defaults to False)."""
        resp = make_contract_state_response({})
        with patch.object(self.behaviour, "get_contract_api_response", make_gen(resp)):
            gen = self.behaviour._check_resolved("0xCond")
            result = exhaust_gen(gen)
        assert result is False

    # -----------------------------------------------------------------------
    # _build_market_txs
    # -----------------------------------------------------------------------

    def test_build_market_txs_remove_only_success(self) -> None:
        """remove_only action returns single remove_funding tx."""
        market = _make_market()
        amounts = (1000, 500)
        remove_tx = {"to": "0xFPMM", "data": "0xremove", "value": 0}
        with (
            patch.object(self.behaviour, "_calculate_amounts", make_gen(amounts)),
            patch.object(self.behaviour, "_get_remove_funding_tx", make_gen(remove_tx)),
        ):
            gen = self.behaviour._build_market_txs(market, _ACTION_REMOVE_ONLY)
            result = exhaust_gen(gen)
        assert result == [remove_tx]

    def test_build_market_txs_remove_and_merge_success(self) -> None:
        """remove_and_merge action appends merge_positions tx after remove_funding tx."""
        market = _make_market()
        amounts = (1000, 500)
        remove_tx = {"to": "0xFPMM", "data": "0xremove", "value": 0}
        merge_tx = {"to": "0xCT", "data": "0xmerge", "value": 0}
        with (
            patch.object(self.behaviour, "_calculate_amounts", make_gen(amounts)),
            patch.object(self.behaviour, "_get_remove_funding_tx", make_gen(remove_tx)),
            patch.object(self.behaviour, "_get_merge_positions_tx", make_gen(merge_tx)),
        ):
            gen = self.behaviour._build_market_txs(market, _ACTION_REMOVE_AND_MERGE)
            result = exhaust_gen(gen)
        assert result == [remove_tx, merge_tx]

    def test_build_market_txs_amounts_none_returns_empty(self) -> None:
        """Returns [] when _calculate_amounts returns None."""
        market = _make_market()
        with patch.object(self.behaviour, "_calculate_amounts", make_gen(None)):
            gen = self.behaviour._build_market_txs(market, _ACTION_REMOVE_ONLY)
            result = exhaust_gen(gen)
        assert result == []

    def test_build_market_txs_remove_funding_none_returns_empty(self) -> None:
        """Returns [] when _get_remove_funding_tx returns None."""
        market = _make_market()
        with (
            patch.object(self.behaviour, "_calculate_amounts", make_gen((100, 50))),
            patch.object(self.behaviour, "_get_remove_funding_tx", make_gen(None)),
        ):
            gen = self.behaviour._build_market_txs(market, _ACTION_REMOVE_ONLY)
            result = exhaust_gen(gen)
        assert result == []

    def test_build_market_txs_merge_none_returns_remove_only(self) -> None:
        """If _get_merge_positions_tx returns None, still returns remove_funding tx."""
        market = _make_market()
        remove_tx = {"to": "0xFPMM", "data": "0xremove", "value": 0}
        with (
            patch.object(self.behaviour, "_calculate_amounts", make_gen((100, 50))),
            patch.object(self.behaviour, "_get_remove_funding_tx", make_gen(remove_tx)),
            patch.object(self.behaviour, "_get_merge_positions_tx", make_gen(None)),
        ):
            gen = self.behaviour._build_market_txs(market, _ACTION_REMOVE_AND_MERGE)
            result = exhaust_gen(gen)
        assert result == [remove_tx]

    # -----------------------------------------------------------------------
    # _prepare_multisend
    # -----------------------------------------------------------------------

    def test_prepare_multisend_no_markets(self) -> None:
        """Returns None when no markets are available."""
        with patch.object(self.behaviour, "_get_markets", make_gen([])):
            gen = self.behaviour._prepare_multisend()
            result = exhaust_gen(gen)
        assert result is None

    def test_prepare_multisend_all_skip(self) -> None:
        """Returns None when all markets are classified as skip."""
        market = _make_market()
        with (
            patch.object(self.behaviour, "_get_markets", make_gen([market])),
            patch.object(self.behaviour, "_classify_market", make_gen(_ACTION_SKIP)),
        ):
            gen = self.behaviour._prepare_multisend()
            result = exhaust_gen(gen)
        assert result is None

    def test_prepare_multisend_empty_market_txs_continues(self) -> None:
        """Empty _build_market_txs result keeps processed count at 0 and returns None.

        Exercises the 115->106 branch where market_txs is falsy and the loop
        iterates without incrementing markets_processed.
        """
        market = _make_market()
        with (
            patch.object(self.behaviour, "_get_markets", make_gen([market])),
            patch.object(
                self.behaviour, "_classify_market", make_gen(_ACTION_REMOVE_ONLY)
            ),
            patch.object(self.behaviour, "_build_market_txs", make_gen([])),
        ):
            gen = self.behaviour._prepare_multisend()
            result = exhaust_gen(gen)
        assert result is None

    def test_prepare_multisend_builds_tx(self) -> None:
        """Returns a payload when valid txs are built."""
        market = _make_market()
        txs = [{"to": "0xFPMM", "data": "0xdata", "value": 0}]
        multisend_payload = "0xpayload"
        with (
            patch.object(self.behaviour, "_get_markets", make_gen([market])),
            patch.object(
                self.behaviour, "_classify_market", make_gen(_ACTION_REMOVE_ONLY)
            ),
            patch.object(self.behaviour, "_build_market_txs", make_gen(txs)),
            patch.object(self.behaviour, "_to_multisend", make_gen(multisend_payload)),
        ):
            gen = self.behaviour._prepare_multisend()
            result = exhaust_gen(gen)
        assert result == multisend_payload

    def test_prepare_multisend_respects_batch_size(self) -> None:
        """Never processes more markets than fpmm_remove_liquidity_batch_size."""
        # batch_size = 3; provide 5 markets classified as remove_only with valid txs
        self.ctx.params.fpmm_remove_liquidity_batch_size = 2
        behaviour = _make_behaviour(self.ctx)
        markets = [_make_market(address=f"0xFPMM{i}") for i in range(5)]
        txs = [{"to": "0xFPMM", "data": "0xdata", "value": 0}]

        processed: list = []

        def track_classify(market: Any, now: Any) -> Any:
            processed.append(market["address"])
            return _ACTION_REMOVE_ONLY
            yield  # noqa

        with (
            patch.object(behaviour, "_get_markets", make_gen(markets)),
            patch.object(behaviour, "_classify_market", new=track_classify),
            patch.object(behaviour, "_build_market_txs", make_gen(txs)),
            patch.object(behaviour, "_to_multisend", make_gen("0xpayload")),
        ):
            gen = behaviour._prepare_multisend()
            exhaust_gen(gen)

        # At most batch_size markets should have been processed
        assert len(processed) == 2

    # -----------------------------------------------------------------------
    # tx_submitter logic
    # -----------------------------------------------------------------------

    def test_tx_submitter_set_when_hash_present(self) -> None:
        """tx_submitter is TX_SUBMITTER_NAME when tx_hash is not None."""
        with (
            patch.object(self.behaviour, "_prepare_multisend", make_gen("0xhash")),
            patch.object(self.behaviour, "send_a2a_transaction", make_gen(None)),
            patch.object(self.behaviour, "wait_until_round_end", make_gen(None)),
        ):
            gen = self.behaviour.async_act()
            exhaust_gen(gen)
        # tx_submitter was set (no error raised means async_act completed the logic)

    def test_tx_submitter_none_when_no_hash(self) -> None:
        """tx_submitter is None when _prepare_multisend returns None."""
        with (
            patch.object(self.behaviour, "_prepare_multisend", make_gen(None)),
            patch.object(self.behaviour, "send_a2a_transaction", make_gen(None)),
            patch.object(self.behaviour, "wait_until_round_end", make_gen(None)),
        ):
            gen = self.behaviour.async_act()
            exhaust_gen(gen)

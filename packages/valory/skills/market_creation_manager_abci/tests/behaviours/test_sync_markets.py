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

"""Tests for SyncMarketsBehaviour."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.sync_markets import (
    FPMM_POOL_MEMBERSHIPS_QUERY,
    SyncMarketsBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.states.sync_markets import (
    SyncMarketsRound,
)


def _make_gen(return_value: Any) -> Any:
    """Create a no-yield generator returning the given value."""

    def gen(*args: Any, **kwargs: Any) -> Any:
        return return_value
        yield  # noqa: unreachable - makes this a generator function

    return gen


def _exhaust_gen(gen: Any) -> Any:
    """Exhaust a generator and return its value."""
    try:
        while True:
            next(gen)
    except StopIteration as e:
        return e.value


def _make_pool_entry(
    pool_id: str = "0xMarket1",
    liquidity: str = "1000",
    opening_ts: str = "1700200000",
    has_question: bool = True,
) -> Any:
    """Create a sample fpmmPoolMemberships entry."""
    condition = {
        "id": "0xCondition1",
        "outcomeSlotCount": 2,
    }
    if has_question:
        condition["question"] = {"id": "0xQuestion1"}
    else:
        condition["question"] = None

    return {
        "amount": "500",
        "id": f"{pool_id}-member",
        "pool": {
            "id": pool_id,
            "openingTimestamp": opening_ts,
            "creator": "0xCreator",
            "conditions": [condition],
            "liquidityMeasure": liquidity,
            "outcomeTokenAmounts": ["300", "200"],
        },
    }


class TestSyncMarketsBehaviour:
    """Tests for SyncMarketsBehaviour."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.synchronized_data = MagicMock()
        context_mock.state.synchronized_data.safe_contract_address = "0xSafe"
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        self.behaviour = SyncMarketsBehaviour(name="test", skill_context=context_mock)

    def test_get_markets_subgraph_none(self) -> None:
        """Test get_markets when subgraph returns None."""
        with patch.object(
            self.behaviour,
            "get_subgraph_result",
            new=_make_gen(None),
        ):
            gen = self.behaviour.get_markets()
            result = _exhaust_gen(gen)

        assert result == ([], 0)

    def test_get_markets_filters_no_liquidity_measure(self) -> None:
        """Test get_markets filters out market without liquidityMeasure."""
        entry = _make_pool_entry()
        entry["pool"]["liquidityMeasure"] = None

        subgraph_response = {"data": {"fpmmPoolMemberships": [entry]}}

        contract_resp = MagicMock()
        contract_resp.performative = ContractApiMessage.Performative.STATE
        contract_resp.state.body = {"data": []}

        with (
            patch.object(
                self.behaviour,
                "get_subgraph_result",
                new=_make_gen(subgraph_response),
            ),
            patch.object(
                self.behaviour,
                "get_contract_api_response",
                new=_make_gen(contract_resp),
            ),
        ):
            gen = self.behaviour.get_markets()
            result = _exhaust_gen(gen)

        markets, from_block = result
        assert len(markets) == 0

    def test_get_markets_filters_zero_liquidity(self) -> None:
        """Test get_markets filters out market with 0 liquidity."""
        entry = _make_pool_entry(liquidity="0")

        subgraph_response = {"data": {"fpmmPoolMemberships": [entry]}}

        contract_resp = MagicMock()
        contract_resp.performative = ContractApiMessage.Performative.STATE
        contract_resp.state.body = {"data": []}

        with (
            patch.object(
                self.behaviour,
                "get_subgraph_result",
                new=_make_gen(subgraph_response),
            ),
            patch.object(
                self.behaviour,
                "get_contract_api_response",
                new=_make_gen(contract_resp),
            ),
        ):
            gen = self.behaviour.get_markets()
            result = _exhaust_gen(gen)

        markets, from_block = result
        assert len(markets) == 0

    def test_get_markets_filters_no_opening_timestamp(self) -> None:
        """Test get_markets filters out market without openingTimestamp."""
        entry = _make_pool_entry()
        entry["pool"]["openingTimestamp"] = None

        subgraph_response = {"data": {"fpmmPoolMemberships": [entry]}}

        contract_resp = MagicMock()
        contract_resp.performative = ContractApiMessage.Performative.STATE
        contract_resp.state.body = {"data": []}

        with (
            patch.object(
                self.behaviour,
                "get_subgraph_result",
                new=_make_gen(subgraph_response),
            ),
            patch.object(
                self.behaviour,
                "get_contract_api_response",
                new=_make_gen(contract_resp),
            ),
        ):
            gen = self.behaviour.get_markets()
            result = _exhaust_gen(gen)

        markets, from_block = result
        assert len(markets) == 0

    def test_get_markets_filters_no_question(self) -> None:
        """Test get_markets filters out condition without question."""
        entry = _make_pool_entry(has_question=False)

        subgraph_response = {"data": {"fpmmPoolMemberships": [entry]}}

        contract_resp = MagicMock()
        contract_resp.performative = ContractApiMessage.Performative.STATE
        contract_resp.state.body = {"data": []}

        with (
            patch.object(
                self.behaviour,
                "get_subgraph_result",
                new=_make_gen(subgraph_response),
            ),
            patch.object(
                self.behaviour,
                "get_contract_api_response",
                new=_make_gen(contract_resp),
            ),
        ):
            gen = self.behaviour.get_markets()
            result = _exhaust_gen(gen)

        markets, from_block = result
        assert len(markets) == 0

    def test_get_markets_success(self) -> None:
        """Test get_markets with valid markets returned."""
        entry = _make_pool_entry(pool_id="0xMarket1")

        subgraph_response = {"data": {"fpmmPoolMemberships": [entry]}}

        contract_resp = MagicMock()
        contract_resp.performative = ContractApiMessage.Performative.STATE
        contract_resp.state.body = {"data": ["0xMarket1"]}

        with (
            patch.object(
                self.behaviour,
                "get_subgraph_result",
                new=_make_gen(subgraph_response),
            ),
            patch.object(
                self.behaviour,
                "get_contract_api_response",
                new=_make_gen(contract_resp),
            ),
        ):
            gen = self.behaviour.get_markets()
            result = _exhaust_gen(gen)

        markets, from_block = result
        assert len(markets) == 1
        assert markets[0]["address"] == "0xMarket1"
        assert markets[0]["condition_id"] == "0xCondition1"
        assert markets[0]["question_id"] == "0xQuestion1"
        assert from_block == 0

    def test_get_markets_with_funds_empty(self) -> None:
        """Test _get_markets_with_funds with no market addresses."""
        gen = self.behaviour._get_markets_with_funds([], "0xSafe")
        result = _exhaust_gen(gen)

        assert result == []

    def test_get_markets_with_funds_success(self) -> None:
        """Test _get_markets_with_funds with successful contract response."""
        contract_resp = MagicMock()
        contract_resp.performative = ContractApiMessage.Performative.STATE
        contract_resp.state.body = {"data": ["0xMarket1", "0xMarket2"]}

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(contract_resp),
        ):
            gen = self.behaviour._get_markets_with_funds(
                ["0xMarket1", "0xMarket2", "0xMarket3"], "0xSafe"
            )
            result = _exhaust_gen(gen)

        assert result == ["0xMarket1", "0xMarket2"]

    def test_get_markets_with_funds_contract_fail(self) -> None:
        """Test _get_markets_with_funds when contract returns wrong performative."""
        contract_resp = MagicMock()
        contract_resp.performative = ContractApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(contract_resp),
        ):
            gen = self.behaviour._get_markets_with_funds(["0xMarket1"], "0xSafe")
            result = _exhaust_gen(gen)

        assert result == []

    def test_get_payload_error(self) -> None:
        """Test get_payload when get_markets returns None."""
        with patch.object(
            self.behaviour,
            "get_markets",
            new=_make_gen(None),
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result == SyncMarketsRound.ERROR_PAYLOAD

    def test_get_payload_no_markets(self) -> None:
        """Test get_payload when get_markets returns empty list."""
        with patch.object(
            self.behaviour,
            "get_markets",
            new=_make_gen(([], 0)),
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result == SyncMarketsRound.NO_UPDATE_PAYLOAD

    def test_get_payload_success(self) -> None:
        """Test get_payload with valid markets."""
        markets = [{"address": "0xMarket1", "amount": 500}]

        with patch.object(
            self.behaviour,
            "get_markets",
            new=_make_gen((markets, 0)),
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        parsed = json.loads(result)
        assert "markets" in parsed
        assert "from_block" in parsed
        assert len(parsed["markets"]) == 1
        assert parsed["from_block"] == 0

    def test_fpmm_pool_query_template(self) -> None:
        """Test that FPMM_POOL_MEMBERSHIPS_QUERY template contains expected fields."""
        template_str = FPMM_POOL_MEMBERSHIPS_QUERY.template
        assert "fpmmPoolMemberships" in template_str
        assert "$creator" in template_str
        assert "liquidityMeasure" in template_str
        assert "openingTimestamp" in template_str
        assert "outcomeSlotCount" in template_str
        assert "outcomeTokenAmounts" in template_str

    def test_async_act(self) -> None:
        """Test async_act wraps get_payload correctly."""
        with (
            patch.object(
                self.behaviour,
                "get_payload",
                new=_make_gen(SyncMarketsRound.NO_UPDATE_PAYLOAD),
            ),
            patch.object(self.behaviour, "send_a2a_transaction", new=_make_gen(None)),
            patch.object(self.behaviour, "wait_until_round_end", new=_make_gen(None)),
            patch.object(self.behaviour, "set_done") as mock_set_done,
        ):
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)
            mock_set_done.assert_called_once()

    def test_get_markets_market_not_in_funds_list(self) -> None:
        """Test get_markets when market address not in get_markets_with_funds result."""
        entry = _make_pool_entry(pool_id="0xMarketNotFunded")

        subgraph_response = {"data": {"fpmmPoolMemberships": [entry]}}

        contract_resp = MagicMock()
        contract_resp.performative = ContractApiMessage.Performative.STATE
        contract_resp.state.body = {"data": ["0xOtherMarket"]}

        with (
            patch.object(
                self.behaviour,
                "get_subgraph_result",
                new=_make_gen(subgraph_response),
            ),
            patch.object(
                self.behaviour,
                "get_contract_api_response",
                new=_make_gen(contract_resp),
            ),
        ):
            gen = self.behaviour.get_markets()
            result = _exhaust_gen(gen)

        markets, from_block = result
        assert len(markets) == 0

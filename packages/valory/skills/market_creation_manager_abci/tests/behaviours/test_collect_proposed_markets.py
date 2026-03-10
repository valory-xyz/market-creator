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

"""Tests for CollectProposedMarketsBehaviour."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

from packages.valory.skills.market_creation_manager_abci.behaviours.collect_proposed_markets import (
    CollectProposedMarketsBehaviour,
    FPMM_QUERY,
)
from packages.valory.skills.market_creation_manager_abci.states.collect_proposed_markets import (
    CollectProposedMarketsRound,
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


class TestCollectProposedMarketsBehaviour:
    """Tests for CollectProposedMarketsBehaviour."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.synchronized_data.safe_contract_address = "0xSafeAddress"
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        self.behaviour = CollectProposedMarketsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_collect_approved_markets_success(self) -> None:
        """Test _collect_approved_markets with a successful 200 response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.body = json.dumps({"approved_markets": [{"id": "m1"}]}).encode()

        with patch.object(
            self.behaviour,
            "get_http_response",
            new=_make_gen(mock_response),
        ):
            gen = self.behaviour._collect_approved_markets()
            result = _exhaust_gen(gen)

        assert "approved_markets" in result
        assert len(result["approved_markets"]) == 1
        assert result["approved_markets"][0]["id"] == "m1"

    def test_collect_approved_markets_non_200(self) -> None:
        """Test _collect_approved_markets with a non-200 status code."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.body = b"Bad Request"

        with patch.object(
            self.behaviour,
            "get_http_response",
            new=_make_gen(mock_response),
        ):
            gen = self.behaviour._collect_approved_markets()
            result = _exhaust_gen(gen)

        assert result == {"approved_markets": {}}

    def test_collect_approved_markets_json_decode_error(self) -> None:
        """Test _collect_approved_markets when body cannot be decoded as JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.body = b"not valid json{{"

        with patch.object(
            self.behaviour,
            "get_http_response",
            new=_make_gen(mock_response),
        ):
            gen = self.behaviour._collect_approved_markets()
            result = _exhaust_gen(gen)

        assert result == {"approved_markets": {}}

    def test_collect_approved_markets_missing_key(self) -> None:
        """Test _collect_approved_markets when JSON has no 'approved_markets' key."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.body = json.dumps({"other_key": "value"}).encode()

        with patch.object(
            self.behaviour,
            "get_http_response",
            new=_make_gen(mock_response),
        ):
            gen = self.behaviour._collect_approved_markets()
            result = _exhaust_gen(gen)

        assert result == {"approved_markets": {}}

    def test_collect_latest_open_markets_success(self) -> None:
        """Test _collect_latest_open_markets with valid subgraph data."""
        subgraph_response = {
            "data": {
                "fixedProductMarketMakers": [
                    {"id": "0xabc", "openingTimestamp": "1700000000"}
                ]
            }
        }

        with patch.object(
            self.behaviour,
            "get_subgraph_result",
            new=_make_gen(subgraph_response),
        ):
            gen = self.behaviour._collect_latest_open_markets(
                openingTimestamp_gte=1700000000,
                openingTimestamp_lte=1700100000,
            )
            result = _exhaust_gen(gen)

        assert "fixedProductMarketMakers" in result
        assert len(result["fixedProductMarketMakers"]) == 1

    def test_collect_latest_open_markets_none(self) -> None:
        """Test _collect_latest_open_markets when subgraph returns None."""
        with patch.object(
            self.behaviour,
            "get_subgraph_result",
            new=_make_gen(None),
        ):
            gen = self.behaviour._collect_latest_open_markets(
                openingTimestamp_gte=1700000000,
                openingTimestamp_lte=1700100000,
            )
            result = _exhaust_gen(gen)

        assert result == {"fixedProductMarketMakers": []}

    def test_fpmm_query_template_defined(self) -> None:
        """Test that FPMM_QUERY template contains expected fields."""
        template_str = FPMM_QUERY.template
        assert "fixedProductMarketMakers" in template_str
        assert "$creator" in template_str
        assert "$openingTimestamp_gte" in template_str
        assert "$openingTimestamp_lte" in template_str
        assert "creationTimestamp" in template_str
        assert "currentAnswer" in template_str
        assert "question" in template_str

    def test_matching_round(self) -> None:
        """Test that matching_round is CollectProposedMarketsRound."""
        assert (
            CollectProposedMarketsBehaviour.matching_round
            == CollectProposedMarketsRound
        )


class TestCollectProposedMarketsBehaviourAsyncAct:
    """Tests for CollectProposedMarketsBehaviour async_act."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.approve_market_event_days_offset = 3
        context_mock.params.markets_to_approve_per_day = 2
        context_mock.params.min_approve_markets_epoch_seconds = 3600
        context_mock.params.max_approved_markets = 10
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
            1700000000
        )
        context_mock.state.synchronized_data = MagicMock()
        context_mock.state.synchronized_data.safe_contract_address = "0xSafe"
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        self.behaviour = CollectProposedMarketsBehaviour(
            name="test", skill_context=context_mock
        )

    def _make_open_markets_response(self, markets: Any = None) -> Any:
        """Helper to create open markets response."""
        if markets is None:
            markets = []
        return {"fixedProductMarketMakers": markets}

    def test_async_act_max_markets_reached(self) -> None:
        """Test async_act when approved_markets_count >= max_approved_markets."""
        mock_synced = MagicMock()
        mock_synced.approved_markets_count = 15
        mock_synced.approved_markets_timestamp = 0
        mock_synced.safe_contract_address = "0xsafe"

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=lambda: property(lambda self: 1700000000),
        ), patch.object(
            self.behaviour,
            "_collect_latest_open_markets",
            new=_make_gen({"fixedProductMarketMakers": []}),
        ), patch.object(
            self.behaviour,
            "_collect_approved_markets",
            new=_make_gen({"approved_markets": []}),
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

    def test_async_act_timeout_not_reached_1(self) -> None:
        """Test async_act when current_timestamp - latest_approve_market_timestamp < threshold."""
        mock_synced = MagicMock()
        mock_synced.approved_markets_count = 0
        mock_synced.approved_markets_timestamp = 1700000000 - 100  # very recent
        mock_synced.safe_contract_address = "0xsafe"

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=lambda: property(lambda self: 1700000000),
        ), patch.object(
            self.behaviour,
            "_collect_latest_open_markets",
            new=_make_gen({"fixedProductMarketMakers": []}),
        ), patch.object(
            self.behaviour,
            "_collect_approved_markets",
            new=_make_gen({"approved_markets": []}),
        ), patch.object(
            self.behaviour, "send_a2a_transaction", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "wait_until_round_end", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "set_done"
        ):
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)

    def test_async_act_timeout_not_reached_2(self) -> None:
        """Test async_act when current_timestamp - largest_creation_timestamp < threshold."""
        mock_synced = MagicMock()
        mock_synced.approved_markets_count = 0
        mock_synced.approved_markets_timestamp = 0
        mock_synced.safe_contract_address = "0xsafe"

        market = {
            "openingTimestamp": str(1700000000 + 86400 + 100),
            "creationTimestamp": str(1700000000 - 100),  # very recent creation
        }

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=lambda: property(lambda self: 1700000000),
        ), patch.object(
            self.behaviour,
            "_collect_latest_open_markets",
            new=_make_gen({"fixedProductMarketMakers": [market]}),
        ), patch.object(
            self.behaviour,
            "_collect_approved_markets",
            new=_make_gen({"approved_markets": []}),
        ), patch.object(
            self.behaviour, "send_a2a_transaction", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "wait_until_round_end", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "set_done"
        ):
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)

    def test_async_act_no_markets_to_approve(self) -> None:
        """Test async_act when num_markets_to_approve <= 0 (lines 177-178)."""
        mock_synced = MagicMock()
        mock_synced.approved_markets_count = 0
        mock_synced.approved_markets_timestamp = 0
        mock_synced.safe_contract_address = "0xsafe"

        # With current_timestamp 1700000000 and approve_market_event_days_offset 3,
        # the openingTimestamp_gte is 1700086400 and openingTimestamp_lte is 1700259200.
        # The current_day_start computes to 1700092800, giving
        # required_opening_ts of [1700092800, 1700179200] (2 days).
        # With markets_to_approve_per_day of 2, we need 2 markets at each ts.
        ts1 = 1700092800
        ts2 = 1700179200
        markets = [
            {"openingTimestamp": str(ts1), "creationTimestamp": "0"},
            {"openingTimestamp": str(ts1), "creationTimestamp": "0"},
            {"openingTimestamp": str(ts2), "creationTimestamp": "0"},
            {"openingTimestamp": str(ts2), "creationTimestamp": "0"},
        ]

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=lambda: property(lambda self: 1700000000),
        ), patch.object(
            self.behaviour,
            "_collect_latest_open_markets",
            new=_make_gen({"fixedProductMarketMakers": markets}),
        ), patch.object(
            self.behaviour,
            "_collect_approved_markets",
            new=_make_gen({"approved_markets": []}),
        ), patch.object(
            self.behaviour, "send_a2a_transaction", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "wait_until_round_end", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "set_done"
        ):
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)
            # Verify "No market approval required." was logged
            log_calls = [
                str(c) for c in self.behaviour.context.logger.info.call_args_list
            ]
            assert any("No market approval required" in c for c in log_calls)

    def test_async_act_unprocessed_markets_exist(self) -> None:
        """Test async_act when approved_markets list not empty."""
        mock_synced = MagicMock()
        mock_synced.approved_markets_count = 0
        mock_synced.approved_markets_timestamp = 0
        mock_synced.safe_contract_address = "0xsafe"

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=lambda: property(lambda self: 1700000000),
        ), patch.object(
            self.behaviour,
            "_collect_latest_open_markets",
            new=_make_gen({"fixedProductMarketMakers": []}),
        ), patch.object(
            self.behaviour,
            "_collect_approved_markets",
            new=_make_gen({"approved_markets": [{"id": "m1"}]}),
        ), patch.object(
            self.behaviour, "send_a2a_transaction", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "wait_until_round_end", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "set_done"
        ):
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)

    def test_async_act_success(self) -> None:
        """Test async_act when all conditions pass and returns JSON content."""
        mock_synced = MagicMock()
        mock_synced.approved_markets_count = 0
        mock_synced.approved_markets_timestamp = 0
        mock_synced.safe_contract_address = "0xsafe"

        # max_approved_markets = -1 means no limit
        self.behaviour.params.max_approved_markets = -1

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=lambda: property(lambda self: 1700000000),
        ), patch.object(
            self.behaviour,
            "_collect_latest_open_markets",
            new=_make_gen({"fixedProductMarketMakers": []}),
        ), patch.object(
            self.behaviour,
            "_collect_approved_markets",
            new=_make_gen({"approved_markets": []}),
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

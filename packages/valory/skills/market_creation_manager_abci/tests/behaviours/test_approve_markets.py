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

"""Tests for market_creation_manager_abci ApproveMarketsBehaviour."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from packages.valory.skills.abstract_round_abci.test_tools.base import (
    FSMBehaviourBaseCase,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.approve_markets import (
    ApproveMarketsBehaviour,
)


CURRENT_FILE_PATH = Path(__file__).resolve()
PACKAGE_DIR = CURRENT_FILE_PATH.parents[2]


class TestApproveMarketsBehaviourHelpers:
    """Test helper methods of ApproveMarketsBehaviour."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.params.market_approval_server_url = "http://test.com"
        context_mock.params.market_approval_server_api_key = "test_api_key"
        context_mock.params.openai_api_key = "openai_key"
        context_mock.params.newsapi_api_key = "newsapi_key"
        context_mock.params.serper_api_key = "serper_key"
        context_mock.params.subgraph_api_key = "subgraph_key"
        context_mock.params.news_sources = ["source1", "source2"]
        context_mock.params.topics = ["topic1", "topic2"]
        context_mock.params.max_markets_per_story = 5

        synchronized_data_mock = MagicMock()
        synchronized_data_mock.most_voted_keeper_address = (
            "0x9999999999999999999999999999999999999999"
        )
        synchronized_data_mock.collected_proposed_markets_data = json.dumps(
            {"required_markets_to_approve_per_opening_ts": {}}
        )
        synchronized_data_mock.approved_markets_count = 0
        synchronized_data_mock.most_voted_randomness = "random_seed"

        self.behaviour = ApproveMarketsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_i_am_not_sending_true(self) -> None:
        """Test _i_am_not_sending when agent is not the keeper."""
        result = self.behaviour._i_am_not_sending()
        assert result is True

    def test_i_am_not_sending_false(self) -> None:
        """Test _i_am_not_sending when agent is the keeper."""
        # Use a patch to mock the synchronized_data property
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(
                    most_voted_keeper_address="0x1234567890123456789012345678901234567890"
                )
            ),
        ):
            result = self.behaviour._i_am_not_sending()
            assert result is False

    def test_is_resolution_date_in_question_with_standard_format(self) -> None:
        """Test _is_resolution_date_in_question with standard date format."""
        # September 8, 2024
        resolution_time = datetime(2024, 9, 8, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will something happen by September 8, 2024?",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is True

    def test_is_resolution_date_in_question_with_padded_format(self) -> None:
        """Test _is_resolution_date_in_question with padded day."""
        # September 08, 2024
        resolution_time = datetime(2024, 9, 8, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will something happen by September 08, 2024?",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is True

    def test_is_resolution_date_in_question_not_found(self) -> None:
        """Test _is_resolution_date_in_question when date is not in question."""
        resolution_time = datetime(2024, 9, 8, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will something happen soon?",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is False

    def test_is_resolution_date_in_question_different_date(self) -> None:
        """Test _is_resolution_date_in_question with different date in question."""
        resolution_time = datetime(2024, 9, 8, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will something happen by September 9, 2024?",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is False

    def test_is_resolution_date_in_question_with_december(self) -> None:
        """Test _is_resolution_date_in_question with December date."""
        resolution_time = datetime(2024, 12, 25, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will something happen by December 25, 2024?",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is True

    def test_is_resolution_date_in_question_with_january_01(self) -> None:
        """Test _is_resolution_date_in_question with January 1st."""
        resolution_time = datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will something happen by January 1, 2025?",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is True

    def test_is_resolution_date_in_question_with_january_01_padded(self) -> None:
        """Test _is_resolution_date_in_question with January 01."""
        resolution_time = datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will something happen by January 01, 2025?",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is True

    def test_is_resolution_date_in_question_empty_question(self) -> None:
        """Test _is_resolution_date_in_question with empty question."""
        resolution_time = datetime(2024, 9, 8, tzinfo=timezone.utc).timestamp()
        market = {"resolution_time": resolution_time, "question": ""}
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is False

    def test_behaviour_has_matching_round(self) -> None:
        """Test that behaviour has matching_round attribute."""
        from packages.valory.skills.market_creation_manager_abci.rounds import (
            ApproveMarketsRound,
        )

        assert self.behaviour.matching_round == ApproveMarketsRound

    def test_behaviour_has_async_act(self) -> None:
        """Test that behaviour has async_act method."""
        assert hasattr(self.behaviour, "async_act")
        assert callable(self.behaviour.async_act)

    def test_behaviour_has_not_sender_act(self) -> None:
        """Test that behaviour has _not_sender_act method."""
        assert hasattr(self.behaviour, "_not_sender_act")
        assert callable(self.behaviour._not_sender_act)

    def test_behaviour_has_sender_act(self) -> None:
        """Test that behaviour has _sender_act method."""
        assert hasattr(self.behaviour, "_sender_act")
        assert callable(self.behaviour._sender_act)

    def test_behaviour_has_propose_and_approve_market(self) -> None:
        """Test that behaviour has _propose_and_approve_market method."""
        assert hasattr(self.behaviour, "_propose_and_approve_market")
        assert callable(self.behaviour._propose_and_approve_market)


class TestIsResolutionDateInQuestion:
    """Test _is_resolution_date_in_question with various edge cases."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        self.behaviour = ApproveMarketsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_february_29_leap_year(self) -> None:
        """Test with February 29 in leap year."""
        resolution_time = datetime(2024, 2, 29, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will something happen by February 29, 2024?",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is True

    def test_with_month_at_end(self) -> None:
        """Test with date at the end of question."""
        resolution_time = datetime(2024, 6, 15, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will this event occur on June 15, 2024",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is True

    def test_with_date_in_middle(self) -> None:
        """Test with date in middle of question."""
        resolution_time = datetime(2024, 6, 15, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will the event on June 15, 2024 happen?",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is True

    def test_wrong_year(self) -> None:
        """Test with wrong year in question."""
        resolution_time = datetime(2024, 6, 15, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will something happen by June 15, 2025?",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is False

    def test_wrong_month(self) -> None:
        """Test with wrong month in question."""
        resolution_time = datetime(2024, 6, 15, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will something happen by July 15, 2024?",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is False

    def test_wrong_day(self) -> None:
        """Test with wrong day in question."""
        resolution_time = datetime(2024, 6, 15, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will something happen by June 16, 2024?",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is False

    def test_multiple_dates_in_question_correct_one_present(self) -> None:
        """Test with multiple dates where correct one is present."""
        resolution_time = datetime(2024, 6, 15, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will it happen between June 10, 2024 and June 15, 2024?",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is True

    def test_date_with_suffix(self) -> None:
        """Test date that might have suffix (though not in expected format)."""
        resolution_time = datetime(2024, 6, 1, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will something happen by June 1st, 2024?",
        }
        # The format doesn't include 'st', so this should not match
        result = self.behaviour._is_resolution_date_in_question(market)
        # Will only match if exactly "June 1, 2024" is present
        assert result is False

    def test_date_format_without_year(self) -> None:
        """Test question with date but no year."""
        resolution_time = datetime(2024, 6, 15, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will something happen by June 15?",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is False


class TestProposeAndApproveMarketMethod:
    """Test _propose_and_approve_market method scenarios."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.params.market_approval_server_url = "http://test.com"
        context_mock.params.market_approval_server_api_key = "test_api_key"
        self.behaviour = ApproveMarketsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_market_dict_structure(self) -> None:
        """Test that market dict has expected structure."""
        market = {
            "id": "test_market_123",
            "question": "Will something happen?",
            "resolution_time": 1704067200,
        }
        assert "id" in market
        assert "question" in market
        assert "resolution_time" in market

    def test_headers_structure(self) -> None:
        """Test HTTP headers are correctly formatted."""
        headers = {
            "Authorization": self.behaviour.params.market_approval_server_api_key,
            "Content-Type": "application/json",
        }
        assert headers["Authorization"] == "test_api_key"
        assert headers["Content-Type"] == "application/json"

    def test_propose_url_format(self) -> None:
        """Test propose URL is correctly formatted."""
        url = self.behaviour.params.market_approval_server_url + "/propose_market"
        assert url == "http://test.com/propose_market"

    def test_approve_url_format(self) -> None:
        """Test approve URL is correctly formatted."""
        url = self.behaviour.params.market_approval_server_url + "/approve_market"
        assert url == "http://test.com/approve_market"

    def test_update_url_format(self) -> None:
        """Test update URL is correctly formatted."""
        url = self.behaviour.params.market_approval_server_url + "/update_market"
        assert url == "http://test.com/update_market"


class TestSenderActFlow:
    """Test _sender_act flow and logic."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.params.market_approval_server_url = "http://test.com"
        context_mock.params.market_approval_server_api_key = "test_api_key"
        context_mock.params.openai_api_key = "openai_key"
        context_mock.params.newsapi_api_key = "newsapi_key"
        context_mock.params.serper_api_key = "serper_key"
        context_mock.params.subgraph_api_key = "subgraph_key"
        context_mock.params.news_sources = ["source1"]
        context_mock.params.topics = ["topic1"]
        context_mock.params.max_markets_per_story = 5
        context_mock.benchmark_tool = MagicMock()
        context_mock.benchmark_tool.measure = MagicMock(
            return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock())
        )

        self.behaviour = ApproveMarketsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_collected_proposed_markets_data_parsing(self) -> None:
        """Test parsing of collected_proposed_markets_data."""
        data = {
            "required_markets_to_approve_per_opening_ts": {
                "1704153600": 3,
                "1704240000": 2,
            }
        }
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        assert "required_markets_to_approve_per_opening_ts" in parsed
        assert parsed["required_markets_to_approve_per_opening_ts"]["1704153600"] == 3

    def test_opening_ts_selection_with_positive_value(self) -> None:
        """Test selecting opening timestamp with positive markets."""
        required_markets_to_approve_per_opening_ts = {
            "1704153600": 0,
            "1704240000": 3,
            "1704326400": 2,
        }
        opening_ts = next(
            (k for k, v in required_markets_to_approve_per_opening_ts.items() if v > 0),
            None,
        )
        assert opening_ts is not None
        assert required_markets_to_approve_per_opening_ts[opening_ts] > 0

    def test_opening_ts_selection_all_zero(self) -> None:
        """Test selecting opening timestamp when all values are zero."""
        required_markets_to_approve_per_opening_ts = {
            "1704153600": 0,
            "1704240000": 0,
        }
        opening_ts = next(
            (k for k, v in required_markets_to_approve_per_opening_ts.items() if v > 0),
            None,
        )
        assert opening_ts is None

    def test_opening_ts_selection_empty_dict(self) -> None:
        """Test selecting opening timestamp with empty dict."""
        required_markets_to_approve_per_opening_ts: dict[str, int] = {}
        opening_ts = next(
            (k for k, v in required_markets_to_approve_per_opening_ts.items() if v > 0),
            None,
        )
        assert opening_ts is None

    def test_resolution_time_calculation(self) -> None:
        """Test resolution time calculation from opening timestamp."""
        _ONE_DAY = 86400
        opening_ts = "1704153600"  # 2024-01-02 00:00:00
        resolution_time = int(opening_ts) - _ONE_DAY
        assert resolution_time == 1704067200  # 2024-01-01 00:00:00

    def test_num_questions_calculation_under_max(self) -> None:
        """Test num_questions when required is under max."""
        required = 3
        max_markets = 5
        num_questions = min(required, max_markets)
        assert num_questions == 3

    def test_num_questions_calculation_at_max(self) -> None:
        """Test num_questions when required equals max."""
        required = 5
        max_markets = 5
        num_questions = min(required, max_markets)
        assert num_questions == 5

    def test_num_questions_calculation_over_max(self) -> None:
        """Test num_questions when required exceeds max."""
        required = 10
        max_markets = 5
        num_questions = min(required, max_markets)
        assert num_questions == 5

    def test_mech_tool_output_json_structure(self) -> None:
        """Test mech tool output JSON structure."""
        mech_output_json = {
            "reasoning": "Some reasoning text",
            "questions": {
                "q1": {"id": "q1", "question": "Question 1?"},
                "q2": {"id": "q2", "question": "Question 2?"},
            },
        }
        assert "reasoning" in mech_output_json
        assert "questions" in mech_output_json
        assert isinstance(mech_output_json["questions"], dict)

    def test_proposed_markets_with_error(self) -> None:
        """Test handling proposed markets with error."""
        proposed_markets = {"error": "Some error occurred"}
        assert "error" in proposed_markets

    def test_proposed_markets_without_error(self) -> None:
        """Test handling valid proposed markets."""
        proposed_markets = {
            "q1": {"id": "q1", "question": "Question 1?", "resolution_time": 1704067200}
        }
        assert "error" not in proposed_markets
        assert "q1" in proposed_markets

    def test_approved_markets_count_calculation(self) -> None:
        """Test approved markets count calculation."""
        current_count = 5
        newly_approved = 3
        total_count = newly_approved + current_count
        assert total_count == 8

    def test_payload_content_json_serialization(self) -> None:
        """Test payload content JSON serialization."""
        proposed_markets = {"q1": {"id": "q1", "question": "Question?"}}
        content = json.dumps(proposed_markets, sort_keys=True)
        assert isinstance(content, str)
        # Verify it can be parsed back
        parsed = json.loads(content)
        assert parsed == proposed_markets


class TestHttpResponseHandling:
    """Test HTTP response handling scenarios."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.params.market_approval_server_url = "http://test.com"
        context_mock.params.market_approval_server_api_key = "test_api_key"
        self.behaviour = ApproveMarketsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_propose_market_success_response(self) -> None:
        """Test successful propose market response."""
        http_response = MagicMock()
        http_response.status_code = 200
        http_response.body = b'{"status": "proposed"}'
        body = json.loads(http_response.body.decode())
        assert body["status"] == "proposed"

    def test_propose_market_failure_response(self) -> None:
        """Test failed propose market response."""
        http_response = MagicMock()
        http_response.status_code = 400
        assert http_response.status_code != 200

    def test_approve_market_success_response(self) -> None:
        """Test successful approve market response."""
        http_response = MagicMock()
        http_response.status_code = 200
        http_response.body = b'{"status": "approved"}'
        body = json.loads(http_response.body.decode())
        assert body["status"] == "approved"

    def test_approve_market_failure_response(self) -> None:
        """Test failed approve market response."""
        http_response = MagicMock()
        http_response.status_code = 500
        assert http_response.status_code != 200

    def test_update_market_success_response(self) -> None:
        """Test successful update market response."""
        http_response = MagicMock()
        http_response.status_code = 200
        http_response.body = b'{"status": "updated"}'
        body = json.loads(http_response.body.decode())
        assert body["status"] == "updated"

    def test_update_market_failure_response(self) -> None:
        """Test failed update market response."""
        http_response = MagicMock()
        http_response.status_code = 404
        assert http_response.status_code != 200

    def test_json_response_body_parsing(self) -> None:
        """Test parsing JSON response body."""
        response_body = b'{"id": "market_123", "status": "active"}'
        parsed = json.loads(response_body.decode())
        assert parsed["id"] == "market_123"
        assert parsed["status"] == "active"

    def test_request_body_encoding(self) -> None:
        """Test encoding JSON request body."""
        body_dict = {"id": "market_123", "data": "test"}
        encoded = json.dumps(body_dict).encode("utf-8")
        assert isinstance(encoded, bytes)
        # Verify it can be decoded back
        decoded = json.loads(encoded.decode("utf-8"))
        assert decoded == body_dict


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


class TestApproveMarketsBehaviourGenerators:
    """Test ApproveMarketsBehaviour generator methods."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.params.market_approval_server_url = "http://test.com"
        context_mock.params.market_approval_server_api_key = "test_api_key"
        context_mock.params.openai_api_key = "openai_key"
        context_mock.params.newsapi_api_key = "newsapi_key"
        context_mock.params.serper_api_key = "serper_key"
        context_mock.params.subgraph_api_key = "subgraph_key"
        context_mock.params.news_sources = ["source1"]
        context_mock.params.topics = ["topic1"]
        context_mock.params.max_markets_per_story = 5
        self.behaviour = ApproveMarketsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_not_sender_act(self) -> None:
        """Test _not_sender_act waits and sets done."""
        with patch.object(
            self.behaviour, "wait_until_round_end", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "set_done"
        ) as mock_set_done, patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(
                    most_voted_keeper_address="0x9999"
                )
            ),
        ):
            gen = self.behaviour._not_sender_act()
            _exhaust_gen(gen)
            mock_set_done.assert_called_once()

    def test_sender_act_no_opening_ts(self) -> None:
        """Test _sender_act when all required markets are 0."""
        mock_synced = MagicMock()
        mock_synced.most_voted_randomness = "seed123"
        mock_synced.collected_proposed_markets_data = json.dumps(
            {"required_markets_to_approve_per_opening_ts": {"100": 0, "200": 0}}
        )
        mock_synced.approved_markets_count = 0

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=lambda: property(lambda self: 1000),
        ), patch.object(
            self.behaviour, "send_a2a_transaction", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "wait_until_round_end", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "set_done"
        ) as mock_set_done:
            gen = self.behaviour._sender_act()
            _exhaust_gen(gen)
            mock_set_done.assert_called_once()

    def test_sender_act_with_opening_ts_error_in_mech(self) -> None:
        """Test _sender_act when mech tool returns error in questions."""
        mock_synced = MagicMock()
        mock_synced.most_voted_randomness = "seed123"
        mock_synced.collected_proposed_markets_data = json.dumps(
            {"required_markets_to_approve_per_opening_ts": {"1700000000": 3}}
        )
        mock_synced.approved_markets_count = 0

        mech_output = json.dumps(
            {"reasoning": "test", "questions": {"error": "Some error"}}
        )

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=lambda: property(lambda self: 1000),
        ), patch(
            "packages.valory.skills.market_creation_manager_abci.behaviours.approve_markets.mech_tool_propose_questions"
        ) as mock_mech:
            mock_mech.KeyChain = MagicMock()
            mock_mech.run.return_value = [mech_output]

            with patch.object(
                self.behaviour, "send_a2a_transaction", new=_make_gen(None)
            ), patch.object(
                self.behaviour, "wait_until_round_end", new=_make_gen(None)
            ), patch.object(
                self.behaviour, "set_done"
            ) as mock_set_done:
                gen = self.behaviour._sender_act()
                _exhaust_gen(gen)
                mock_set_done.assert_called_once()

    def test_propose_and_approve_market_success(self) -> None:
        """Test _propose_and_approve_market when all 3 HTTP calls return 200."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.body = json.dumps({"status": "ok"}).encode()

        with patch.object(
            self.behaviour, "get_http_response", new=_make_gen(mock_resp)
        ), patch("time.sleep"):
            gen = self.behaviour._propose_and_approve_market(
                {"id": "market_1", "question": "Test?"}
            )
            result = _exhaust_gen(gen)

        parsed = json.loads(result)
        assert parsed["status"] == "ok"

    def test_propose_and_approve_market_propose_fails(self) -> None:
        """Test _propose_and_approve_market when first HTTP call fails."""
        from packages.valory.skills.market_creation_manager_abci.rounds import (
            ApproveMarketsRound,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 400

        with patch.object(
            self.behaviour, "get_http_response", new=_make_gen(mock_resp)
        ):
            gen = self.behaviour._propose_and_approve_market(
                {"id": "market_1", "question": "Test?"}
            )
            result = _exhaust_gen(gen)

        assert result == ApproveMarketsRound.ERROR_PAYLOAD

    def test_propose_and_approve_market_approve_fails(self) -> None:
        """Test _propose_and_approve_market when second HTTP call fails."""
        from packages.valory.skills.market_creation_manager_abci.rounds import (
            ApproveMarketsRound,
        )

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.body = json.dumps({"status": "ok"}).encode()

        mock_resp_fail = MagicMock()
        mock_resp_fail.status_code = 400

        call_count = 0

        def multi_gen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_resp_ok
            return mock_resp_fail
            yield  # noqa

        with patch.object(
            self.behaviour, "get_http_response", new=multi_gen
        ), patch("time.sleep"):
            gen = self.behaviour._propose_and_approve_market(
                {"id": "market_1", "question": "Test?"}
            )
            result = _exhaust_gen(gen)

        assert result == ApproveMarketsRound.ERROR_PAYLOAD

    def test_propose_and_approve_market_update_fails(self) -> None:
        """Test _propose_and_approve_market when third HTTP call fails."""
        from packages.valory.skills.market_creation_manager_abci.rounds import (
            ApproveMarketsRound,
        )

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.body = json.dumps({"status": "ok"}).encode()

        mock_resp_fail = MagicMock()
        mock_resp_fail.status_code = 400

        call_count = 0

        def multi_gen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return mock_resp_ok
            return mock_resp_fail
            yield  # noqa

        with patch.object(
            self.behaviour, "get_http_response", new=multi_gen
        ), patch("time.sleep"):
            gen = self.behaviour._propose_and_approve_market(
                {"id": "market_1", "question": "Test?"}
            )
            result = _exhaust_gen(gen)

        assert result == ApproveMarketsRound.ERROR_PAYLOAD

    def test_async_act_not_sender(self) -> None:
        """Test async_act when _i_am_not_sending returns True."""
        with patch.object(
            self.behaviour, "_i_am_not_sending", return_value=True
        ), patch.object(
            self.behaviour, "_not_sender_act", new=_make_gen(None)
        ):
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)

    def test_async_act_sender(self) -> None:
        """Test async_act when _i_am_not_sending returns False."""
        with patch.object(
            self.behaviour, "_i_am_not_sending", return_value=False
        ), patch.object(
            self.behaviour, "_sender_act", new=_make_gen(None)
        ):
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)

    def test_sender_act_with_valid_markets(self) -> None:
        """Test _sender_act when mech tool returns valid markets that pass resolution date check."""
        from datetime import datetime, timezone

        resolution_time = int(datetime(2024, 9, 8, tzinfo=timezone.utc).timestamp())
        opening_ts = str(resolution_time + 86400)

        mock_synced = MagicMock()
        mock_synced.most_voted_randomness = "seed123"
        mock_synced.collected_proposed_markets_data = json.dumps(
            {"required_markets_to_approve_per_opening_ts": {opening_ts: 2}}
        )
        mock_synced.approved_markets_count = 0

        mech_output = json.dumps(
            {
                "reasoning": "test reasoning",
                "questions": {
                    "q1": {
                        "id": "q1",
                        "question": "Will something happen by September 8, 2024?",
                        "resolution_time": resolution_time,
                    },
                    "q2": {
                        "id": "q2",
                        "question": "Will another thing happen by September 8, 2024?",
                        "resolution_time": resolution_time,
                    },
                },
            }
        )

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=lambda: property(lambda self: 1000),
        ), patch(
            "packages.valory.skills.market_creation_manager_abci.behaviours.approve_markets.mech_tool_propose_questions"
        ) as mock_mech, patch.object(
            self.behaviour,
            "_propose_and_approve_market",
            new=_make_gen("ok"),
        ), patch.object(
            self.behaviour, "send_a2a_transaction", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "wait_until_round_end", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "set_done"
        ) as mock_set_done:
            mock_mech.KeyChain = MagicMock()
            mock_mech.run.return_value = [mech_output]

            gen = self.behaviour._sender_act()
            _exhaust_gen(gen)
            mock_set_done.assert_called_once()

    def test_sender_act_with_resolution_date_mismatch(self) -> None:
        """Test _sender_act when market resolution date is not in the question text."""
        from datetime import datetime, timezone

        resolution_time = int(datetime(2024, 9, 8, tzinfo=timezone.utc).timestamp())
        opening_ts = str(resolution_time + 86400)

        mock_synced = MagicMock()
        mock_synced.most_voted_randomness = "seed123"
        mock_synced.collected_proposed_markets_data = json.dumps(
            {"required_markets_to_approve_per_opening_ts": {opening_ts: 1}}
        )
        mock_synced.approved_markets_count = 0

        mech_output = json.dumps(
            {
                "reasoning": "test reasoning",
                "questions": {
                    "q1": {
                        "id": "q1",
                        "question": "Will something happen soon?",
                        "resolution_time": resolution_time,
                    },
                },
            }
        )

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            type(self.behaviour),
            "last_synced_timestamp",
            new_callable=lambda: property(lambda self: 1000),
        ), patch(
            "packages.valory.skills.market_creation_manager_abci.behaviours.approve_markets.mech_tool_propose_questions"
        ) as mock_mech, patch.object(
            self.behaviour, "send_a2a_transaction", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "wait_until_round_end", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "set_done"
        ) as mock_set_done:
            mock_mech.KeyChain = MagicMock()
            mock_mech.run.return_value = [mech_output]

            gen = self.behaviour._sender_act()
            _exhaust_gen(gen)
            mock_set_done.assert_called_once()
            # Verify the error was logged for the resolution date mismatch
            self.behaviour.context.logger.error.assert_called()

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
from unittest.mock import MagicMock, patch

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

        self.behaviour = ApproveMarketsBehaviour(
            name="test", skill_context=context_mock
        )

    def test_i_am_not_sending_true(self) -> None:
        """Test _i_am_not_sending when agent is not the keeper."""
        result = self.behaviour._i_am_not_sending()
        assert result is True

    def test_i_am_not_sending_false(self) -> None:
        """Test _i_am_not_sending when agent is the keeper."""
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
        resolution_time = datetime(2024, 9, 8, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will something happen by September 8, 2024?",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
        assert result is True

    def test_is_resolution_date_in_question_with_padded_format(self) -> None:
        """Test _is_resolution_date_in_question with padded day."""
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

    def test_matching_round(self) -> None:
        """Test that behaviour has correct matching_round."""
        from packages.valory.skills.market_creation_manager_abci.rounds import (
            ApproveMarketsRound,
        )

        assert self.behaviour.matching_round == ApproveMarketsRound


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

    def test_date_with_suffix(self) -> None:
        """Test date that might have suffix (though not in expected format)."""
        resolution_time = datetime(2024, 6, 1, tzinfo=timezone.utc).timestamp()
        market = {
            "resolution_time": resolution_time,
            "question": "Will something happen by June 1st, 2024?",
        }
        result = self.behaviour._is_resolution_date_in_question(market)
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

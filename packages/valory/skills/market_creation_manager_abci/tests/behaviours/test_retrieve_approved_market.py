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

"""Tests for RetrieveApprovedMarketBehaviour."""

import json
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from packages.valory.skills.market_creation_manager_abci.behaviours.retrieve_approved_market import (
    RetrieveApprovedMarketBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    RetrieveApprovedMarketRound,
)

CURRENT_FILE_PATH = Path(__file__).resolve()
PACKAGE_DIR = CURRENT_FILE_PATH.parents[2]


def _make_gen(return_value):
    """Create a no-yield generator returning the given value."""

    def gen(*args, **kwargs):
        return return_value
        yield  # noqa: unreachable

    return gen


def _exhaust_gen(gen):
    """Exhaust a generator and return its value."""
    try:
        while True:
            next(gen)
    except StopIteration as e:
        return e.value


class TestRetrieveApprovedMarketBehaviour:
    """Test RetrieveApprovedMarketBehaviour."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.params.market_approval_server_url = "http://test.com"
        context_mock.params.market_approval_server_api_key = "test_key"
        self.behaviour = RetrieveApprovedMarketBehaviour(
            name="test", skill_context=context_mock
        )

    def test_matching_round(self) -> None:
        """Test matching_round is correctly set."""
        assert self.behaviour.matching_round == RetrieveApprovedMarketRound

    def test_i_am_not_sending_true(self) -> None:
        """Test _i_am_not_sending when agent is not keeper."""
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(
                    most_voted_keeper_address="0x9999999999999999999999999999999999999999"
                )
            ),
        ):
            assert self.behaviour._i_am_not_sending() is True

    def test_i_am_not_sending_false(self) -> None:
        """Test _i_am_not_sending when agent is keeper."""
        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(
                    most_voted_keeper_address="0x1234567890123456789012345678901234567890"
                )
            ),
        ):
            assert self.behaviour._i_am_not_sending() is False

    def test_get_process_random_approved_market_success(self) -> None:
        """Test _get_process_random_approved_market with 200 OK response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        response_data = {"id": "m1", "question": "Test?"}
        mock_response.body = json.dumps(response_data).encode()

        with patch.object(
            self.behaviour, "get_http_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._get_process_random_approved_market()
            result = _exhaust_gen(gen)

        parsed = json.loads(result)
        assert parsed["id"] == "m1"

    def test_get_process_random_approved_market_no_content(self) -> None:
        """Test _get_process_random_approved_market with 204 No Content."""
        mock_response = MagicMock()
        mock_response.status_code = 204

        with patch.object(
            self.behaviour, "get_http_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._get_process_random_approved_market()
            result = _exhaust_gen(gen)

        assert result == RetrieveApprovedMarketRound.NO_MARKETS_RETRIEVED_PAYLOAD

    def test_get_process_random_approved_market_error_max_retries(self) -> None:
        """Test _get_process_random_approved_market with error status and max retries reached."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch.object(
            self.behaviour, "get_http_response", new=_make_gen(mock_response)
        ):
            gen = self.behaviour._get_process_random_approved_market()
            result = _exhaust_gen(gen)

        # retries=3 >= MAX_RETRIES=3, so should return MAX_RETRIES_PAYLOAD
        assert result == RetrieveApprovedMarketRound.MAX_RETRIES_PAYLOAD

    def test_not_sender_act(self) -> None:
        """Test _not_sender_act waits for round end."""
        with patch.object(
            self.behaviour, "wait_until_round_end", new=_make_gen(None)
        ), patch.object(self.behaviour, "set_done") as mock_set_done, patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(
                lambda self: MagicMock(
                    most_voted_keeper_address="0x9999999999999999999999999999999999999999"
                )
            ),
        ):
            gen = self.behaviour._not_sender_act()
            _exhaust_gen(gen)
            mock_set_done.assert_called_once()

    def test_sender_act(self) -> None:
        """Test _sender_act sends transaction."""
        mock_response = MagicMock()
        mock_response.status_code = 204

        with patch.object(
            self.behaviour, "get_http_response", new=_make_gen(mock_response)
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

    def test_async_act_not_sender(self) -> None:
        """Test async_act when not sender."""
        with patch.object(
            self.behaviour, "_i_am_not_sending", return_value=True
        ), patch.object(self.behaviour, "_not_sender_act", new=_make_gen(None)):
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)

    def test_async_act_sender(self) -> None:
        """Test async_act when sender."""
        with patch.object(
            self.behaviour, "_i_am_not_sending", return_value=False
        ), patch.object(self.behaviour, "_sender_act", new=_make_gen(None)):
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)

    def test_get_process_random_approved_market_error_below_max_retries(
        self,
    ) -> None:
        """Test _get_process_random_approved_market with error and retries < MAX_RETRIES."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch.object(
            self.behaviour, "get_http_response", new=_make_gen(mock_response)
        ), patch(
            "packages.valory.skills.market_creation_manager_abci.behaviours.retrieve_approved_market.MAX_RETRIES",
            10,
        ):
            gen = self.behaviour._get_process_random_approved_market()
            result = _exhaust_gen(gen)

        assert result == RetrieveApprovedMarketRound.ERROR_PAYLOAD

# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2024 Valory AG
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

"""Tests for the retrieve_approved_market.py module."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    HTTP_OK,
    HTTP_NO_CONTENT,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    RetrieveApprovedMarketPayload,
    RetrieveApprovedMarketRound,
)


# Helper to create mock HTTP response
def mock_http_response(status_code, body_dict=None):
    """Create mock HTTP response with the given status code and body."""
    response = MagicMock()
    response.status_code = status_code
    if body_dict is not None:
        response.body = json.dumps(body_dict).encode("utf-8")
    return response


def dummy_ctx():
    """Create a dummy context for testing."""
    context = MagicMock()
    context.benchmark_tool.measure.return_value.local.return_value.__enter__.return_value = (
        None
    )
    context.benchmark_tool.measure.return_value.local.return_value.__exit__.return_value = (
        None
    )
    context.benchmark_tool.measure.return_value.consensus.return_value.__enter__.return_value = (
        None
    )
    context.benchmark_tool.measure.return_value.consensus.return_value.__exit__.return_value = (
        None
    )
    context.logger = MagicMock()
    context.agent_address = "agent_address"
    return context


# Create a dummy class for testing
class DummyRetrieveApprovedMarketBehaviour:
    """A minimal concrete subclass for testing."""

    matching_round = RetrieveApprovedMarketRound

    def __init__(self, is_sender=True):
        self._params = SimpleNamespace(
            market_approval_server_url="https://example.com/market_approval_server_url",
            market_approval_server_api_key="test_api_key",
        )

        # Set up the synchronized data, making current agent the sender or not based on parameter
        agent_address = "agent_address"
        keeper_address = agent_address if is_sender else "other_address"

        self._synchronized_data = SimpleNamespace(
            most_voted_keeper_address=keeper_address,
            safe_contract_address="0xSAFE",
        )

        # Mock properties and methods
        self.behaviour_id = "retrieve_approved_market"
        self.wait_until_round_end = MagicMock()
        self.set_done = MagicMock()
        self.send_a2a_transaction = MagicMock()

        # Set up context
        self._context = dummy_ctx()

    @property
    def params(self):
        """Return params."""
        return self._params

    @property
    def synchronized_data(self):
        """Return synchronized data."""
        return self._synchronized_data

    @property
    def context(self):
        """Return context."""
        return self._context

    def _i_am_not_sending(self):
        """Indicates if the current agent is the sender or not."""
        return (
            self.context.agent_address
            != self.synchronized_data.most_voted_keeper_address
        )

    def _not_sender_act(self):
        """Do the non-sender action."""
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            self.context.logger.info(
                f"Waiting for the keeper to do its keeping: {self.synchronized_data.most_voted_keeper_address}"
            )
            self.wait_until_round_end()
        self.set_done()
        return None  # Return None to make this a generator with no yield

    def get_http_response(self, **kwargs):
        """Mock implementation of get_http_response."""
        # This is to be patched in tests
        return None

    def _get_process_random_approved_market(self):
        """Auxiliary method to collect data from endpoint."""
        url = (
            self.params.market_approval_server_url
            + "/get_process_random_approved_market"
        )
        headers = {
            "Authorization": self.params.market_approval_server_api_key,
            "Content-Type": "application/json",
        }

        response = self.get_http_response(
            method="POST",
            url=url,
            headers=headers,
        )

        if response.status_code == HTTP_NO_CONTENT:
            return RetrieveApprovedMarketRound.NO_MARKETS_RETRIEVED_PAYLOAD

        if response.status_code != HTTP_OK:
            self.context.logger.error(
                f"Could not retrieve response from {url}."
                f"Received status code {response.status_code}.\n{response}"
            )
            # For simplicity in tests - in real code there's retry logic
            return RetrieveApprovedMarketRound.ERROR_PAYLOAD

        response_data = json.loads(response.body.decode())
        return json.dumps(response_data, sort_keys=True)

    def _sender_act(self):
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            response = self._get_process_random_approved_market()
            payload = RetrieveApprovedMarketPayload(sender=sender, content=response)
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            self.send_a2a_transaction(payload)
            self.wait_until_round_end()
        self.set_done()
        return None  # Return None to make this a generator with no yield

    def async_act(self):
        """Do the action."""
        if self._i_am_not_sending():
            return self._not_sender_act()
        else:
            return self._sender_act()


# Fixtures
@pytest.fixture
def sender_behaviour():
    """Provide a behaviour instance that is the sender."""
    return DummyRetrieveApprovedMarketBehaviour(is_sender=True)


@pytest.fixture
def non_sender_behaviour():
    """Provide a behaviour instance that is NOT the sender."""
    return DummyRetrieveApprovedMarketBehaviour(is_sender=False)


# Tests
def test_i_am_not_sending(sender_behaviour, non_sender_behaviour):
    """Test _i_am_not_sending method."""
    assert sender_behaviour._i_am_not_sending() is False
    assert non_sender_behaviour._i_am_not_sending() is True


def test_not_sender_act(non_sender_behaviour):
    """Test _not_sender_act method when agent is not the sender."""
    # Call the method directly
    non_sender_behaviour._not_sender_act()

    # Verify wait_until_round_end was called
    non_sender_behaviour.wait_until_round_end.assert_called_once()
    non_sender_behaviour.set_done.assert_called_once()


def test_get_process_random_approved_market_success(sender_behaviour):
    """Test _get_process_random_approved_market with successful response."""
    # Mock success response with market data
    response = mock_http_response(HTTP_OK, {"id": "market1", "data": "test_data"})
    sender_behaviour.get_http_response = MagicMock(return_value=response)

    # Call the method directly
    result = sender_behaviour._get_process_random_approved_market()

    # Check result
    assert json.loads(result) == {"id": "market1", "data": "test_data"}

    # Verify HTTP request
    sender_behaviour.get_http_response.assert_called_once_with(
        method="POST",
        url="https://example.com/market_approval_server_url/get_process_random_approved_market",
        headers={
            "Authorization": "test_api_key",
            "Content-Type": "application/json",
        },
    )


def test_get_process_random_approved_market_no_content(sender_behaviour):
    """Test _get_process_random_approved_market when no markets are available."""
    # Mock no content response (204)
    response = mock_http_response(HTTP_NO_CONTENT)
    sender_behaviour.get_http_response = MagicMock(return_value=response)

    # Call the method directly
    result = sender_behaviour._get_process_random_approved_market()

    # Check result
    assert result == RetrieveApprovedMarketRound.NO_MARKETS_RETRIEVED_PAYLOAD


def test_get_process_random_approved_market_error(sender_behaviour):
    """Test _get_process_random_approved_market with error response."""
    # Mock error response
    response = mock_http_response(500)
    sender_behaviour.get_http_response = MagicMock(return_value=response)

    # Call the method directly
    result = sender_behaviour._get_process_random_approved_market()

    # Check result
    assert result == RetrieveApprovedMarketRound.ERROR_PAYLOAD

    # Verify logging was called
    sender_behaviour.context.logger.error.assert_called_once()


def test_sender_act(sender_behaviour):
    """Test _sender_act method with a successful response."""
    # Mock successful response
    response = mock_http_response(HTTP_OK, {"id": "market1", "data": "test_data"})
    sender_behaviour.get_http_response = MagicMock(return_value=response)

    # Call the method
    sender_behaviour._sender_act()

    # Verify transaction was sent with correct payload
    sender_behaviour.send_a2a_transaction.assert_called_once()
    payload = sender_behaviour.send_a2a_transaction.call_args[0][0]
    assert isinstance(payload, RetrieveApprovedMarketPayload)
    assert payload.sender == "agent_address"
    assert json.loads(payload.content) == {"id": "market1", "data": "test_data"}

    # Verify other methods were called
    sender_behaviour.wait_until_round_end.assert_called_once()
    sender_behaviour.set_done.assert_called_once()


def test_async_act_as_sender(sender_behaviour):
    """Test async_act when agent is the sender."""
    with patch.object(sender_behaviour, "_sender_act") as mock_sender_act:
        # Call async_act
        sender_behaviour.async_act()

        # Verify _sender_act was called
        mock_sender_act.assert_called_once()


def test_async_act_as_non_sender(non_sender_behaviour):
    """Test async_act when agent is not the sender."""
    with patch.object(non_sender_behaviour, "_not_sender_act") as mock_not_sender_act:
        # Call async_act
        non_sender_behaviour.async_act()

        # Verify _not_sender_act was called
        mock_not_sender_act.assert_called_once()

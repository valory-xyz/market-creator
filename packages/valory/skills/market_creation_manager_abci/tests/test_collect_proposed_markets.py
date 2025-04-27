# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2025 Valory AG
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

"""Tests for the collect_proposed_markets module."""

import json
from types import SimpleNamespace
from typing import Any, Dict, Generator, List, Optional

import pytest
from hypothesis import given
from hypothesis import strategies as st
from unittest.mock import MagicMock, PropertyMock, patch

from packages.valory.skills.market_creation_manager_abci.behaviours.collect_proposed_markets import CollectProposedMarketsBehaviour, _ONE_DAY
from packages.valory.protocols.http import HttpMessage
from packages.valory.skills.market_creation_manager_abci.rounds import CollectProposedMarketsRound

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def gen_side_effect(resp):
    """Return a generator object that yields once then returns *resp*."""
    def _g(*_a, **_kw):
        yield
        return resp
    return _g()


def dummy_ctx() -> MagicMock:
    """Create a standard mock context for behaviour testing."""
    ctx = MagicMock()
    ctx.state = MagicMock()
    ctx.logger = MagicMock()
    ctx.benchmark_tool = MagicMock()
    ctx.benchmark_tool.measure.return_value = MagicMock()
    ctx.benchmark_tool.measure.return_value.local.return_value = MagicMock()
    ctx.benchmark_tool.measure.return_value.consensus.return_value = MagicMock()
    ctx.agent_address = "agent_address"
    ctx.outbox = MagicMock()
    ctx.requests = MagicMock()
    ctx.requests.request_id_to_callback = {}
    return ctx


class DummyCollectProposedMarketsBehaviour(CollectProposedMarketsBehaviour):
    """A minimal concrete subclass so we can instantiate & test."""

    matching_round = CollectProposedMarketsRound  # satisfy framework requirement

    def __init__(self):
        self._params = SimpleNamespace(
            multisend_address="0xMULTI", 
            conditional_tokens_contract="0xCONDITIONAL_TOKENS", 
            min_approve_markets_epoch_seconds=10, 
            market_approval_server_url="https://example.com/market_approval_server_url", 
            approve_market_event_days_offset=7, 
            market_approval_server_api_key="test_api_key", 
            markets_to_approve_per_day=5, 
            max_approved_markets=10
        )
        self._synchronized_data = SimpleNamespace(
            settled_tx_hash="test_tx_hash", 
            tx_sender=None, 
            safe_contract_address="0xSAFE", 
            most_voted_keeper_address="agent_address", 
            approved_markets_count=0, 
            approved_markets_timestamp=1712345678
        )
        self._shared_state = MagicMock()
        self.last_synced_timestamp = 1712345678  # Mock the last_synced_timestamp property

    # Mock generator methods
    def get_subgraph_result(self, *args, **kwargs):
        return (yield {})
        
    def wait_until_round_end(self, *args, **kwargs):
        return (yield None)
        
    def send_a2a_transaction(self, *args, **kwargs):
        return (yield None)
        
    def get_http_response(self, *args, **kwargs):
        return (yield MagicMock())
        
    def wait_for_message(self, *args, **kwargs):
        return (yield MagicMock())
        
    def get_contract_api_response(self, *args, **kwargs):
        return (yield MagicMock())
    
    async def async_act(self):
        pass


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture
def behaviour(monkeypatch):
    """Provide a behaviour instance with mocked context."""
    beh = DummyCollectProposedMarketsBehaviour()
    ctx_patch = patch.object(DummyCollectProposedMarketsBehaviour, "context", new_callable=PropertyMock)
    monkeypatch.setattr("_pytest_context_patch", ctx_patch)  # store for cleanup
    mock_ctx_prop = ctx_patch.start()
    mock_ctx_prop.return_value = dummy_ctx()
    yield beh
    ctx_patch.stop()

@pytest.fixture
def mock_http_response():
    """Create a mock HTTP response."""
    response = MagicMock()
    response.status_code = 200
    response.body = json.dumps({"approved_markets": []}).encode()
    return response

@pytest.fixture
def mock_http_response_with_approved_markets():
    """Create a mock HTTP response with approved markets."""
    response = MagicMock()
    response.status_code = 200
    response.body = json.dumps({"approved_markets": [{"id": "market1"}]}).encode()
    return response

@pytest.fixture
def mock_subgraph_empty_result():
    """Create a mock empty subgraph result."""
    return {"data": {"fixedProductMarketMakers": []}}

@pytest.fixture
def mock_subgraph_result_with_markets():
    """Create a mock subgraph result with markets."""
    current_timestamp = 1712345678
    opening_timestamp = current_timestamp + _ONE_DAY + 100  # Add some offset
    
    return {
        "data": {
            "fixedProductMarketMakers": [
                {
                    "id": "0xmarket1",
                    "openingTimestamp": str(opening_timestamp),
                    "creationTimestamp": str(current_timestamp - 1000),
                },
                {
                    "id": "0xmarket2",
                    "openingTimestamp": str(opening_timestamp),
                    "creationTimestamp": str(current_timestamp - 500),
                }
            ]
        }
    }


# --------------------------------------------------------------------------- #
# _collect_approved_markets tests                                              #
# --------------------------------------------------------------------------- #
def test_collect_approved_markets_success(behaviour, mock_http_response):
    """Test _collect_approved_markets with successful response."""
    # Setup
    behaviour.get_http_response = MagicMock(
        side_effect=[gen_side_effect(mock_http_response)]
    )
    
    # Call the method
    gen = behaviour._collect_approved_markets()
    
    # Start the generator
    next(gen)
    
    # Complete the generator and check result
    with pytest.raises(StopIteration) as exc:
        next(gen)
    
    result = exc.value.value
    assert "approved_markets" in result
    assert result["approved_markets"] == []
    
    # Verify HTTP request
    behaviour.get_http_response.assert_called_once_with(
        method="GET",
        url="https://example.com/market_approval_server_url/approved_markets",
        headers={
            "Authorization": "test_api_key",
            "Content-Type": "application/json",
        },
    )

def test_collect_approved_markets_with_data(behaviour, mock_http_response_with_approved_markets):
    """Test _collect_approved_markets with actual market data."""
    # Setup
    behaviour.get_http_response = MagicMock(
        side_effect=[gen_side_effect(mock_http_response_with_approved_markets)]
    )
    
    # Call the method
    gen = behaviour._collect_approved_markets()
    next(gen)
    
    # Complete the generator and check result
    with pytest.raises(StopIteration) as exc:
        next(gen)
    
    result = exc.value.value
    assert "approved_markets" in result
    assert len(result["approved_markets"]) == 1
    assert result["approved_markets"][0]["id"] == "market1"

def test_collect_approved_markets_error(behaviour):
    """Test _collect_approved_markets with error response."""
    # Setup error response
    error_response = MagicMock()
    error_response.status_code = 404
    
    behaviour.get_http_response = MagicMock(
        side_effect=[gen_side_effect(error_response)]
    )
    
    # Call the method
    gen = behaviour._collect_approved_markets()
    next(gen)
    
    # Complete the generator and check result
    with pytest.raises(StopIteration) as exc:
        next(gen)
    
    result = exc.value.value
    assert "approved_markets" in result
    assert result["approved_markets"] == {}  # Empty dict on error


# --------------------------------------------------------------------------- #
# _collect_latest_open_markets tests                                          #
# --------------------------------------------------------------------------- #
def test_collect_latest_open_markets_success(behaviour, mock_subgraph_result_with_markets):
    """Test _collect_latest_open_markets with successful response."""
    # Setup
    behaviour.get_subgraph_result = MagicMock(
        side_effect=[gen_side_effect(mock_subgraph_result_with_markets)]
    )
    
    # Call the method with dummy timestamps
    gen = behaviour._collect_latest_open_markets(1712345678, 1712345678 + 7 * _ONE_DAY)
    next(gen)
    
    # Complete the generator and check result
    with pytest.raises(StopIteration) as exc:
        next(gen)
    
    result = exc.value.value
    assert "fixedProductMarketMakers" in result
    assert len(result["fixedProductMarketMakers"]) == 2
    assert result["fixedProductMarketMakers"][0]["id"] == "0xmarket1"
    assert result["fixedProductMarketMakers"][1]["id"] == "0xmarket2"

def test_collect_latest_open_markets_empty(behaviour, mock_subgraph_empty_result):
    """Test _collect_latest_open_markets with empty result."""
    # Setup
    behaviour.get_subgraph_result = MagicMock(
        side_effect=[gen_side_effect(mock_subgraph_empty_result)]
    )
    
    # Call the method with dummy timestamps
    gen = behaviour._collect_latest_open_markets(1712345678, 1712345678 + 7 * _ONE_DAY)
    next(gen)
    
    # Complete the generator and check result
    with pytest.raises(StopIteration) as exc:
        next(gen)
    
    result = exc.value.value
    assert "fixedProductMarketMakers" in result
    assert result["fixedProductMarketMakers"] == []

def test_collect_latest_open_markets_none_response(behaviour):
    """Test _collect_latest_open_markets with None response."""
    # Setup
    behaviour.get_subgraph_result = MagicMock(
        side_effect=[gen_side_effect(None)]
    )
    
    # Call the method with dummy timestamps
    gen = behaviour._collect_latest_open_markets(1712345678, 1712345678 + 7 * _ONE_DAY)
    next(gen)
    
    # Complete the generator and check result
    with pytest.raises(StopIteration) as exc:
        next(gen)
    
    result = exc.value.value
    assert "fixedProductMarketMakers" in result
    assert result["fixedProductMarketMakers"] == []


# --------------------------------------------------------------------------- #
# async_act main logic tests                                                  #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "approved_markets_count, max_approved_markets, expected_payload",
    [
        (10, 10, CollectProposedMarketsRound.MAX_APPROVED_MARKETS_REACHED_PAYLOAD),  # Equal to max
        (11, 10, CollectProposedMarketsRound.MAX_APPROVED_MARKETS_REACHED_PAYLOAD),  # Exceeds max
        (9, 10, CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD),  # Below max but default case
    ]
)
def test_async_act_max_approved_markets(
    behaviour, mock_http_response, mock_subgraph_empty_result, 
    approved_markets_count, max_approved_markets, expected_payload
):
    """Test async_act when max approved markets condition is met."""
    # Setup
    behaviour._synchronized_data.approved_markets_count = approved_markets_count
    behaviour._params.max_approved_markets = max_approved_markets
    
    behaviour.get_http_response = MagicMock(
        side_effect=[gen_side_effect(mock_http_response)]
    )
    behaviour.get_subgraph_result = MagicMock(
        side_effect=[gen_side_effect(mock_subgraph_empty_result)]
    )
    
    # Call the method
    gen = behaviour.async_act()
    next(gen)
    
    # Check that send_a2a_transaction was called with the right payload
    assert behaviour.send_a2a_transaction.called
    payload_arg = behaviour.send_a2a_transaction.call_args[0][0]
    assert payload_arg.content == expected_payload

def test_async_act_timeout_not_reached(behaviour, mock_http_response, mock_subgraph_empty_result):
    """Test async_act when timeout to approve markets is not reached."""
    # Setup - make current timestamp too close to last approval
    current_timestamp = 1712345678
    behaviour.last_synced_timestamp = current_timestamp
    behaviour._synchronized_data.approved_markets_timestamp = current_timestamp - 5  # Less than min_approve_markets_epoch_seconds
    behaviour._params.min_approve_markets_epoch_seconds = 10
    
    behaviour.get_http_response = MagicMock(
        side_effect=[gen_side_effect(mock_http_response)]
    )
    behaviour.get_subgraph_result = MagicMock(
        side_effect=[gen_side_effect(mock_subgraph_empty_result)]
    )
    
    # Call the method
    gen = behaviour.async_act()
    next(gen)
    
    # Check that send_a2a_transaction was called with SKIP payload
    assert behaviour.send_a2a_transaction.called
    payload_arg = behaviour.send_a2a_transaction.call_args[0][0]
    assert payload_arg.content == CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD

def test_async_act_with_existing_approved_markets(behaviour, mock_http_response_with_approved_markets, mock_subgraph_empty_result):
    """Test async_act when there are unprocessed approved markets."""
    # Setup - ensure we would otherwise proceed (far from last approval)
    current_timestamp = 1712345678
    behaviour.last_synced_timestamp = current_timestamp
    behaviour._synchronized_data.approved_markets_timestamp = current_timestamp - 100  # More than min_approve_markets_epoch_seconds
    behaviour._params.min_approve_markets_epoch_seconds = 10
    
    behaviour.get_http_response = MagicMock(
        side_effect=[gen_side_effect(mock_http_response_with_approved_markets)]
    )
    behaviour.get_subgraph_result = MagicMock(
        side_effect=[gen_side_effect(mock_subgraph_empty_result)]
    )
    
    # Call the method
    gen = behaviour.async_act()
    next(gen)
    
    # Check that send_a2a_transaction was called with SKIP payload due to existing approved markets
    assert behaviour.send_a2a_transaction.called
    payload_arg = behaviour.send_a2a_transaction.call_args[0][0]
    assert payload_arg.content == CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD

def test_async_act_normal_flow(behaviour, mock_http_response, mock_subgraph_result_with_markets):
    """Test async_act with normal flow producing full content."""
    # Setup conditions for normal flow
    current_timestamp = 1712345678
    behaviour.last_synced_timestamp = current_timestamp
    # Set timestamps to allow approval
    behaviour._synchronized_data.approved_markets_timestamp = current_timestamp - 100  # More than min_approve_markets_epoch_seconds
    behaviour._params.min_approve_markets_epoch_seconds = 10
    # Make sure we need additional markets
    behaviour._params.markets_to_approve_per_day = 5  # We need 5 per day
    
    behaviour.get_http_response = MagicMock(
        side_effect=[gen_side_effect(mock_http_response)]  # Empty approved markets
    )
    behaviour.get_subgraph_result = MagicMock(
        side_effect=[gen_side_effect(mock_subgraph_result_with_markets)]  # Only 2 markets exist
    )
    
    # Call the method
    gen = behaviour.async_act()
    next(gen)
    
    # Check that send_a2a_transaction was called with content containing data
    assert behaviour.send_a2a_transaction.called
    payload_arg = behaviour.send_a2a_transaction.call_args[0][0]
    
    # Verify it's not one of the special payloads
    assert payload_arg.content != CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD
    assert payload_arg.content != CollectProposedMarketsRound.MAX_APPROVED_MARKETS_REACHED_PAYLOAD
    
    # Parse the JSON content
    content_data = json.loads(payload_arg.content)
    
    # Check that all required fields are in the content
    assert "fixedProductMarketMakers" in content_data
    assert "approved_markets" in content_data
    assert "required_markets_to_approve_per_opening_ts" in content_data
    assert "timestamp" in content_data
    
    # Verify the number of markets
    assert len(content_data["fixedProductMarketMakers"]) == 2
    
    # Check the timestamp matches
    assert content_data["timestamp"] == current_timestamp


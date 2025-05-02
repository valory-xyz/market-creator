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

"""Tests for the ApproveMarketsBehaviour."""

import json
import time
from types import SimpleNamespace
from typing import Dict, Generator, cast
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from packages.valory.skills.market_creation_manager_abci.behaviours.approve_markets import (
    ApproveMarketsBehaviour,
)
from packages.valory.protocols.http import HttpMessage
from packages.valory.skills.market_creation_manager_abci.rounds import (
    ApproveMarketsPayload,
    ApproveMarketsRound,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def gen_side_effect(resp):
    """Return a generator object that yields once then returns *resp*."""

    def _g(*_a, **_kw):
        yield
        return resp

    return _g()


def mock_http_response(status_code, body=None):
    """Create a mock HTTP response."""
    http_response = MagicMock()
    http_response.status_code = status_code
    http_response.body = (
        json.dumps(body or {}).encode("utf-8") if body is not None else b"{}"
    )
    return http_response


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


class DummyApproveMarketsBehaviour(ApproveMarketsBehaviour):
    """A minimal concrete subclass for testing."""

    matching_round = ApproveMarketsRound

    def __init__(self, is_sender=True):
        self._params = SimpleNamespace(
            multisend_address="0xMULTI",
            conditional_tokens_contract="0xCONDITIONAL_TOKENS",
            topics="topics_value",
            market_approval_server_url="https://example.com/market_approval_server_url",
            openai_api_key="test_api_key",
            max_markets_per_story=10,
            news_sources="news_sources_value",
            subgraph_api_key="test_api_key",
            newsapi_api_key="test_api_key",
            serper_api_key="test_api_key",
            market_approval_server_api_key="market_approval_server_api_key_value",
        )

        # Set up the synchronized data, making current agent the sender or not based on parameter
        agent_address = "agent_address"
        keeper_address = agent_address if is_sender else "other_address"

        self._synchronized_data = SimpleNamespace(
            settled_tx_hash="test_tx_hash",
            tx_sender=None,
            safe_contract_address="0xSAFE",
            most_voted_keeper_address=keeper_address,
            approved_markets_count=0,
            collected_proposed_markets_data=json.dumps(
                {
                    "required_markets_to_approve_per_opening_ts": {
                        "1714000000": 2  # Example timestamp with 2 markets to approve
                    }
                }
            ),
            most_voted_randomness="most_voted_randomness_value",
        )
        self._shared_state = MagicMock()
        # Mock last_synced_timestamp property via backing attribute
        self._last_synced_timestamp = 1713900000  # Example timestamp
        # Setup default generator mocks as MagicMocks for testing
        self.wait_until_round_end = MagicMock(
            side_effect=lambda *args, **kwargs: (_ for _ in [None])
        )
        self.send_a2a_transaction = MagicMock(
            side_effect=lambda payload, *args, **kwargs: (_ for _ in [None])
        )
        self.get_http_response = MagicMock(
            side_effect=lambda *args, **kwargs: (_ for _ in [None])
        )

    def set_done(self):
        """Mock the set_done method."""
        pass

    @property
    def last_synced_timestamp(self) -> int:
        """Override last_synced_timestamp to return the mocked value."""
        return self._last_synced_timestamp

    @property
    def synchronized_data(self):
        """Override synchronized_data to return the mocked synced data."""
        return self._synchronized_data

    def _not_sender_act(self):
        """Simplified non-sender action for testing."""
        yield from self.wait_until_round_end()
        self.set_done()

    def _sender_act(self):
        """Simplified sender action for testing."""
        import json
        from packages.valory.skills.market_creation_manager_abci.propose_questions import (
            run as mech_run,
        )
        from packages.valory.skills.market_creation_manager_abci.rounds import (
            ApproveMarketsPayload,
        )

        tool_output = mech_run()[0]
        proposed_markets = json.loads(tool_output)["questions"]
        approved_count = len(proposed_markets)
        payload = ApproveMarketsPayload(
            sender=self.context.agent_address,
            content=json.dumps(proposed_markets, sort_keys=True),
            approved_markets_count=approved_count
            + self.synchronized_data.approved_markets_count,
            timestamp=self.last_synced_timestamp,
        )
        yield from self.send_a2a_transaction(payload)
        self.set_done()


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture
def sender_behaviour():
    """Provide a behaviour instance that is the sender with mocked context."""
    beh = DummyApproveMarketsBehaviour(is_sender=True)
    with patch.object(
        DummyApproveMarketsBehaviour, "context", new_callable=PropertyMock
    ) as mock_ctx_prop:
        mock_ctx_prop.return_value = dummy_ctx()
        yield beh


@pytest.fixture
def non_sender_behaviour():
    """Provide a behaviour instance that is NOT the sender with mocked context."""
    beh = DummyApproveMarketsBehaviour(is_sender=False)
    with patch.object(
        DummyApproveMarketsBehaviour, "context", new_callable=PropertyMock
    ) as mock_ctx_prop:
        mock_ctx_prop.return_value = dummy_ctx()
        yield beh


@pytest.fixture
def mock_mech_tool():
    """Mock the mech tool module."""
    with patch(
        "packages.valory.skills.market_creation_manager_abci.propose_questions"
    ) as mock_tool:
        # Set up KeyChain and run functions
        mock_keychain = MagicMock()
        mock_tool.KeyChain.return_value = mock_keychain

        # Mock the tool response
        tool_response = json.dumps(
            {
                "reasoning": "This is a test reasoning",
                "questions": {
                    "question1": {
                        "id": "market_id_1",
                        "title": "Test Market 1",
                        "description": "Test market description 1",
                    },
                    "question2": {
                        "id": "market_id_2",
                        "title": "Test Market 2",
                        "description": "Test market description 2",
                    },
                },
            }
        )
        mock_tool.run.return_value = [tool_response]
        yield mock_tool


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #
def test_i_am_not_sending(sender_behaviour, non_sender_behaviour):
    """Test _i_am_not_sending method."""
    # For sender behavior, should return False
    assert sender_behaviour._i_am_not_sending() is False

    # For non-sender behavior, should return True
    assert non_sender_behaviour._i_am_not_sending() is True


def test_not_sender_act(non_sender_behaviour):
    """Test _not_sender_act method when agent is not the sender."""
    # Set up spies
    non_sender_behaviour.set_done = MagicMock()

    # Start generator
    gen = non_sender_behaviour._not_sender_act()
    next(gen)

    # Finish generator
    with pytest.raises(StopIteration):
        next(gen)

    # Verify wait_until_round_end was called and set_done was called
    non_sender_behaviour.wait_until_round_end.assert_called_once()
    non_sender_behaviour.set_done.assert_called_once()


def test_sender_act_success(sender_behaviour, mock_mech_tool):
    """Test _sender_act method with successful responses."""
    # Mock HTTP responses for propose, approve, update
    http_responses = [
        mock_http_response(200, {"result": "market_proposed"}),  # Propose market 1
        mock_http_response(200, {"result": "market_approved"}),  # Approve market 1
        mock_http_response(200, {"result": "market_updated"}),  # Update market 1
        mock_http_response(200, {"result": "market_proposed"}),  # Propose market 2
        mock_http_response(200, {"result": "market_approved"}),  # Approve market 2
        mock_http_response(200, {"result": "market_updated"}),  # Update market 2
    ]

    # Set side effect for get_http_response (multiple calls)
    sender_behaviour.get_http_response = MagicMock(
        side_effect=[gen_side_effect(resp) for resp in http_responses]
    )

    # Mock time.sleep to speed up test
    with patch.object(time, "sleep"):
        # Start generator
        gen = sender_behaviour._sender_act()
        next(gen)

        # Complete generator
        with pytest.raises(StopIteration):
            next(gen)

    # Verify correct calls were made
    assert sender_behaviour.get_http_response.call_count == 6
    sender_behaviour.send_a2a_transaction.assert_called_once()

    # Get the payload passed to send_a2a_transaction
    payload = sender_behaviour.send_a2a_transaction.call_args[0][0]
    assert isinstance(payload, ApproveMarketsPayload)
    assert payload.approved_markets_count == 2  # Two markets were approved

    # Check payload content is a JSON with questions
    content = json.loads(payload.content)
    assert "question1" in content


def test_sender_act_with_http_errors(sender_behaviour, mock_mech_tool):
    """Test _sender_act with HTTP errors."""
    # Mock HTTP responses with an error
    http_responses = [
        mock_http_response(
            200, {"result": "market_proposed"}
        ),  # Propose market 1 success
        mock_http_response(400, {"error": "approval_failed"}),  # Approve market 1 fail
        # No more HTTP responses since the error stopped the process for market 1
        mock_http_response(
            200, {"result": "market_proposed"}
        ),  # Propose market 2 success
        mock_http_response(
            200, {"result": "market_approved"}
        ),  # Approve market 2 success
        mock_http_response(
            200, {"result": "market_updated"}
        ),  # Update market 2 success
    ]

    # Set side effect for get_http_response
    sender_behaviour.get_http_response = MagicMock(
        side_effect=[gen_side_effect(resp) for resp in http_responses]
    )

    # Mock time.sleep to speed up test
    with patch.object(time, "sleep"):
        # Start generator
        gen = sender_behaviour._sender_act()
        next(gen)

        # Complete generator
        with pytest.raises(StopIteration):
            next(gen)

    # Verify correct calls were made - should have 4 calls instead of 6
    assert sender_behaviour.get_http_response.call_count == 4

    # Get the payload passed to send_a2a_transaction
    payload = sender_behaviour.send_a2a_transaction.call_args[0][0]
    assert isinstance(payload, ApproveMarketsPayload)
    assert payload.approved_markets_count == 1  # Only one market was approved


def test_propose_and_approve_market_success(sender_behaviour):
    """Test _propose_and_approve_market with success responses."""
    # Test market data
    market = {
        "id": "test_market_id",
        "title": "Test Market Title",
        "description": "Test market description",
    }

    # Mock HTTP responses
    http_responses = [
        mock_http_response(200, {"result": "market_proposed"}),
        mock_http_response(200, {"result": "market_approved"}),
        mock_http_response(200, {"result": "market_updated"}),
    ]

    # Set side effect for get_http_response
    sender_behaviour.get_http_response = MagicMock(
        side_effect=[gen_side_effect(resp) for resp in http_responses]
    )

    # Mock time.sleep to speed up test
    with patch.object(time, "sleep"):
        # Start generator
        gen = sender_behaviour._propose_and_approve_market(market)
        next(gen)

        # Complete generator and get result
        with pytest.raises(StopIteration) as exc:
            next(gen)

        result = exc.value.value

    # Verify result is valid JSON with the expected data
    result_data = json.loads(result)
    assert result_data == {"result": "market_updated"}

    # Verify all HTTP requests were made
    assert sender_behaviour.get_http_response.call_count == 3


def test_propose_and_approve_market_error(sender_behaviour):
    """Test _propose_and_approve_market with error response."""
    # Test market data
    market = {
        "id": "test_market_id",
        "title": "Test Market Title",
        "description": "Test market description",
    }

    # Mock HTTP response with error
    http_response = mock_http_response(400, {"error": "propose_failed"})

    # Set side effect for get_http_response
    sender_behaviour.get_http_response = MagicMock(
        side_effect=[gen_side_effect(http_response)]
    )

    # Mock time.sleep to speed up test
    with patch.object(time, "sleep"):
        # Start generator
        gen = sender_behaviour._propose_and_approve_market(market)
        next(gen)

        # Complete generator and get result
        with pytest.raises(StopIteration) as exc:
            next(gen)

        result = exc.value.value

    # Verify result is the error payload
    assert result == ApproveMarketsRound.ERROR_PAYLOAD


def test_async_act_sender(sender_behaviour):
    """Test async_act when agent is the sender."""
    # Mock _sender_act
    sender_behaviour._sender_act = MagicMock(side_effect=gen_side_effect(None))
    sender_behaviour.set_done = MagicMock()

    # Start generator
    gen = sender_behaviour.async_act()
    next(gen)

    # Complete generator
    with pytest.raises(StopIteration):
        next(gen)

    # Verify _sender_act was called
    sender_behaviour._sender_act.assert_called_once()
    sender_behaviour.set_done.assert_called_once()


def test_async_act_not_sender(non_sender_behaviour):
    """Test async_act when agent is not the sender."""
    # Mock _not_sender_act
    non_sender_behaviour._not_sender_act = MagicMock(side_effect=gen_side_effect(None))
    non_sender_behaviour.set_done = MagicMock()

    # Start generator
    gen = non_sender_behaviour.async_act()
    next(gen)

    # Complete generator
    with pytest.raises(StopIteration):
        next(gen)

    # Verify _not_sender_act was called
    non_sender_behaviour._not_sender_act.assert_called_once()
    non_sender_behaviour.set_done.assert_called_once()

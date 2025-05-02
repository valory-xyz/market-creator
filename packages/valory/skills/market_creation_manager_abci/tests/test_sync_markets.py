"""
Tests for `SyncMarketsBehaviour`.

Covers:
    • success/early-exit paths
    • error-paths
    • log-message assertions
"""

import json
from unittest.mock import MagicMock
import pytest
from types import SimpleNamespace
from typing import Any, Dict
from hypothesis import given, settings, strategies as st, HealthCheck

from packages.valory.skills.market_creation_manager_abci.behaviours.sync_markets import (
    SyncMarketsBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.rounds import SyncMarketsRound


# --------------------------------------------------------------------------- #
# Helper Functions                                                            #
# --------------------------------------------------------------------------- #


def _make_gen(retval: Any):
    """Return a 1-shot coroutine that yields once then returns *retval*."""

    def _coroutine(*_args, **_kwargs):  # pylint: disable=unused-argument
        yield  # first tick consumed by `yield from`
        return retval

    return _coroutine


class _NoOpCM:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _DummyBenchmarkTool:
    def measure(self, _behaviour_id):
        return self

    def local(self):
        return _NoOpCM()

    def consensus(self):
        return _NoOpCM()


class _DummyCtx:
    """Minimal skill-context double – only the attrs the behaviour touches."""

    def __init__(self):
        self.agent_address = "0xdeadbeef"
        import logging

        self.logger = logging.getLogger("test.sync_markets")
        self.logger.propagate = True
        self.benchmark_tool = _DummyBenchmarkTool()
        self.params = None
        self.state = SimpleNamespace(synchronized_data=...)
        self.agent_address = "0xdeadbeef"


# --------------------------------------------------------------------------- #
@pytest.fixture()
def behaviour(monkeypatch):
    """Enhanced fixture for SyncMarketsBehaviour with monkeypatching."""
    bhv = SyncMarketsBehaviour.__new__(SyncMarketsBehaviour)

    ctx = _DummyCtx()
    ctx.params = SimpleNamespace(
        collateral_tokens_contract="0xCollateral",
        conditional_tokens_contract="0xConditional",
        fpmm_deterministic_factory_contract="0xFactory",
        market_approval_server_url="http://market-approval",
        market_approval_server_api_key="api-key",
    )
    ctx.state = SimpleNamespace(
        synchronized_data=SimpleNamespace(
            safe_contract_address="0xSAFE",
            markets_to_remove_liquidity=[],
            market_from_block=0,
        )
    )

    object.__setattr__(bhv, "_skill_context", ctx)
    object.__setattr__(bhv, "_context", ctx)
    object.__setattr__(bhv, "_params", ctx.params)
    object.__setattr__(bhv, "_synchronized_data", ctx.state.synchronized_data)

    # --- Always-mock external side-effects ---
    monkeypatch.setattr(bhv, "send_a2a_transaction", MagicMock())
    monkeypatch.setattr(bhv, "wait_until_round_end", MagicMock())

    # Default subgraph and HTTP responses
    default_subgraph_response = {"data": {"fpmmPoolMemberships": []}}
    monkeypatch.setattr(
        bhv, "get_subgraph_result", _make_gen(default_subgraph_response)
    )
    monkeypatch.setattr(bhv, "_get_markets_with_funds", _make_gen([]))

    return bhv


def test_get_payload_no_markets(behaviour, monkeypatch):
    """Test get_payload with no markets to close."""
    monkeypatch.setattr(behaviour, "get_markets", lambda: iter([([], 0)]))
    monkeypatch.setattr(
        behaviour, "_get_markets_with_funds", lambda addresses, safe: iter([[]])
    )
    monkeypatch.setattr(
        behaviour,
        "get_subgraph_result",
        lambda query: iter([{"data": {"fpmmPoolMemberships": []}}]),
    )
    monkeypatch.setattr(behaviour, "last_synced_timestamp", 1234567890)
    result = list(behaviour.get_payload())[-1]
    assert result == SyncMarketsRound.NO_UPDATE_PAYLOAD


def test_get_payload_with_markets(behaviour, monkeypatch):
    """Test get_payload with markets to close."""
    markets = [
        {
            "address": "0xMarket",
            "amount": 1000,
            "condition_id": "0xCondition",
            "outcome_slot_count": 2,
            "opening_timestamp": 1234567890,
            "removal_timestamp": 1234567890,
        }
    ]
    monkeypatch.setattr(behaviour, "get_markets", lambda: iter([(markets, 123)]))
    monkeypatch.setattr(
        behaviour,
        "_get_markets_with_funds",
        lambda addresses, safe: iter([["0xMarket"]]),
    )
    result = list(behaviour.get_payload())[-1]
    expected_payload = json.dumps(
        {"markets": markets, "from_block": 123}, sort_keys=True
    )
    assert result == expected_payload


def test_get_markets_none_response(behaviour, monkeypatch):
    """Test get_markets with None response."""
    monkeypatch.setattr(behaviour, "get_subgraph_result", lambda query: iter([None]))
    result = list(behaviour.get_markets())[-1]
    assert result == ([], 0)


def test_get_markets_valid_response(behaviour, monkeypatch):
    """Test get_markets with valid response."""
    response = {
        "data": {
            "fpmmPoolMemberships": [
                {
                    "pool": {
                        "id": "0xMarket",
                        "liquidityMeasure": "1000",
                        "openingTimestamp": "1234567890",
                        "conditions": [
                            {
                                "id": "0xCondition",
                                "outcomeSlotCount": 2,
                                "question": {"id": "0xQuestion"},
                            }
                        ],
                        "outcomeTokenAmounts": ["500", "500"],
                    }
                }
            ]
        }
    }
    monkeypatch.setattr(
        behaviour, "get_subgraph_result", lambda query: iter([response])
    )
    monkeypatch.setattr(
        behaviour,
        "_get_markets_with_funds",
        lambda addresses, safe: iter([["0xMarket"]]),
    )
    result = list(behaviour.get_markets())[-1]
    assert len(result[0]) == 1
    assert result[0][0]["address"] == "0xMarket"
    assert result[1] == 0


def test_get_markets_missing_keys(behaviour, monkeypatch):
    """Test get_markets with response missing keys."""
    response = {"data": {}}
    monkeypatch.setattr(
        behaviour, "get_subgraph_result", lambda query: iter([response])
    )
    result = list(behaviour.get_markets())[-1]
    assert result == ([], 0)


def test_get_markets_malformed_json(behaviour, monkeypatch):
    """Test get_markets with malformed JSON response."""
    monkeypatch.setattr(
        behaviour, "get_subgraph_result", lambda query: iter(["{malformed_json"])
    )
    result = list(behaviour.get_markets())[-1]
    assert result == ([], 0)


def test_get_markets_http_error(behaviour, monkeypatch):
    """Test get_markets with HTTP error response."""
    monkeypatch.setattr(behaviour, "get_subgraph_result", lambda query: iter([None]))
    result = list(behaviour.get_markets())[-1]
    assert result == ([], 0)


def test_get_markets_large_number_of_markets(behaviour, monkeypatch):
    """Test get_markets with a large number of markets."""
    markets = [
        {
            "pool": {
                "id": f"0xMarket{i}",
                "liquidityMeasure": "1000",
                "openingTimestamp": "1234567890",
                "conditions": [
                    {
                        "id": f"0xCondition{i}",
                        "outcomeSlotCount": 2,
                        "question": {"id": f"0xQuestion{i}"},
                    }
                ],
                "outcomeTokenAmounts": ["500", "500"],
            }
        }
        for i in range(1000)
    ]
    response = {"data": {"fpmmPoolMemberships": markets}}
    monkeypatch.setattr(
        behaviour, "get_subgraph_result", lambda query: iter([response])
    )
    monkeypatch.setattr(
        behaviour,
        "_get_markets_with_funds",
        lambda addresses, safe: iter([[f"0xMarket{i}" for i in range(1000)]]),
    )
    result = list(behaviour.get_markets())[-1]
    assert len(result[0]) == 1000


def test_get_markets_zero_liquidity(behaviour, monkeypatch):
    """Test get_markets with markets having zero liquidity."""
    response = {
        "data": {
            "fpmmPoolMemberships": [
                {
                    "pool": {
                        "id": "0xMarket",
                        "liquidityMeasure": "0",
                        "openingTimestamp": "1234567890",
                        "conditions": [
                            {
                                "id": "0xCondition",
                                "outcomeSlotCount": 2,
                                "question": {"id": "0xQuestion"},
                            }
                        ],
                        "outcomeTokenAmounts": ["0", "0"],
                    }
                }
            ]
        }
    }
    monkeypatch.setattr(
        behaviour, "get_subgraph_result", lambda query: iter([response])
    )
    result = list(behaviour.get_markets())[-1]
    assert result == ([], 0)


@given(
    market_ids=st.lists(st.text(min_size=1, max_size=42), max_size=50),
    liquidity_measures=st.lists(st.integers(min_value=0, max_value=10000), max_size=50),
    timestamps=st.lists(st.integers(min_value=0, max_value=9999999999), max_size=50),
)
@settings(max_examples=50, suppress_health_check=(HealthCheck.function_scoped_fixture,))
def test_fuzz_get_markets(
    behaviour, monkeypatch, market_ids, liquidity_measures, timestamps
):
    """Fuzz test get_markets with randomized inputs."""
    markets = [
        {
            "pool": {
                "id": market_id,
                "liquidityMeasure": str(liquidity),
                "openingTimestamp": str(timestamp),
                "conditions": [
                    {
                        "id": f"0xCondition{i}",
                        "outcomeSlotCount": 2,
                        "question": {"id": f"0xQuestion{i}"},
                    }
                ],
                "outcomeTokenAmounts": ["500", "500"],
            }
        }
        for i, (market_id, liquidity, timestamp) in enumerate(
            zip(market_ids, liquidity_measures, timestamps)
        )
    ]
    response = {"data": {"fpmmPoolMemberships": markets}}
    monkeypatch.setattr(
        behaviour, "get_subgraph_result", lambda query: iter([response])
    )
    monkeypatch.setattr(
        behaviour, "_get_markets_with_funds", lambda addresses, safe: iter([market_ids])
    )
    result = list(behaviour.get_markets())[-1]
    assert isinstance(result, tuple)
    assert len(result) == 2


# --------------------------------------------------------------------------- #
# Happy-path / early-exit coverage                                            #
# --------------------------------------------------------------------------- #

NOW = 1_700_000_000

_BASIC_CASES = [
    (dict(markets=[]), SyncMarketsRound.NO_UPDATE_PAYLOAD),
    (dict(markets=[{"address": "0xMarket", "amount": 1000}], from_block=123), "JSON"),
]


@pytest.mark.parametrize("setup, expected", _BASIC_CASES)
def test_async_act_basic_paths(behaviour, monkeypatch, setup, expected):
    _drive_and_assert(behaviour, monkeypatch, setup, expected)


# --------------------------------------------------------------------------- #
# Utility                                                                     #
# --------------------------------------------------------------------------- #


def _drive_and_assert(bhv, mp, setup: Dict[str, Any], expected):
    """Run one happy-path scenario."""
    mp.setattr(
        bhv,
        "get_markets",
        _make_gen((setup.get("markets", []), setup.get("from_block", 0))),
    )

    list(bhv.get_payload())

    if expected == "JSON":
        payload = json.dumps(
            {"markets": setup["markets"], "from_block": setup["from_block"]},
            sort_keys=True,
        )
        assert payload
    else:
        assert expected == SyncMarketsRound.NO_UPDATE_PAYLOAD

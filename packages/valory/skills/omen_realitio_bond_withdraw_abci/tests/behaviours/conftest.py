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

"""Shared fixtures and helpers for omen_realitio_bond_withdraw_abci behaviour tests."""

# pylint: disable=unused-argument

from typing import Any
from unittest.mock import MagicMock

import pytest
from hypothesis import HealthCheck, settings  # type: ignore[import-not-found]

from packages.valory.protocols.contract_api import ContractApiMessage

# Configure Hypothesis for CI/dev environments
settings.register_profile(
    "ci",
    max_examples=10,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
settings.register_profile("dev", max_examples=10)
settings.load_profile("ci")


def make_gen(return_value: Any) -> Any:
    """Create a no-yield generator returning the given value."""

    def gen(*args: Any, **kwargs: Any) -> Any:
        return return_value
        yield  # noqa: unreachable - makes this a generator function

    return gen


def exhaust_gen(gen: Any) -> Any:
    """Exhaust a generator and return its value."""
    try:
        while True:
            next(gen)
    except StopIteration as e:
        return e.value


def make_contract_state_response(body_data: Any) -> Any:
    """Create a mock contract API STATE response."""
    mock_resp = MagicMock()
    mock_resp.performative = ContractApiMessage.Performative.STATE
    mock_resp.state.body = body_data
    return mock_resp


def make_contract_error_response() -> Any:
    """Create a mock contract API ERROR response."""
    mock_resp = MagicMock()
    mock_resp.performative = ContractApiMessage.Performative.ERROR
    return mock_resp


def make_raw_tx_response(body_data: Any) -> Any:
    """Create a mock contract API RAW_TRANSACTION response."""
    mock_resp = MagicMock()
    mock_resp.performative = ContractApiMessage.Performative.RAW_TRANSACTION
    mock_resp.raw_transaction.body = body_data
    return mock_resp


def make_http_response(status_code: int, body: bytes) -> Any:
    """Create a mock HTTP response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.body = body
    return mock_resp


@pytest.fixture
def mock_context() -> MagicMock:
    """Create a mocked skill context for behaviour tests."""
    context = MagicMock()
    context.params = MagicMock()
    context.params.realitio_contract = "0xRealitio"
    context.params.realitio_bond_withdraw_batch_size = 10
    context.params.min_balance_withdraw_realitio = 10000000000000000000
    context.params.multisend_address = "0xMultisend"
    context.state.round_sequence = MagicMock()
    context.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
        1700100000
    )
    context.state.synchronized_data = MagicMock()
    context.state.synchronized_data.safe_contract_address = "0xSafe"
    context.benchmark_tool = MagicMock()
    context.agent_address = "0x1234567890123456789012345678901234567890"
    context.logger = MagicMock()
    context.realitio_subgraph = MagicMock()
    context.realitio_subgraph.get_spec.return_value = {
        "method": "POST",
        "url": "https://realitio.example.com",
    }
    return context

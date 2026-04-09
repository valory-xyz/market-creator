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

"""Shared fixtures for behaviour tests."""

import sys
from unittest.mock import MagicMock

import pytest
from hypothesis import HealthCheck, settings  # type: ignore[import-not-found]

# Mock openai module to allow importing propose_questions.py
sys.modules["openai"] = MagicMock()
sys.modules["tiktoken"] = MagicMock()
sys.modules["anthropic"] = MagicMock()
sys.modules["google"] = MagicMock()
sys.modules["google.generativeai"] = MagicMock()

# Configure Hypothesis for CI/dev environments
settings.register_profile(
    "ci",
    max_examples=10,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
settings.register_profile("dev", max_examples=10)
settings.load_profile("ci")


@pytest.fixture
def mock_context() -> MagicMock:
    """Create a mocked skill context for behaviour tests."""
    context = MagicMock()
    context.params = MagicMock()
    context.state.round_sequence = MagicMock()
    context.handlers = MagicMock()
    context.benchmark_tool = MagicMock()
    context.agent_address = "0x1234567890123456789012345678901234567890"
    context.logger = MagicMock()
    return context


@pytest.fixture
def mock_ledger_api() -> MagicMock:
    """Create a mocked ledger API."""
    ledger_api = MagicMock()
    ledger_api.get_balance = MagicMock(return_value=10**18)  # 1 ETH in wei
    ledger_api.get_state = MagicMock(return_value="0x0")
    return ledger_api


@pytest.fixture
def mock_contract_instance() -> MagicMock:
    """Create a mocked contract instance."""
    contract = MagicMock()
    contract.functions = MagicMock()
    contract.events = MagicMock()
    return contract


@pytest.fixture
def mock_http_client() -> MagicMock:
    """Create a mocked HTTP client."""
    client = MagicMock()
    client.get = MagicMock()
    client.post = MagicMock()
    return client


@pytest.fixture
def mock_subgraph_client() -> MagicMock:
    """Create a mocked subgraph client."""
    client = MagicMock()
    client.query = MagicMock(return_value={})
    return client

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

"""Tests for the market_creation_manager_abci models."""

from typing import Any
from unittest.mock import MagicMock, patch

from packages.valory.skills.abstract_round_abci.models import BaseParams
from packages.valory.skills.market_creation_manager_abci.models import (
    MarketCreationManagerParams,
)

# Minimal kwargs required by MarketCreationManagerParams.__init__
_REQUIRED_KWARGS = {
    "market_approval_server_url": "http://example.com",
    "market_approval_server_api_key": "api-key",
    "max_proposed_markets": 10,
    "max_approved_markets": 5,
    "markets_to_approve_per_day": 3,
    "markets_to_approve_per_epoch": 2,
    "realitio_answer_question_bounty": 100,
    "min_approve_markets_epoch_seconds": 3600,
    "approve_market_event_days_offset": 7,
    "realitio_contract": "0x1234",
    "realitio_oracle_proxy_contract": "0x5678",
    "conditional_tokens_contract": "0x9abc",
    "fpmm_deterministic_factory_contract": "0xdef0",
    "collateral_tokens_contract": "0x1111",
    "arbitrator_contract": "0x2222",
    "market_fee": 0.02,
    "market_timeout": 86400,
    "event_offset_start_days": 1,
    "event_offset_end_days": 30,
    "min_market_proposal_interval_seconds": 3600,
    "market_proposal_round_timeout_seconds_per_day": 60,
    "max_markets_per_story": 5,
    "topics": ["business", "science"],
    "news_sources": ["bbc-news"],
    "initial_funds": 100.0,
    "xdai_threshold": 1000000000000000000,
    "service_endpoint_base": "https://example.com",
    # Optional with defaults
    "mech_tool_propose_question": "propose-question",
    "mech_interact_round_timeout_seconds": 1200,
}


class TestMarketCreationManagerParams:
    """Tests for MarketCreationManagerParams.__init__."""

    def _make_instance(self, **overrides: Any) -> Any:
        """Create a mocked instance with patched super().__init__."""
        kwargs = {**_REQUIRED_KWARGS, **overrides}
        mock_self = MagicMock(spec=MarketCreationManagerParams)
        mock_self._ensure = MagicMock(
            side_effect=lambda key, kwargs, type_: kwargs.pop(key)
        )
        with patch.object(BaseParams, "__init__", return_value=None):
            MarketCreationManagerParams.__init__(mock_self, **kwargs)
        return mock_self

    def test_init_sets_market_approval_server_url(self) -> None:
        """Test market_approval_server_url is set."""
        instance = self._make_instance()
        assert instance.market_approval_server_url == "http://example.com"

    def test_init_sets_market_approval_server_api_key(self) -> None:
        """Test market_approval_server_api_key is set."""
        instance = self._make_instance()
        assert instance.market_approval_server_api_key == "api-key"

    def test_init_sets_realitio_contract(self) -> None:
        """Test realitio_contract is set."""
        instance = self._make_instance()
        assert instance.realitio_contract == "0x1234"

    def test_init_sets_topics(self) -> None:
        """Test topics is set from kwargs."""
        instance = self._make_instance()
        assert instance.topics == ["business", "science"]

    def test_init_sets_news_sources(self) -> None:
        """Test news_sources is set from kwargs."""
        instance = self._make_instance()
        assert instance.news_sources == ["bbc-news"]

    def test_init_sets_mech_tool_propose_question_default(self) -> None:
        """Test mech_tool_propose_question defaults to 'propose-question'."""
        kwargs = {**_REQUIRED_KWARGS}
        del kwargs["mech_tool_propose_question"]
        mock_self = MagicMock(spec=MarketCreationManagerParams)
        mock_self._ensure = MagicMock(
            side_effect=lambda key, kwargs, type_: kwargs.pop(key)
        )
        with patch.object(BaseParams, "__init__", return_value=None):
            MarketCreationManagerParams.__init__(mock_self, **kwargs)
        assert mock_self.mech_tool_propose_question == "propose-question"

    def test_init_sets_mech_tool_propose_question_custom(self) -> None:
        """Test mech_tool_propose_question can be overridden."""
        instance = self._make_instance(mech_tool_propose_question="custom-tool")
        assert instance.mech_tool_propose_question == "custom-tool"

    def test_init_sets_mech_interact_round_timeout_seconds_default(self) -> None:
        """Test mech_interact_round_timeout_seconds defaults to 1200."""
        kwargs = {**_REQUIRED_KWARGS}
        del kwargs["mech_interact_round_timeout_seconds"]
        mock_self = MagicMock(spec=MarketCreationManagerParams)
        mock_self._ensure = MagicMock(
            side_effect=lambda key, kwargs, type_: kwargs.pop(key)
        )
        with patch.object(BaseParams, "__init__", return_value=None):
            MarketCreationManagerParams.__init__(mock_self, **kwargs)
        assert mock_self.mech_interact_round_timeout_seconds == 1200

    def test_init_sets_mech_interact_round_timeout_seconds_custom(self) -> None:
        """Test mech_interact_round_timeout_seconds can be overridden."""
        instance = self._make_instance(mech_interact_round_timeout_seconds=600)
        assert instance.mech_interact_round_timeout_seconds == 600

    def test_init_sets_service_endpoint_base(self) -> None:
        """Test service_endpoint_base is set."""
        instance = self._make_instance()
        assert instance.service_endpoint_base == "https://example.com"

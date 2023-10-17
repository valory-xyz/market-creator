# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023 Valory AG
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

"""This module contains the shared state for the abci skill of MarketCreationManagerAbciApp."""

from typing import Any, List

from packages.valory.skills.abstract_round_abci.models import ApiSpecs, BaseParams
from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.abstract_round_abci.models import (
    SharedState as BaseSharedState,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    MarketCreationManagerAbciApp,
)


DEFAULT_MARKET_FEE = 2.0
DEFAULT_INITIAL_FUNDS = 1.0
DEFAULT_MARKET_TIMEOUT = 1  # days
DEFAULT_MAX_PROPOSED_MARKETS = -1
DEFAULT_EVENT_OFFSET_START_DAYS = 4
DEFAULT_EVENT_OFFSET_END_DAYS = 7
DEFAULT_MIN_MARKET_PROPOSAL_INTERVAL_SECONDS = 7200


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls = MarketCreationManagerAbciApp


class MarketCreationManagerParams(BaseParams):
    """Parameters."""

    multisend_address: str

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the parameters object."""

        self.market_approval_server_url = self._ensure(
            key="market_approval_server_url", kwargs=kwargs, type_=str
        )
        self.market_approval_server_api_key = self._ensure(
            key="market_approval_server_api_key", kwargs=kwargs, type_=str
        )
        self.newsapi_api_key = self._ensure(
            key="newsapi_api_key", kwargs=kwargs, type_=str
        )
        self.newsapi_endpoint = self._ensure(
            key="newsapi_endpoint", kwargs=kwargs, type_=str
        )
        self.market_identification_prompt = self._ensure(
            key="market_identification_prompt", kwargs=kwargs, type_=str
        )
        self.topics = self._ensure(key="topics", kwargs=kwargs, type_=List[str])
        self.news_sources = self._ensure(
            key="news_sources", kwargs=kwargs, type_=List[str]
        )
        self.max_proposed_markets = kwargs.get(
            "max_proposed_markets", DEFAULT_MAX_PROPOSED_MARKETS
        )
        self.realitio_contract = self._ensure(
            key="realitio_contract",
            kwargs=kwargs,
            type_=str,
        )
        self.realitio_oracle_proxy_contract = self._ensure(
            key="realitio_oracle_proxy_contract",
            kwargs=kwargs,
            type_=str,
        )
        self.conditional_tokens_contract = self._ensure(
            key="conditional_tokens_contract",
            kwargs=kwargs,
            type_=str,
        )
        self.fpmm_deterministic_factory_contract = self._ensure(
            key="fpmm_deterministic_factory_contract",
            kwargs=kwargs,
            type_=str,
        )
        self.collateral_tokens_contract = self._ensure(
            key="collateral_tokens_contract",
            kwargs=kwargs,
            type_=str,
        )
        self.arbitrator_contract = self._ensure(
            key="arbitrator_contract",
            kwargs=kwargs,
            type_=str,
        )
        self.market_fee = kwargs.get("market_fee", DEFAULT_MARKET_FEE)
        self.market_timeout = kwargs.get("market_timeout", DEFAULT_MARKET_TIMEOUT)
        self.event_offset_start_days = kwargs.get(
            "event_offset_start_days", DEFAULT_EVENT_OFFSET_START_DAYS
        )
        self.event_offset_end_days = kwargs.get(
            "event_offset_end_days", DEFAULT_EVENT_OFFSET_END_DAYS
        )
        self.min_market_proposal_interval_seconds = kwargs.get(
            "min_market_proposal_interval_seconds",
            DEFAULT_MIN_MARKET_PROPOSAL_INTERVAL_SECONDS,
        )

        self.initial_funds = kwargs.get("initial_funds", DEFAULT_INITIAL_FUNDS)
        super().__init__(*args, **kwargs)


class RandomnessApi(ApiSpecs):
    """A model for randomness api specifications."""


class OmenSubgraph(ApiSpecs):
    """A model that wraps ApiSpecs for the OMEN's subgraph specifications."""


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool

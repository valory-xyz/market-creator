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

from typing import Any, List, Set, Type

from aea.skills.base import SkillContext

from packages.valory.skills.abstract_round_abci.base import AbciApp
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


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls: Type[AbciApp] = MarketCreationManagerAbciApp

    def __init__(self, *args: Any, skill_context: SkillContext, **kwargs: Any) -> None:
        """Initialize the shared state object."""
        self.processed_question_ids: Set[str] = set()
        super().__init__(*args, skill_context=skill_context, **kwargs)


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
        self.max_proposed_markets = self._ensure(
            "max_proposed_markets", kwargs, type_=int
        )
        self.max_approved_markets = self._ensure(
            "max_approved_markets", kwargs, type_=int
        )
        self.markets_to_approve_per_day = self._ensure(
            "markets_to_approve_per_day", kwargs, type_=int
        )
        self.markets_to_approve_per_epoch = self._ensure(
            "markets_to_approve_per_epoch", kwargs, type_=int
        )
        self.questions_to_close_batch_size = self._ensure(
            "questions_to_close_batch_size", kwargs, type_=int
        )
        self.close_question_bond = self._ensure(
            "close_question_bond", kwargs, type_=int
        )
        self.min_approve_markets_epoch_seconds = self._ensure(
            "min_approve_markets_epoch_seconds", kwargs, type_=int
        )
        self.approve_market_event_days_offset = self._ensure(
            "approve_market_event_days_offset", kwargs, type_=int
        )
        self.approve_market_creator = self._ensure(
            key="approve_market_creator",
            kwargs=kwargs,
            type_=str,
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
        self.market_fee = self._ensure("market_fee", kwargs, type_=float)
        self.market_timeout = self._ensure("market_timeout", kwargs, type_=int)
        self.event_offset_start_days = self._ensure(
            "event_offset_start_days", kwargs, type_=int
        )
        self.event_offset_end_days = self._ensure(
            "event_offset_end_days", kwargs, type_=int
        )
        self.min_market_proposal_interval_seconds = self._ensure(
            "min_market_proposal_interval_seconds", kwargs, type_=int
        )
        self.market_proposal_round_timeout_seconds_per_day = self._ensure(
            "market_proposal_round_timeout_seconds_per_day", kwargs, type_=int
        )
        self.market_closing_newsapi_api_key = self._ensure(
            "market_closing_newsapi_api_key", kwargs, type_=str
        )
        self.initial_funds = self._ensure("initial_funds", kwargs, type_=float)
        self.xdai_threshold = self._ensure("xdai_threshold", kwargs, type_=int)
        super().__init__(*args, **kwargs)


class RandomnessApi(ApiSpecs):
    """A model for randomness api specifications."""


class OmenSubgraph(ApiSpecs):
    """A model that wraps ApiSpecs for the OMEN's subgraph specifications."""


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool

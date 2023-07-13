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

from typing import Any

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
DEFAULT_MARKET_TIMEOUT = 7  # days


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls = MarketCreationManagerAbciApp


class MarketCreationManagerParams(BaseParams):
    """Parameters."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the parameters object."""

        self.newsapi_api_key = kwargs.get("newsapi_api_key")
        self.newsapi_endpoint = kwargs.get("newsapi_endpoint")
        self.num_markets = kwargs.get("num_markets")
        self.multisend_address = self._ensure(
            key="multisend_address", kwargs=kwargs, type_=str
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
        self.initial_funds = kwargs.get("initial_funds", DEFAULT_INITIAL_FUNDS)

        super().__init__(*args, **kwargs)


class RandomnessApi(ApiSpecs):
    """A model for randomness api specifications."""


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool

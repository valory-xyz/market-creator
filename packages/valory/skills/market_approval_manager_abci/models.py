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

"""This module contains the shared state for the abci skill of MarketApprovalManagerAbciApp."""

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



class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls = MarketCreationManagerAbciApp


class MarketApprovalManagerParams(BaseParams):
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
        self.market_identification_prompt = self._ensure(
            key="market_identification_prompt", kwargs=kwargs, type_=str
        )
        super().__init__(*args, **kwargs)


class RandomnessApi(ApiSpecs):
    """A model for randomness api specifications."""


class OmenSubgraph(ApiSpecs):
    """A model that wraps ApiSpecs for the OMEN's subgraph specifications."""


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool

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

"""This module contains the shared state for the omen_funds_recoverer_abci skill."""

from typing import Any, Type

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
from packages.valory.skills.omen_funds_recoverer_abci.rounds import (
    OmenFundsRecovererAbciApp,
)


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls: Type[AbciApp] = OmenFundsRecovererAbciApp

    def __init__(self, *args: Any, skill_context: SkillContext, **kwargs: Any) -> None:
        """Initialize the shared state object."""
        super().__init__(*args, skill_context=skill_context, **kwargs)


class OmenFundsRecovererParams(BaseParams):
    """Parameters for the omen_funds_recoverer_abci skill."""

    # These parameters are from other ABCI skills, and are added
    # here as class attributes to avoid subclassing issues in MRO.
    # They get set by whichever parent class calls _ensure first.
    multisend_address: str
    multisend_batch_size: int
    realitio_contract: str
    realitio_oracle_proxy_contract: str
    conditional_tokens_contract: str
    collateral_tokens_contract: str

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the parameters object."""
        self.liquidity_removal_lead_time = self._ensure(
            "liquidity_removal_lead_time", kwargs, type_=int
        )
        self.remove_liquidity_batch_size = self._ensure(
            "remove_liquidity_batch_size", kwargs, type_=int
        )
        self.redeem_positions_batch_size = self._ensure(
            "redeem_positions_batch_size", kwargs, type_=int
        )
        self.claim_bonds_batch_size = self._ensure(
            "claim_bonds_batch_size", kwargs, type_=int
        )
        self.min_balance_withdraw_realitio = self._ensure(
            "min_balance_withdraw_realitio", kwargs, type_=int
        )
        self.realitio_start_block = self._ensure(
            "realitio_start_block", kwargs, type_=int
        )
        super().__init__(*args, **kwargs)


class OmenSubgraph(ApiSpecs):
    """A model that wraps ApiSpecs for the Omen subgraph."""


class ConditionalTokensSubgraph(ApiSpecs):
    """A model that wraps ApiSpecs for the ConditionalTokens subgraph."""


class RealitioSubgraph(ApiSpecs):
    """A model that wraps ApiSpecs for the Realitio subgraph."""


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool

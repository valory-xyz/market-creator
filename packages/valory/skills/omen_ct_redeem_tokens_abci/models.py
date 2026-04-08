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

"""This module contains the shared state for the omen_ct_redeem_tokens_abci skill."""

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
from packages.valory.skills.omen_ct_redeem_tokens_abci.rounds import (
    OmenCtRedeemTokensAbciApp,
)


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls: Type[AbciApp] = OmenCtRedeemTokensAbciApp

    def __init__(  # pylint: disable=useless-parent-delegation
        self, *args: Any, skill_context: SkillContext, **kwargs: Any
    ) -> None:
        """Initialize the shared state object."""
        super().__init__(*args, skill_context=skill_context, **kwargs)


class CtRedeemTokensParams(BaseParams):
    """Parameters for the omen_ct_redeem_tokens_abci skill."""

    # These parameters are from other ABCI skills, and are added
    # here to avoid subclassing and avoid MyPy linter issues.
    multisend_address: str
    multisend_batch_size: int

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the parameters object."""
        self.ct_redeem_tokens_batch_size = self._ensure(
            "ct_redeem_tokens_batch_size", kwargs, type_=int
        )
        self.conditional_tokens_contract = self._ensure(
            key="conditional_tokens_contract", kwargs=kwargs, type_=str
        )
        self.realitio_oracle_proxy_contract = self._ensure(
            key="realitio_oracle_proxy_contract", kwargs=kwargs, type_=str
        )
        self.collateral_tokens_contract = self._ensure(
            key="collateral_tokens_contract", kwargs=kwargs, type_=str
        )
        super().__init__(*args, **kwargs)


class OmenSubgraph(ApiSpecs):
    """A model that wraps ApiSpecs for the Omen subgraph."""


class ConditionalTokensSubgraph(ApiSpecs):
    """A model that wraps ApiSpecs for the ConditionalTokens subgraph."""


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool

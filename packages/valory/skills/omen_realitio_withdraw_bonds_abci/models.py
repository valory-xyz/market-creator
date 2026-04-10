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

"""Shared state and params for the omen_realitio_withdraw_bonds_abci skill."""

from typing import Any, Type

from aea.exceptions import enforce

from packages.valory.skills.abstract_round_abci.base import AbciApp
from packages.valory.skills.abstract_round_abci.models import ApiSpecs, BaseParams
from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.abstract_round_abci.models import (
    SharedState as BaseSharedState,
)
from packages.valory.skills.omen_realitio_withdraw_bonds_abci.rounds import (
    OmenRealitioWithdrawBondsAbciApp,
)


class SharedState(BaseSharedState):
    """Shared state of the skill."""

    abci_app_cls: Type[AbciApp] = OmenRealitioWithdrawBondsAbciApp


class RealitioWithdrawBondsParams(BaseParams):
    """Parameters for the omen_realitio_withdraw_bonds_abci skill."""

    multisend_address: str
    multisend_batch_size: int

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the parameters object."""
        self.realitio_withdraw_bonds_batch_size = self._ensure(
            "realitio_withdraw_bonds_batch_size", kwargs, type_=int
        )
        self.min_realitio_withdraw_balance = self._ensure(
            "min_realitio_withdraw_balance", kwargs, type_=int
        )
        # Contract address is read without popping so sibling params
        # classes in a composed MRO can still see it.
        self.realitio_contract: str = kwargs.get(
            "realitio_contract"
        )  # type: ignore[assignment]
        enforce(
            self.realitio_contract is not None,
            "`realitio_contract` is required",
        )
        super().__init__(*args, **kwargs)


class RealitioSubgraph(ApiSpecs):
    """ApiSpecs wrapper for the Realitio subgraph."""


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool

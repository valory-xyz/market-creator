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

"""Models for the omen_realitio_bond_withdraw_abci skill."""

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
from packages.valory.skills.omen_realitio_bond_withdraw_abci.rounds import (
    OmenRealitioBondWithdrawAbciApp,
)


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls: Type[AbciApp] = OmenRealitioBondWithdrawAbciApp

    def __init__(  # pylint: disable=useless-parent-delegation
        self, *args: Any, skill_context: SkillContext, **kwargs: Any
    ) -> None:
        """Initialize the shared state object."""
        super().__init__(*args, skill_context=skill_context, **kwargs)


class RealitioBondWithdrawParams(BaseParams):
    """Parameters for the omen_realitio_bond_withdraw_abci skill.

    Carries only the params this skill actually uses. Notably absent:

    - ``realitio_start_block``: deleted from the design entirely. The
      per-question ``from_block = max(0, createdBlock - 1)`` is computed
      from the subgraph result inside the behaviour, so a global lower
      bound is unnecessary and misleading. Keeping it would invite
      operators to set it back to a chain-wide value and re-introduce
      the timeout bug fixed in the prior debugging session.
    """

    # Inherited from BaseParams via the skill.yaml override path,
    # declared here as class attributes for mypy.
    multisend_address: str
    multisend_batch_size: int

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the parameters object."""
        self.realitio_bond_withdraw_batch_size = self._ensure(
            "realitio_bond_withdraw_batch_size", kwargs, type_=int
        )
        self.min_balance_withdraw_realitio = self._ensure(
            "min_balance_withdraw_realitio", kwargs, type_=int
        )
        self.realitio_contract = self._ensure(
            key="realitio_contract", kwargs=kwargs, type_=str
        )
        super().__init__(*args, **kwargs)


class RealitioSubgraph(ApiSpecs):
    """A model that wraps ApiSpecs for the Realitio subgraph."""


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool

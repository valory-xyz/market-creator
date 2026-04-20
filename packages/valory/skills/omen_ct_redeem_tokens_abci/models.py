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

"""Shared state and params for the omen_ct_redeem_tokens_abci skill."""

from typing import Any, Set, Type

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
from packages.valory.skills.omen_ct_redeem_tokens_abci.rounds import (
    OmenCtRedeemTokensAbciApp,
)


class SharedState(BaseSharedState):
    """Shared state of the skill."""

    abci_app_cls: Type[AbciApp] = OmenCtRedeemTokensAbciApp

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the shared state."""
        super().__init__(*args, **kwargs)
        self.ignored_ct_positions: Set[str] = set()


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
        self.ct_redeem_tokens_min_payout = self._ensure(
            "ct_redeem_tokens_min_payout", kwargs, type_=int
        )
        # Contract addresses are read without popping so sibling params
        # classes in a composed MRO can still see them.
        self.conditional_tokens_contract: str = kwargs.get(
            "conditional_tokens_contract"
        )  # type: ignore[assignment]
        enforce(
            self.conditional_tokens_contract is not None,
            "`conditional_tokens_contract` is required",
        )
        self.collateral_tokens_contract: str = kwargs.get(
            "collateral_tokens_contract"
        )  # type: ignore[assignment]
        enforce(
            self.collateral_tokens_contract is not None,
            "`collateral_tokens_contract` is required",
        )
        self.realitio_oracle_proxy_contract: str = kwargs.get(
            "realitio_oracle_proxy_contract"
        )  # type: ignore[assignment]
        enforce(
            self.realitio_oracle_proxy_contract is not None,
            "`realitio_oracle_proxy_contract` is required",
        )
        super().__init__(*args, **kwargs)


class OmenSubgraph(ApiSpecs):
    """ApiSpecs wrapper for the Omen subgraph."""


class ConditionalTokensSubgraph(ApiSpecs):
    """ApiSpecs wrapper for the ConditionalTokens subgraph."""


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool

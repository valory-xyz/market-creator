# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2021-2023 Valory AG
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

"""This module contains the shared state for the price estimation app ABCI application."""

from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.market_creation_manager_abci.models import (
    MarketCreationManagerParams,
)
from packages.valory.skills.market_creation_manager_abci.models import (
    OmenSubgraph as BaseOmenSubgraph,
)
from packages.valory.skills.market_creation_manager_abci.models import (
    RandomnessApi as MarketCreationManagerRandomnessApi,
)
from packages.valory.skills.market_creation_manager_abci.models import (
    SharedState as BaseSharedState,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    Event as MarketCreationManagerEvent,
)
from packages.valory.skills.market_maker_abci.composition import MarketCreatorAbciApp
from packages.valory.skills.reset_pause_abci.rounds import Event as ResetPauseEvent
from packages.valory.skills.termination_abci.models import TerminationParams
from packages.valory.skills.transaction_settlement_abci.rounds import Event as TSEvent


MARGIN = 5
MULTIPLIER = 2

Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool
RandomnessApi = MarketCreationManagerRandomnessApi
OmenSubgraph = BaseOmenSubgraph


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls = MarketCreatorAbciApp

    def setup(self) -> None:
        """Set up."""
        super().setup()
        MarketCreatorAbciApp.event_to_timeout[
            MarketCreationManagerEvent.ROUND_TIMEOUT
        ] = self.context.params.round_timeout_seconds
        MarketCreatorAbciApp.event_to_timeout[
            TSEvent.ROUND_TIMEOUT
        ] = self.context.params.round_timeout_seconds

        # The MARKET_PROPOSAL_ROUND_TIMEOUT must be computed based on the "market_proposal_round_timeout_seconds_per_day" parameter.
        # This parameter represents the maximum timeout it takes to execute the LLM query + proposing the received questions to the
        # market proposal server for a single day. It should be typically set about 30-45 seconds.
        MarketCreatorAbciApp.event_to_timeout[
            MarketCreationManagerEvent.MARKET_PROPOSAL_ROUND_TIMEOUT
        ] = (
            max(
                self.context.params.round_timeout_seconds,
                self.context.params.market_proposal_round_timeout_seconds_per_day
                * (
                    self.context.params.event_offset_end_days
                    - self.context.params.event_offset_start_days
                    + 1
                ),
            )
            + MARGIN
        )

        MarketCreatorAbciApp.event_to_timeout[
            ResetPauseEvent.ROUND_TIMEOUT
        ] = self.context.params.round_timeout_seconds
        MarketCreatorAbciApp.event_to_timeout[TSEvent.RESET_TIMEOUT] = (
            self.context.params.round_timeout_seconds * MULTIPLIER
        )
        MarketCreatorAbciApp.event_to_timeout[
            TSEvent.VALIDATE_TIMEOUT
        ] = self.context.params.validate_timeout
        MarketCreatorAbciApp.event_to_timeout[
            TSEvent.FINALIZE_TIMEOUT
        ] = self.context.params.finalize_timeout
        MarketCreatorAbciApp.event_to_timeout[
            TSEvent.CHECK_TIMEOUT
        ] = self.context.params.history_check_timeout
        MarketCreatorAbciApp.event_to_timeout[
            ResetPauseEvent.RESET_AND_PAUSE_TIMEOUT
        ] = (self.context.params.reset_pause_duration + MARGIN)


class Params(
    MarketCreationManagerParams,
    TerminationParams,
):
    """A model to represent params for multiple abci apps."""

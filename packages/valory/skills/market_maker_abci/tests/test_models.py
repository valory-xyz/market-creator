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

"""Tests for the market_maker_abci models."""

from unittest.mock import MagicMock, patch

from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.market_creation_manager_abci.models import (
    OmenSubgraph as BaseOmenSubgraph,
)
from packages.valory.skills.market_creation_manager_abci.models import (
    RandomnessApi as MarketCreationManagerRandomnessApi,
)
from packages.valory.skills.market_creation_manager_abci.models import (
    SharedState as BaseSharedState,
)
from packages.valory.skills.market_maker_abci.models import (
    BenchmarkTool,
    MARGIN,
    MULTIPLIER,
    OmenSubgraph,
    Params,
    RandomnessApi,
    Requests,
    SharedState,
)
from packages.valory.skills.termination_abci.models import TerminationParams


class TestModelAliases:
    """Test module-level model aliases."""

    def test_requests_alias(self) -> None:
        """Test Requests alias."""
        assert Requests is BaseRequests

    def test_benchmark_tool_alias(self) -> None:
        """Test BenchmarkTool alias."""
        assert BenchmarkTool is BaseBenchmarkTool

    def test_randomness_api_alias(self) -> None:
        """Test RandomnessApi alias."""
        assert RandomnessApi is MarketCreationManagerRandomnessApi

    def test_omen_subgraph_alias(self) -> None:
        """Test OmenSubgraph alias."""
        assert OmenSubgraph is BaseOmenSubgraph


class TestConstants:
    """Test module-level constants."""

    def test_margin(self) -> None:
        """Test MARGIN value."""
        assert MARGIN == 5

    def test_multiplier(self) -> None:
        """Test MULTIPLIER value."""
        assert MULTIPLIER == 2


class TestSharedState:
    """Test SharedState class."""

    def test_inherits_base_shared_state(self) -> None:
        """Test inheritance."""
        assert issubclass(SharedState, BaseSharedState)

    def test_abci_app_cls(self) -> None:
        """Test abci_app_cls is set."""
        from packages.valory.skills.market_maker_abci.composition import (
            MarketCreatorAbciApp,
        )

        assert SharedState.abci_app_cls == MarketCreatorAbciApp

    def test_setup_populates_event_to_timeout(self) -> None:
        """Test that setup populates event_to_timeout with the right keys."""
        from packages.valory.skills.funds_forwarder_abci.rounds import (
            Event as FundsForwarderEvent,
        )
        from packages.valory.skills.identify_service_owner_abci.rounds import (
            Event as IdentifyServiceOwnerEvent,
        )
        from packages.valory.skills.market_creation_manager_abci.rounds import (
            Event as MarketCreationManagerEvent,
        )
        from packages.valory.skills.market_maker_abci.composition import (
            MarketCreatorAbciApp,
        )
        from packages.valory.skills.reset_pause_abci.rounds import (
            Event as ResetPauseEvent,
        )
        from packages.valory.skills.transaction_settlement_abci.rounds import (
            Event as TSEvent,
        )

        context = MagicMock()
        context.params.round_timeout_seconds = 30
        context.params.reset_pause_duration = 10
        context.params.validate_timeout = 60
        context.params.finalize_timeout = 90
        context.params.history_check_timeout = 120

        state = SharedState.__new__(SharedState)
        state._context = context  # type: ignore[attr-defined]
        state._skill_context = context  # type: ignore[attr-defined]

        with patch.object(BaseSharedState, "setup"):
            state.setup()

        assert (
            MarketCreatorAbciApp.event_to_timeout[
                MarketCreationManagerEvent.ROUND_TIMEOUT
            ]
            == 30
        )
        assert MarketCreatorAbciApp.event_to_timeout[TSEvent.ROUND_TIMEOUT] == 30
        assert (
            MarketCreatorAbciApp.event_to_timeout[ResetPauseEvent.ROUND_TIMEOUT] == 30
        )
        assert (
            MarketCreatorAbciApp.event_to_timeout[TSEvent.RESET_TIMEOUT]
            == 30 * MULTIPLIER
        )
        assert MarketCreatorAbciApp.event_to_timeout[TSEvent.VALIDATE_TIMEOUT] == 60
        assert MarketCreatorAbciApp.event_to_timeout[TSEvent.FINALIZE_TIMEOUT] == 90
        assert MarketCreatorAbciApp.event_to_timeout[TSEvent.CHECK_TIMEOUT] == 120
        assert (
            MarketCreatorAbciApp.event_to_timeout[
                ResetPauseEvent.RESET_AND_PAUSE_TIMEOUT
            ]
            == 10 + MARGIN
        )
        assert (
            MarketCreatorAbciApp.event_to_timeout[
                IdentifyServiceOwnerEvent.ROUND_TIMEOUT
            ]
            == 30
        )
        assert (
            MarketCreatorAbciApp.event_to_timeout[FundsForwarderEvent.ROUND_TIMEOUT]
            == 30
        )


class TestParams:
    """Test Params class."""

    def test_params_mro(self) -> None:
        """Test Params inherits from all required param classes."""
        from packages.valory.skills.market_creation_manager_abci.models import (
            MarketCreationManagerParams,
        )

        assert issubclass(Params, MarketCreationManagerParams)
        assert issubclass(Params, TerminationParams)

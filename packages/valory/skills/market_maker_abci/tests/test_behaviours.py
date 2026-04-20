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

"""Tests for the market_maker_abci behaviours."""

from packages.valory.skills.abstract_round_abci.behaviours import AbstractRoundBehaviour
from packages.valory.skills.market_creation_manager_abci.behaviours.round_behaviour import (
    MarketCreationManagerRoundBehaviour,
)
from packages.valory.skills.market_maker_abci.behaviours import (
    MarketCreatorRoundBehaviour,
)
from packages.valory.skills.market_maker_abci.composition import MarketCreatorAbciApp
from packages.valory.skills.registration_abci.behaviours import (
    AgentRegistrationRoundBehaviour,
    RegistrationStartupBehaviour,
)
from packages.valory.skills.reset_pause_abci.behaviours import (
    ResetPauseABCIConsensusBehaviour,
)
from packages.valory.skills.termination_abci.behaviours import (
    BackgroundBehaviour,
    TerminationAbciBehaviours,
)
from packages.valory.skills.transaction_settlement_abci.behaviours import (
    TransactionSettlementRoundBehaviour,
)


class TestMarketCreatorRoundBehaviour:
    """Test MarketCreatorRoundBehaviour class."""

    def test_inherits_abstract_round_behaviour(self) -> None:
        """Test inheritance."""
        assert issubclass(MarketCreatorRoundBehaviour, AbstractRoundBehaviour)

    def test_initial_behaviour_cls(self) -> None:
        """Test initial_behaviour_cls."""
        assert (
            MarketCreatorRoundBehaviour.initial_behaviour_cls
            == RegistrationStartupBehaviour
        )

    def test_abci_app_cls(self) -> None:
        """Test abci_app_cls."""
        assert MarketCreatorRoundBehaviour.abci_app_cls == MarketCreatorAbciApp

    def test_behaviours_contains_registration(self) -> None:
        """Test behaviours set contains agent registration."""
        assert AgentRegistrationRoundBehaviour.behaviours.issubset(
            MarketCreatorRoundBehaviour.behaviours
        )

    def test_behaviours_contains_market_creation_manager(self) -> None:
        """Test behaviours set contains market creation manager."""
        assert MarketCreationManagerRoundBehaviour.behaviours.issubset(
            MarketCreatorRoundBehaviour.behaviours
        )

    def test_behaviours_contains_transaction_settlement(self) -> None:
        """Test behaviours set contains transaction settlement."""
        assert TransactionSettlementRoundBehaviour.behaviours.issubset(
            MarketCreatorRoundBehaviour.behaviours
        )

    def test_behaviours_contains_reset_pause(self) -> None:
        """Test behaviours set contains reset pause."""
        assert ResetPauseABCIConsensusBehaviour.behaviours.issubset(
            MarketCreatorRoundBehaviour.behaviours
        )

    def test_behaviours_contains_termination(self) -> None:
        """Test behaviours set contains termination."""
        assert TerminationAbciBehaviours.behaviours.issubset(
            MarketCreatorRoundBehaviour.behaviours
        )

    def test_background_behaviours_cls(self) -> None:
        """Test background_behaviours_cls."""
        assert MarketCreatorRoundBehaviour.background_behaviours_cls == {
            BackgroundBehaviour
        }

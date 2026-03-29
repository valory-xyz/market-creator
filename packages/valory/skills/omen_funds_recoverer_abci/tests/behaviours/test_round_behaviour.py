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

"""Tests for OmenFundsRecovererRoundBehaviour."""

from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
)
from packages.valory.skills.omen_funds_recoverer_abci.behaviours.build_multisend import (
    BuildMultisendBehaviour,
)
from packages.valory.skills.omen_funds_recoverer_abci.behaviours.claim_bonds import (
    ClaimBondsBehaviour,
)
from packages.valory.skills.omen_funds_recoverer_abci.behaviours.redeem_positions import (
    RedeemPositionsBehaviour,
)
from packages.valory.skills.omen_funds_recoverer_abci.behaviours.remove_liquidity import (
    RemoveLiquidityBehaviour,
)
from packages.valory.skills.omen_funds_recoverer_abci.behaviours.round_behaviour import (
    OmenFundsRecovererRoundBehaviour,
)
from packages.valory.skills.omen_funds_recoverer_abci.rounds import (
    OmenFundsRecovererAbciApp,
)


class TestOmenFundsRecovererRoundBehaviour:
    """Tests for OmenFundsRecovererRoundBehaviour class."""

    def test_inherits_abstract_round_behaviour(self) -> None:
        """Test that it inherits from AbstractRoundBehaviour."""
        assert issubclass(OmenFundsRecovererRoundBehaviour, AbstractRoundBehaviour)

    def test_initial_behaviour_cls(self) -> None:
        """Test initial_behaviour_cls is RemoveLiquidityBehaviour."""
        assert (
            OmenFundsRecovererRoundBehaviour.initial_behaviour_cls
            is RemoveLiquidityBehaviour
        )

    def test_abci_app_cls(self) -> None:
        """Test abci_app_cls is OmenFundsRecovererAbciApp."""
        assert (
            OmenFundsRecovererRoundBehaviour.abci_app_cls is OmenFundsRecovererAbciApp
        )

    def test_behaviours_set(self) -> None:
        """Test behaviours set contains all 4 behaviours."""
        expected = {
            RemoveLiquidityBehaviour,
            RedeemPositionsBehaviour,
            ClaimBondsBehaviour,
            BuildMultisendBehaviour,
        }
        assert OmenFundsRecovererRoundBehaviour.behaviours == expected

    def test_behaviours_count(self) -> None:
        """Test that there are exactly 4 behaviours."""
        assert len(OmenFundsRecovererRoundBehaviour.behaviours) == 4

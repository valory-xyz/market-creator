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

"""Tests for OmenFpmmLiquidityRemoveRoundBehaviour."""

from packages.valory.skills.abstract_round_abci.behaviours import AbstractRoundBehaviour
from packages.valory.skills.omen_fpmm_liquidity_remove_abci.behaviours.fpmm_liquidity_remove import (
    FpmmLiquidityRemoveBehaviour,
)
from packages.valory.skills.omen_fpmm_liquidity_remove_abci.behaviours.round_behaviour import (
    OmenFpmmLiquidityRemoveRoundBehaviour,
)
from packages.valory.skills.omen_fpmm_liquidity_remove_abci.rounds import (
    OmenFpmmLiquidityRemoveAbciApp,
)


class TestOmenFpmmLiquidityRemoveRoundBehaviour:
    """Tests for OmenFpmmLiquidityRemoveRoundBehaviour class attributes."""

    def test_is_abstract_round_behaviour(self) -> None:
        """Test that OmenFpmmLiquidityRemoveRoundBehaviour subclasses AbstractRoundBehaviour."""
        assert issubclass(OmenFpmmLiquidityRemoveRoundBehaviour, AbstractRoundBehaviour)

    def test_initial_behaviour_cls(self) -> None:
        """initial_behaviour_cls is FpmmLiquidityRemoveBehaviour."""
        assert (
            OmenFpmmLiquidityRemoveRoundBehaviour.initial_behaviour_cls
            is FpmmLiquidityRemoveBehaviour
        )

    def test_abci_app_cls(self) -> None:
        """abci_app_cls is OmenFpmmLiquidityRemoveAbciApp."""
        assert (
            OmenFpmmLiquidityRemoveRoundBehaviour.abci_app_cls
            is OmenFpmmLiquidityRemoveAbciApp
        )

    def test_behaviours_contains_fpmm_behaviour(self) -> None:
        """Test that behaviours set contains FpmmLiquidityRemoveBehaviour."""
        assert (
            FpmmLiquidityRemoveBehaviour
            in OmenFpmmLiquidityRemoveRoundBehaviour.behaviours
        )

    def test_behaviours_count(self) -> None:
        """Test that behaviours set contains exactly one behaviour."""
        assert len(OmenFpmmLiquidityRemoveRoundBehaviour.behaviours) == 1

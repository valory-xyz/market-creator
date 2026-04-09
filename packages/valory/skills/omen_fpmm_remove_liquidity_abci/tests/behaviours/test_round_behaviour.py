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

"""Tests for OmenFpmmRemoveLiquidityRoundBehaviour."""

from packages.valory.skills.abstract_round_abci.behaviours import AbstractRoundBehaviour
from packages.valory.skills.omen_fpmm_remove_liquidity_abci.behaviours.remove_liquidity import (
    FpmmRemoveLiquidityBehaviour,
)
from packages.valory.skills.omen_fpmm_remove_liquidity_abci.behaviours.round_behaviour import (
    OmenFpmmRemoveLiquidityRoundBehaviour,
)
from packages.valory.skills.omen_fpmm_remove_liquidity_abci.rounds import (
    OmenFpmmRemoveLiquidityAbciApp,
)


class TestOmenFpmmRemoveLiquidityRoundBehaviour:
    """Tests for OmenFpmmRemoveLiquidityRoundBehaviour class attributes."""

    def test_is_abstract_round_behaviour(self) -> None:
        """Test that OmenFpmmRemoveLiquidityRoundBehaviour subclasses AbstractRoundBehaviour."""
        assert issubclass(OmenFpmmRemoveLiquidityRoundBehaviour, AbstractRoundBehaviour)

    def test_initial_behaviour_cls(self) -> None:
        """initial_behaviour_cls is FpmmRemoveLiquidityBehaviour."""
        assert (
            OmenFpmmRemoveLiquidityRoundBehaviour.initial_behaviour_cls
            is FpmmRemoveLiquidityBehaviour
        )

    def test_abci_app_cls(self) -> None:
        """abci_app_cls is OmenFpmmRemoveLiquidityAbciApp."""
        assert (
            OmenFpmmRemoveLiquidityRoundBehaviour.abci_app_cls
            is OmenFpmmRemoveLiquidityAbciApp
        )

    def test_behaviours_contains_fpmm_behaviour(self) -> None:
        """Test that behaviours set contains FpmmRemoveLiquidityBehaviour."""
        assert (
            FpmmRemoveLiquidityBehaviour
            in OmenFpmmRemoveLiquidityRoundBehaviour.behaviours
        )

    def test_behaviours_count(self) -> None:
        """Test that behaviours set contains exactly one behaviour."""
        assert len(OmenFpmmRemoveLiquidityRoundBehaviour.behaviours) == 1

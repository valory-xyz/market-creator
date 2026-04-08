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

"""Tests for OmenRealitioWithdrawBondRoundBehaviour."""

from packages.valory.skills.abstract_round_abci.behaviours import AbstractRoundBehaviour
from packages.valory.skills.omen_realitio_withdraw_bond_abci.behaviours.round_behaviour import (
    OmenRealitioWithdrawBondRoundBehaviour,
)
from packages.valory.skills.omen_realitio_withdraw_bond_abci.behaviours.withdraw_bond import (
    RealitioWithdrawBondBehaviour,
)
from packages.valory.skills.omen_realitio_withdraw_bond_abci.rounds import (
    OmenRealitioWithdrawBondAbciApp,
)


class TestOmenRealitioWithdrawBondRoundBehaviour:
    """Tests for OmenRealitioWithdrawBondRoundBehaviour class."""

    def test_inherits_abstract_round_behaviour(self) -> None:
        """Test that it inherits from AbstractRoundBehaviour."""
        assert issubclass(
            OmenRealitioWithdrawBondRoundBehaviour, AbstractRoundBehaviour
        )

    def test_initial_behaviour_cls(self) -> None:
        """Test initial_behaviour_cls is RealitioWithdrawBondBehaviour."""
        assert (
            OmenRealitioWithdrawBondRoundBehaviour.initial_behaviour_cls
            is RealitioWithdrawBondBehaviour
        )

    def test_abci_app_cls(self) -> None:
        """Test abci_app_cls is OmenRealitioWithdrawBondAbciApp."""
        assert (
            OmenRealitioWithdrawBondRoundBehaviour.abci_app_cls
            is OmenRealitioWithdrawBondAbciApp
        )

    def test_behaviours_set(self) -> None:
        """Test behaviours set contains exactly RealitioWithdrawBondBehaviour."""
        assert OmenRealitioWithdrawBondRoundBehaviour.behaviours == {
            RealitioWithdrawBondBehaviour
        }

    def test_behaviours_count(self) -> None:
        """Test that there is exactly 1 behaviour."""
        assert len(OmenRealitioWithdrawBondRoundBehaviour.behaviours) == 1

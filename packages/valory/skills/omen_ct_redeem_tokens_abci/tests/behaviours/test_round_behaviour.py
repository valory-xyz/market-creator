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

"""Tests for CtRedeemTokensRoundBehaviour."""

from packages.valory.skills.abstract_round_abci.behaviours import AbstractRoundBehaviour
from packages.valory.skills.omen_ct_redeem_tokens_abci.behaviours.redeem_tokens import (
    CtRedeemTokensBehaviour,
)
from packages.valory.skills.omen_ct_redeem_tokens_abci.behaviours.round_behaviour import (
    CtRedeemTokensRoundBehaviour,
)
from packages.valory.skills.omen_ct_redeem_tokens_abci.rounds import (
    OmenCtRedeemTokensAbciApp,
)


class TestCtRedeemTokensRoundBehaviour:
    """Tests for CtRedeemTokensRoundBehaviour class."""

    def test_inherits_abstract_round_behaviour(self) -> None:
        """Test that it inherits from AbstractRoundBehaviour."""
        assert issubclass(CtRedeemTokensRoundBehaviour, AbstractRoundBehaviour)

    def test_initial_behaviour_cls(self) -> None:
        """Test initial_behaviour_cls is CtRedeemTokensBehaviour."""
        assert (
            CtRedeemTokensRoundBehaviour.initial_behaviour_cls
            is CtRedeemTokensBehaviour
        )

    def test_abci_app_cls(self) -> None:
        """Test abci_app_cls is OmenCtRedeemTokensAbciApp."""
        assert CtRedeemTokensRoundBehaviour.abci_app_cls is OmenCtRedeemTokensAbciApp

    def test_behaviours_set(self) -> None:
        """Test behaviours set contains exactly CtRedeemTokensBehaviour."""
        expected = {CtRedeemTokensBehaviour}
        assert CtRedeemTokensRoundBehaviour.behaviours == expected

    def test_behaviours_count(self) -> None:
        """Test that there is exactly 1 behaviour."""
        assert len(CtRedeemTokensRoundBehaviour.behaviours) == 1

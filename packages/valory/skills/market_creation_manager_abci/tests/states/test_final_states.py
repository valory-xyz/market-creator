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

"""Tests for the final states of the MarketCreationManagerAbciApp."""

import pytest

from packages.valory.skills.abstract_round_abci.base import DegenerateRound
from packages.valory.skills.market_creation_manager_abci.states.final_states import (
    FinishedMarketCreationManagerRound,
    FinishedWithAnswerQuestionsRound,
    FinishedWithDepositDaiRound,
    FinishedWithGetPendingQuestionsRound,
    FinishedWithMechRequestRound,
    FinishedWithRedeemBondRound,
    FinishedWithRemoveFundingRound,
    FinishedWithoutTxRound,
)


ALL_FINAL_STATES = [
    FinishedMarketCreationManagerRound,
    FinishedWithRemoveFundingRound,
    FinishedWithDepositDaiRound,
    FinishedWithRedeemBondRound,
    FinishedWithoutTxRound,
    FinishedWithGetPendingQuestionsRound,
    FinishedWithAnswerQuestionsRound,
    FinishedWithMechRequestRound,
]


@pytest.mark.parametrize("final_state_cls", ALL_FINAL_STATES)
def test_final_state_is_degenerate_round(final_state_cls: type) -> None:
    """Test that each final state is a subclass of DegenerateRound."""
    assert issubclass(final_state_cls, DegenerateRound)


def test_all_final_states_count() -> None:
    """Test that we have exactly 8 final states."""
    assert len(ALL_FINAL_STATES) == 8


@pytest.mark.parametrize("final_state_cls", ALL_FINAL_STATES)
def test_final_state_has_docstring(final_state_cls: type) -> None:
    """Test that each final state has a docstring."""
    assert final_state_cls.__doc__ is not None

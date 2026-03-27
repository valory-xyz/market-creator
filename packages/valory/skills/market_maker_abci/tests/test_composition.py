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

"""Tests for the market_maker_abci composition."""

import pytest

import packages.valory.skills.funds_forwarder_abci.rounds as FundsForwarderAbci
import packages.valory.skills.identify_service_owner_abci.rounds as IdentifyServiceOwnerAbci
import packages.valory.skills.market_creation_manager_abci.rounds as MarketCreationManagerAbci
import packages.valory.skills.mech_interact_abci.states.final_states as MechFinalStates
import packages.valory.skills.mech_interact_abci.states.mech_version as MechVersionStates
import packages.valory.skills.mech_interact_abci.states.request as MechRequestStates
import packages.valory.skills.mech_interact_abci.states.response as MechResponseStates
import packages.valory.skills.transaction_settlement_abci.rounds as TransactionSettlementAbci
from packages.valory.skills.market_maker_abci.composition import (
    MarketCreatorAbciApp,
    abci_app_transition_mapping,
    termination_config,
)
from packages.valory.skills.registration_abci.rounds import (
    FinishedRegistrationRound,
    RegistrationRound,
)
from packages.valory.skills.reset_pause_abci.rounds import (
    FinishedResetAndPauseErrorRound,
    FinishedResetAndPauseRound,
    ResetAndPauseRound,
)
from packages.valory.skills.termination_abci.rounds import BackgroundRound, Event

# All expected (source_round, target_round) pairs in the transition mapping.
EXPECTED_TRANSITIONS = [
    (FinishedRegistrationRound, IdentifyServiceOwnerAbci.IdentifyServiceOwnerRound),
    (MarketCreationManagerAbci.FinishedWithoutTxRound, ResetAndPauseRound),
    (
        MarketCreationManagerAbci.FinishedWithDepositDaiRound,
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    ),
    (
        MarketCreationManagerAbci.FinishedWithRedeemBondRound,
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    ),
    (
        MarketCreationManagerAbci.FinishedMarketCreationManagerRound,
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    ),
    (
        MarketCreationManagerAbci.FinishedWithRemoveFundingRound,
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    ),
    (
        MarketCreationManagerAbci.FinishedWithGetPendingQuestionsRound,
        MechVersionStates.MechVersionDetectionRound,
    ),
    (
        MechFinalStates.FinishedMarketplaceLegacyDetectedRound,
        MechRequestStates.MechRequestRound,
    ),
    (
        MechFinalStates.FinishedMechLegacyDetectedRound,
        MechRequestStates.MechRequestRound,
    ),
    (MechFinalStates.FinishedMechInformationRound, MechRequestStates.MechRequestRound),
    (
        MechFinalStates.FailedMechInformationRound,
        MechVersionStates.MechVersionDetectionRound,
    ),
    (
        MechFinalStates.FinishedMechRequestRound,
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    ),
    (
        MechFinalStates.FinishedMechPurchaseSubscriptionRound,
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    ),
    (
        MechFinalStates.FinishedMechResponseRound,
        MarketCreationManagerAbci.AnswerQuestionsRound,
    ),
    (
        MechFinalStates.FinishedMechRequestSkipRound,
        MarketCreationManagerAbci.CollectRandomnessRound,
    ),
    (
        MechFinalStates.FinishedMechResponseTimeoutRound,
        MarketCreationManagerAbci.CollectRandomnessRound,
    ),
    (
        MarketCreationManagerAbci.FinishedWithMechRequestRound,
        MechResponseStates.MechResponseRound,
    ),
    (
        MarketCreationManagerAbci.FinishedWithRedeemWinningsRound,
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    ),
    (
        MarketCreationManagerAbci.FinishedWithAnswerQuestionsRound,
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    ),
    (
        TransactionSettlementAbci.FinishedTransactionSubmissionRound,
        MarketCreationManagerAbci.PostTransactionRound,
    ),
    (TransactionSettlementAbci.FailedRound, ResetAndPauseRound),
    (FinishedResetAndPauseRound, IdentifyServiceOwnerAbci.IdentifyServiceOwnerRound),
    (FinishedResetAndPauseErrorRound, RegistrationRound),
    (
        IdentifyServiceOwnerAbci.FinishedIdentifyServiceOwnerRound,
        FundsForwarderAbci.FundsForwarderRound,
    ),
    (
        IdentifyServiceOwnerAbci.FinishedIdentifyServiceOwnerErrorRound,
        MarketCreationManagerAbci.SyncMarketsRound,
    ),
    (
        FundsForwarderAbci.FinishedFundsForwarderNoTxRound,
        MarketCreationManagerAbci.SyncMarketsRound,
    ),
    (
        FundsForwarderAbci.FinishedFundsForwarderWithTxRound,
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    ),
]


class TestAbciAppTransitionMapping:
    """Test abci_app_transition_mapping entries."""

    @pytest.mark.parametrize(
        "source, target",
        EXPECTED_TRANSITIONS,
        ids=[src.__name__ for src, _ in EXPECTED_TRANSITIONS],
    )
    def test_transition(self, source: type, target: type) -> None:
        """Test that source round maps to the expected target round."""
        assert abci_app_transition_mapping[source] == target

    def test_mapping_count(self) -> None:
        """Test total mapping count matches expected transitions."""
        assert len(abci_app_transition_mapping) == len(EXPECTED_TRANSITIONS)


class TestTerminationConfig:
    """Test termination_config."""

    def test_round_cls(self) -> None:
        """Test round_cls is BackgroundRound."""
        assert termination_config.round_cls == BackgroundRound

    def test_start_event(self) -> None:
        """Test start_event is Event.TERMINATE."""
        assert termination_config.start_event == Event.TERMINATE


class TestMarketCreatorAbciApp:
    """Test MarketCreatorAbciApp chained app."""

    def test_app_is_not_none(self) -> None:
        """Test chained app was created."""
        assert MarketCreatorAbciApp is not None

    def test_app_has_transition_function(self) -> None:
        """Test app has a transition function."""
        assert hasattr(MarketCreatorAbciApp, "transition_function")
        assert len(MarketCreatorAbciApp.transition_function) > 0

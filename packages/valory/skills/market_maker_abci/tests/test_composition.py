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


class TestAbciAppTransitionMapping:
    """Test abci_app_transition_mapping entries."""

    def test_finished_registration_round(self) -> None:
        """Test FinishedRegistrationRound maps to SyncMarketsRound."""
        assert (
            abci_app_transition_mapping[FinishedRegistrationRound]
            == MarketCreationManagerAbci.SyncMarketsRound
        )

    def test_finished_without_tx_round(self) -> None:
        """Test FinishedWithoutTxRound maps to ResetAndPauseRound."""
        assert (
            abci_app_transition_mapping[
                MarketCreationManagerAbci.FinishedWithoutTxRound
            ]
            == ResetAndPauseRound
        )

    def test_finished_with_deposit_dai_round(self) -> None:
        """Test FinishedWithDepositDaiRound maps to TransactionSettlement."""
        assert (
            abci_app_transition_mapping[
                MarketCreationManagerAbci.FinishedWithDepositDaiRound
            ]
            == TransactionSettlementAbci.RandomnessTransactionSubmissionRound
        )

    def test_finished_with_redeem_bond_round(self) -> None:
        """Test FinishedWithRedeemBondRound maps to TransactionSettlement."""
        assert (
            abci_app_transition_mapping[
                MarketCreationManagerAbci.FinishedWithRedeemBondRound
            ]
            == TransactionSettlementAbci.RandomnessTransactionSubmissionRound
        )

    def test_finished_market_creation_manager_round(self) -> None:
        """Test FinishedMarketCreationManagerRound maps to TransactionSettlement."""
        assert (
            abci_app_transition_mapping[
                MarketCreationManagerAbci.FinishedMarketCreationManagerRound
            ]
            == TransactionSettlementAbci.RandomnessTransactionSubmissionRound
        )

    def test_finished_with_remove_funding_round(self) -> None:
        """Test FinishedWithRemoveFundingRound maps to TransactionSettlement."""
        assert (
            abci_app_transition_mapping[
                MarketCreationManagerAbci.FinishedWithRemoveFundingRound
            ]
            == TransactionSettlementAbci.RandomnessTransactionSubmissionRound
        )

    def test_finished_with_get_pending_questions_round(self) -> None:
        """Test FinishedWithGetPendingQuestionsRound maps to MechVersionDetection."""
        assert (
            abci_app_transition_mapping[
                MarketCreationManagerAbci.FinishedWithGetPendingQuestionsRound
            ]
            == MechVersionStates.MechVersionDetectionRound
        )

    def test_mech_legacy_detected(self) -> None:
        """Test FinishedMechLegacyDetectedRound maps to MechRequestRound."""
        assert (
            abci_app_transition_mapping[MechFinalStates.FinishedMechLegacyDetectedRound]
            == MechRequestStates.MechRequestRound
        )

    def test_mech_information_finished(self) -> None:
        """Test FinishedMechInformationRound maps to MechRequestRound."""
        assert (
            abci_app_transition_mapping[MechFinalStates.FinishedMechInformationRound]
            == MechRequestStates.MechRequestRound
        )

    def test_mech_information_failed(self) -> None:
        """Test FailedMechInformationRound maps to MechVersionDetection."""
        assert (
            abci_app_transition_mapping[MechFinalStates.FailedMechInformationRound]
            == MechVersionStates.MechVersionDetectionRound
        )

    def test_mech_request_finished(self) -> None:
        """Test FinishedMechRequestRound maps to TransactionSettlement."""
        assert (
            abci_app_transition_mapping[MechFinalStates.FinishedMechRequestRound]
            == TransactionSettlementAbci.RandomnessTransactionSubmissionRound
        )

    def test_mech_response_finished(self) -> None:
        """Test FinishedMechResponseRound maps to AnswerQuestionsRound."""
        assert (
            abci_app_transition_mapping[MechFinalStates.FinishedMechResponseRound]
            == MarketCreationManagerAbci.AnswerQuestionsRound
        )

    def test_mech_request_skip_finished(self) -> None:
        """Test FinishedMechRequestSkipRound maps to CollectRandomnessRound."""
        assert (
            abci_app_transition_mapping[MechFinalStates.FinishedMechRequestSkipRound]
            == MarketCreationManagerAbci.CollectRandomnessRound
        )

    def test_mech_response_timeout_finished(self) -> None:
        """Test FinishedMechResponseTimeoutRound maps to CollectRandomnessRound."""
        assert (
            abci_app_transition_mapping[
                MechFinalStates.FinishedMechResponseTimeoutRound
            ]
            == MarketCreationManagerAbci.CollectRandomnessRound
        )

    def test_finished_with_mech_request_round(self) -> None:
        """Test FinishedWithMechRequestRound maps to MechResponseRound."""
        assert (
            abci_app_transition_mapping[
                MarketCreationManagerAbci.FinishedWithMechRequestRound
            ]
            == MechResponseStates.MechResponseRound
        )

    def test_finished_with_answer_questions_round(self) -> None:
        """Test FinishedWithAnswerQuestionsRound maps to TransactionSettlement."""
        assert (
            abci_app_transition_mapping[
                MarketCreationManagerAbci.FinishedWithAnswerQuestionsRound
            ]
            == TransactionSettlementAbci.RandomnessTransactionSubmissionRound
        )

    def test_transaction_settlement_finished(self) -> None:
        """Test FinishedTransactionSubmissionRound maps to PostTransactionRound."""
        assert (
            abci_app_transition_mapping[
                TransactionSettlementAbci.FinishedTransactionSubmissionRound
            ]
            == MarketCreationManagerAbci.PostTransactionRound
        )

    def test_transaction_settlement_failed(self) -> None:
        """Test FailedRound maps to ResetAndPauseRound."""
        assert (
            abci_app_transition_mapping[TransactionSettlementAbci.FailedRound]
            == ResetAndPauseRound
        )

    def test_finished_reset_and_pause(self) -> None:
        """Test FinishedResetAndPauseRound maps to SyncMarketsRound."""
        assert (
            abci_app_transition_mapping[FinishedResetAndPauseRound]
            == MarketCreationManagerAbci.SyncMarketsRound
        )

    def test_finished_reset_and_pause_error(self) -> None:
        """Test FinishedResetAndPauseErrorRound maps to RegistrationRound."""
        assert (
            abci_app_transition_mapping[FinishedResetAndPauseErrorRound]
            == RegistrationRound
        )

    def test_finished_with_redeem_winnings_round(self) -> None:
        """Test FinishedWithRedeemWinningsRound maps to TransactionSettlement."""
        assert (
            abci_app_transition_mapping[
                MarketCreationManagerAbci.FinishedWithRedeemWinningsRound
            ]
            == TransactionSettlementAbci.RandomnessTransactionSubmissionRound
        )

    def test_mapping_count(self) -> None:
        """Test total mapping count."""
        assert len(abci_app_transition_mapping) == 23


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

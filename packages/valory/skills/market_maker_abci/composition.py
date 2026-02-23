# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2024 Valory AG
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

"""This module contains the price estimation ABCI application."""

import packages.valory.skills.market_creation_manager_abci.rounds as MarketCreationManagerAbci
import packages.valory.skills.mech_interact_abci.rounds as MechInteractAbci
import packages.valory.skills.mech_interact_abci.states.final_states as MechFinalStates
import packages.valory.skills.mech_interact_abci.states.mech_version as MechVersionStates
import packages.valory.skills.mech_interact_abci.states.request as MechRequestStates
import packages.valory.skills.mech_interact_abci.states.response as MechResponseStates
import packages.valory.skills.transaction_settlement_abci.rounds as TransactionSettlementAbci
from packages.valory.skills.abstract_round_abci.abci_app_chain import (
    AbciAppTransitionMapping,
    chain,
)
from packages.valory.skills.abstract_round_abci.base import BackgroundAppConfig
from packages.valory.skills.registration_abci.rounds import (
    AgentRegistrationAbciApp,
    FinishedRegistrationRound,
    RegistrationRound,
)
from packages.valory.skills.reset_pause_abci.rounds import (
    FinishedResetAndPauseErrorRound,
    FinishedResetAndPauseRound,
    ResetAndPauseRound,
    ResetPauseAbciApp,
)
from packages.valory.skills.termination_abci.rounds import (
    BackgroundRound,
    Event,
    TerminationAbciApp,
)


abci_app_transition_mapping: AbciAppTransitionMapping = {
    FinishedRegistrationRound: MarketCreationManagerAbci.SyncMarketsRound,
    MarketCreationManagerAbci.FinishedWithoutTxRound: ResetAndPauseRound,
    MarketCreationManagerAbci.FinishedWithDepositDaiRound: TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    MarketCreationManagerAbci.FinishedWithRedeemBondRound: TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    MarketCreationManagerAbci.FinishedMarketCreationManagerRound: TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    MarketCreationManagerAbci.FinishedWithRemoveFundingRound: TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    MarketCreationManagerAbci.FinishedWithGetPendingQuestionsRound: MechVersionStates.MechVersionDetectionRound,
    MechFinalStates.FinishedMechLegacyDetectedRound: MechRequestStates.MechRequestRound,
    MechFinalStates.FinishedMechInformationRound: MechRequestStates.MechRequestRound,
    MechFinalStates.FailedMechInformationRound: MechVersionStates.MechVersionDetectionRound,
    MechFinalStates.FinishedMechRequestRound: TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    MechFinalStates.FinishedMechResponseRound: MarketCreationManagerAbci.AnswerQuestionsRound,
    MechFinalStates.FinishedMechRequestSkipRound: MarketCreationManagerAbci.CollectRandomnessRound,
    MechFinalStates.FinishedMechResponseTimeoutRound: MarketCreationManagerAbci.CollectRandomnessRound,
    MarketCreationManagerAbci.FinishedWithMechRequestRound: MechResponseStates.MechResponseRound,
    MarketCreationManagerAbci.FinishedWithAnswerQuestionsRound: TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    TransactionSettlementAbci.FinishedTransactionSubmissionRound: MarketCreationManagerAbci.PostTransactionRound,
    TransactionSettlementAbci.FailedRound: ResetAndPauseRound,
    FinishedResetAndPauseRound: MarketCreationManagerAbci.SyncMarketsRound,
    FinishedResetAndPauseErrorRound: RegistrationRound,
}

termination_config = BackgroundAppConfig(
    round_cls=BackgroundRound,
    start_event=Event.TERMINATE,
    abci_app=TerminationAbciApp,
)

MarketCreatorAbciApp = chain(
    (
        AgentRegistrationAbciApp,
        MarketCreationManagerAbci.MarketCreationManagerAbciApp,
        TransactionSettlementAbci.TransactionSubmissionAbciApp,
        ResetPauseAbciApp,
        MechInteractAbci.MechInteractAbciApp,
    ),
    abci_app_transition_mapping,
).add_background_app(termination_config)

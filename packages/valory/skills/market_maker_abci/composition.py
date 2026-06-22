# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2026 Valory AG
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

"""This module contains the market maker composed ABCI application."""

import packages.valory.skills.funds_forwarder_abci.rounds as FundsForwarderAbci
import packages.valory.skills.identify_service_owner_abci.rounds as IdentifyServiceOwnerAbci
import packages.valory.skills.market_creation_manager_abci.rounds as MarketCreationManagerAbci
import packages.valory.skills.mech_interact_abci.rounds as MechInteractAbci
import packages.valory.skills.mech_interact_abci.states.final_states as MechFinalStates
import packages.valory.skills.mech_interact_abci.states.mech_version as MechVersionStates
import packages.valory.skills.mech_interact_abci.states.request as MechRequestStates
import packages.valory.skills.mech_interact_abci.states.response as MechResponseStates
import packages.valory.skills.omen_ct_redeem_tokens_abci.rounds as OmenCtRedeemTokensAbci
import packages.valory.skills.omen_fpmm_remove_liquidity_abci.rounds as OmenFpmmRemoveLiquidityAbci
import packages.valory.skills.omen_realitio_withdraw_bonds_abci.rounds as OmenRealitioWithdrawBondsAbci
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
    # Registration -> IdentifyServiceOwner
    FinishedRegistrationRound: IdentifyServiceOwnerAbci.IdentifyServiceOwnerRound,
    # IdentifyServiceOwner -> FundsForwarder (ok) / FpmmRemoveLiquidity (error)
    IdentifyServiceOwnerAbci.FinishedIdentifyServiceOwnerRound: (
        FundsForwarderAbci.FundsForwarderRound
    ),
    IdentifyServiceOwnerAbci.FinishedIdentifyServiceOwnerErrorRound: (
        OmenFpmmRemoveLiquidityAbci.FpmmRemoveLiquidityRound
    ),
    # FundsForwarder: tx -> TxSettlement; no tx -> FpmmRemoveLiquidity
    FundsForwarderAbci.FinishedFundsForwarderNoTxRound: (
        OmenFpmmRemoveLiquidityAbci.FpmmRemoveLiquidityRound
    ),
    FundsForwarderAbci.FinishedFundsForwarderWithTxRound: (
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound
    ),
    # Linear recovery chain (FpmmRemoveLiquidity -> CtRedeemTokens ->
    # RealitioWithdrawBonds) -- each step either builds a multisend
    # (-> TxSettlement -> PostTx -> next step) or produces no tx
    # (-> next step directly).
    #
    # Step 1: FpmmRemoveLiquidity
    OmenFpmmRemoveLiquidityAbci.FinishedWithFpmmRemoveLiquidityTxRound: (
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound
    ),
    OmenFpmmRemoveLiquidityAbci.FinishedWithoutFpmmRemoveLiquidityTxRound: (
        OmenCtRedeemTokensAbci.CtRedeemTokensRound
    ),
    # Step 2: CtRedeemTokens
    OmenCtRedeemTokensAbci.FinishedWithCtRedeemTokensTxRound: (
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound
    ),
    OmenCtRedeemTokensAbci.FinishedWithoutCtRedeemTokensTxRound: (
        OmenRealitioWithdrawBondsAbci.RealitioWithdrawBondsRound
    ),
    # Step 3: RealitioWithdrawBonds
    OmenRealitioWithdrawBondsAbci.FinishedWithRealitioWithdrawBondsTxRound: (
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound
    ),
    OmenRealitioWithdrawBondsAbci.FinishedWithoutRealitioWithdrawBondsTxRound: (
        MarketCreationManagerAbci.DepositDaiRound
    ),
    # PostTx fan-out: each recovery tx returns to the NEXT step of the chain.
    MarketCreationManagerAbci.FinishedWithFundsForwarderPostTxRound: (
        OmenFpmmRemoveLiquidityAbci.FpmmRemoveLiquidityRound
    ),
    MarketCreationManagerAbci.FinishedWithFpmmRemoveLiquidityPostTxRound: (
        OmenCtRedeemTokensAbci.CtRedeemTokensRound
    ),
    MarketCreationManagerAbci.FinishedWithCtRedeemTokensPostTxRound: (
        OmenRealitioWithdrawBondsAbci.RealitioWithdrawBondsRound
    ),
    MarketCreationManagerAbci.FinishedWithRealitioWithdrawBondsPostTxRound: (
        MarketCreationManagerAbci.DepositDaiRound
    ),
    # Core market-creation flow
    MarketCreationManagerAbci.FinishedWithoutTxRound: ResetAndPauseRound,
    MarketCreationManagerAbci.FinishedWithDepositDaiRound: (
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound
    ),
    MarketCreationManagerAbci.FinishedMarketCreationManagerRound: (
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound
    ),
    # TxSettlement -> PostTransactionRound (multiplexes by tx_submitter)
    TransactionSettlementAbci.FinishedTransactionSubmissionRound: (
        MarketCreationManagerAbci.PostTransactionRound
    ),
    TransactionSettlementAbci.FailedRound: ResetAndPauseRound,
    # Mech flow: RequestProposedQuestionsRound sends mech_requests
    # -> FinishedWithMechRequestRound -> MechVersionDetection -> MechRequest
    MarketCreationManagerAbci.FinishedWithMechRequestRound: (
        MechVersionStates.MechVersionDetectionRound
    ),
    # MechInteract version-detection finals -> MechRequestRound
    MechFinalStates.FinishedMarketplaceLegacyDetectedRound: (
        MechRequestStates.MechRequestRound
    ),
    MechFinalStates.FinishedMechLegacyDetectedRound: (
        MechRequestStates.MechRequestRound
    ),
    MechFinalStates.FinishedMechInformationRound: MechRequestStates.MechRequestRound,
    MechFinalStates.FailedMechInformationRound: (
        MechVersionStates.MechVersionDetectionRound
    ),
    # MechRequest tx -> TxSettlement; subscription -> TxSettlement
    MechFinalStates.FinishedMechRequestRound: (
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound
    ),
    MechFinalStates.FinishedMechPurchaseSubscriptionRound: (
        TransactionSettlementAbci.RandomnessTransactionSubmissionRound
    ),
    # Mech delivered response -> ProcessProposedQuestionsRound (consume it)
    MechFinalStates.FinishedMechResponseRound: (
        MarketCreationManagerAbci.ProcessProposedQuestionsRound
    ),
    # Timeouts / skips -> continue without blocking
    MechFinalStates.FinishedMechRequestSkipRound: ResetAndPauseRound,
    MechFinalStates.FinishedMechResponseTimeoutRound: ResetAndPauseRound,
    # PostTx: Mech request tx settled -> poll for response
    MarketCreationManagerAbci.FinishedWithMechPollRound: (
        MechResponseStates.MechResponseRound
    ),
    # Reset -> next period
    FinishedResetAndPauseRound: IdentifyServiceOwnerAbci.IdentifyServiceOwnerRound,
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
        IdentifyServiceOwnerAbci.IdentifyServiceOwnerAbciApp,
        FundsForwarderAbci.FundsForwarderAbciApp,
        OmenFpmmRemoveLiquidityAbci.OmenFpmmRemoveLiquidityAbciApp,
        OmenCtRedeemTokensAbci.OmenCtRedeemTokensAbciApp,
        OmenRealitioWithdrawBondsAbci.OmenRealitioWithdrawBondsAbciApp,
        MarketCreationManagerAbci.MarketCreationManagerAbciApp,
        TransactionSettlementAbci.TransactionSubmissionAbciApp,
        MechInteractAbci.MechInteractAbciApp,
        ResetPauseAbciApp,
    ),
    abci_app_transition_mapping,
).add_background_app(termination_config)

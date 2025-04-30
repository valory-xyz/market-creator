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

"""This package contains the rounds of MarketCreationManagerAbciApp."""

from typing import Any, Dict, Set
from packages.valory.skills.abstract_round_abci.base import (
    AbciApp,
    AbciAppTransitionFunction,
    AppState,
    EventToTimeout,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.states.base import ( Event, SynchronizedData)
from packages.valory.skills.market_creation_manager_abci.states.collect_randomness_round import CollectRandomnessRound
from packages.valory.skills.market_creation_manager_abci.states.answer_questions_round import AnswerQuestionsRound
from packages.valory.skills.market_creation_manager_abci.states.deposit_dai_round import DepositDaiRound
from packages.valory.skills.market_creation_manager_abci.states.post_transaction_round import PostTransactionRound
from packages.valory.skills.market_creation_manager_abci.states.sync_markets_round import SyncMarketsRound
from packages.valory.skills.market_creation_manager_abci.states.get_pending_questions_round import GetPendingQuestionsRound
from packages.valory.skills.market_creation_manager_abci.states.final_states import (
    FinishedWithDepositDaiRound,
    FinishedWithoutTxRound,
    FinishedWithMechRequestRound,
    FinishedWithAnswerQuestionsRound,
    FinishedWithGetPendingQuestionsRound,
    FinishedWithRedeemBondRound,
    FinishedWithRemoveFundingRound,
    FinishedMarketCreationManagerRound,
)
from packages.valory.skills.market_creation_manager_abci.states.select_keeper_round import SelectKeeperRound
from packages.valory.skills.market_creation_manager_abci.states.redeem_bond_round import RedeemBondRound
from packages.valory.skills.market_creation_manager_abci.states.collect_proposed_markets_round import CollectProposedMarketsRound
from packages.valory.skills.market_creation_manager_abci.states.approve_markets_round import ApproveMarketsRound
from packages.valory.skills.market_creation_manager_abci.states.retrieve_approved_market_round import RetrieveApprovedMarketRound
from packages.valory.skills.market_creation_manager_abci.states.prepare_transaction_round import PrepareTransactionRound
from packages.valory.skills.market_creation_manager_abci.states.remove_funding_round import RemoveFundingRound


class MarketCreationManagerAbciApp(AbciApp[Event]):
    """MarketCreationManagerAbciApp"""

    initial_round_cls: AppState = CollectRandomnessRound
    initial_states: Set[AppState] = {
        AnswerQuestionsRound,
        CollectRandomnessRound,
        DepositDaiRound,
        PostTransactionRound,
        SyncMarketsRound,
        GetPendingQuestionsRound,
    }
    transition_function: AbciAppTransitionFunction = {
        DepositDaiRound: {
            Event.DONE: FinishedWithDepositDaiRound,
            Event.NO_TX: GetPendingQuestionsRound,
            Event.NO_MAJORITY: GetPendingQuestionsRound,
            Event.ERROR: GetPendingQuestionsRound,
        },
        PostTransactionRound: {
            Event.DONE: FinishedWithoutTxRound,
            Event.ERROR: DepositDaiRound,
            Event.NO_MAJORITY: PostTransactionRound,
            Event.DEPOSIT_DAI_DONE: GetPendingQuestionsRound,
            Event.MECH_REQUEST_DONE: FinishedWithMechRequestRound,
            Event.ANSWER_QUESTION_DONE: CollectRandomnessRound,
            Event.REDEEM_BOND_DONE: CollectProposedMarketsRound,
            Event.REMOVE_FUNDING_DONE: DepositDaiRound,
        },
        GetPendingQuestionsRound: {
            Event.DONE: FinishedWithGetPendingQuestionsRound,
            Event.NO_TX: CollectRandomnessRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ERROR: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        AnswerQuestionsRound: {
            Event.DONE: FinishedWithAnswerQuestionsRound,
            Event.NO_TX: CollectRandomnessRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ERROR: CollectRandomnessRound,
        },
        CollectRandomnessRound: {
            Event.DONE: SelectKeeperRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        SelectKeeperRound: {
            Event.DONE: RedeemBondRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        RedeemBondRound: {
            Event.DONE: FinishedWithRedeemBondRound,
            Event.NO_TX: CollectProposedMarketsRound,
            Event.NO_MAJORITY: CollectProposedMarketsRound,
            Event.ERROR: CollectProposedMarketsRound,
        },
        CollectProposedMarketsRound: {
            Event.DONE: ApproveMarketsRound,
            Event.MAX_APPROVED_MARKETS_REACHED: RetrieveApprovedMarketRound,
            Event.MAX_RETRIES_REACHED: RetrieveApprovedMarketRound,
            Event.SKIP_MARKET_APPROVAL: RetrieveApprovedMarketRound,
            Event.NO_MAJORITY: RetrieveApprovedMarketRound,
            Event.ROUND_TIMEOUT: RetrieveApprovedMarketRound,
            Event.ERROR: RetrieveApprovedMarketRound,
        },
        ApproveMarketsRound: {
            Event.DONE: RetrieveApprovedMarketRound,
            Event.ROUND_TIMEOUT: RetrieveApprovedMarketRound,
            Event.MAX_RETRIES_REACHED: RetrieveApprovedMarketRound,
            Event.ERROR: RetrieveApprovedMarketRound,
        },
        RetrieveApprovedMarketRound: {
            Event.DONE: PrepareTransactionRound,
            Event.NO_MAJORITY: FinishedWithoutTxRound,
            Event.ROUND_TIMEOUT: FinishedWithoutTxRound,
            Event.DID_NOT_SEND: FinishedWithoutTxRound,
            Event.ERROR: FinishedWithoutTxRound,
            Event.NO_MARKETS_RETRIEVED: FinishedWithoutTxRound,
        },
        PrepareTransactionRound: {
            Event.DONE: FinishedMarketCreationManagerRound,
            Event.NO_MAJORITY: FinishedWithoutTxRound,
            Event.ROUND_TIMEOUT: FinishedWithoutTxRound,
        },
        SyncMarketsRound: {
            Event.DONE: RemoveFundingRound,
            Event.NO_MAJORITY: DepositDaiRound,
            Event.ERROR: DepositDaiRound,
            Event.ROUND_TIMEOUT: DepositDaiRound,
        },
        RemoveFundingRound: {
            Event.DONE: FinishedWithRemoveFundingRound,
            Event.NO_TX: DepositDaiRound,
            Event.NO_MAJORITY: GetPendingQuestionsRound,
            Event.ERROR: GetPendingQuestionsRound,
            Event.ROUND_TIMEOUT: GetPendingQuestionsRound,
        },
        FinishedMarketCreationManagerRound: {},
        FinishedWithAnswerQuestionsRound: {},
        FinishedWithMechRequestRound: {},
        FinishedWithRemoveFundingRound: {},
        FinishedWithDepositDaiRound: {},
        FinishedWithGetPendingQuestionsRound: {},
        FinishedWithRedeemBondRound: {},
        FinishedWithoutTxRound: {},
    }
    final_states: Set[AppState] = {
        FinishedMarketCreationManagerRound,
        FinishedWithAnswerQuestionsRound,
        FinishedWithMechRequestRound,
        FinishedWithRemoveFundingRound,
        FinishedWithDepositDaiRound,
        FinishedWithGetPendingQuestionsRound,
        FinishedWithRedeemBondRound,
        FinishedWithoutTxRound,
    }
    event_to_timeout: EventToTimeout = {
        # MARKET_PROPOSAL_ROUND_TIMEOUT must be computed on the chained app.
    }
    cross_period_persisted_keys: Set[str] = {
        get_name(SynchronizedData.proposed_markets_count),
        get_name(SynchronizedData.proposed_markets_data),
        get_name(SynchronizedData.approved_markets_count),
        get_name(SynchronizedData.approved_markets_timestamp),
        get_name(SynchronizedData.mech_responses),
    }  # type: ignore
    db_pre_conditions: Dict[AppState, Set[str]] = {
        AnswerQuestionsRound: set(),
        DepositDaiRound: set(),
        GetPendingQuestionsRound: set(),
        CollectRandomnessRound: set(),
        PostTransactionRound: set(),
        SyncMarketsRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedWithAnswerQuestionsRound: {
            get_name(SynchronizedData.most_voted_tx_hash),
        },
        FinishedWithDepositDaiRound: {
            get_name(SynchronizedData.most_voted_tx_hash),
        },
        FinishedWithRedeemBondRound: {
            get_name(SynchronizedData.most_voted_tx_hash),
        },
        FinishedMarketCreationManagerRound: {
            get_name(SynchronizedData.most_voted_tx_hash),
        },
        FinishedWithRemoveFundingRound: {
            get_name(SynchronizedData.most_voted_tx_hash),
        },
        FinishedWithMechRequestRound: set(),
        FinishedWithGetPendingQuestionsRound: set(),
        FinishedWithoutTxRound: set(),
    }

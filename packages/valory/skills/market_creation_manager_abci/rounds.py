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

"""This module contains the rounds of the MarketCreationManagerAbciApp."""

from typing import Dict, Set

from packages.valory.skills.abstract_round_abci.base import (
    AbciApp,
    AbciAppTransitionFunction,
    AppState,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.states.answer_questions import (
    AnswerQuestionsRound,
)
from packages.valory.skills.market_creation_manager_abci.states.approve_markets import (
    ApproveMarketsRound,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)
from packages.valory.skills.market_creation_manager_abci.states.collect_proposed_markets import (
    CollectProposedMarketsRound,
)
from packages.valory.skills.market_creation_manager_abci.states.collect_randomness import (
    CollectRandomnessRound,
)
from packages.valory.skills.market_creation_manager_abci.states.deposit_dai import (
    DepositDaiRound,
)
from packages.valory.skills.market_creation_manager_abci.states.final_states import (
    FinishedMarketCreationManagerRound,
    FinishedWithAnswerQuestionsRound,
    FinishedWithDepositDaiRound,
    FinishedWithGetPendingQuestionsRound,
    FinishedWithMechRequestRound,
    FinishedWithRedeemBondRound,
    FinishedWithRedeemWinningsRound,
    FinishedWithRemoveFundingRound,
    FinishedWithoutTxRound,
)
from packages.valory.skills.market_creation_manager_abci.states.get_pending_questions import (
    GetPendingQuestionsRound,
)
from packages.valory.skills.market_creation_manager_abci.states.post_transaction import (
    PostTransactionRound,
)
from packages.valory.skills.market_creation_manager_abci.states.prepare_transaction import (
    PrepareTransactionRound,
)
from packages.valory.skills.market_creation_manager_abci.states.redeem_bond import (
    RedeemBondRound,
)
from packages.valory.skills.market_creation_manager_abci.states.redeem_winnings import (
    RedeemWinningsRound,
)
from packages.valory.skills.market_creation_manager_abci.states.remove_funding import (
    RemoveFundingRound,
)
from packages.valory.skills.market_creation_manager_abci.states.retrieve_approved_market import (
    RetrieveApprovedMarketRound,
)
from packages.valory.skills.market_creation_manager_abci.states.select_keeper import (
    SelectKeeperRound,
)
from packages.valory.skills.market_creation_manager_abci.states.sync_markets import (
    SyncMarketsRound,
)


class MarketCreationManagerAbciApp(AbciApp[Event]):
    """MarketCreationManagerAbciApp

    Initial round: CollectRandomnessRound

    Initial states: {AnswerQuestionsRound, CollectRandomnessRound, DepositDaiRound, GetPendingQuestionsRound, PostTransactionRound, RedeemWinningsRound, SyncMarketsRound}

    Transition states:
        0. DepositDaiRound
            - done: 19.
            - no majority: 2.
            - none: 2.
            - round timeout: 2.
        1. PostTransactionRound
            - done: 22.
            - api error: 0.
            - no majority: 1.
            - none: 1.
            - deposit dai done: 2.
            - mech request done: 16.
            - answer question done: 4.
            - redeem bond done: 7.
            - remove funding done: 13.
            - redeem winnings done: 0.
            - fund sweep done: 11.
        2. GetPendingQuestionsRound
            - done: 20.
            - no tx: 4.
            - no majority: 4.
            - none: 4.
            - api error: 4.
            - round timeout: 4.
        3. AnswerQuestionsRound
            - done: 15.
            - no majority: 4.
            - none: 4.
            - round timeout: 4.
        4. CollectRandomnessRound
            - done: 5.
            - no majority: 4.
            - none: 4.
            - round timeout: 4.
        5. SelectKeeperRound
            - done: 6.
            - no majority: 4.
            - none: 4.
            - round timeout: 4.
        6. RedeemBondRound
            - done: 21.
            - no majority: 7.
            - none: 7.
            - round timeout: 7.
        7. CollectProposedMarketsRound
            - done: 8.
            - max approved markets reached: 9.
            - max retries reached: 9.
            - skip market approval: 9.
            - no majority: 9.
            - none: 9.
            - round timeout: 9.
            - api error: 9.
        8. ApproveMarketsRound
            - done: 9.
            - round timeout: 9.
            - max retries reached: 9.
            - api error: 9.
        9. RetrieveApprovedMarketRound
            - done: 10.
            - round timeout: 22.
            - api error: 22.
            - no markets retrieved: 22.
        10. PrepareTransactionRound
            - done: 14.
            - no majority: 22.
            - none: 22.
            - round timeout: 22.
        11. SyncMarketsRound
            - done: 12.
            - no majority: 0.
            - none: 0.
            - api error: 0.
            - round timeout: 0.
        12. RemoveFundingRound
            - done: 17.
            - none: 13.
            - no majority: 13.
            - round timeout: 13.
            - no tx: 13.
            - api error: 13.
        13. RedeemWinningsRound
            - done: 18.
            - no majority: 0.
            - none: 0.
            - round timeout: 0.
        14. FinishedMarketCreationManagerRound
        15. FinishedWithAnswerQuestionsRound
        16. FinishedWithMechRequestRound
        17. FinishedWithRemoveFundingRound
        18. FinishedWithRedeemWinningsRound
        19. FinishedWithDepositDaiRound
        20. FinishedWithGetPendingQuestionsRound
        21. FinishedWithRedeemBondRound
        22. FinishedWithoutTxRound

    Final states: {FinishedMarketCreationManagerRound, FinishedWithAnswerQuestionsRound, FinishedWithDepositDaiRound, FinishedWithGetPendingQuestionsRound, FinishedWithMechRequestRound, FinishedWithRedeemBondRound, FinishedWithRedeemWinningsRound, FinishedWithRemoveFundingRound, FinishedWithoutTxRound}

    Timeouts:
        round timeout: 180.0
    """

    initial_round_cls: AppState = CollectRandomnessRound
    initial_states: Set[AppState] = {
        AnswerQuestionsRound,
        CollectRandomnessRound,
        DepositDaiRound,
        PostTransactionRound,
        RedeemWinningsRound,
        SyncMarketsRound,
        GetPendingQuestionsRound,
    }
    transition_function: AbciAppTransitionFunction = {
        DepositDaiRound: {
            Event.DONE: FinishedWithDepositDaiRound,
            Event.NO_MAJORITY: GetPendingQuestionsRound,
            Event.NONE: GetPendingQuestionsRound,
            Event.ROUND_TIMEOUT: GetPendingQuestionsRound,
        },
        PostTransactionRound: {
            Event.DONE: FinishedWithoutTxRound,
            Event.ERROR: DepositDaiRound,
            Event.NO_MAJORITY: PostTransactionRound,
            Event.NONE: PostTransactionRound,
            Event.DEPOSIT_DAI_DONE: GetPendingQuestionsRound,
            Event.MECH_REQUEST_DONE: FinishedWithMechRequestRound,
            Event.ANSWER_QUESTION_DONE: CollectRandomnessRound,
            Event.REDEEM_BOND_DONE: CollectProposedMarketsRound,
            Event.REMOVE_FUNDING_DONE: RedeemWinningsRound,
            Event.REDEEM_WINNINGS_DONE: DepositDaiRound,
            Event.FUND_SWEEP_DONE: SyncMarketsRound,
        },
        GetPendingQuestionsRound: {
            Event.DONE: FinishedWithGetPendingQuestionsRound,
            Event.NO_TX: CollectRandomnessRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.NONE: CollectRandomnessRound,
            Event.ERROR: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        AnswerQuestionsRound: {
            Event.DONE: FinishedWithAnswerQuestionsRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.NONE: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        CollectRandomnessRound: {
            Event.DONE: SelectKeeperRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.NONE: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        SelectKeeperRound: {
            Event.DONE: RedeemBondRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.NONE: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        RedeemBondRound: {
            Event.DONE: FinishedWithRedeemBondRound,
            Event.NO_MAJORITY: CollectProposedMarketsRound,
            Event.NONE: CollectProposedMarketsRound,
            Event.ROUND_TIMEOUT: CollectProposedMarketsRound,
        },
        CollectProposedMarketsRound: {
            Event.DONE: ApproveMarketsRound,
            Event.MAX_APPROVED_MARKETS_REACHED: RetrieveApprovedMarketRound,
            Event.MAX_RETRIES_REACHED: RetrieveApprovedMarketRound,
            Event.SKIP_MARKET_APPROVAL: RetrieveApprovedMarketRound,
            Event.NO_MAJORITY: RetrieveApprovedMarketRound,
            Event.NONE: RetrieveApprovedMarketRound,
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
            Event.ROUND_TIMEOUT: FinishedWithoutTxRound,
            Event.ERROR: FinishedWithoutTxRound,
            Event.NO_MARKETS_RETRIEVED: FinishedWithoutTxRound,
        },
        PrepareTransactionRound: {
            Event.DONE: FinishedMarketCreationManagerRound,
            Event.NO_MAJORITY: FinishedWithoutTxRound,
            Event.NONE: FinishedWithoutTxRound,
            Event.ROUND_TIMEOUT: FinishedWithoutTxRound,
        },
        SyncMarketsRound: {
            Event.DONE: RemoveFundingRound,
            Event.NO_MAJORITY: DepositDaiRound,
            Event.NONE: DepositDaiRound,
            Event.ERROR: DepositDaiRound,
            Event.ROUND_TIMEOUT: DepositDaiRound,
        },
        RemoveFundingRound: {
            Event.DONE: FinishedWithRemoveFundingRound,
            Event.NONE: RedeemWinningsRound,
            Event.NO_MAJORITY: RedeemWinningsRound,
            Event.ROUND_TIMEOUT: RedeemWinningsRound,
            Event.NO_TX: RedeemWinningsRound,
            Event.ERROR: RedeemWinningsRound,
        },
        RedeemWinningsRound: {
            Event.DONE: FinishedWithRedeemWinningsRound,
            Event.NO_MAJORITY: DepositDaiRound,
            Event.NONE: DepositDaiRound,
            Event.ROUND_TIMEOUT: DepositDaiRound,
        },
        FinishedMarketCreationManagerRound: {},
        FinishedWithAnswerQuestionsRound: {},
        FinishedWithMechRequestRound: {},
        FinishedWithRemoveFundingRound: {},
        FinishedWithRedeemWinningsRound: {},
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
        FinishedWithRedeemWinningsRound,
        FinishedWithDepositDaiRound,
        FinishedWithGetPendingQuestionsRound,
        FinishedWithRedeemBondRound,
        FinishedWithoutTxRound,
    }
    event_to_timeout: Dict[Event, float] = {
        Event.ROUND_TIMEOUT: 180.0,
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
        RedeemWinningsRound: set(),
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
        FinishedWithRedeemWinningsRound: {
            get_name(SynchronizedData.most_voted_tx_hash),
        },
        FinishedWithMechRequestRound: set(),
        FinishedWithGetPendingQuestionsRound: set(),
        FinishedWithoutTxRound: set(),
    }

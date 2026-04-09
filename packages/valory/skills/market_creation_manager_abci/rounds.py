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
    FinishedWithDepositDaiRound,
    FinishedWithRedeemWinningsRound,
    FinishedWithRemoveFundingRound,
    FinishedWithoutTxRound,
)
from packages.valory.skills.market_creation_manager_abci.states.post_transaction import (
    PostTransactionRound,
)
from packages.valory.skills.market_creation_manager_abci.states.prepare_transaction import (
    PrepareTransactionRound,
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

    Initial states: {CollectRandomnessRound, DepositDaiRound, PostTransactionRound, RedeemWinningsRound, SyncMarketsRound}

    Transition states:
        0. DepositDaiRound
            - done: 14.
            - no majority: 2.
            - none: 2.
            - round timeout: 2.
        1. PostTransactionRound
            - done: 15.
            - api error: 0.
            - no majority: 1.
            - none: 1.
            - deposit dai done: 2.
            - remove funding done: 10.
            - redeem winnings done: 0.
            - fund sweep done: 8.
        2. CollectRandomnessRound
            - done: 3.
            - no majority: 2.
            - none: 2.
            - round timeout: 2.
        3. SelectKeeperRound
            - done: 4.
            - no majority: 2.
            - none: 2.
            - round timeout: 2.
        4. CollectProposedMarketsRound
            - done: 5.
            - max approved markets reached: 6.
            - max retries reached: 6.
            - skip market approval: 6.
            - no majority: 6.
            - none: 6.
            - round timeout: 6.
            - api error: 6.
        5. ApproveMarketsRound
            - done: 6.
            - round timeout: 6.
            - max retries reached: 6.
            - api error: 6.
        6. RetrieveApprovedMarketRound
            - done: 7.
            - round timeout: 15.
            - api error: 15.
            - no markets retrieved: 15.
        7. PrepareTransactionRound
            - done: 11.
            - no majority: 15.
            - none: 15.
            - round timeout: 15.
        8. SyncMarketsRound
            - done: 9.
            - no majority: 0.
            - none: 0.
            - api error: 0.
            - round timeout: 0.
        9. RemoveFundingRound
            - done: 12.
            - none: 10.
            - no majority: 10.
            - round timeout: 10.
            - no tx: 10.
            - api error: 10.
        10. RedeemWinningsRound
            - done: 13.
            - no majority: 0.
            - none: 0.
            - round timeout: 0.
        11. FinishedMarketCreationManagerRound
        12. FinishedWithRemoveFundingRound
        13. FinishedWithRedeemWinningsRound
        14. FinishedWithDepositDaiRound
        15. FinishedWithoutTxRound

    Final states: {FinishedMarketCreationManagerRound, FinishedWithDepositDaiRound, FinishedWithRedeemWinningsRound, FinishedWithRemoveFundingRound, FinishedWithoutTxRound}

    Timeouts:
        round timeout: 180.0
    """

    initial_round_cls: AppState = CollectRandomnessRound
    initial_states: Set[AppState] = {
        CollectRandomnessRound,
        DepositDaiRound,
        PostTransactionRound,
        RedeemWinningsRound,
        SyncMarketsRound,
    }
    transition_function: AbciAppTransitionFunction = {
        DepositDaiRound: {
            Event.DONE: FinishedWithDepositDaiRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.NONE: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        PostTransactionRound: {
            Event.DONE: FinishedWithoutTxRound,
            Event.ERROR: DepositDaiRound,
            Event.NO_MAJORITY: PostTransactionRound,
            Event.NONE: PostTransactionRound,
            Event.DEPOSIT_DAI_DONE: CollectRandomnessRound,
            Event.REMOVE_FUNDING_DONE: RedeemWinningsRound,
            Event.REDEEM_WINNINGS_DONE: DepositDaiRound,
            Event.FUND_SWEEP_DONE: SyncMarketsRound,
        },
        CollectRandomnessRound: {
            Event.DONE: SelectKeeperRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.NONE: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        SelectKeeperRound: {
            Event.DONE: CollectProposedMarketsRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.NONE: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
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
        FinishedWithRemoveFundingRound: {},
        FinishedWithRedeemWinningsRound: {},
        FinishedWithDepositDaiRound: {},
        FinishedWithoutTxRound: {},
    }
    final_states: Set[AppState] = {
        FinishedMarketCreationManagerRound,
        FinishedWithRemoveFundingRound,
        FinishedWithRedeemWinningsRound,
        FinishedWithDepositDaiRound,
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
    }  # type: ignore
    db_pre_conditions: Dict[AppState, Set[str]] = {
        DepositDaiRound: set(),
        CollectRandomnessRound: set(),
        PostTransactionRound: set(),
        RedeemWinningsRound: set(),
        SyncMarketsRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedWithDepositDaiRound: {
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
        FinishedWithoutTxRound: set(),
    }

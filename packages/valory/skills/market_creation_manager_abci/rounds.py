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
    FinishedWithCtRedeemTokensPostTxRound,
    FinishedWithDepositDaiRound,
    FinishedWithFpmmRemoveLiquidityPostTxRound,
    FinishedWithFundsForwarderPostTxRound,
    FinishedWithRealitioWithdrawBondsPostTxRound,
    FinishedWithoutTxRound,
)
from packages.valory.skills.market_creation_manager_abci.states.post_transaction import (
    PostTransactionRound,
)
from packages.valory.skills.market_creation_manager_abci.states.prepare_transaction import (
    PrepareTransactionRound,
)
from packages.valory.skills.market_creation_manager_abci.states.retrieve_approved_market import (
    RetrieveApprovedMarketRound,
)
from packages.valory.skills.market_creation_manager_abci.states.select_keeper import (
    SelectKeeperRound,
)


class MarketCreationManagerAbciApp(AbciApp[Event]):
    """MarketCreationManagerAbciApp

    Initial round: CollectRandomnessRound

    Initial states: {CollectRandomnessRound, DepositDaiRound, PostTransactionRound}

    Transition states:
        0. DepositDaiRound
            - done: 9.
            - no majority: 2.
            - none: 2.
            - round timeout: 2.
        1. PostTransactionRound
            - done: 10.
            - api error: 0.
            - no majority: 1.
            - none: 1.
            - deposit dai done: 2.
            - funds forwarder tx done: 11.
            - fpmm remove liquidity tx done: 12.
            - ct redeem tokens tx done: 13.
            - realitio withdraw bonds tx done: 14.
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
            - round timeout: 10.
            - api error: 10.
            - no markets retrieved: 10.
        7. PrepareTransactionRound
            - done: 8.
            - no majority: 10.
            - none: 10.
            - round timeout: 10.
        8. FinishedMarketCreationManagerRound
        9. FinishedWithDepositDaiRound
        10. FinishedWithoutTxRound
        11. FinishedWithFundsForwarderPostTxRound
        12. FinishedWithFpmmRemoveLiquidityPostTxRound
        13. FinishedWithCtRedeemTokensPostTxRound
        14. FinishedWithRealitioWithdrawBondsPostTxRound

    Final states: {FinishedMarketCreationManagerRound, FinishedWithCtRedeemTokensPostTxRound, FinishedWithDepositDaiRound, FinishedWithFpmmRemoveLiquidityPostTxRound, FinishedWithFundsForwarderPostTxRound, FinishedWithRealitioWithdrawBondsPostTxRound, FinishedWithoutTxRound}

    Timeouts:
        round timeout: 180.0
    """

    initial_round_cls: AppState = CollectRandomnessRound
    initial_states: Set[AppState] = {
        CollectRandomnessRound,
        DepositDaiRound,
        PostTransactionRound,
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
            Event.FUNDS_FORWARDER_TX_DONE: FinishedWithFundsForwarderPostTxRound,
            Event.FPMM_REMOVE_LIQUIDITY_TX_DONE: FinishedWithFpmmRemoveLiquidityPostTxRound,
            Event.CT_REDEEM_TOKENS_TX_DONE: FinishedWithCtRedeemTokensPostTxRound,
            Event.REALITIO_WITHDRAW_BONDS_TX_DONE: FinishedWithRealitioWithdrawBondsPostTxRound,
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
        FinishedMarketCreationManagerRound: {},
        FinishedWithDepositDaiRound: {},
        FinishedWithoutTxRound: {},
        FinishedWithFundsForwarderPostTxRound: {},
        FinishedWithFpmmRemoveLiquidityPostTxRound: {},
        FinishedWithCtRedeemTokensPostTxRound: {},
        FinishedWithRealitioWithdrawBondsPostTxRound: {},
    }
    final_states: Set[AppState] = {
        FinishedMarketCreationManagerRound,
        FinishedWithDepositDaiRound,
        FinishedWithoutTxRound,
        FinishedWithFundsForwarderPostTxRound,
        FinishedWithFpmmRemoveLiquidityPostTxRound,
        FinishedWithCtRedeemTokensPostTxRound,
        FinishedWithRealitioWithdrawBondsPostTxRound,
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
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedWithDepositDaiRound: {
            get_name(SynchronizedData.most_voted_tx_hash),
        },
        FinishedMarketCreationManagerRound: {
            get_name(SynchronizedData.most_voted_tx_hash),
        },
        FinishedWithoutTxRound: set(),
        FinishedWithFundsForwarderPostTxRound: set(),
        FinishedWithFpmmRemoveLiquidityPostTxRound: set(),
        FinishedWithCtRedeemTokensPostTxRound: set(),
        FinishedWithRealitioWithdrawBondsPostTxRound: set(),
    }

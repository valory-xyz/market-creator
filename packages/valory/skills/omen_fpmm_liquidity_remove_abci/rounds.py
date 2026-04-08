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

"""This module contains the rounds of the OmenFpmmLiquidityRemoveAbciApp.

Initial round: FpmmLiquidityRemoveRound

Initial states: {FpmmLiquidityRemoveRound}

Transition states:
    0. FpmmLiquidityRemoveRound
        - done: 1.
        - no_majority: 2.
        - none: 2.
        - round_timeout: 2.
    1. FinishedWithFpmmLiquidityRemoveTxRound
    2. FinishedWithoutFpmmLiquidityRemoveTxRound

Final states: {FinishedWithFpmmLiquidityRemoveTxRound,
FinishedWithoutFpmmLiquidityRemoveTxRound}

Timeouts:
    round timeout: 120.0
"""

from enum import Enum
from typing import Dict, Set, Tuple, cast

from packages.valory.skills.abstract_round_abci.base import (
    AbciApp,
    AbciAppTransitionFunction,
    AppState,
    CollectSameUntilThresholdRound,
    CollectionRound,
    DegenerateRound,
    DeserializedCollection,
    get_name,
)
from packages.valory.skills.omen_fpmm_liquidity_remove_abci.payloads import (
    FpmmLiquidityRemovePayload,
)
from packages.valory.skills.transaction_settlement_abci.rounds import (
    SynchronizedData as TxSynchronizedData,
)


class Event(Enum):
    """OmenFpmmLiquidityRemoveAbciApp Events."""

    DONE = "done"
    NO_MAJORITY = "no_majority"
    NONE = "none"
    ROUND_TIMEOUT = "round_timeout"


class SynchronizedData(TxSynchronizedData):
    """Synchronized data replicated by the Tendermint application."""

    def _get_deserialized(self, key: str) -> DeserializedCollection:
        """Strictly get a collection and return it deserialized."""
        serialized = self.db.get_strict(key)
        return CollectionRound.deserialize_collection(serialized)

    @property
    def most_voted_tx_hash(self) -> str:
        """Get the most_voted_tx_hash."""
        return cast(str, self.db.get_strict("most_voted_tx_hash"))

    @property
    def tx_submitter(self) -> str:
        """Get the round that sent the transaction through transaction settlement."""
        return cast(str, self.db.get_strict("tx_submitter"))

    @property
    def participant_to_fpmm_liquidity_remove_tx(self) -> DeserializedCollection:
        """Get the participant_to_fpmm_liquidity_remove_tx."""
        return self._get_deserialized("participant_to_fpmm_liquidity_remove_tx")


class FpmmLiquidityRemoveRound(CollectSameUntilThresholdRound):
    """A consensus round that builds a multisend to remove LP from closing or closed FPMMs.

    FpmmLiquidityRemoveRound:
        0. done    -> FinishedWithFpmmLiquidityRemoveTxRound
        1. no_majority -> FinishedWithoutFpmmLiquidityRemoveTxRound
        2. none      -> FinishedWithoutFpmmLiquidityRemoveTxRound
        3. round_timeout -> FinishedWithoutFpmmLiquidityRemoveTxRound
    """

    payload_class = FpmmLiquidityRemovePayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    none_event = Event.NONE
    no_majority_event = Event.NO_MAJORITY
    selection_key: Tuple[str, ...] = (
        get_name(SynchronizedData.tx_submitter),
        get_name(SynchronizedData.most_voted_tx_hash),
    )
    collection_key = get_name(SynchronizedData.participant_to_fpmm_liquidity_remove_tx)


class FinishedWithFpmmLiquidityRemoveTxRound(DegenerateRound):
    """A degenerate round indicating LP removal produced a tx for settlement."""


class FinishedWithoutFpmmLiquidityRemoveTxRound(DegenerateRound):
    """A degenerate round indicating no LP removal tx was needed."""


class OmenFpmmLiquidityRemoveAbciApp(AbciApp[Event]):
    """OmenFpmmLiquidityRemoveAbciApp

    Initial round: FpmmLiquidityRemoveRound

    Initial states: {FpmmLiquidityRemoveRound}

    Transition states:
        0. FpmmLiquidityRemoveRound
            - done: 1.
            - none: 2.
            - no majority: 2.
            - round timeout: 2.
        1. FinishedWithFpmmLiquidityRemoveTxRound
        2. FinishedWithoutFpmmLiquidityRemoveTxRound

    Final states: {FinishedWithFpmmLiquidityRemoveTxRound, FinishedWithoutFpmmLiquidityRemoveTxRound}

    Timeouts:
        round timeout: 120.0
    """

    initial_round_cls: AppState = FpmmLiquidityRemoveRound
    initial_states: Set[AppState] = {FpmmLiquidityRemoveRound}
    transition_function: AbciAppTransitionFunction = {
        FpmmLiquidityRemoveRound: {
            Event.DONE: FinishedWithFpmmLiquidityRemoveTxRound,
            Event.NONE: FinishedWithoutFpmmLiquidityRemoveTxRound,
            Event.NO_MAJORITY: FinishedWithoutFpmmLiquidityRemoveTxRound,
            Event.ROUND_TIMEOUT: FinishedWithoutFpmmLiquidityRemoveTxRound,
        },
        FinishedWithFpmmLiquidityRemoveTxRound: {},
        FinishedWithoutFpmmLiquidityRemoveTxRound: {},
    }
    final_states: Set[AppState] = {
        FinishedWithFpmmLiquidityRemoveTxRound,
        FinishedWithoutFpmmLiquidityRemoveTxRound,
    }
    event_to_timeout: Dict[Event, float] = {
        Event.ROUND_TIMEOUT: 120.0,
    }
    cross_period_persisted_keys: Set[str] = frozenset()  # type: ignore[assignment]
    db_pre_conditions: Dict[AppState, Set[str]] = {
        FpmmLiquidityRemoveRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedWithFpmmLiquidityRemoveTxRound: {"most_voted_tx_hash"},
        FinishedWithoutFpmmLiquidityRemoveTxRound: set(),
    }

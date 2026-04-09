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

"""This module contains the rounds of the OmenFpmmRemoveLiquidityAbciApp.

Initial round: FpmmRemoveLiquidityRound

Initial states: {FpmmRemoveLiquidityRound}

Transition states:
    0. FpmmRemoveLiquidityRound
        - done: 1.
        - no_majority: 2.
        - none: 2.
        - round_timeout: 2.
    1. FinishedWithFpmmRemoveLiquidityTxRound
    2. FinishedWithoutFpmmRemoveLiquidityTxRound

Final states: {FinishedWithFpmmRemoveLiquidityTxRound,
FinishedWithoutFpmmRemoveLiquidityTxRound}

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
from packages.valory.skills.omen_fpmm_remove_liquidity_abci.payloads import (
    FpmmRemoveLiquidityPayload,
)
from packages.valory.skills.transaction_settlement_abci.rounds import (
    SynchronizedData as TxSynchronizedData,
)


class Event(Enum):
    """OmenFpmmRemoveLiquidityAbciApp Events."""

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
    def participant_to_fpmm_remove_liquidity_tx(self) -> DeserializedCollection:
        """Get the participant_to_fpmm_remove_liquidity_tx."""
        return self._get_deserialized("participant_to_fpmm_remove_liquidity_tx")


class FpmmRemoveLiquidityRound(CollectSameUntilThresholdRound):
    """A consensus round that builds a multisend to remove LP from closing or closed FPMMs.

    FpmmRemoveLiquidityRound:
        0. done    -> FinishedWithFpmmRemoveLiquidityTxRound
        1. no_majority -> FinishedWithoutFpmmRemoveLiquidityTxRound
        2. none      -> FinishedWithoutFpmmRemoveLiquidityTxRound
        3. round_timeout -> FinishedWithoutFpmmRemoveLiquidityTxRound
    """

    payload_class = FpmmRemoveLiquidityPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    none_event = Event.NONE
    no_majority_event = Event.NO_MAJORITY
    selection_key: Tuple[str, ...] = (
        get_name(SynchronizedData.tx_submitter),
        get_name(SynchronizedData.most_voted_tx_hash),
    )
    collection_key = get_name(SynchronizedData.participant_to_fpmm_remove_liquidity_tx)


class FinishedWithFpmmRemoveLiquidityTxRound(DegenerateRound):
    """A degenerate round indicating LP removal produced a tx for settlement."""


class FinishedWithoutFpmmRemoveLiquidityTxRound(DegenerateRound):
    """A degenerate round indicating no LP removal tx was needed."""


class OmenFpmmRemoveLiquidityAbciApp(AbciApp[Event]):
    """OmenFpmmRemoveLiquidityAbciApp

    Initial round: FpmmRemoveLiquidityRound

    Initial states: {FpmmRemoveLiquidityRound}

    Transition states:
        0. FpmmRemoveLiquidityRound
            - done: 1.
            - none: 2.
            - no majority: 2.
            - round timeout: 2.
        1. FinishedWithFpmmRemoveLiquidityTxRound
        2. FinishedWithoutFpmmRemoveLiquidityTxRound

    Final states: {FinishedWithFpmmRemoveLiquidityTxRound, FinishedWithoutFpmmRemoveLiquidityTxRound}

    Timeouts:
        round timeout: 120.0
    """

    initial_round_cls: AppState = FpmmRemoveLiquidityRound
    initial_states: Set[AppState] = {FpmmRemoveLiquidityRound}
    transition_function: AbciAppTransitionFunction = {
        FpmmRemoveLiquidityRound: {
            Event.DONE: FinishedWithFpmmRemoveLiquidityTxRound,
            Event.NONE: FinishedWithoutFpmmRemoveLiquidityTxRound,
            Event.NO_MAJORITY: FinishedWithoutFpmmRemoveLiquidityTxRound,
            Event.ROUND_TIMEOUT: FinishedWithoutFpmmRemoveLiquidityTxRound,
        },
        FinishedWithFpmmRemoveLiquidityTxRound: {},
        FinishedWithoutFpmmRemoveLiquidityTxRound: {},
    }
    final_states: Set[AppState] = {
        FinishedWithFpmmRemoveLiquidityTxRound,
        FinishedWithoutFpmmRemoveLiquidityTxRound,
    }
    event_to_timeout: Dict[Event, float] = {
        Event.ROUND_TIMEOUT: 120.0,
    }
    cross_period_persisted_keys: Set[str] = frozenset()  # type: ignore[assignment]
    db_pre_conditions: Dict[AppState, Set[str]] = {
        FpmmRemoveLiquidityRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedWithFpmmRemoveLiquidityTxRound: {"most_voted_tx_hash"},
        FinishedWithoutFpmmRemoveLiquidityTxRound: set(),
    }

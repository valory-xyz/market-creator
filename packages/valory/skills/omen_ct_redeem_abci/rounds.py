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

"""This module contains the rounds of the OmenCtRedeemAbciApp."""

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
from packages.valory.skills.omen_ct_redeem_abci.payloads import CtRedeemPayload
from packages.valory.skills.transaction_settlement_abci.rounds import (
    SynchronizedData as TxSynchronizedData,
)


class Event(Enum):
    """OmenCtRedeemAbciApp Events"""

    DONE = "done"
    NO_MAJORITY = "no_majority"
    NONE = "none"
    ROUND_TIMEOUT = "round_timeout"


class SynchronizedData(TxSynchronizedData):
    """Synchronized data replicated by the tendermint application."""

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
    def participant_to_ct_redeem_tx(self) -> DeserializedCollection:
        """Get the participant_to_ct_redeem_tx."""
        return self._get_deserialized("participant_to_ct_redeem_tx")


# --- Active Rounds ---


class CtRedeemRound(CollectSameUntilThresholdRound):
    """A round for redeeming conditional token positions from resolved markets."""

    payload_class = CtRedeemPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    none_event = Event.NONE
    no_majority_event = Event.NO_MAJORITY
    selection_key: Tuple[str, ...] = (
        get_name(SynchronizedData.tx_submitter),
        get_name(SynchronizedData.most_voted_tx_hash),
    )
    collection_key = get_name(SynchronizedData.participant_to_ct_redeem_tx)


# --- Final (Degenerate) Rounds ---


class FinishedWithCtRedeemTxRound(DegenerateRound):
    """A degenerate round indicating CT redemption produced a tx for settlement."""


class FinishedWithoutCtRedeemTxRound(DegenerateRound):
    """A degenerate round indicating no CT redemption tx was needed."""


class OmenCtRedeemAbciApp(AbciApp[Event]):
    """OmenCtRedeemAbciApp

    Initial round: CtRedeemRound

    Initial states: {CtRedeemRound}

    Transition states:
        0. CtRedeemRound
            - done: 1.
            - none: 2.
            - no majority: 2.
            - round timeout: 2.
        1. FinishedWithCtRedeemTxRound
        2. FinishedWithoutCtRedeemTxRound

    Final states: {FinishedWithCtRedeemTxRound, FinishedWithoutCtRedeemTxRound}

    Timeouts:
        round timeout: 120.0
    """

    initial_round_cls: AppState = CtRedeemRound
    initial_states: Set[AppState] = {CtRedeemRound}
    transition_function: AbciAppTransitionFunction = {
        CtRedeemRound: {
            Event.DONE: FinishedWithCtRedeemTxRound,
            Event.NONE: FinishedWithoutCtRedeemTxRound,
            Event.NO_MAJORITY: FinishedWithoutCtRedeemTxRound,
            Event.ROUND_TIMEOUT: FinishedWithoutCtRedeemTxRound,
        },
        FinishedWithCtRedeemTxRound: {},
        FinishedWithoutCtRedeemTxRound: {},
    }
    final_states: Set[AppState] = {
        FinishedWithCtRedeemTxRound,
        FinishedWithoutCtRedeemTxRound,
    }
    event_to_timeout: Dict[Event, float] = {
        Event.ROUND_TIMEOUT: 120.0,
    }
    cross_period_persisted_keys: frozenset[str] = frozenset()
    db_pre_conditions: Dict[AppState, Set[str]] = {
        CtRedeemRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedWithCtRedeemTxRound: {
            get_name(SynchronizedData.most_voted_tx_hash),
        },
        FinishedWithoutCtRedeemTxRound: set(),
    }

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

"""Rounds of the OmenRealitioWithdrawBondAbciApp."""

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
from packages.valory.skills.omen_realitio_withdraw_bond_abci.payloads import (
    RealitioWithdrawBondPayload,
)
from packages.valory.skills.transaction_settlement_abci.rounds import (
    SynchronizedData as TxSynchronizedData,
)


class Event(Enum):
    """OmenRealitioWithdrawBondAbciApp Events."""

    DONE = "done"
    NO_MAJORITY = "no_majority"
    NONE = "none"
    ROUND_TIMEOUT = "round_timeout"


class SynchronizedData(TxSynchronizedData):
    """Synchronized data replicated by the tendermint application.

    Inherits tx_submitter and most_voted_tx_hash from TxSynchronizedData.
    No skill-specific accumulator field — each round's payload carries
    its own multisend hash directly.
    """

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
    def participant_to_realitio_withdraw_bond_tx(self) -> DeserializedCollection:
        """Get the participant_to_realitio_withdraw_bond_tx mapping."""
        return self._get_deserialized("participant_to_realitio_withdraw_bond_tx")


class RealitioWithdrawBondRound(CollectSameUntilThresholdRound):
    """Single consensus round.

    The behaviour queries the Realitio subgraph for unclaimed finalized
    responses, builds an optional withdraw tx + per-question claim txs,
    wraps them in a multisend, and produces a payload with the safe tx
    hash. If there's nothing to do this period, the payload's tx_hash
    is None and the round emits Event.NONE.
    """

    payload_class = RealitioWithdrawBondPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    none_event = Event.NONE
    no_majority_event = Event.NO_MAJORITY
    selection_key: Tuple[str, ...] = (
        get_name(SynchronizedData.tx_submitter),
        get_name(SynchronizedData.most_voted_tx_hash),
    )
    collection_key = get_name(SynchronizedData.participant_to_realitio_withdraw_bond_tx)


class FinishedWithRealitioWithdrawBondTxRound(DegenerateRound):
    """Routed to TransactionSettlementAbci by the parent composition."""


class FinishedWithoutRealitioWithdrawBondTxRound(DegenerateRound):
    """Routed directly to the next skill, skipping TransactionSettlementAbci."""


class OmenRealitioWithdrawBondAbciApp(AbciApp[Event]):
    """OmenRealitioWithdrawBondAbciApp.

    Initial round: RealitioWithdrawBondRound

    Initial states: {RealitioWithdrawBondRound}

    Transition states:
        0. RealitioWithdrawBondRound
            - done: 1.
            - none: 2.
            - no majority: 2.
            - round timeout: 2.
        1. FinishedWithRealitioWithdrawBondTxRound
        2. FinishedWithoutRealitioWithdrawBondTxRound

    Final states: {FinishedWithRealitioWithdrawBondTxRound, FinishedWithoutRealitioWithdrawBondTxRound}

    Timeouts:
        round timeout: 120.0
    """

    initial_round_cls: AppState = RealitioWithdrawBondRound
    initial_states: Set[AppState] = {RealitioWithdrawBondRound}
    transition_function: AbciAppTransitionFunction = {
        RealitioWithdrawBondRound: {
            Event.DONE: FinishedWithRealitioWithdrawBondTxRound,
            Event.NONE: FinishedWithoutRealitioWithdrawBondTxRound,
            Event.NO_MAJORITY: FinishedWithoutRealitioWithdrawBondTxRound,
            Event.ROUND_TIMEOUT: FinishedWithoutRealitioWithdrawBondTxRound,
        },
        FinishedWithRealitioWithdrawBondTxRound: {},
        FinishedWithoutRealitioWithdrawBondTxRound: {},
    }
    final_states: Set[AppState] = {
        FinishedWithRealitioWithdrawBondTxRound,
        FinishedWithoutRealitioWithdrawBondTxRound,
    }
    event_to_timeout: Dict[Event, float] = {
        Event.ROUND_TIMEOUT: 120.0,
    }
    cross_period_persisted_keys: frozenset[str] = frozenset()
    db_pre_conditions: Dict[AppState, Set[str]] = {
        RealitioWithdrawBondRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedWithRealitioWithdrawBondTxRound: {
            get_name(SynchronizedData.most_voted_tx_hash),
        },
        FinishedWithoutRealitioWithdrawBondTxRound: set(),
    }

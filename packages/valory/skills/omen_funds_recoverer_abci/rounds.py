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

"""This module contains the rounds of the OmenFundsRecovererAbciApp."""

import json
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, cast

from packages.valory.skills.abstract_round_abci.base import (
    AbciApp,
    AbciAppTransitionFunction,
    AppState,
    BaseSynchronizedData,
    CollectSameUntilThresholdRound,
    CollectionRound,
    DegenerateRound,
    DeserializedCollection,
    get_name,
)
from packages.valory.skills.omen_funds_recoverer_abci.payloads import (
    BuildMultisendPayload,
    RecoveryTxsPayload,
)
from packages.valory.skills.transaction_settlement_abci.rounds import (
    SynchronizedData as TxSynchronizedData,
)


class Event(Enum):
    """OmenFundsRecovererAbciApp Events"""

    DONE = "done"
    NO_TX = "no_tx"
    NO_MAJORITY = "no_majority"
    NONE = "none"
    ROUND_TIMEOUT = "round_timeout"


class SynchronizedData(TxSynchronizedData):
    """Class to represent the synchronized data.

    This data is replicated by the tendermint application.
    """

    def _get_deserialized(self, key: str) -> DeserializedCollection:
        """Strictly get a collection and return it deserialized."""
        serialized = self.db.get_strict(key)
        return CollectionRound.deserialize_collection(serialized)

    @property
    def recovery_txs(self) -> List[Dict[str, Any]]:
        """Get the accumulated recovery transactions to bundle into a single multisend."""
        raw = self.db.get("recovery_txs", "[]")
        if isinstance(raw, str):
            return json.loads(raw)
        return cast(List[Dict[str, Any]], raw)

    @property
    def most_voted_tx_hash(self) -> str:
        """Get the most_voted_tx_hash."""
        return cast(str, self.db.get_strict("most_voted_tx_hash"))

    @property
    def tx_submitter(self) -> str:
        """Get the round that sent the transaction through transaction settlement."""
        return cast(str, self.db.get_strict("tx_submitter"))

    @property
    def participant_to_recovery_txs(self) -> DeserializedCollection:
        """Get the participant_to_recovery_txs."""
        return self._get_deserialized("participant_to_recovery_txs")

    @property
    def participant_to_tx_prep(self) -> DeserializedCollection:
        """Get the participant_to_tx_prep."""
        return self._get_deserialized("participant_to_tx_prep")


class RecoveryTxsRound(CollectSameUntilThresholdRound):
    """Base round for recovery stages that accumulate txs.

    Each recovery round queries its subgraph, builds tx dicts, and appends
    them to recovery_txs in SynchronizedData. Then moves to the next round.
    """

    payload_class = RecoveryTxsPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    none_event = Event.NONE
    no_majority_event = Event.NO_MAJORITY
    selection_key: Tuple[str, ...] = ()
    collection_key = get_name(SynchronizedData.participant_to_recovery_txs)

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            payload = self.most_voted_payload
            existing = self.synchronized_data.recovery_txs
            new_txs = json.loads(payload) if payload else []
            combined = existing + new_txs
            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.recovery_txs): json.dumps(combined),
                },
            )
            return synchronized_data, Event.DONE
        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


# --- Active Rounds ---


class RemoveLiquidityRound(RecoveryTxsRound):
    """A round for removing liquidity from FPMM markets and merging positions."""


class RedeemPositionsRound(RecoveryTxsRound):
    """A round for redeeming conditional token positions from resolved markets."""


class ClaimBondsRound(RecoveryTxsRound):
    """A round for claiming Realitio bonds and withdrawing internal balance."""


class BuildMultisendRound(CollectSameUntilThresholdRound):
    """A round that bundles all accumulated recovery_txs into a single multisend.

    If recovery_txs is empty, emits NO_TX. Otherwise builds the safe multisend
    tx hash and emits DONE.
    """

    NO_TX_PAYLOAD = "NO_TX"

    payload_class = BuildMultisendPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    none_event = Event.NONE
    no_majority_event = Event.NO_MAJORITY
    selection_key: Tuple[str, ...] = (
        get_name(SynchronizedData.tx_submitter),
        get_name(SynchronizedData.most_voted_tx_hash),
    )
    collection_key = get_name(SynchronizedData.participant_to_tx_prep)


# --- Final (Degenerate) Rounds ---


class FinishedWithRecoveryTxRound(DegenerateRound):
    """A degenerate round indicating recovery produced a tx for settlement."""


class FinishedWithoutRecoveryTxRound(DegenerateRound):
    """A degenerate round indicating no recovery txs were needed."""


class OmenFundsRecovererAbciApp(AbciApp[Event]):
    """OmenFundsRecovererAbciApp

    Initial round: RemoveLiquidityRound

    Initial states: {RemoveLiquidityRound}

    Transition states:
        0. RemoveLiquidityRound
            - done: RedeemPositionsRound
            - no majority: RedeemPositionsRound
            - round timeout: RedeemPositionsRound
        1. RedeemPositionsRound
            - done: ClaimBondsRound
            - no majority: ClaimBondsRound
            - round timeout: ClaimBondsRound
        2. ClaimBondsRound
            - done: BuildMultisendRound
            - no majority: BuildMultisendRound
            - round timeout: BuildMultisendRound
        3. BuildMultisendRound
            - done: FinishedWithRecoveryTxRound
            - no tx: FinishedWithoutRecoveryTxRound
            - no majority: FinishedWithoutRecoveryTxRound
            - round timeout: FinishedWithoutRecoveryTxRound
        4. FinishedWithRecoveryTxRound - Loss
        5. FinishedWithoutRecoveryTxRound - Loss

    Final states: {FinishedWithRecoveryTxRound, FinishedWithoutRecoveryTxRound}

    Timeouts:
        round timeout: 30.0
    """

    initial_round_cls: AppState = RemoveLiquidityRound
    initial_states: Set[AppState] = {RemoveLiquidityRound}
    transition_function: AbciAppTransitionFunction = {
        RemoveLiquidityRound: {
            Event.DONE: RedeemPositionsRound,
            Event.NO_MAJORITY: RedeemPositionsRound,
            Event.ROUND_TIMEOUT: RedeemPositionsRound,
        },
        RedeemPositionsRound: {
            Event.DONE: ClaimBondsRound,
            Event.NO_MAJORITY: ClaimBondsRound,
            Event.ROUND_TIMEOUT: ClaimBondsRound,
        },
        ClaimBondsRound: {
            Event.DONE: BuildMultisendRound,
            Event.NO_MAJORITY: BuildMultisendRound,
            Event.ROUND_TIMEOUT: BuildMultisendRound,
        },
        BuildMultisendRound: {
            Event.DONE: FinishedWithRecoveryTxRound,
            Event.NO_TX: FinishedWithoutRecoveryTxRound,
            Event.NO_MAJORITY: FinishedWithoutRecoveryTxRound,
            Event.ROUND_TIMEOUT: FinishedWithoutRecoveryTxRound,
        },
        FinishedWithRecoveryTxRound: {},
        FinishedWithoutRecoveryTxRound: {},
    }
    final_states: Set[AppState] = {
        FinishedWithRecoveryTxRound,
        FinishedWithoutRecoveryTxRound,
    }
    event_to_timeout: Dict[Event, float] = {
        Event.ROUND_TIMEOUT: 30.0,
    }
    cross_period_persisted_keys: Set[str] = set()
    db_pre_conditions: Dict[AppState, Set[str]] = {
        RemoveLiquidityRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedWithRecoveryTxRound: {
            get_name(SynchronizedData.most_voted_tx_hash),
        },
        FinishedWithoutRecoveryTxRound: set(),
    }

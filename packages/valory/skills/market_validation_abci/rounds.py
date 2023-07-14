# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023 Valory AG
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

"""This package contains the rounds of MarketValidationAbciApp."""

import json
from enum import Enum
from typing import Dict, Optional, Set, Tuple, cast

from packages.valory.skills.abstract_round_abci.base import (
    AbciApp,
    AbciAppTransitionFunction,
    AppState,
    BaseSynchronizedData,
    CollectSameUntilThresholdRound,
    DegenerateRound,
    EventToTimeout,
    get_name,
)
from packages.valory.skills.market_validation_abci.payloads import (
    MarketValidationPayload,
)
from packages.valory.skills.transaction_settlement_abci.rounds import (
    SynchronizedData as TxSynchronizedData,
)


class Event(Enum):
    """MarketValidationAbciApp Events"""

    DONE = "done"
    NO_MAJORITY = "no_majority"
    ROUND_TIMEOUT = "round_timeout"
    ERROR = "error"


class SynchronizedData(TxSynchronizedData):
    """
    Class to represent the synchronized data.

    This data is replicated by the tendermint application.
    """

    @property
    def markets_created(self) -> int:
        """Get the amount of API call retries."""
        return cast(int, self.db.get("markets_created", 0))


class MarketValidationRound(CollectSameUntilThresholdRound):
    """MarketValidationRound"""

    payload_class = MarketValidationPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = "market_created"

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached and self.most_voted_payload is None:
            return self.synchronized_data, Event.ERROR

        if self.threshold_reached and self.most_voted_payload is not None:
            markets_created = cast(
                SynchronizedData, self.synchronized_data
            ).markets_created
            markets_created += 1
            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.markets_created): markets_created,
                },
            )
            return synchronized_data, Event.DONE
        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class FinishedMarketValidationRound(DegenerateRound):
    """FinishedMarketValidationRound"""


class MarketValidationAbciApp(AbciApp[Event]):
    """MarketValidationAbciApp"""

    initial_round_cls: AppState = MarketValidationRound
    initial_states: Set[AppState] = {
        MarketValidationRound,
    }
    transition_function: AbciAppTransitionFunction = {
        MarketValidationRound: {
            Event.DONE: FinishedMarketValidationRound,
            Event.ERROR: MarketValidationRound,
            Event.ROUND_TIMEOUT: MarketValidationRound,
            Event.NO_MAJORITY: FinishedMarketValidationRound,
        },
        FinishedMarketValidationRound: {},
    }
    final_states: Set[AppState] = {
        FinishedMarketValidationRound,
    }
    event_to_timeout: EventToTimeout = {}
    cross_period_persisted_keys: Set[str] = {
        get_name(SynchronizedData.markets_created),
    }  # type: ignore
    db_pre_conditions: Dict[AppState, Set[str]] = {
        MarketValidationRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedMarketValidationRound: set()
    }

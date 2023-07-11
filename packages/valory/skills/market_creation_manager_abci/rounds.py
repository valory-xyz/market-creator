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

"""This package contains the rounds of MarketCreationManagerAbciApp."""

from ctypes import cast
from enum import Enum
import json
from typing import Dict, List, Optional, Set, Tuple

from packages.valory.skills.abstract_round_abci.base import (
    AbciApp,
    AbciAppTransitionFunction,
    AbstractRound,
    AppState,
    BaseSynchronizedData,
    CollectSameUntilThresholdRound,
    DegenerateRound,
    EventToTimeout,
    get_name
)

from packages.valory.skills.market_creation_manager_abci.payloads import (
    CollectRandomnessPayload,
    DataGatheringPayload,
    SelectKeeperPayload,
    MarketIdentificationPayload,
    PrepareTransactionPayload,
)


class Event(Enum):
    """MarketCreationManagerAbciApp Events"""

    NO_MAJORITY = "no_majority"
    DONE = "done"
    ROUND_TIMEOUT = "round_timeout"
    API_ERROR = "api_error"


class SynchronizedData(BaseSynchronizedData):
    """
    Class to represent the synchronized data.

    This data is replicated by the tendermint application.
    """

    @property
    def gathered_data(self) -> str:
        """Get the llm_values."""
        return cast(str, self.db.get_strict("gathered_data"))
    
    @property
    def newsapi_api_retries(self) -> int:
        """Get the amount of API call retries."""
        return cast(int, self.db.get("newsapi_api_retries", 0))


class CollectRandomnessRound(CollectSameUntilThresholdRound):
    """A round for generating collecting randomness"""

    payload_class = CollectRandomnessPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = get_name(SynchronizedData.participant_to_randomness)
    selection_key = ("ignored", get_name(SynchronizedData.most_voted_randomness))


class DataGatheringRound(CollectSameUntilThresholdRound):
    """DataGatheringRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    MAX_RETRIES_PAYLOAD = "MAX_RETRIES_PAYLOAD"

    payload_class = DataGatheringPayload
    #payload_attribute = "gathered_data"
    synchronized_data_class = SynchronizedData
    #done_event = Event.DONE
    #no_majority_event = Event.NO_MAJORITY

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:

            if self.most_voted_payload == self.ERROR_PAYLOAD:
                newsapi_api_retries = cast(
                    SynchronizedData, self.synchronized_data
                ).newsapi_api_retries
                synchronized_data = self.synchronized_data.update(
                    synchronized_data_class=SynchronizedData,
                    **{
                        get_name(
                            SynchronizedData.newsapi_api_retries
                        ): newsapi_api_retries
                        + 1,
                    },
                )
                return synchronized_data, Event.API_ERROR

            if (
                self.most_voted_payload
                == DataGatheringRound.MAX_RETRIES_PAYLOAD
            ):
                return self.synchronized_data, Event.DONE

            #TODO convert to JSON at this point? Needs to update SynchronizedData type
            payload = self.most_voted_payload

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.gathered_data): payload,
                },
            )
            return synchronized_data, Event.DONE
        
        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None

class SelectKeeperRound(CollectSameUntilThresholdRound):
    """A round in a which keeper is selected"""
    
    payload_class = SelectKeeperPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = get_name(SynchronizedData.participant_to_selection)
    selection_key = get_name(SynchronizedData.most_voted_keeper_address)


class MarketIdentificationRound(CollectSameUntilThresholdRound):
    """MarketIdentificationRound"""

    payload_class = MarketIdentificationPayload
    payload_attribute = "content"
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY



class PrepareTransactionRound(CollectSameUntilThresholdRound):
    """PrepareTransactionRound"""

    payload_class = PrepareTransactionPayload
    payload_attribute = "content"
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY


class FinishedMarketCreationManagerRound(DegenerateRound):
    """FinishedMarketCreationManagerRound"""


class MarketCreationManagerAbciApp(AbciApp[Event]):
    """MarketCreationManagerAbciApp"""

    initial_round_cls: AppState = CollectRandomnessRound
    initial_states: Set[AppState] = {CollectRandomnessRound}
    transition_function: AbciAppTransitionFunction = {
        CollectRandomnessRound: {
            Event.DONE: DataGatheringRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound
        },
        DataGatheringRound: {
            Event.DONE: SelectKeeperRound,
            Event.API_ERROR: CollectRandomnessRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound
        },
        SelectKeeperRound: {
            Event.DONE: MarketIdentificationRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound
        },        
        MarketIdentificationRound: {
            Event.DONE: PrepareTransactionRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound
        },
        PrepareTransactionRound: {
            Event.DONE: FinishedMarketCreationManagerRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound
        },
        FinishedMarketCreationManagerRound: {}
    }
    final_states: Set[AppState] = {FinishedMarketCreationManagerRound}
    event_to_timeout: EventToTimeout = {}
    cross_period_persisted_keys: Set[str] = []
    db_pre_conditions: Dict[AppState, Set[str]] = {
        CollectRandomnessRound: [],
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedMarketCreationManagerRound: [],
    }

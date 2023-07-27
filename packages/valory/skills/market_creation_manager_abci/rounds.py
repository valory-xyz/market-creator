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
    OnlyKeeperSendsRound,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    CollectRandomnessPayload,
    DataGatheringPayload,
    MarketProposalPayload,
    PrepareTransactionPayload,
    RetrieveApprovedMarketPayload,
    SelectKeeperPayload,
)
from packages.valory.skills.transaction_settlement_abci.rounds import (
    SynchronizedData as TxSynchronizedData,
)


class Event(Enum):
    """MarketCreationManagerAbciApp Events"""

    NO_MAJORITY = "no_majority"
    DONE = "done"
    ROUND_TIMEOUT = "round_timeout"
    API_ERROR = "api_error"
    DID_NOT_SEND = "did_not_send"
    MAX_MARKETS_REACHED = "max_markets_reached"
    NO_MARKETS_RETRIEVED = "no_markets_retrieved"


class SynchronizedData(TxSynchronizedData):
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

    @property
    def markets_created(self) -> int:
        """Get the amount of API call retries."""
        return cast(int, self.db.get("markets_created", 0))

    @property
    def proposed_question_data(self) -> dict:
        """Get the proposed_question_data."""
        return cast(dict, self.db.get_strict("proposed_question_data"))

    @property
    def approved_question_data(self) -> dict:
        """Get the approved_question_data."""
        return cast(dict, self.db.get_strict("approved_question_data"))

    @property
    def all_approved_question_data(self) -> dict:
        """Get the approved_question_data."""
        return cast(dict, self.db.get_strict("all_approved_question_data"))`

    @property
    def most_voted_tx_hash(self) -> str:
        """Get the most_voted_tx_hash."""
        return cast(str, self.db.get_strict("most_voted_tx_hash"))

    @property
    def most_voted_keeper_address(self) -> str:
        """Get the most_voted_keeper_address."""
        return cast(str, self.db.get_strict("most_voted_keeper_address"))


class CollectRandomnessRound(CollectSameUntilThresholdRound):
    """A round for generating collecting randomness"""

    payload_class = CollectRandomnessPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = get_name(SynchronizedData.participant_to_randomness)
    selection_key = ("ignored", get_name(SynchronizedData.most_voted_randomness))


class RemoveFundingRound(CollectSameUntilThresholdRound):
    """RemoveFundingRound"""

    payload_class = PrepareTransactionPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = "content"

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Enum]]:
        """End block."""
        # TODO: incomplete implementation
        if self.threshold_reached and any(
            [val is not None for val in self.most_voted_payload_values]
        ):
            return (
                self.synchronized_data.update(
                    synchronized_data_class=self.synchronized_data_class,
                    **{
                        get_name(
                            SynchronizedData.most_voted_tx_hash
                        ): self.most_voted_payload
                    },
                ),
                Event.DONE,
            )
        return None

class DataGatheringRound(CollectSameUntilThresholdRound):
    """DataGatheringRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    MAX_RETRIES_PAYLOAD = "MAX_RETRIES_PAYLOAD"
    MAX_MARKETS_REACHED = "MAX_MARKETS_REACHED"

    payload_class = DataGatheringPayload
    synchronized_data_class = SynchronizedData

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

            if self.most_voted_payload == DataGatheringRound.MAX_RETRIES_PAYLOAD:
                return self.synchronized_data, Event.DONE

            if self.most_voted_payload == DataGatheringRound.MAX_MARKETS_REACHED:
                return self.synchronized_data, Event.MAX_MARKETS_REACHED

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.gathered_data): self.most_voted_payload,
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


class MarketProposalRound(OnlyKeeperSendsRound):
    """MarketProposalRound"""

    payload_class = MarketProposalPayload
    payload_attribute = "content"
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY

    ERROR_PAYLOAD = "error"

    def end_block(
        self,
    ) -> Optional[
        Tuple[BaseSynchronizedData, Enum]
    ]:  # pylint: disable=too-many-return-statements
        """Process the end of the block."""
        if self.keeper_payload is None:
            return None

        # Keeper did not send
        if self.keeper_payload is None:  # pragma: no cover
            return self.synchronized_data, Event.DID_NOT_SEND

        # API error
        if (
            cast(MarketProposalPayload, self.keeper_payload).content
            == self.ERROR_PAYLOAD
        ):
            return self.synchronized_data, Event.API_ERROR

        # Happy path
        proposed_question_data = json.loads(
            cast(MarketProposalPayload, self.keeper_payload).content
        )  # there could be problems loading this from the LLM response

        synchronized_data = self.synchronized_data.update(
            synchronized_data_class=SynchronizedData,
            **{
                get_name(
                    SynchronizedData.proposed_question_data
                ): proposed_question_data,
                get_name(SynchronizedData.markets_created): cast(
                    SynchronizedData, self.synchronized_data
                ).markets_created
                + 1,
            },
        )

        return synchronized_data, Event.DONE


class RetrieveApprovedMarketRound(OnlyKeeperSendsRound):
    """RetrieveApprovedMarketRound"""

    payload_class = RetrieveApprovedMarketPayload
    payload_attribute = "content"
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    MAX_RETRIES_PAYLOAD = "MAX_RETRIES_PAYLOAD"
    NO_MARKETS_RETRIEVED_PAYLOAD = "NO_MARKETS_RETRIEVED_PAYLOAD"

    def end_block(
        self,
    ) -> Optional[
        Tuple[BaseSynchronizedData, Enum]
    ]:  # pylint: disable=too-many-return-statements
        """Process the end of the block."""
        if self.keeper_payload is None:
            return None

        # Keeper did not send
        if self.keeper_payload is None:  # pragma: no cover
            return self.synchronized_data, Event.DID_NOT_SEND

        # API error
        if (
            cast(RetrieveApprovedMarketPayload, self.keeper_payload).content
            == self.ERROR_PAYLOAD
        ):
            return self.synchronized_data, Event.API_ERROR

        # No markets available
        if (
            cast(RetrieveApprovedMarketPayload, self.keeper_payload).content
            == self.NO_MARKETS_RETRIEVED_PAYLOAD
        ):
            return (
                self.synchronized_data.update(
                    synchronized_data_class=self.synchronized_data_class,
                    **{
                        get_name(SynchronizedData.markets_created): cast(
                            SynchronizedData, self.synchronized_data
                        ).markets_created,
                    },
                ),
                Event.NO_MARKETS_RETRIEVED,
            )

        # Happy path
        approved_question_data = json.loads(
            cast(MarketProposalPayload, self.keeper_payload).content
        )

        synchronized_data = self.synchronized_data.update(
            synchronized_data_class=SynchronizedData,
            **{
                get_name(
                    SynchronizedData.approved_question_data
                ): approved_question_data,
            },
        )

        return synchronized_data, Event.DONE


class PrepareTransactionRound(CollectSameUntilThresholdRound):
    """PrepareTransactionRound"""

    payload_class = PrepareTransactionPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = "content"

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Enum]]:
        """End block."""
        # TODO: incomplete implementation
        if self.threshold_reached and any(
            [val is not None for val in self.most_voted_payload_values]
        ):
            return (
                self.synchronized_data.update(
                    synchronized_data_class=self.synchronized_data_class,
                    **{
                        get_name(
                            SynchronizedData.most_voted_tx_hash
                        ): self.most_voted_payload
                    },
                ),
                Event.DONE,
            )
        return None


class FinishedMarketCreationManagerRound(DegenerateRound):
    """FinishedMarketCreationManagerRound"""


class SkippedMarketCreationManagerRound(DegenerateRound):
    """SkippedMarketCreationManagerRound"""


class MarketCreationManagerAbciApp(AbciApp[Event]):
    """MarketCreationManagerAbciApp"""

    initial_round_cls: AppState = CollectRandomnessRound
    initial_states: Set[AppState] = {CollectRandomnessRound}
    transition_function: AbciAppTransitionFunction = {
        CollectRandomnessRound: {
            Event.DONE: DataGatheringRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        DataGatheringRound: {
            Event.DONE: SelectKeeperRound,
            Event.MAX_MARKETS_REACHED: RetrieveApprovedMarketRound,
            Event.API_ERROR: CollectRandomnessRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        SelectKeeperRound: {
            Event.DONE: MarketProposalRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        MarketProposalRound: {
            Event.DONE: RetrieveApprovedMarketRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
            Event.DID_NOT_SEND: CollectRandomnessRound,
            Event.API_ERROR: CollectRandomnessRound,
        },
        RetrieveApprovedMarketRound: {
            Event.DONE: PrepareTransactionRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
            Event.DID_NOT_SEND: CollectRandomnessRound,
            Event.API_ERROR: CollectRandomnessRound,
            Event.NO_MARKETS_RETRIEVED: SkippedMarketCreationManagerRound,
        },
        PrepareTransactionRound: {
            Event.DONE: FinishedMarketCreationManagerRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        FinishedMarketCreationManagerRound: {},
        SkippedMarketCreationManagerRound: {},
    }
    final_states: Set[AppState] = {
        FinishedMarketCreationManagerRound,
        SkippedMarketCreationManagerRound,
    }
    event_to_timeout: EventToTimeout = {}
    cross_period_persisted_keys: Set[str] = {
        get_name(SynchronizedData.markets_created),
    }  # type: ignore
    db_pre_conditions: Dict[AppState, Set[str]] = {
        CollectRandomnessRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedMarketCreationManagerRound: {
            get_name(SynchronizedData.most_voted_tx_hash),
        },
        SkippedMarketCreationManagerRound: set(),
    }

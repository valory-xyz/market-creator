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
from typing import Any, Dict, List, Optional, Set, Tuple, cast

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
from packages.valory.skills.market_approval_manager_abci.payloads import (
    CollectRandomnessPayload,
    CollectMarketsDataPayload,
    SelectKeeperPayload,
    MarketApprovalPayload,
)
from packages.valory.skills.transaction_settlement_abci.rounds import (
    SynchronizedData as TxSynchronizedData,
)


class Event(Enum):
    """MarketCreationManagerAbciApp Events"""

    NO_MAJORITY = "no_majority"
    DONE = "done"
    NO_TX = "no_tx"
    ROUND_TIMEOUT = "round_timeout"
    ERROR = "api_error"
    DID_NOT_SEND = "did_not_send"
    MAX_RETRIES_REACHED = "max_retries_reached"


DEFAULT_PROPOSED_MARKETS_DATA = {"proposed_markets": [], "timestamp": 0}


class SynchronizedData(TxSynchronizedData):
    """
    Class to represent the synchronized data.

    This data is replicated by the tendermint application.
    """

    @property
    def approved_markets_count(self) -> int:
        """Get the approved_markets_count."""
        return cast(int, self.db.get("approved_markets_count", 0))

    @property
    def collected_markets_data(self) -> dict:
        """Get the collected_markets_data."""
        return cast(
            dict, self.db.get("collected_markets_data", DEFAULT_PROPOSED_MARKETS_DATA)
        )


class CollectRandomnessRound(CollectSameUntilThresholdRound):
    """A round for generating collecting randomness"""

    payload_class = CollectRandomnessPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = get_name(SynchronizedData.participant_to_randomness)
    selection_key = ("ignored", get_name(SynchronizedData.most_voted_randomness))


class CollectMarketsDataRound(CollectSameUntilThresholdRound):
    """CollectMarketsDataRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    MAX_RETRIES_PAYLOAD = "MAX_RETRIES_PAYLOAD"
    MAX_PROPOSED_MARKETS_REACHED_PAYLOAD = "MAX_PROPOSED_MARKETS_REACHED_PAYLOAD"
    SKIP_MARKET_PROPOSAL_PAYLOAD = "SKIP_MARKET_PROPOSAL_PAYLOAD"

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
                return synchronized_data, Event.ERROR

            if self.most_voted_payload == DataGatheringRound.MAX_RETRIES_PAYLOAD:
                return self.synchronized_data, Event.MAX_RETRIES_REACHED

            if (
                self.most_voted_payload
                == DataGatheringRound.MAX_PROPOSED_MARKETS_REACHED_PAYLOAD
            ):
                return self.synchronized_data, Event.MAX_PROPOSED_MARKETS_REACHED

            if (
                self.most_voted_payload
                == DataGatheringRound.SKIP_MARKET_PROPOSAL_PAYLOAD
            ):
                return self.synchronized_data, Event.SKIP_MARKET_PROPOSAL

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


class MarketApprovalRound(OnlyKeeperSendsRound):
    """MarketApprovalRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    MAX_RETRIES_PAYLOAD = "MAX_RETRIES_PAYLOAD"

    payload_class = MarketProposalPayload
    payload_attribute = "content"
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY

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
            return self.synchronized_data, Event.ERROR

        # Happy path
        proposed_markets_data = json.loads(
            cast(MarketProposalPayload, self.keeper_payload).content
        )  # there could be problems loading this from the LLM response

        proposed_markets_count = len(proposed_markets_data.get("proposed_markets", []))

        synchronized_data = self.synchronized_data.update(
            synchronized_data_class=SynchronizedData,
            **{
                get_name(SynchronizedData.proposed_markets_data): proposed_markets_data,
                get_name(SynchronizedData.proposed_markets_count): cast(
                    SynchronizedData, self.synchronized_data
                ).proposed_markets_count
                + proposed_markets_count,
            },
        )

        return synchronized_data, Event.DONE


class FinishedWithErrorRound(DegenerateRound):
    """FinishedWithErrorRound"""


class FinishedRound(DegenerateRound):
    """FinishedRound"""


class MarketApprovalManagerAbciApp(AbciApp[Event]):
    """MarketApprovalManagerAbciApp"""

    initial_round_cls: AppState = CollectRandomnessRound
    initial_states: Set[AppState] = {CollectRandomnessRound}
    transition_function: AbciAppTransitionFunction = {
        CollectRandomnessRound: {
            Event.DONE: SelectKeeperRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        CollectMarketsDataRound: {
            Event.DONE: SelectKeeperRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
            Event.ERROR: FinishedWithErrorRound
        },
        SelectKeeperRound: {
            Event.DONE: MarketApprovalRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        MarketApprovalRound: {
            Event.DONE: FinishedRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
            Event.ERROR: FinishedWithErrorRound
        },
        FinishedWithErrorRound: {},
        FinishedRound: {},
    }
    final_states: Set[AppState] = {
        FinishedWithErrorRound,
        FinishedRound,
    }
    event_to_timeout: EventToTimeout = {
    }
    cross_period_persisted_keys: Set[str] = {
        get_name(SynchronizedData.approved_markets_count),
    }  # type: ignore
    db_pre_conditions: Dict[AppState, Set[str]] = {
        CollectRandomnessRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedWithErrorRound: {
            get_name(SynchronizedData.randomness),
        },
        FinishedRound: {
            get_name(SynchronizedData.randomness),
        },
    }

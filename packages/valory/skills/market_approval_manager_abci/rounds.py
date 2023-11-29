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
    CollectRandomnessMarketApprovalPayload,
    CollectMarketsDataMarketApprovalPayload,
    SelectKeeperMarketApprovalPayload,
    ExecuteApprovalMarketApprovalPayload,
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
    MAX_APPROVED_MARKETS_REACHED = "max_approved_markets_reached"
    SKIP_MARKET_APPROVAL = "skip_market_approval"

DEFAULT_COLLECTED_MARKETS_DATA = {"collected_markets": [], "timestamp": 0}
DEFAULT_APPROVED_MARKETS_DATA = {"approved_markets": [], "timestamp": 0}


class SynchronizedData(TxSynchronizedData):
    """
    Class to represent the synchronized data.

    This data is replicated by the tendermint application.
    """

    @property
    def collected_markets_retries(self) -> int:
        """Get the approved_markets_count."""
        return cast(int, self.db.get("collected_markets_retries", 0))

    @property
    def approved_markets_count(self) -> int:
        """Get the approved_markets_count."""
        return cast(int, self.db.get("approved_markets_count", 0))

    @property
    def collected_markets_data(self) -> dict:
        """Get the collected_markets_data."""
        return cast(
            dict, self.db.get("collected_markets_data", DEFAULT_COLLECTED_MARKETS_DATA)
        )

    @property
    def approved_markets_data(self) -> dict:
        """Get the approved_markets_data."""
        return cast(
            dict, self.db.get("approved_markets_data", DEFAULT_APPROVED_MARKETS_DATA)
        )

class CollectRandomnessMarketApprovalRound(CollectSameUntilThresholdRound):
    """A round for generating collecting randomness"""

    payload_class = CollectRandomnessMarketApprovalPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = get_name(SynchronizedData.participant_to_randomness)
    selection_key = ("ignored", get_name(SynchronizedData.most_voted_randomness))


class CollectMarketsDataMarketApprovalRound(CollectSameUntilThresholdRound):
    """CollectMarketsDataMarketApprovalRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    MAX_RETRIES_PAYLOAD = "MAX_RETRIES_PAYLOAD"
    MAX_APPROVED_MARKETS_REACHED_PAYLOAD = "MAX_APPROVED_MARKETS_REACHED_PAYLOAD"
    SKIP_MARKET_APPROVAL_PAYLOAD = "SKIP_MARKET_APPROVAL_PAYLOAD"

    payload_class = CollectMarketsDataMarketApprovalPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            if self.most_voted_payload == self.ERROR_PAYLOAD:
                collected_markets_retries = cast(
                    SynchronizedData, self.synchronized_data
                ).collected_markets_retries
                synchronized_data = self.synchronized_data.update(
                    synchronized_data_class=SynchronizedData,
                    **{
                        get_name(
                            SynchronizedData.collected_markets_retries
                        ): collected_markets_retries
                        + 1,
                    },
                )
                return synchronized_data, Event.ERROR

            if self.most_voted_payload == self.MAX_RETRIES_PAYLOAD:
                return self.synchronized_data, Event.MAX_RETRIES_REACHED

            if (
                self.most_voted_payload
                == self.MAX_APPROVED_MARKETS_REACHED_PAYLOAD
            ):
                return self.synchronized_data, Event.MAX_APPROVED_MARKETS_REACHED

            if (
                self.most_voted_payload
                == self.SKIP_MARKET_APPROVAL_PAYLOAD
            ):
                return self.synchronized_data, Event.SKIP_MARKET_APPROVAL

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.collected_markets_data): self.most_voted_payload,
                },
            )
            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class SelectKeeperMarketApprovalRound(CollectSameUntilThresholdRound):
    """A round in a which keeper is selected"""

    payload_class = SelectKeeperMarketApprovalPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = get_name(SynchronizedData.participant_to_selection)
    selection_key = get_name(SynchronizedData.most_voted_keeper_address)


class ExecuteApprovalMarketApprovalRound(OnlyKeeperSendsRound):
    """ExecuteApprovalMarketApprovalRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    MAX_RETRIES_PAYLOAD = "MAX_RETRIES_PAYLOAD"

    payload_class = ExecuteApprovalMarketApprovalPayload
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
            cast(ExecuteApprovalMarketApprovalPayload, self.keeper_payload).content
            == self.ERROR_PAYLOAD
        ):
            return self.synchronized_data, Event.ERROR

        # Happy path
        approved_markets_data = json.loads(
            cast(ExecuteApprovalMarketApprovalPayload, self.keeper_payload).content
        )

        approved_markets_count = len(approved_markets_data.get("proposed_markets", []))

        synchronized_data = self.synchronized_data.update(
            synchronized_data_class=SynchronizedData,
            **{
                get_name(SynchronizedData.approved_markets_data): approved_markets_data,
                get_name(SynchronizedData.approved_markets_count): cast(
                    SynchronizedData, self.synchronized_data
                ).approved_markets_count
                + approved_markets_count,
            },
        )

        return synchronized_data, Event.DONE


class FinishedWithErrorRound(DegenerateRound):
    """FinishedWithErrorRound"""


class FinishedRound(DegenerateRound):
    """FinishedRound"""


class MarketApprovalManagerAbciApp(AbciApp[Event]):
    """MarketApprovalManagerAbciApp"""

    initial_round_cls: AppState = CollectRandomnessMarketApprovalRound
    initial_states: Set[AppState] = {CollectRandomnessMarketApprovalRound}
    transition_function: AbciAppTransitionFunction = {
        CollectRandomnessMarketApprovalRound: {
            Event.DONE: SelectKeeperMarketApprovalRound,
            Event.NO_MAJORITY: CollectRandomnessMarketApprovalRound,
            Event.ROUND_TIMEOUT: CollectRandomnessMarketApprovalRound,
        },
        CollectMarketsDataMarketApprovalRound: {
            Event.DONE: SelectKeeperMarketApprovalRound,
            Event.NO_MAJORITY: CollectRandomnessMarketApprovalRound,
            Event.ROUND_TIMEOUT: CollectRandomnessMarketApprovalRound,
            Event.ERROR: FinishedWithErrorRound
        },
        SelectKeeperMarketApprovalRound: {
            Event.DONE: ExecuteApprovalMarketApprovalRound,
            Event.NO_MAJORITY: CollectRandomnessMarketApprovalRound,
            Event.ROUND_TIMEOUT: CollectRandomnessMarketApprovalRound,
        },
        ExecuteApprovalMarketApprovalRound: {
            Event.DONE: FinishedRound,
            Event.NO_MAJORITY: CollectRandomnessMarketApprovalRound,
            Event.ROUND_TIMEOUT: CollectRandomnessMarketApprovalRound,
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
        CollectRandomnessMarketApprovalRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedWithErrorRound: set(),
        FinishedRound: set(),
    }

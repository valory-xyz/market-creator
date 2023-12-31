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
from packages.valory.skills.market_creation_manager_abci.payloads import (
    ApproveMarketsPayload,
    CloseMarketsPayload,
    CollectProposedMarketsPayload,
    CollectRandomnessPayload,
    DataGatheringPayload,
    DepositDaiPayload,
    MarketProposalPayload,
    PostTxPayload,
    PrepareTransactionPayload,
    RemoveFundingPayload,
    RetrieveApprovedMarketPayload,
    SelectKeeperPayload,
    SyncMarketsPayload,
)
from packages.valory.skills.transaction_settlement_abci.rounds import (
    SynchronizedData as TxSynchronizedData,
)


class Event(Enum):
    """MarketCreationManagerAbciApp Events"""

    NO_MAJORITY = "no_majority"
    DONE = "done"
    NONE = "none"
    NO_TX = "no_tx"
    ROUND_TIMEOUT = "round_timeout"
    MARKET_PROPOSAL_ROUND_TIMEOUT = "market_proposal_round_timeout"
    ERROR = "api_error"
    DID_NOT_SEND = "did_not_send"
    MAX_PROPOSED_MARKETS_REACHED = "max_markets_reached"
    MAX_APPROVED_MARKETS_REACHED = "max_approved_markets_reached"
    MAX_RETRIES_REACHED = "max_retries_reached"
    NO_MARKETS_RETRIEVED = "no_markets_retrieved"
    SKIP_MARKET_PROPOSAL = "skip_market_proposal"
    SKIP_MARKET_APPROVAL = "skip_market_approval"


DEFAULT_PROPOSED_MARKETS_DATA = {"proposed_markets": [], "timestamp": 0}
DEFAULT_COLLECTED_PROPOSED_MARKETS_DATA = json.dumps(
    {
        "proposed_markets": [],
        "fixedProductMarketMakers": [],
        "num_markets_to_approve": 0,
        "timestamp": 0,
    }
)


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
    def proposed_markets_api_retries(self) -> int:
        """Get the amount of API call retries."""
        return cast(int, self.db.get("proposed_markets_api_retries", 0))

    @property
    def proposed_markets_count(self) -> int:
        """Get the proposed_markets_count."""
        return cast(int, self.db.get("proposed_markets_count", 0))

    @property
    def approved_markets_count(self) -> int:
        """Get the approved_markets_count."""
        return cast(int, self.db.get("approved_markets_count", 0))

    @property
    def approved_markets_timestamp(self) -> int:
        """Get the approved_markets_count."""
        return cast(int, self.db.get("approved_markets_timestamp", 0))

    @property
    def proposed_markets_data(self) -> dict:
        """Get the proposed_markets_data."""
        return cast(
            dict, self.db.get("proposed_markets_data", DEFAULT_PROPOSED_MARKETS_DATA)
        )

    @property
    def collected_proposed_markets_data(self) -> str:
        """Get the collected_proposed_markets_data."""
        return cast(
            str,
            self.db.get(
                "collected_proposed_markets_data",
                DEFAULT_COLLECTED_PROPOSED_MARKETS_DATA,
            ),
        )

    @property
    def approved_markets_data(self) -> dict:
        """Get the approved_markets_data."""
        return cast(dict, self.db.get_strict("approved_markets_data"))

    @property
    def approved_question_data(self) -> dict:
        """Get the approved_question_data."""
        return cast(dict, self.db.get_strict("approved_question_data"))

    @property
    def is_approved_question_data_set(self) -> bool:
        """Get the is_approved."""
        approved_question_data = self.db.get("approved_question_data", None)
        return approved_question_data is not None

    @property
    def all_approved_question_data(self) -> dict:
        """Get the approved_question_data."""
        return cast(dict, self.db.get_strict("all_approved_question_data"))

    @property
    def most_voted_tx_hash(self) -> str:
        """Get the most_voted_tx_hash."""
        return cast(str, self.db.get_strict("most_voted_tx_hash"))

    @property
    def most_voted_keeper_address(self) -> str:
        """Get the most_voted_keeper_address."""
        return cast(str, self.db.get_strict("most_voted_keeper_address"))

    @property
    def markets_to_remove_liquidity(self) -> List[Dict[str, Any]]:
        """Get the markets_to_remove_liquidity."""
        return cast(
            List[Dict[str, Any]], self.db.get("markets_to_remove_liquidity", [])
        )

    @property
    def market_from_block(self) -> int:
        """Get the market_from_block."""
        return cast(int, self.db.get("market_from_block", 0))

    @property
    def settled_tx_hash(self) -> Optional[str]:
        """Get the settled_tx_hash."""
        return cast(str, self.db.get("final_tx_hash", None))

    @property
    def tx_sender(self) -> str:
        """Get the round that send the transaction through transaction settlement."""
        return cast(str, self.db.get_strict("tx_sender"))

    # This is a fix to ensure a given property is always set up on
    # the SynchronizedData before ResetAndPause
    def ensure_property_is_set(self, property_name: str) -> "SynchronizedData":
        """Ensure a property is set."""
        try:
            value = self.db.get_strict(property_name)
        except ValueError:
            value = getattr(self, property_name)

        return cast(
            SynchronizedData,
            self.update(
                synchronized_data_class=SynchronizedData,
                **{property_name: value},
            ),
        )


class CollectRandomnessRound(CollectSameUntilThresholdRound):
    """A round for generating collecting randomness"""

    payload_class = CollectRandomnessPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = get_name(SynchronizedData.participant_to_randomness)
    selection_key = ("ignored", get_name(SynchronizedData.most_voted_randomness))

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Enum]]:
        """Process the end of the block."""
        res = super().end_block()
        if res is None:
            return None

        synced_data, event = cast(Tuple[SynchronizedData, Enum], res)

        # Fix to ensure properties are present on the SynchronizedData
        # before ResetAndPause round.
        synced_data = synced_data.ensure_property_is_set(
            get_name(SynchronizedData.approved_markets_count)
        )
        synced_data = synced_data.ensure_property_is_set(
            get_name(SynchronizedData.proposed_markets_count)
        )
        synced_data = synced_data.ensure_property_is_set(
            get_name(SynchronizedData.proposed_markets_data)
        )
        synced_data = synced_data.ensure_property_is_set(
            get_name(SynchronizedData.approved_markets_timestamp)
        )

        return synced_data, event


class PostTransactionRound(CollectSameUntilThresholdRound):
    """A round to be run after a transaction has been settled."""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    DONE_PAYLOAD = "DONE_PAYLOAD"

    payload_class = PostTxPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            if self.most_voted_payload == self.ERROR_PAYLOAD:
                return self.synchronized_data, Event.ERROR

            # no database update is required
            return self.synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class DepositDaiRound(CollectSameUntilThresholdRound):
    """A round for depositing Dai"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    NO_TX_PAYLOAD = "NO_TX"

    payload_class = DepositDaiPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            if self.most_voted_payload == self.ERROR_PAYLOAD:
                return self.synchronized_data, Event.ERROR

            if self.most_voted_payload == self.NO_TX_PAYLOAD:
                return self.synchronized_data, Event.NO_TX

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(
                        SynchronizedData.most_voted_tx_hash
                    ): self.most_voted_payload,
                    get_name(SynchronizedData.tx_sender): self.round_id,
                },
            )
            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class RemoveFundingRound(CollectSameUntilThresholdRound):
    """RemoveFundingRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    NO_UPDATE_PAYLOAD = "NO_UPDATE"

    payload_class = RemoveFundingPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            if self.most_voted_payload == self.ERROR_PAYLOAD:
                return self.synchronized_data, Event.ERROR

            if self.most_voted_payload == self.NO_UPDATE_PAYLOAD:
                return self.synchronized_data, Event.NO_TX

            payload = json.loads(self.most_voted_payload)
            tx_data, market_address = payload["tx"], payload["market"]

            # Note that popping the markets_to_remove_liquidity here
            # is optimistically assuming that the transaction will be successful.
            markets_to_remove_liquidity = cast(
                SynchronizedData,
                self.synchronized_data,
            ).markets_to_remove_liquidity
            markets_to_remove_liquidity = [
                market
                for market in markets_to_remove_liquidity
                if market["address"] != market_address
            ]
            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(
                        SynchronizedData.markets_to_remove_liquidity
                    ): markets_to_remove_liquidity,
                    get_name(SynchronizedData.most_voted_tx_hash): tx_data,
                    get_name(SynchronizedData.tx_sender): self.round_id,
                },
            )
            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class SyncMarketsRound(CollectSameUntilThresholdRound):
    """SyncMarketsRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    NO_UPDATE_PAYLOAD = "NO_UPDATE"

    payload_class = SyncMarketsPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            if self.most_voted_payload == self.ERROR_PAYLOAD:
                return self.synchronized_data, Event.ERROR
            if self.most_voted_payload == self.NO_UPDATE_PAYLOAD:
                return self.synchronized_data, Event.DONE
            payload = json.loads(self.most_voted_payload)
            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.markets_to_remove_liquidity): payload[
                        "markets"
                    ],
                    get_name(SynchronizedData.market_from_block): payload["from_block"],
                },
            )
            return synchronized_data, Event.DONE
        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class CollectProposedMarketsRound(CollectSameUntilThresholdRound):
    """CollectProposedMarketsRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    MAX_RETRIES_PAYLOAD = "MAX_RETRIES_PAYLOAD"
    MAX_APPROVED_MARKETS_REACHED_PAYLOAD = "MAX_APPROVED_MARKETS_REACHED_PAYLOAD"
    SKIP_MARKET_APPROVAL_PAYLOAD = "SKIP_MARKET_APPROVAL_PAYLOAD"

    payload_class = CollectProposedMarketsPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    none_event = Event.NONE
    collection_key = get_name(SynchronizedData.participant_to_selection)
    selection_key = get_name(SynchronizedData.collected_proposed_markets_data)

    def end_block(self) -> Optional[Tuple[SynchronizedData, Enum]]:
        """Process the end of the block."""
        res = super().end_block()
        if res is None:
            return None

        synced_data, event = cast(Tuple[SynchronizedData, Enum], res)
        payload = self.most_voted_payload

        if event == Event.DONE and payload == self.ERROR_PAYLOAD:
            return synced_data, Event.ERROR

        if event == Event.DONE and payload == self.MAX_RETRIES_PAYLOAD:
            return synced_data, Event.MAX_RETRIES_REACHED

        if event == Event.DONE and payload == self.MAX_APPROVED_MARKETS_REACHED_PAYLOAD:
            return synced_data, Event.MAX_APPROVED_MARKETS_REACHED

        if event == Event.DONE and payload == self.SKIP_MARKET_APPROVAL_PAYLOAD:
            return synced_data, Event.SKIP_MARKET_APPROVAL

        return synced_data, event


class ApproveMarketsRound(OnlyKeeperSendsRound):
    """ApproveMarketsRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    MAX_RETRIES_PAYLOAD = "MAX_RETRIES_PAYLOAD"

    payload_class = ApproveMarketsPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    fail_event = Event.ERROR
    payload_key = (
        get_name(SynchronizedData.approved_markets_data),
        get_name(SynchronizedData.approved_markets_count),
        get_name(SynchronizedData.approved_markets_timestamp),
    )
    collection_key = get_name(SynchronizedData.participant_to_selection)

    def end_block(
        self,
    ) -> Optional[Tuple[BaseSynchronizedData, Enum]]:
        """Process the end of the block."""
        res = super().end_block()
        if res is None:
            return None

        synced_data, event = cast(Tuple[SynchronizedData, Enum], res)
        payload = cast(ApproveMarketsPayload, self.keeper_payload).content

        if event == Event.DONE and payload == self.ERROR_PAYLOAD:
            return synced_data, Event.ERROR

        if event == Event.DONE and payload == self.MAX_RETRIES_PAYLOAD:
            return synced_data, Event.MAX_RETRIES_REACHED

        return synced_data, event


class DataGatheringRound(CollectSameUntilThresholdRound):
    """DataGatheringRound"""

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


class MarketProposalRound(OnlyKeeperSendsRound):
    """MarketProposalRound"""

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
            return self.synchronized_data, Event.ERROR

        # No markets available
        if (
            cast(RetrieveApprovedMarketPayload, self.keeper_payload).content
            == self.NO_MARKETS_RETRIEVED_PAYLOAD
        ):
            return (
                self.synchronized_data.update(
                    synchronized_data_class=self.synchronized_data_class,
                    **{
                        get_name(SynchronizedData.proposed_markets_count): cast(
                            SynchronizedData, self.synchronized_data
                        ).proposed_markets_count,
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
                        ): self.most_voted_payload,
                        get_name(SynchronizedData.tx_sender): self.round_id,
                    },
                ),
                Event.DONE,
            )
        return None


class CloseMarketsRound(CollectSameUntilThresholdRound):
    """CloseMarketsRound"""

    payload_class = CloseMarketsPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = "content"

    NO_TX = "no_tx"
    ERROR_PAYLOAD = "error"

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Enum]]:
        """End block."""

        if self.threshold_reached:
            if self.most_voted_payload == self.ERROR_PAYLOAD:
                return self.synchronized_data, Event.ERROR
            if self.most_voted_payload == self.NO_TX:
                return self.synchronized_data, Event.NO_TX
            synced_data = cast(SynchronizedData, self.synchronized_data)

            # Fix to ensure properties are present on the SynchronizedData
            # before ResetAndPause round.
            synced_data = synced_data.ensure_property_is_set(
                get_name(SynchronizedData.approved_markets_count)
            )
            synced_data = synced_data.ensure_property_is_set(
                get_name(SynchronizedData.proposed_markets_count)
            )
            synced_data = synced_data.ensure_property_is_set(
                get_name(SynchronizedData.proposed_markets_data)
            )
            synced_data = synced_data.ensure_property_is_set(
                get_name(SynchronizedData.approved_markets_timestamp)
            )
            state = synced_data.update(
                synchronized_data_class=self.synchronized_data_class,
                **{
                    get_name(
                        SynchronizedData.most_voted_tx_hash
                    ): self.most_voted_payload,
                },
            )
            return state, Event.DONE
        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None


class FinishedMarketCreationManagerRound(DegenerateRound):
    """FinishedMarketCreationManagerRound"""


class FinishedWithRemoveFundingRound(DegenerateRound):
    """FinishedMarketCreationManagerRound"""


class FinishedWithDepositDaiRound(DegenerateRound):
    """FinishedMarketCreationManagerRound"""


class FinishedWithoutTxRound(DegenerateRound):
    """FinishedWithoutTxRound"""


class MarketCreationManagerAbciApp(AbciApp[Event]):
    """MarketCreationManagerAbciApp"""

    initial_round_cls: AppState = CollectRandomnessRound
    initial_states: Set[AppState] = {
        CollectRandomnessRound,
        PostTransactionRound,
        CloseMarketsRound,
    }
    transition_function: AbciAppTransitionFunction = {
        PostTransactionRound: {
            Event.DONE: CloseMarketsRound,
            Event.ERROR: PostTransactionRound,
            Event.NO_MAJORITY: PostTransactionRound,
        },
        CloseMarketsRound: {
            Event.DONE: FinishedMarketCreationManagerRound,
            Event.NO_TX: CollectRandomnessRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ERROR: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CloseMarketsRound,
        },
        CollectRandomnessRound: {
            Event.DONE: SelectKeeperRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        SelectKeeperRound: {
            Event.DONE: CollectProposedMarketsRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        CollectProposedMarketsRound: {
            Event.DONE: ApproveMarketsRound,
            Event.MAX_APPROVED_MARKETS_REACHED: DataGatheringRound,
            Event.MAX_RETRIES_REACHED: DataGatheringRound,
            Event.SKIP_MARKET_APPROVAL: DataGatheringRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: DataGatheringRound,
            Event.ERROR: DataGatheringRound,
        },
        ApproveMarketsRound: {
            Event.DONE: DataGatheringRound,
            Event.ROUND_TIMEOUT: DataGatheringRound,
            Event.MAX_RETRIES_REACHED: DataGatheringRound,
            Event.ERROR: DataGatheringRound,
        },
        DataGatheringRound: {
            Event.DONE: MarketProposalRound,
            Event.MAX_PROPOSED_MARKETS_REACHED: RetrieveApprovedMarketRound,
            Event.MAX_RETRIES_REACHED: RetrieveApprovedMarketRound,
            Event.SKIP_MARKET_PROPOSAL: RetrieveApprovedMarketRound,
            Event.ERROR: CollectRandomnessRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        MarketProposalRound: {
            Event.DONE: RetrieveApprovedMarketRound,
            Event.NO_MAJORITY: RetrieveApprovedMarketRound,
            Event.MARKET_PROPOSAL_ROUND_TIMEOUT: RetrieveApprovedMarketRound,
            Event.DID_NOT_SEND: RetrieveApprovedMarketRound,
            Event.ERROR: RetrieveApprovedMarketRound,
        },
        RetrieveApprovedMarketRound: {
            Event.DONE: PrepareTransactionRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
            Event.DID_NOT_SEND: CollectRandomnessRound,
            Event.ERROR: CollectRandomnessRound,
            Event.NO_MARKETS_RETRIEVED: DepositDaiRound,
        },
        PrepareTransactionRound: {
            Event.DONE: FinishedMarketCreationManagerRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        DepositDaiRound: {
            Event.DONE: FinishedWithDepositDaiRound,
            Event.NO_TX: SyncMarketsRound,
            Event.NO_MAJORITY: DepositDaiRound,
            Event.ERROR: DepositDaiRound,
        },
        SyncMarketsRound: {
            Event.DONE: RemoveFundingRound,
            Event.NO_MAJORITY: CollectRandomnessRound,
            Event.ERROR: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        RemoveFundingRound: {
            Event.DONE: FinishedWithRemoveFundingRound,
            Event.NO_TX: FinishedWithoutTxRound,
            Event.NO_MAJORITY: RemoveFundingRound,
            Event.ERROR: CollectRandomnessRound,
            Event.ROUND_TIMEOUT: CollectRandomnessRound,
        },
        FinishedMarketCreationManagerRound: {},
        FinishedWithRemoveFundingRound: {},
        FinishedWithDepositDaiRound: {},
        FinishedWithoutTxRound: {},
    }
    final_states: Set[AppState] = {
        FinishedMarketCreationManagerRound,
        FinishedWithRemoveFundingRound,
        FinishedWithDepositDaiRound,
        FinishedWithoutTxRound,
    }
    event_to_timeout: EventToTimeout = {
        # MARKET_PROPOSAL_ROUND_TIMEOUT must be computed on the chained app.
    }
    cross_period_persisted_keys: Set[str] = {
        get_name(SynchronizedData.proposed_markets_count),
        get_name(SynchronizedData.proposed_markets_data),
        get_name(SynchronizedData.approved_markets_count),
        get_name(SynchronizedData.approved_markets_timestamp),
    }  # type: ignore
    db_pre_conditions: Dict[AppState, Set[str]] = {
        CloseMarketsRound: set(),
        CollectRandomnessRound: set(),
        PostTransactionRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedWithDepositDaiRound: {
            get_name(SynchronizedData.most_voted_tx_hash),
        },
        FinishedMarketCreationManagerRound: {
            get_name(SynchronizedData.most_voted_tx_hash),
        },
        FinishedWithRemoveFundingRound: {
            get_name(SynchronizedData.most_voted_tx_hash),
        },
        FinishedWithoutTxRound: set(),
    }

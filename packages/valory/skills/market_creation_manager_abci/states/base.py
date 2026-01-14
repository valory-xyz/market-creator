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

"""This module contains the base functionality for the rounds of the MarketCreationManagerAbciApp."""

import json
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, cast

from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
    CollectionRound,
    DeserializedCollection,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    MultisigTxPayload,
)
from packages.valory.skills.mech_interact_abci.states.base import (
    MechInteractionResponse,
    MechMetadata,
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
    MECH_REQUEST_DONE = "mech_request_done"
    NO_MARKETS_RETRIEVED = "no_markets_retrieved"
    REDEEM_BOND_DONE = "redeem_bond_done"
    DEPOSIT_DAI_DONE = "deposit_dai_done"
    ANSWER_QUESTION_DONE = "answer_question_done"
    REMOVE_FUNDING_DONE = "remove_funding_done"
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

    def _get_deserialized(self, key: str) -> DeserializedCollection:
        """Strictly get a collection and return it deserialized."""
        serialized = self.db.get_strict(key)
        return CollectionRound.deserialize_collection(serialized)

    @property
    def gathered_data(self) -> str:
        """Get the llm_values."""
        return cast(str, self.db.get_strict("gathered_data"))

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
    def mech_requests(self) -> List[MechMetadata]:
        """Get the mech requests."""
        serialized = self.db.get("mech_requests", "[]")
        if serialized is None:
            serialized = "[]"
        requests = json.loads(serialized)
        return [MechMetadata(**metadata_item) for metadata_item in requests]

    @property
    def mech_responses(self) -> List[MechInteractionResponse]:
        """Get the mech responses."""
        serialized = self.db.get("mech_responses", "[]")
        if serialized is None:
            serialized = "[]"
        responses = json.loads(serialized)
        return [MechInteractionResponse(**response_item) for response_item in responses]

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
    def tx_submitter(self) -> str:
        """Get the round that send the transaction through transaction settlement."""
        return cast(str, self.db.get_strict("tx_submitter"))

    @property
    def participant_to_tx_prep(self) -> DeserializedCollection:
        """Get the participant_to_tx_prep."""
        return self._get_deserialized("participant_to_tx_prep")


class TxPreparationRound(CollectSameUntilThresholdRound):
    """A round for preparing a transaction."""

    payload_class = MultisigTxPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    none_event = Event.NONE
    no_majority_event = Event.NO_MAJORITY
    selection_key: Tuple[str, ...] = (
        get_name(SynchronizedData.tx_submitter),
        get_name(SynchronizedData.most_voted_tx_hash),
    )
    collection_key = get_name(SynchronizedData.participant_to_tx_prep)

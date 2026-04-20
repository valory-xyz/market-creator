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
from typing import Optional, Tuple, cast

from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
    CollectionRound,
    DeserializedCollection,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    MultisigTxPayload,
)
from packages.valory.skills.transaction_settlement_abci.rounds import (
    SynchronizedData as TxSynchronizedData,
)


class Event(Enum):
    """MarketCreationManagerAbciApp Events"""

    NO_MAJORITY = "no_majority"
    DONE = "done"
    NONE = "none"
    ROUND_TIMEOUT = "round_timeout"
    ERROR = "api_error"
    MAX_APPROVED_MARKETS_REACHED = "max_approved_markets_reached"
    MAX_RETRIES_REACHED = "max_retries_reached"
    NO_MARKETS_RETRIEVED = "no_markets_retrieved"
    DEPOSIT_DAI_DONE = "deposit_dai_done"
    SKIP_MARKET_APPROVAL = "skip_market_approval"
    FUNDS_FORWARDER_TX_DONE = "funds_forwarder_tx_done"
    FPMM_REMOVE_LIQUIDITY_TX_DONE = "fpmm_remove_liquidity_tx_done"
    CT_REDEEM_TOKENS_TX_DONE = "ct_redeem_tokens_tx_done"
    REALITIO_WITHDRAW_BONDS_TX_DONE = "realitio_withdraw_bonds_tx_done"


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

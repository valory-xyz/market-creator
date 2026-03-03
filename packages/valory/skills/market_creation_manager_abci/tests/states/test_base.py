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

"""Tests for the base module of the MarketCreationManagerAbciApp."""

import json
from unittest.mock import MagicMock, patch

import pytest

from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    MultisigTxPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    DEFAULT_COLLECTED_PROPOSED_MARKETS_DATA,
    DEFAULT_PROPOSED_MARKETS_DATA,
    Event,
    SynchronizedData,
    TxPreparationRound,
)


class TestEvent:
    """Test Event enum."""

    def test_event_values(self) -> None:
        """Test that all expected Event values exist."""
        expected = {
            "NO_MAJORITY": "no_majority",
            "DONE": "done",
            "NONE": "none",
            "NO_TX": "no_tx",
            "ROUND_TIMEOUT": "round_timeout",
            "MARKET_PROPOSAL_ROUND_TIMEOUT": "market_proposal_round_timeout",
            "ERROR": "api_error",
            "DID_NOT_SEND": "did_not_send",
            "MAX_PROPOSED_MARKETS_REACHED": "max_markets_reached",
            "MAX_APPROVED_MARKETS_REACHED": "max_approved_markets_reached",
            "MAX_RETRIES_REACHED": "max_retries_reached",
            "MECH_REQUEST_DONE": "mech_request_done",
            "NO_MARKETS_RETRIEVED": "no_markets_retrieved",
            "REDEEM_BOND_DONE": "redeem_bond_done",
            "DEPOSIT_DAI_DONE": "deposit_dai_done",
            "ANSWER_QUESTION_DONE": "answer_question_done",
            "REMOVE_FUNDING_DONE": "remove_funding_done",
            "SKIP_MARKET_PROPOSAL": "skip_market_proposal",
            "SKIP_MARKET_APPROVAL": "skip_market_approval",
        }
        for name, value in expected.items():
            assert Event[name].value == value

    def test_event_count(self) -> None:
        """Test that Event has the expected number of members."""
        assert len(Event) == 19


class TestDefaults:
    """Test default constants."""

    def test_default_proposed_markets_data(self) -> None:
        """Test DEFAULT_PROPOSED_MARKETS_DATA."""
        assert DEFAULT_PROPOSED_MARKETS_DATA == {
            "proposed_markets": [],
            "timestamp": 0,
        }

    def test_default_collected_proposed_markets_data(self) -> None:
        """Test DEFAULT_COLLECTED_PROPOSED_MARKETS_DATA."""
        data = json.loads(DEFAULT_COLLECTED_PROPOSED_MARKETS_DATA)
        assert data == {
            "proposed_markets": [],
            "fixedProductMarketMakers": [],
            "num_markets_to_approve": 0,
            "timestamp": 0,
        }


class TestSynchronizedData:
    """Test SynchronizedData properties."""

    @pytest.fixture
    def mocked_db(self) -> MagicMock:
        """Create a mocked database."""
        return MagicMock()

    @pytest.fixture
    def sync_data(self, mocked_db: MagicMock) -> SynchronizedData:
        """Create a SynchronizedData instance."""
        return SynchronizedData(db=mocked_db)

    def test_gathered_data(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test gathered_data property."""
        mocked_db.get_strict.return_value = "some_data"
        assert sync_data.gathered_data == "some_data"
        mocked_db.get_strict.assert_called_once_with("gathered_data")

    def test_proposed_markets_count(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test proposed_markets_count property."""
        mocked_db.get.return_value = 5
        assert sync_data.proposed_markets_count == 5
        mocked_db.get.assert_called_once_with("proposed_markets_count", 0)

    def test_proposed_markets_count_default(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test proposed_markets_count default."""
        mocked_db.get.return_value = 0
        assert sync_data.proposed_markets_count == 0

    def test_approved_markets_count(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test approved_markets_count property."""
        mocked_db.get.return_value = 3
        assert sync_data.approved_markets_count == 3
        mocked_db.get.assert_called_once_with("approved_markets_count", 0)

    def test_approved_markets_timestamp(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test approved_markets_timestamp property."""
        mocked_db.get.return_value = 1700000000
        assert sync_data.approved_markets_timestamp == 1700000000
        mocked_db.get.assert_called_once_with("approved_markets_timestamp", 0)

    def test_proposed_markets_data(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test proposed_markets_data property."""
        mock_data = {"proposed_markets": [{"q": "test?"}], "timestamp": 123}
        mocked_db.get.return_value = mock_data
        assert sync_data.proposed_markets_data == mock_data

    def test_proposed_markets_data_default(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test proposed_markets_data returns default."""
        mocked_db.get.return_value = DEFAULT_PROPOSED_MARKETS_DATA
        assert sync_data.proposed_markets_data == DEFAULT_PROPOSED_MARKETS_DATA

    def test_collected_proposed_markets_data(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test collected_proposed_markets_data property."""
        mock_val = '{"proposed_markets": [{"q": "test?"}]}'
        mocked_db.get.return_value = mock_val
        assert sync_data.collected_proposed_markets_data == mock_val

    def test_collected_proposed_markets_data_default(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test collected_proposed_markets_data returns default."""
        mocked_db.get.return_value = DEFAULT_COLLECTED_PROPOSED_MARKETS_DATA
        assert (
            sync_data.collected_proposed_markets_data
            == DEFAULT_COLLECTED_PROPOSED_MARKETS_DATA
        )

    def test_mech_requests_empty(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test mech_requests with empty list."""
        mocked_db.get.return_value = "[]"
        assert sync_data.mech_requests == []

    def test_mech_requests_none_fallback(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test mech_requests with None serialized value."""
        mocked_db.get.return_value = None
        assert sync_data.mech_requests == []

    def test_mech_responses_empty(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test mech_responses with empty list."""
        mocked_db.get.return_value = "[]"
        assert sync_data.mech_responses == []

    def test_mech_responses_none_fallback(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test mech_responses with None serialized value."""
        mocked_db.get.return_value = None
        assert sync_data.mech_responses == []

    def test_approved_markets_data(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test approved_markets_data property."""
        mock_data = {"markets": ["m1"]}
        mocked_db.get_strict.return_value = mock_data
        assert sync_data.approved_markets_data == mock_data
        mocked_db.get_strict.assert_called_once_with("approved_markets_data")

    def test_approved_question_data(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test approved_question_data property."""
        mock_data = {"question": "test?"}
        mocked_db.get_strict.return_value = mock_data
        assert sync_data.approved_question_data == mock_data
        mocked_db.get_strict.assert_called_once_with("approved_question_data")

    def test_is_approved_question_data_set_true(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test is_approved_question_data_set when data is set."""
        mocked_db.get.return_value = {"question": "test?"}
        assert sync_data.is_approved_question_data_set is True

    def test_is_approved_question_data_set_false(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test is_approved_question_data_set when data is not set."""
        mocked_db.get.return_value = None
        assert sync_data.is_approved_question_data_set is False

    def test_most_voted_tx_hash(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test most_voted_tx_hash property."""
        mocked_db.get_strict.return_value = "0xabc123"
        assert sync_data.most_voted_tx_hash == "0xabc123"
        mocked_db.get_strict.assert_called_once_with("most_voted_tx_hash")

    def test_most_voted_keeper_address(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test most_voted_keeper_address property."""
        mocked_db.get_strict.return_value = "0xkeeper"
        assert sync_data.most_voted_keeper_address == "0xkeeper"
        mocked_db.get_strict.assert_called_once_with("most_voted_keeper_address")

    def test_markets_to_remove_liquidity(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test markets_to_remove_liquidity property."""
        markets = [{"address": "0x1"}, {"address": "0x2"}]
        mocked_db.get.return_value = markets
        assert sync_data.markets_to_remove_liquidity == markets

    def test_markets_to_remove_liquidity_default(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test markets_to_remove_liquidity default."""
        mocked_db.get.return_value = []
        assert sync_data.markets_to_remove_liquidity == []

    def test_market_from_block(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test market_from_block property."""
        mocked_db.get.return_value = 12345
        assert sync_data.market_from_block == 12345

    def test_market_from_block_default(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test market_from_block default."""
        mocked_db.get.return_value = 0
        assert sync_data.market_from_block == 0

    def test_settled_tx_hash(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test settled_tx_hash property."""
        mocked_db.get.return_value = "0xfinal"
        assert sync_data.settled_tx_hash == "0xfinal"

    def test_settled_tx_hash_none(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test settled_tx_hash when None."""
        mocked_db.get.return_value = None
        assert sync_data.settled_tx_hash is None

    def test_tx_submitter(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test tx_submitter property."""
        mocked_db.get_strict.return_value = "some_round_id"
        assert sync_data.tx_submitter == "some_round_id"
        mocked_db.get_strict.assert_called_once_with("tx_submitter")

    @patch(
        "packages.valory.skills.market_creation_manager_abci.states.base.CollectionRound.deserialize_collection"
    )
    def test_participant_to_tx_prep(
        self,
        mock_deserialize: MagicMock,
        sync_data: SynchronizedData,
        mocked_db: MagicMock,
    ) -> None:
        """Test participant_to_tx_prep property with deserialization."""
        serialized = '{"agent_0": "payload_0"}'
        expected = {"agent_0": "payload_0"}
        mocked_db.get_strict.return_value = serialized
        mock_deserialize.return_value = expected
        result = sync_data.participant_to_tx_prep
        mocked_db.get_strict.assert_called_once_with("participant_to_tx_prep")
        mock_deserialize.assert_called_once_with(serialized)
        assert result == expected


class TestTxPreparationRound:
    """Test TxPreparationRound class attributes."""

    def test_payload_class(self) -> None:
        """Test payload_class."""
        assert TxPreparationRound.payload_class == MultisigTxPayload

    def test_synchronized_data_class(self) -> None:
        """Test synchronized_data_class."""
        assert TxPreparationRound.synchronized_data_class == SynchronizedData

    def test_done_event(self) -> None:
        """Test done_event."""
        assert TxPreparationRound.done_event == Event.DONE

    def test_none_event(self) -> None:
        """Test none_event."""
        assert TxPreparationRound.none_event == Event.NONE

    def test_no_majority_event(self) -> None:
        """Test no_majority_event."""
        assert TxPreparationRound.no_majority_event == Event.NO_MAJORITY

    def test_selection_key(self) -> None:
        """Test selection_key."""
        assert TxPreparationRound.selection_key == (
            get_name(SynchronizedData.tx_submitter),
            get_name(SynchronizedData.most_voted_tx_hash),
        )

    def test_collection_key(self) -> None:
        """Test collection_key."""
        assert TxPreparationRound.collection_key == get_name(
            SynchronizedData.participant_to_tx_prep
        )

    def test_inherits_collect_same(self) -> None:
        """Test that it inherits from CollectSameUntilThresholdRound."""
        assert issubclass(TxPreparationRound, CollectSameUntilThresholdRound)

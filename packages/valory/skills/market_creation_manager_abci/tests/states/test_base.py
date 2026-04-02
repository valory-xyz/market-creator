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

from unittest.mock import MagicMock, patch

import pytest

from packages.valory.skills.market_creation_manager_abci.states.base import (
    SynchronizedData,
)


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

    def test_proposed_markets_count(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test proposed_markets_count property."""
        mocked_db.get.return_value = 5
        assert sync_data.proposed_markets_count == 5

    def test_approved_markets_count(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test approved_markets_count property."""
        mocked_db.get.return_value = 3
        assert sync_data.approved_markets_count == 3

    def test_approved_markets_timestamp(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test approved_markets_timestamp property."""
        mocked_db.get.return_value = 1700000000
        assert sync_data.approved_markets_timestamp == 1700000000

    def test_proposed_markets_data(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test proposed_markets_data property."""
        mock_data = {"proposed_markets": [{"q": "test?"}], "timestamp": 123}
        mocked_db.get.return_value = mock_data
        assert sync_data.proposed_markets_data == mock_data

    def test_collected_proposed_markets_data(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test collected_proposed_markets_data property."""
        mock_val = '{"proposed_markets": [{"q": "test?"}]}'
        mocked_db.get.return_value = mock_val
        assert sync_data.collected_proposed_markets_data == mock_val

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

    def test_approved_question_data(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test approved_question_data property."""
        mock_data = {"question": "test?"}
        mocked_db.get_strict.return_value = mock_data
        assert sync_data.approved_question_data == mock_data

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

    def test_most_voted_keeper_address(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test most_voted_keeper_address property."""
        mocked_db.get_strict.return_value = "0xkeeper"
        assert sync_data.most_voted_keeper_address == "0xkeeper"

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
        mock_deserialize.assert_called_once_with(serialized)
        assert result == expected

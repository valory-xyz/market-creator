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

"""Tests for the GetPendingQuestionsRound."""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    GetPendingQuestionsPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)
from packages.valory.skills.market_creation_manager_abci.states.get_pending_questions import (
    GetPendingQuestionsRound,
)


class TestGetPendingQuestionsRound:
    """Tests for GetPendingQuestionsRound attributes."""

    def test_inherits_collect_same(self) -> None:
        """Test class hierarchy."""
        assert issubclass(GetPendingQuestionsRound, CollectSameUntilThresholdRound)

    def test_payload_class(self) -> None:
        """Test payload class."""
        assert GetPendingQuestionsRound.payload_class == GetPendingQuestionsPayload

    def test_synchronized_data_class(self) -> None:
        """Test synchronized data class."""
        assert GetPendingQuestionsRound.synchronized_data_class == SynchronizedData

    def test_done_event(self) -> None:
        """Test done event."""
        assert GetPendingQuestionsRound.done_event == Event.DONE

    def test_no_majority_event(self) -> None:
        """Test no majority event."""
        assert GetPendingQuestionsRound.no_majority_event == Event.NO_MAJORITY

    def test_none_event(self) -> None:
        """Test none event."""
        assert GetPendingQuestionsRound.none_event == Event.NONE

    def test_collection_key(self) -> None:
        """Test collection key."""
        assert GetPendingQuestionsRound.collection_key == get_name(
            SynchronizedData.participant_to_selection
        )

    def test_selection_key(self) -> None:
        """Test selection key."""
        assert GetPendingQuestionsRound.selection_key == get_name(
            SynchronizedData.mech_requests
        )

    def test_constants(self) -> None:
        """Test constants."""
        assert GetPendingQuestionsRound.ERROR_PAYLOAD == "ERROR_PAYLOAD"
        assert GetPendingQuestionsRound.NO_TX_PAYLOAD == "NO_TX_PAYLOAD"


class TestGetPendingQuestionsRoundEndBlock:
    """Tests for GetPendingQuestionsRound.end_block."""

    @pytest.fixture
    def setup_round(self) -> GetPendingQuestionsRound:
        """Set up round."""
        context = MagicMock()
        synced_data = MagicMock(spec=SynchronizedData)
        return GetPendingQuestionsRound(synchronized_data=synced_data, context=context)

    def test_end_block_returns_none_when_parent_returns_none(
        self, setup_round: GetPendingQuestionsRound
    ) -> None:
        """Test returns None when parent returns None."""
        with patch.object(
            CollectSameUntilThresholdRound, "end_block", return_value=None
        ):
            assert setup_round.end_block() is None

    def test_end_block_error_payload(
        self, setup_round: GetPendingQuestionsRound
    ) -> None:
        """Test error payload returns ERROR event."""
        synced_data = MagicMock(spec=SynchronizedData)
        with patch.object(
            CollectSameUntilThresholdRound,
            "end_block",
            return_value=(synced_data, Event.DONE),
        ):
            with patch.object(
                type(setup_round),
                "most_voted_payload",
                new_callable=PropertyMock,
                return_value="ERROR_PAYLOAD",
            ):
                result = setup_round.end_block()
                assert result is not None
                _, event = result
                assert event == Event.ERROR

    def test_end_block_no_tx_payload(
        self, setup_round: GetPendingQuestionsRound
    ) -> None:
        """Test NO_TX_PAYLOAD returns NO_TX event."""
        synced_data = MagicMock(spec=SynchronizedData)
        with patch.object(
            CollectSameUntilThresholdRound,
            "end_block",
            return_value=(synced_data, Event.DONE),
        ):
            with patch.object(
                type(setup_round),
                "most_voted_payload",
                new_callable=PropertyMock,
                return_value="NO_TX_PAYLOAD",
            ):
                result = setup_round.end_block()
                assert result is not None
                _, event = result
                assert event == Event.NO_TX

    def test_end_block_happy_path_updates_tx_submitter(
        self, setup_round: GetPendingQuestionsRound
    ) -> None:
        """Test happy path updates tx_submitter to MechRequestRound id."""
        synced_data = MagicMock(spec=SynchronizedData)
        updated_data = MagicMock(spec=SynchronizedData)
        synced_data.update.return_value = updated_data

        with patch.object(
            CollectSameUntilThresholdRound,
            "end_block",
            return_value=(synced_data, Event.DONE),
        ):
            with patch.object(
                type(setup_round),
                "most_voted_payload",
                new_callable=PropertyMock,
                return_value='[{"request_id": "1"}]',
            ):
                result = setup_round.end_block()
                assert result is not None
                result_data, event = result
                assert event == Event.DONE
                # The synced_data.update should have been called
                synced_data.update.assert_called_once()

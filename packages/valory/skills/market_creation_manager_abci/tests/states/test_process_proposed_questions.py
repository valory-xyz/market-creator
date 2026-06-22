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

"""Tests for the ProcessProposedQuestionsRound."""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    ProcessProposedQuestionsPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)
from packages.valory.skills.market_creation_manager_abci.states.process_proposed_questions import (
    ProcessProposedQuestionsRound,
)


class TestProcessProposedQuestionsRoundAttributes:
    """Tests for ProcessProposedQuestionsRound class attributes."""

    def test_inherits_collect_same_until_threshold(self) -> None:
        """Test class hierarchy."""
        assert issubclass(ProcessProposedQuestionsRound, CollectSameUntilThresholdRound)

    def test_payload_class(self) -> None:
        """Test payload class."""
        assert (
            ProcessProposedQuestionsRound.payload_class
            == ProcessProposedQuestionsPayload
        )

    def test_synchronized_data_class(self) -> None:
        """Test synchronized data class."""
        assert ProcessProposedQuestionsRound.synchronized_data_class == SynchronizedData

    def test_done_event(self) -> None:
        """Test done event."""
        assert ProcessProposedQuestionsRound.done_event == Event.DONE

    def test_none_event(self) -> None:
        """Test none event."""
        assert ProcessProposedQuestionsRound.none_event == Event.NONE

    def test_no_majority_event(self) -> None:
        """Test no_majority event."""
        assert ProcessProposedQuestionsRound.no_majority_event == Event.NO_MAJORITY

    def test_selection_key(self) -> None:
        """Test selection_key has 3 fields."""
        key = ProcessProposedQuestionsRound.selection_key
        assert isinstance(key, tuple)
        assert len(key) == 3
        assert "content" in key
        assert get_name(SynchronizedData.approved_markets_count) in key
        assert get_name(SynchronizedData.approved_markets_timestamp) in key

    def test_collection_key(self) -> None:
        """Test collection_key."""
        assert ProcessProposedQuestionsRound.collection_key == get_name(
            SynchronizedData.participant_to_votes
        )

    def test_error_payload_constant(self) -> None:
        """Test ERROR_PAYLOAD constant."""
        assert ProcessProposedQuestionsRound.ERROR_PAYLOAD == "ERROR_PAYLOAD"


class TestProcessProposedQuestionsRoundEndBlock:
    """Tests for ProcessProposedQuestionsRound.end_block (inherited logic)."""

    @pytest.fixture
    def setup_round(self) -> ProcessProposedQuestionsRound:
        """Set up the round instance."""
        context = MagicMock()
        synced_data = MagicMock(spec=SynchronizedData)
        synced_data.nb_participants = 4
        return ProcessProposedQuestionsRound(
            synchronized_data=synced_data, context=context
        )

    def test_end_block_returns_none_while_waiting(
        self, setup_round: ProcessProposedQuestionsRound
    ) -> None:
        """Test returns None when threshold not reached and majority still possible."""
        with patch.object(
            type(setup_round),
            "threshold_reached",
            new_callable=PropertyMock,
            return_value=False,
        ):
            with patch.object(
                ProcessProposedQuestionsRound,
                "is_majority_possible",
                return_value=True,
            ):
                result = setup_round.end_block()
                assert result is None

    def test_end_block_no_majority(
        self, setup_round: ProcessProposedQuestionsRound
    ) -> None:
        """Test NO_MAJORITY when majority impossible."""
        with patch.object(
            type(setup_round),
            "threshold_reached",
            new_callable=PropertyMock,
            return_value=False,
        ):
            with patch.object(
                ProcessProposedQuestionsRound,
                "is_majority_possible",
                return_value=False,
            ):
                result = setup_round.end_block()
                assert result is not None
                _, event = result
                assert event == Event.NO_MAJORITY

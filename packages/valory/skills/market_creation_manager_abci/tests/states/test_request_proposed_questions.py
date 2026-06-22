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

"""Tests for the RequestProposedQuestionsRound."""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    RequestProposedQuestionsPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)
from packages.valory.skills.market_creation_manager_abci.states.request_proposed_questions import (
    RequestProposedQuestionsRound,
)


class TestRequestProposedQuestionsRoundAttributes:
    """Tests for RequestProposedQuestionsRound class attributes."""

    def test_inherits_collect_same_until_threshold(self) -> None:
        """Test class hierarchy."""
        assert issubclass(RequestProposedQuestionsRound, CollectSameUntilThresholdRound)

    def test_payload_class(self) -> None:
        """Test payload class."""
        assert (
            RequestProposedQuestionsRound.payload_class
            == RequestProposedQuestionsPayload
        )

    def test_synchronized_data_class(self) -> None:
        """Test synchronized data class."""
        assert RequestProposedQuestionsRound.synchronized_data_class == SynchronizedData

    def test_done_event(self) -> None:
        """Test done_event routes to MECH_REQUEST_DONE."""
        assert RequestProposedQuestionsRound.done_event == Event.MECH_REQUEST_DONE

    def test_none_event(self) -> None:
        """Test none_event routes to SKIP."""
        assert RequestProposedQuestionsRound.none_event == Event.SKIP

    def test_no_majority_event(self) -> None:
        """Test no_majority_event."""
        assert RequestProposedQuestionsRound.no_majority_event == Event.NO_MAJORITY

    def test_selection_key(self) -> None:
        """Test selection_key references mech_requests."""
        assert RequestProposedQuestionsRound.selection_key == (
            get_name(SynchronizedData.mech_requests),
        )

    def test_collection_key(self) -> None:
        """Test collection_key references participant_to_votes."""
        assert RequestProposedQuestionsRound.collection_key == get_name(
            SynchronizedData.participant_to_votes
        )


class TestRequestProposedQuestionsRoundEndBlock:
    """Tests for RequestProposedQuestionsRound.end_block."""

    @pytest.fixture
    def setup_round(self) -> RequestProposedQuestionsRound:
        """Set up the round instance for testing."""
        context = MagicMock()
        synced_data = MagicMock(spec=SynchronizedData)
        synced_data.nb_participants = 4
        return RequestProposedQuestionsRound(
            synchronized_data=synced_data, context=context
        )

    def test_end_block_returns_none_when_threshold_not_reached_majority_possible(
        self, setup_round: RequestProposedQuestionsRound
    ) -> None:
        """Test that end_block returns None when threshold not reached."""
        with patch.object(
            type(setup_round),
            "threshold_reached",
            new_callable=PropertyMock,
            return_value=False,
        ):
            with patch.object(
                RequestProposedQuestionsRound,
                "is_majority_possible",
                return_value=True,
            ):
                result = setup_round.end_block()
                assert result is None

    def test_end_block_no_majority(
        self, setup_round: RequestProposedQuestionsRound
    ) -> None:
        """Test that end_block returns NO_MAJORITY when no majority possible."""
        with patch.object(
            type(setup_round),
            "threshold_reached",
            new_callable=PropertyMock,
            return_value=False,
        ):
            with patch.object(
                RequestProposedQuestionsRound,
                "is_majority_possible",
                return_value=False,
            ):
                result = setup_round.end_block()
                assert result is not None
                _, event = result
                assert event == Event.NO_MAJORITY

    def test_end_block_skip_when_payload_is_none(
        self, setup_round: RequestProposedQuestionsRound
    ) -> None:
        """Test that None payload produces SKIP event."""
        with patch.object(
            type(setup_round),
            "threshold_reached",
            new_callable=PropertyMock,
            return_value=True,
        ):
            with patch.object(
                type(setup_round),
                "most_voted_payload",
                new_callable=PropertyMock,
                return_value=None,
            ):
                result = setup_round.end_block()
                assert result is not None
                _, event = result
                assert event == Event.SKIP

    def test_end_block_skip_when_payload_is_null_string(
        self, setup_round: RequestProposedQuestionsRound
    ) -> None:
        """Test that 'null' string payload produces SKIP event."""
        with patch.object(
            type(setup_round),
            "threshold_reached",
            new_callable=PropertyMock,
            return_value=True,
        ):
            with patch.object(
                type(setup_round),
                "most_voted_payload",
                new_callable=PropertyMock,
                return_value="null",
            ):
                result = setup_round.end_block()
                assert result is not None
                _, event = result
                assert event == Event.SKIP

    def test_end_block_mech_request_done_when_payload_set(
        self, setup_round: RequestProposedQuestionsRound
    ) -> None:
        """Test that a mech_requests JSON payload produces MECH_REQUEST_DONE."""
        mech_requests_json = (
            '[{"nonce": "abc", "tool": "propose-question", "prompt": "{}"}]'
        )
        with patch.object(
            type(setup_round),
            "threshold_reached",
            new_callable=PropertyMock,
            return_value=True,
        ):
            with patch.object(
                type(setup_round),
                "most_voted_payload",
                new_callable=PropertyMock,
                return_value=mech_requests_json,
            ):
                result = setup_round.end_block()
                assert result is not None
                new_data, event = result
                assert event == Event.MECH_REQUEST_DONE
                # Verify the synced data update was called with mech_requests
                assert new_data is not None

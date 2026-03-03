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

"""Tests for the CollectProposedMarketsRound."""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    CollectProposedMarketsPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)
from packages.valory.skills.market_creation_manager_abci.states.collect_proposed_markets import (
    CollectProposedMarketsRound,
)


class TestCollectProposedMarketsRound:
    """Tests for CollectProposedMarketsRound attributes."""

    def test_inherits_collect_same(self) -> None:
        """Test class hierarchy."""
        assert issubclass(CollectProposedMarketsRound, CollectSameUntilThresholdRound)

    def test_payload_class(self) -> None:
        """Test payload class."""
        assert CollectProposedMarketsRound.payload_class == CollectProposedMarketsPayload

    def test_synchronized_data_class(self) -> None:
        """Test synchronized data class."""
        assert CollectProposedMarketsRound.synchronized_data_class == SynchronizedData

    def test_done_event(self) -> None:
        """Test done event."""
        assert CollectProposedMarketsRound.done_event == Event.DONE

    def test_no_majority_event(self) -> None:
        """Test no majority event."""
        assert CollectProposedMarketsRound.no_majority_event == Event.NO_MAJORITY

    def test_none_event(self) -> None:
        """Test none event."""
        assert CollectProposedMarketsRound.none_event == Event.NONE

    def test_collection_key(self) -> None:
        """Test collection key."""
        assert CollectProposedMarketsRound.collection_key == get_name(
            SynchronizedData.participant_to_selection
        )

    def test_selection_key(self) -> None:
        """Test selection key."""
        assert CollectProposedMarketsRound.selection_key == get_name(
            SynchronizedData.collected_proposed_markets_data
        )

    def test_constants(self) -> None:
        """Test constants."""
        assert CollectProposedMarketsRound.ERROR_PAYLOAD == "ERROR_PAYLOAD"
        assert CollectProposedMarketsRound.MAX_RETRIES_PAYLOAD == "MAX_RETRIES_PAYLOAD"
        assert (
            CollectProposedMarketsRound.MAX_APPROVED_MARKETS_REACHED_PAYLOAD
            == "MAX_APPROVED_MARKETS_REACHED_PAYLOAD"
        )
        assert (
            CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD
            == "SKIP_MARKET_APPROVAL_PAYLOAD"
        )


class TestCollectProposedMarketsRoundEndBlock:
    """Tests for CollectProposedMarketsRound.end_block."""

    @pytest.fixture
    def setup_round(self) -> CollectProposedMarketsRound:
        """Set up round for testing."""
        context = MagicMock()
        synced_data = MagicMock(spec=SynchronizedData)
        return CollectProposedMarketsRound(
            synchronized_data=synced_data, context=context
        )

    def test_end_block_returns_none_when_parent_returns_none(
        self, setup_round: CollectProposedMarketsRound
    ) -> None:
        """Test returns None when parent returns None."""
        with patch.object(
            CollectSameUntilThresholdRound, "end_block", return_value=None
        ):
            assert setup_round.end_block() is None

    @pytest.mark.parametrize(
        "payload,expected_event",
        [
            ("ERROR_PAYLOAD", Event.ERROR),
            ("MAX_RETRIES_PAYLOAD", Event.MAX_RETRIES_REACHED),
            ("MAX_APPROVED_MARKETS_REACHED_PAYLOAD", Event.MAX_APPROVED_MARKETS_REACHED),
            ("SKIP_MARKET_APPROVAL_PAYLOAD", Event.SKIP_MARKET_APPROVAL),
        ],
    )
    def test_end_block_special_payloads(
        self,
        setup_round: CollectProposedMarketsRound,
        payload: str,
        expected_event: Event,
    ) -> None:
        """Test that special payloads map to correct events."""
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
                return_value=payload,
            ):
                result = setup_round.end_block()
                assert result is not None
                _, event = result
                assert event == expected_event

    def test_end_block_normal_done(
        self, setup_round: CollectProposedMarketsRound
    ) -> None:
        """Test normal DONE passes through."""
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
                return_value='{"some": "data"}',
            ):
                result = setup_round.end_block()
                assert result is not None
                _, event = result
                assert event == Event.DONE

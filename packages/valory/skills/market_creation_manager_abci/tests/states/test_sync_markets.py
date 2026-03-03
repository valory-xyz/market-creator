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

"""Tests for the SyncMarketsRound."""

import json
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    SyncMarketsPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)
from packages.valory.skills.market_creation_manager_abci.states.sync_markets import (
    SyncMarketsRound,
)


class TestSyncMarketsRound:
    """Tests for SyncMarketsRound attributes."""

    def test_inherits_collect_same(self) -> None:
        """Test class hierarchy."""
        assert issubclass(SyncMarketsRound, CollectSameUntilThresholdRound)

    def test_payload_class(self) -> None:
        """Test payload class."""
        assert SyncMarketsRound.payload_class == SyncMarketsPayload

    def test_synchronized_data_class(self) -> None:
        """Test synchronized data class."""
        assert SyncMarketsRound.synchronized_data_class == SynchronizedData

    def test_done_event(self) -> None:
        """Test done event."""
        assert SyncMarketsRound.done_event == Event.DONE

    def test_no_majority_event(self) -> None:
        """Test no majority event."""
        assert SyncMarketsRound.no_majority_event == Event.NO_MAJORITY

    def test_none_event(self) -> None:
        """Test none event."""
        assert SyncMarketsRound.none_event == Event.NONE

    def test_constants(self) -> None:
        """Test constants."""
        assert SyncMarketsRound.ERROR_PAYLOAD == "ERROR_PAYLOAD"
        assert SyncMarketsRound.NO_UPDATE_PAYLOAD == "NO_UPDATE"


class TestSyncMarketsRoundEndBlock:
    """Tests for SyncMarketsRound.end_block."""

    @pytest.fixture
    def setup_round(self) -> SyncMarketsRound:
        """Set up round."""
        context = MagicMock()
        synced_data = MagicMock(spec=SynchronizedData)
        synced_data.nb_participants = 4
        return SyncMarketsRound(synchronized_data=synced_data, context=context)

    def test_end_block_threshold_error(self, setup_round: SyncMarketsRound) -> None:
        """Test error payload returns ERROR event."""
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
                return_value="ERROR_PAYLOAD",
            ):
                result = setup_round.end_block()
                assert result is not None
                _, event = result
                assert event == Event.ERROR

    def test_end_block_threshold_no_update(self, setup_round: SyncMarketsRound) -> None:
        """Test NO_UPDATE payload returns DONE event."""
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
                return_value="NO_UPDATE",
            ):
                result = setup_round.end_block()
                assert result is not None
                _, event = result
                assert event == Event.DONE

    def test_end_block_threshold_happy_path(
        self, setup_round: SyncMarketsRound
    ) -> None:
        """Test happy path parses JSON and updates data."""
        payload = json.dumps(
            {
                "markets": [{"address": "0x1"}],
                "from_block": 12345,
            }
        )
        updated_data = MagicMock(spec=SynchronizedData)
        setup_round.synchronized_data.update.return_value = updated_data  # type: ignore[attr-defined]

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
                return_value=payload,
            ):
                result = setup_round.end_block()
                assert result is not None
                result_data, event = result
                assert event == Event.DONE
                # update should have been called with markets and from_block
                setup_round.synchronized_data.update.assert_called_once()  # type: ignore[attr-defined]

    def test_end_block_no_threshold_no_majority(
        self, setup_round: SyncMarketsRound
    ) -> None:
        """Test no threshold and no majority possible."""
        with patch.object(
            type(setup_round),
            "threshold_reached",
            new_callable=PropertyMock,
            return_value=False,
        ):
            with patch.object(
                SyncMarketsRound,
                "is_majority_possible",
                return_value=False,
            ):
                result = setup_round.end_block()
                assert result is not None
                _, event = result
                assert event == Event.NO_MAJORITY

    def test_end_block_no_threshold_majority_possible(
        self, setup_round: SyncMarketsRound
    ) -> None:
        """Test returns None when majority is still possible."""
        with patch.object(
            type(setup_round),
            "threshold_reached",
            new_callable=PropertyMock,
            return_value=False,
        ):
            with patch.object(
                SyncMarketsRound,
                "is_majority_possible",
                return_value=True,
            ):
                assert setup_round.end_block() is None

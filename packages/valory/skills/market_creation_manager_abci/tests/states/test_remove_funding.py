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

"""Tests for the RemoveFundingRound."""

import json
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    RemoveFundingPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)
from packages.valory.skills.market_creation_manager_abci.states.remove_funding import (
    RemoveFundingRound,
)


class TestRemoveFundingRound:
    """Tests for RemoveFundingRound attributes."""

    def test_inherits_collect_same(self) -> None:
        """Test class hierarchy."""
        assert issubclass(RemoveFundingRound, CollectSameUntilThresholdRound)

    def test_payload_class(self) -> None:
        """Test payload class."""
        assert RemoveFundingRound.payload_class == RemoveFundingPayload

    def test_synchronized_data_class(self) -> None:
        """Test synchronized data class."""
        assert RemoveFundingRound.synchronized_data_class == SynchronizedData

    def test_done_event(self) -> None:
        """Test done event."""
        assert RemoveFundingRound.done_event == Event.DONE

    def test_no_majority_event(self) -> None:
        """Test no majority event."""
        assert RemoveFundingRound.no_majority_event == Event.NO_MAJORITY

    def test_none_event(self) -> None:
        """Test none event."""
        assert RemoveFundingRound.none_event == Event.NONE

    def test_selection_key(self) -> None:
        """Test selection key."""
        assert RemoveFundingRound.selection_key == (
            get_name(SynchronizedData.tx_submitter),
            get_name(SynchronizedData.most_voted_tx_hash),
        )

    def test_collection_key(self) -> None:
        """Test collection key."""
        assert RemoveFundingRound.collection_key == get_name(
            SynchronizedData.participant_to_tx_prep
        )

    def test_constants(self) -> None:
        """Test constants."""
        assert RemoveFundingRound.ERROR_PAYLOAD == "ERROR_PAYLOAD"
        assert RemoveFundingRound.NO_UPDATE_PAYLOAD == "NO_UPDATE"


class TestRemoveFundingRoundEndBlock:
    """Tests for RemoveFundingRound.end_block."""

    @pytest.fixture
    def setup_round(self) -> RemoveFundingRound:
        """Set up round."""
        context = MagicMock()
        synced_data = MagicMock(spec=SynchronizedData)
        synced_data.nb_participants = 4
        synced_data.markets_to_remove_liquidity = [
            {"address": "0x1", "data": "a"},
            {"address": "0x2", "data": "b"},
        ]
        return RemoveFundingRound(
            synchronized_data=synced_data, context=context
        )

    def test_end_block_threshold_error_payload(
        self, setup_round: RemoveFundingRound
    ) -> None:
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

    def test_end_block_threshold_no_update_payload(
        self, setup_round: RemoveFundingRound
    ) -> None:
        """Test NO_UPDATE payload returns NO_TX event."""
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
                assert event == Event.NO_TX

    def test_end_block_threshold_happy_path(
        self, setup_round: RemoveFundingRound
    ) -> None:
        """Test happy path with JSON payload updates data."""
        payload_data = json.dumps({"tx": "0xabc", "market": "0x1"})
        updated_data = MagicMock(spec=SynchronizedData)
        setup_round.synchronized_data.update.return_value = updated_data

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
                return_value=payload_data,
            ):
                result = setup_round.end_block()
                assert result is not None
                result_data, event = result
                assert event == Event.DONE
                # The update should have been called with the remaining market
                setup_round.synchronized_data.update.assert_called_once()

    def test_end_block_no_threshold_no_majority(
        self, setup_round: RemoveFundingRound
    ) -> None:
        """Test no threshold and no majority possible."""
        with patch.object(
            type(setup_round),
            "threshold_reached",
            new_callable=PropertyMock,
            return_value=False,
        ):
            with patch.object(
                RemoveFundingRound,
                "is_majority_possible",
                return_value=False,
            ):
                result = setup_round.end_block()
                assert result is not None
                _, event = result
                assert event == Event.NO_MAJORITY

    def test_end_block_no_threshold_majority_possible(
        self, setup_round: RemoveFundingRound
    ) -> None:
        """Test returns None when majority is still possible."""
        with patch.object(
            type(setup_round),
            "threshold_reached",
            new_callable=PropertyMock,
            return_value=False,
        ):
            with patch.object(
                RemoveFundingRound,
                "is_majority_possible",
                return_value=True,
            ):
                assert setup_round.end_block() is None

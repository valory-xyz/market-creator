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

"""Tests for the PostTransactionRound."""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import PostTxPayload
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)
from packages.valory.skills.market_creation_manager_abci.states.post_transaction import (
    PostTransactionRound,
)


class TestPostTransactionRound:
    """Tests for PostTransactionRound attributes."""

    def test_inherits_collect_same(self) -> None:
        """Test class hierarchy."""
        assert issubclass(PostTransactionRound, CollectSameUntilThresholdRound)

    def test_payload_class(self) -> None:
        """Test payload class."""
        assert PostTransactionRound.payload_class == PostTxPayload

    def test_synchronized_data_class(self) -> None:
        """Test synchronized data class."""
        assert PostTransactionRound.synchronized_data_class == SynchronizedData

    def test_done_event(self) -> None:
        """Test done event."""
        assert PostTransactionRound.done_event == Event.DONE

    def test_no_majority_event(self) -> None:
        """Test no majority event."""
        assert PostTransactionRound.no_majority_event == Event.NO_MAJORITY

    def test_none_event(self) -> None:
        """Test none event."""
        assert PostTransactionRound.none_event == Event.NONE

    def test_collection_key(self) -> None:
        """Test collection key."""
        assert PostTransactionRound.collection_key == get_name(
            SynchronizedData.participant_to_votes
        )

    def test_selection_key(self) -> None:
        """Test selection key."""
        assert PostTransactionRound.selection_key == ("ignored",)

    def test_payload_constants(self) -> None:
        """Test all payload constants."""
        assert PostTransactionRound.DONE_PAYLOAD == "DONE_PAYLOAD"
        assert PostTransactionRound.ERROR_PAYLOAD == "ERROR_PAYLOAD"
        assert (
            PostTransactionRound.DEPOSIT_DAI_DONE_PAYLOAD == "DEPOSIT_DAI_DONE_PAYLOAD"
        )
        assert (
            PostTransactionRound.REMOVE_FUNDING_DONE_PAYLOAD
            == "REMOVE_FUNDING_DONE_PAYLOAD"
        )
        assert (
            PostTransactionRound.REDEEM_WINNINGS_DONE_PAYLOAD
            == "REDEEM_WINNINGS_DONE_PAYLOAD"
        )
        assert PostTransactionRound.FUND_SWEEP_DONE_PAYLOAD == "FUND_SWEEP_DONE_PAYLOAD"


class TestPostTransactionRoundEndBlock:
    """Tests for PostTransactionRound.end_block."""

    @pytest.fixture
    def setup_round(self) -> PostTransactionRound:
        """Set up the round instance."""
        context = MagicMock()
        synced_data = MagicMock(spec=SynchronizedData)
        synced_data.nb_participants = 4
        return PostTransactionRound(synchronized_data=synced_data, context=context)

    @pytest.mark.parametrize(
        "payload,expected_event",
        [
            ("ERROR_PAYLOAD", Event.ERROR),
            ("DEPOSIT_DAI_DONE_PAYLOAD", Event.DEPOSIT_DAI_DONE),
            ("REMOVE_FUNDING_DONE_PAYLOAD", Event.REMOVE_FUNDING_DONE),
            ("REDEEM_WINNINGS_DONE_PAYLOAD", Event.REDEEM_WINNINGS_DONE),
            ("FUND_SWEEP_DONE_PAYLOAD", Event.FUND_SWEEP_DONE),
            ("some_other_payload", Event.DONE),
        ],
    )
    def test_end_block_threshold_reached(
        self,
        setup_round: PostTransactionRound,
        payload: str,
        expected_event: Event,
    ) -> None:
        """Test end_block when threshold is reached with various payloads."""
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
                _, event = result
                assert event == expected_event

    def test_end_block_no_threshold_no_majority(
        self, setup_round: PostTransactionRound
    ) -> None:
        """Test end_block when threshold not reached and no majority possible."""
        with patch.object(
            type(setup_round),
            "threshold_reached",
            new_callable=PropertyMock,
            return_value=False,
        ):
            with patch.object(
                PostTransactionRound,
                "is_majority_possible",
                return_value=False,
            ):
                result = setup_round.end_block()
                assert result is not None
                _, event = result
                assert event == Event.NO_MAJORITY

    def test_end_block_no_threshold_majority_possible(
        self, setup_round: PostTransactionRound
    ) -> None:
        """Test end_block when threshold not reached but majority still possible."""
        with patch.object(
            type(setup_round),
            "threshold_reached",
            new_callable=PropertyMock,
            return_value=False,
        ):
            with patch.object(
                PostTransactionRound,
                "is_majority_possible",
                return_value=True,
            ):
                result = setup_round.end_block()
                assert result is None

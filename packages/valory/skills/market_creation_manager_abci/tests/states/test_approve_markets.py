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

"""Tests for the ApproveMarketsRound."""

from unittest.mock import MagicMock, patch

import pytest

from packages.valory.skills.abstract_round_abci.base import OnlyKeeperSendsRound
from packages.valory.skills.market_creation_manager_abci.payloads import (
    ApproveMarketsPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.approve_markets import (
    ApproveMarketsRound,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)


class TestApproveMarketsRound:
    """Tests for ApproveMarketsRound."""

    def test_inherits_only_keeper_sends_round(self) -> None:
        """Test class hierarchy."""
        assert issubclass(ApproveMarketsRound, OnlyKeeperSendsRound)

    def test_payload_class(self) -> None:
        """Test payload class."""
        assert ApproveMarketsRound.payload_class == ApproveMarketsPayload

    def test_synchronized_data_class(self) -> None:
        """Test synchronized data class."""
        assert ApproveMarketsRound.synchronized_data_class == SynchronizedData

    def test_done_event(self) -> None:
        """Test done_event."""
        assert ApproveMarketsRound.done_event == Event.DONE

    def test_fail_event(self) -> None:
        """Test fail_event."""
        assert ApproveMarketsRound.fail_event == Event.ERROR

    def test_error_payload_constant(self) -> None:
        """Test ERROR_PAYLOAD constant."""
        assert ApproveMarketsRound.ERROR_PAYLOAD == "ERROR_PAYLOAD"

    def test_max_retries_payload_constant(self) -> None:
        """Test MAX_RETRIES_PAYLOAD constant."""
        assert ApproveMarketsRound.MAX_RETRIES_PAYLOAD == "MAX_RETRIES_PAYLOAD"


class TestApproveMarketsRoundEndBlock:
    """Tests for ApproveMarketsRound.end_block custom logic."""

    @pytest.fixture
    def setup_round(self) -> ApproveMarketsRound:
        """Set up the round instance for testing."""
        context = MagicMock()
        synced_data = MagicMock(spec=SynchronizedData)
        round_instance = ApproveMarketsRound(
            synchronized_data=synced_data, context=context
        )
        return round_instance

    def test_end_block_returns_none_when_parent_returns_none(
        self, setup_round: ApproveMarketsRound
    ) -> None:
        """Test that end_block returns None when parent returns None."""
        with patch.object(
            OnlyKeeperSendsRound, "end_block", return_value=None
        ):
            result = setup_round.end_block()
            assert result is None

    def test_end_block_error_payload_returns_error_event(
        self, setup_round: ApproveMarketsRound
    ) -> None:
        """Test that error payload maps to ERROR event."""
        synced_data = MagicMock(spec=SynchronizedData)
        keeper_payload = MagicMock(spec=ApproveMarketsPayload)
        keeper_payload.content = ApproveMarketsRound.ERROR_PAYLOAD
        setup_round.keeper_payload = keeper_payload

        with patch.object(
            OnlyKeeperSendsRound,
            "end_block",
            return_value=(synced_data, Event.DONE),
        ):
            result = setup_round.end_block()
            assert result is not None
            _, event = result
            assert event == Event.ERROR

    def test_end_block_max_retries_payload_returns_max_retries_event(
        self, setup_round: ApproveMarketsRound
    ) -> None:
        """Test that max retries payload maps to MAX_RETRIES_REACHED event."""
        synced_data = MagicMock(spec=SynchronizedData)
        keeper_payload = MagicMock(spec=ApproveMarketsPayload)
        keeper_payload.content = ApproveMarketsRound.MAX_RETRIES_PAYLOAD
        setup_round.keeper_payload = keeper_payload

        with patch.object(
            OnlyKeeperSendsRound,
            "end_block",
            return_value=(synced_data, Event.DONE),
        ):
            result = setup_round.end_block()
            assert result is not None
            _, event = result
            assert event == Event.MAX_RETRIES_REACHED

    def test_end_block_normal_done_passes_through(
        self, setup_round: ApproveMarketsRound
    ) -> None:
        """Test that normal DONE event passes through unchanged."""
        synced_data = MagicMock(spec=SynchronizedData)
        keeper_payload = MagicMock(spec=ApproveMarketsPayload)
        keeper_payload.content = '{"some": "valid_data"}'
        setup_round.keeper_payload = keeper_payload

        with patch.object(
            OnlyKeeperSendsRound,
            "end_block",
            return_value=(synced_data, Event.DONE),
        ):
            result = setup_round.end_block()
            assert result is not None
            _, event = result
            assert event == Event.DONE

    def test_end_block_non_done_event_passes_through(
        self, setup_round: ApproveMarketsRound
    ) -> None:
        """Test that a non-DONE event from parent passes through."""
        synced_data = MagicMock(spec=SynchronizedData)
        keeper_payload = MagicMock(spec=ApproveMarketsPayload)
        keeper_payload.content = ApproveMarketsRound.ERROR_PAYLOAD
        setup_round.keeper_payload = keeper_payload

        with patch.object(
            OnlyKeeperSendsRound,
            "end_block",
            return_value=(synced_data, Event.ERROR),
        ):
            result = setup_round.end_block()
            assert result is not None
            _, event = result
            # Not DONE, so the error/max_retries checks don't apply
            assert event == Event.ERROR

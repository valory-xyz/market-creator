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

"""Tests for the RetrieveApprovedMarketRound."""

import json
from unittest.mock import MagicMock

import pytest

from packages.valory.skills.abstract_round_abci.base import OnlyKeeperSendsRound
from packages.valory.skills.market_creation_manager_abci.payloads import (
    RetrieveApprovedMarketPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)
from packages.valory.skills.market_creation_manager_abci.states.retrieve_approved_market import (
    RetrieveApprovedMarketRound,
)


class TestRetrieveApprovedMarketRound:
    """Tests for RetrieveApprovedMarketRound attributes."""

    def test_inherits_only_keeper_sends(self) -> None:
        """Test class hierarchy."""
        assert issubclass(RetrieveApprovedMarketRound, OnlyKeeperSendsRound)

    def test_payload_class(self) -> None:
        """Test payload class."""
        assert (
            RetrieveApprovedMarketRound.payload_class == RetrieveApprovedMarketPayload
        )

    def test_synchronized_data_class(self) -> None:
        """Test synchronized data class."""
        assert RetrieveApprovedMarketRound.synchronized_data_class == SynchronizedData

    def test_payload_attribute(self) -> None:
        """Test payload attribute."""
        assert RetrieveApprovedMarketRound.payload_attribute == "content"

    def test_done_event(self) -> None:
        """Test done event."""
        assert RetrieveApprovedMarketRound.done_event == Event.DONE

    def test_fail_event(self) -> None:
        """Test fail event."""
        assert RetrieveApprovedMarketRound.fail_event == Event.ERROR

    def test_constants(self) -> None:
        """Test constants."""
        assert RetrieveApprovedMarketRound.ERROR_PAYLOAD == "ERROR_PAYLOAD"
        assert (
            RetrieveApprovedMarketRound.NO_MARKETS_RETRIEVED_PAYLOAD
            == "NO_MARKETS_RETRIEVED_PAYLOAD"
        )


class TestRetrieveApprovedMarketRoundEndBlock:
    """Tests for RetrieveApprovedMarketRound.end_block."""

    @pytest.fixture
    def setup_round(self) -> RetrieveApprovedMarketRound:
        """Set up round."""
        context = MagicMock()
        synced_data = MagicMock(spec=SynchronizedData)
        synced_data.proposed_markets_count = 5
        round_instance = RetrieveApprovedMarketRound(
            synchronized_data=synced_data, context=context
        )
        return round_instance

    def test_end_block_returns_none_when_keeper_payload_none(
        self, setup_round: RetrieveApprovedMarketRound
    ) -> None:
        """Test returns None when keeper_payload is None."""
        setup_round.keeper_payload = None
        result = setup_round.end_block()
        assert result is None

    def test_end_block_error_payload(
        self, setup_round: RetrieveApprovedMarketRound
    ) -> None:
        """Test error payload returns ERROR event."""
        keeper_payload = MagicMock(spec=RetrieveApprovedMarketPayload)
        keeper_payload.content = RetrieveApprovedMarketRound.ERROR_PAYLOAD
        setup_round.keeper_payload = keeper_payload

        result = setup_round.end_block()
        assert result is not None
        _, event = result
        assert event == Event.ERROR

    def test_end_block_no_markets_retrieved_payload(
        self, setup_round: RetrieveApprovedMarketRound
    ) -> None:
        """Test NO_MARKETS_RETRIEVED payload."""
        keeper_payload = MagicMock(spec=RetrieveApprovedMarketPayload)
        keeper_payload.content = (
            RetrieveApprovedMarketRound.NO_MARKETS_RETRIEVED_PAYLOAD
        )
        setup_round.keeper_payload = keeper_payload
        updated_data = MagicMock(spec=SynchronizedData)
        setup_round.synchronized_data.update.return_value = updated_data  # type: ignore[attr-defined]

        result = setup_round.end_block()
        assert result is not None
        _, event = result
        assert event == Event.NO_MARKETS_RETRIEVED

    def test_end_block_happy_path(
        self, setup_round: RetrieveApprovedMarketRound
    ) -> None:
        """Test happy path with valid JSON."""
        approved_data = {"question": "Will X happen?", "outcomes": ["Yes", "No"]}
        keeper_payload = MagicMock(spec=RetrieveApprovedMarketPayload)
        keeper_payload.content = json.dumps(approved_data)
        setup_round.keeper_payload = keeper_payload
        updated_data = MagicMock(spec=SynchronizedData)
        setup_round.synchronized_data.update.return_value = updated_data  # type: ignore[attr-defined]

        result = setup_round.end_block()
        assert result is not None
        result_data, event = result
        assert event == Event.DONE
        setup_round.synchronized_data.update.assert_called_once()  # type: ignore[attr-defined]

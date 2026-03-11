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

"""Tests for the RedeemWinningsRound."""

from packages.valory.skills.abstract_round_abci.base import get_name
from packages.valory.skills.market_creation_manager_abci.payloads import (
    MultisigTxPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
    TxPreparationRound,
)
from packages.valory.skills.market_creation_manager_abci.states.redeem_winnings import (
    RedeemWinningsRound,
)


class TestRedeemWinningsRound:
    """Tests for RedeemWinningsRound attributes."""

    def test_inherits_tx_preparation_round(self) -> None:
        """Test class hierarchy."""
        assert issubclass(RedeemWinningsRound, TxPreparationRound)

    def test_payload_class(self) -> None:
        """Test payload class."""
        assert RedeemWinningsRound.payload_class == MultisigTxPayload

    def test_synchronized_data_class(self) -> None:
        """Test synchronized data class."""
        assert RedeemWinningsRound.synchronized_data_class == SynchronizedData

    def test_done_event(self) -> None:
        """Test done event."""
        assert RedeemWinningsRound.done_event == Event.DONE

    def test_no_majority_event(self) -> None:
        """Test no majority event."""
        assert RedeemWinningsRound.no_majority_event == Event.NO_MAJORITY

    def test_none_event(self) -> None:
        """Test none event."""
        assert RedeemWinningsRound.none_event == Event.NONE

    def test_selection_key(self) -> None:
        """Test selection key."""
        assert RedeemWinningsRound.selection_key == (
            get_name(SynchronizedData.tx_submitter),
            get_name(SynchronizedData.most_voted_tx_hash),
        )

    def test_collection_key(self) -> None:
        """Test collection key."""
        assert RedeemWinningsRound.collection_key == get_name(
            SynchronizedData.participant_to_tx_prep
        )

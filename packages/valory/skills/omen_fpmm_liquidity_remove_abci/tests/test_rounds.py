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

"""Tests for rounds in the omen_fpmm_liquidity_remove_abci skill."""

# pylint: disable=import-outside-toplevel

import pytest

from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
    DegenerateRound,
)
from packages.valory.skills.omen_fpmm_liquidity_remove_abci.rounds import (
    Event,
    FinishedWithFpmmLiquidityRemoveTxRound,
    FinishedWithoutFpmmLiquidityRemoveTxRound,
    FpmmLiquidityRemoveRound,
    OmenFpmmLiquidityRemoveAbciApp,
    SynchronizedData,
)


class TestEvent:
    """Tests for the Event enum."""

    def test_all_events_present(self) -> None:
        """All expected events exist."""
        assert Event.DONE.value == "done"
        assert Event.NONE.value == "none"
        assert Event.NO_MAJORITY.value == "no_majority"
        assert Event.ROUND_TIMEOUT.value == "round_timeout"

    def test_event_count(self) -> None:
        """Exactly 4 events are defined."""
        assert len(Event) == 4


class TestFpmmLiquidityRemoveRound:
    """Tests for FpmmLiquidityRemoveRound."""

    def test_is_collect_same_until_threshold(self) -> None:
        """Round is a CollectSameUntilThresholdRound."""
        assert issubclass(FpmmLiquidityRemoveRound, CollectSameUntilThresholdRound)

    def test_done_event(self) -> None:
        """done_event is Event.DONE."""
        assert FpmmLiquidityRemoveRound.done_event == Event.DONE

    def test_none_event(self) -> None:
        """none_event is Event.NONE."""
        assert FpmmLiquidityRemoveRound.none_event == Event.NONE

    def test_no_majority_event(self) -> None:
        """no_majority_event is Event.NO_MAJORITY."""
        assert FpmmLiquidityRemoveRound.no_majority_event == Event.NO_MAJORITY

    def test_selection_key_is_tuple(self) -> None:
        """selection_key is a 2-tuple of field name strings."""
        key = FpmmLiquidityRemoveRound.selection_key
        assert isinstance(key, tuple)
        assert len(key) == 2
        assert "tx_submitter" in key
        assert "most_voted_tx_hash" in key

    def test_collection_key(self) -> None:
        """collection_key is participant_to_fpmm_liquidity_remove_tx."""
        assert (
            FpmmLiquidityRemoveRound.collection_key
            == "participant_to_fpmm_liquidity_remove_tx"
        )


class TestFinishedRounds:
    """Tests for degenerate final rounds."""

    def test_finished_with_tx_is_degenerate(self) -> None:
        """Test that FinishedWithFpmmLiquidityRemoveTxRound is a DegenerateRound."""
        assert issubclass(FinishedWithFpmmLiquidityRemoveTxRound, DegenerateRound)

    def test_finished_without_tx_is_degenerate(self) -> None:
        """Test that FinishedWithoutFpmmLiquidityRemoveTxRound is a DegenerateRound."""
        assert issubclass(FinishedWithoutFpmmLiquidityRemoveTxRound, DegenerateRound)


class TestOmenFpmmLiquidityRemoveAbciApp:
    """Tests for OmenFpmmLiquidityRemoveAbciApp."""

    def test_initial_round(self) -> None:
        """initial_round_cls is FpmmLiquidityRemoveRound."""
        assert (
            OmenFpmmLiquidityRemoveAbciApp.initial_round_cls is FpmmLiquidityRemoveRound
        )

    def test_initial_states(self) -> None:
        """initial_states contains FpmmLiquidityRemoveRound."""
        assert FpmmLiquidityRemoveRound in OmenFpmmLiquidityRemoveAbciApp.initial_states

    def test_final_states(self) -> None:
        """final_states contains both finished rounds."""
        finals = OmenFpmmLiquidityRemoveAbciApp.final_states
        assert FinishedWithFpmmLiquidityRemoveTxRound in finals
        assert FinishedWithoutFpmmLiquidityRemoveTxRound in finals

    def test_transition_function_done(self) -> None:
        """DONE transitions to FinishedWithFpmmLiquidityRemoveTxRound."""
        tf = OmenFpmmLiquidityRemoveAbciApp.transition_function
        assert (
            tf[FpmmLiquidityRemoveRound][Event.DONE]
            is FinishedWithFpmmLiquidityRemoveTxRound
        )

    @pytest.mark.parametrize(
        "event",
        [Event.NONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT],
    )
    def test_transition_function_no_tx(self, event: Event) -> None:
        """Non-DONE events transition to FinishedWithoutFpmmLiquidityRemoveTxRound."""
        tf = OmenFpmmLiquidityRemoveAbciApp.transition_function
        assert (
            tf[FpmmLiquidityRemoveRound][event]
            is FinishedWithoutFpmmLiquidityRemoveTxRound
        )

    def test_round_timeout_value(self) -> None:
        """ROUND_TIMEOUT is 120 seconds."""
        assert (
            OmenFpmmLiquidityRemoveAbciApp.event_to_timeout[Event.ROUND_TIMEOUT]
            == 120.0
        )

    def test_db_post_conditions_with_tx(self) -> None:
        """Post-condition for finished with tx includes most_voted_tx_hash."""
        conds = OmenFpmmLiquidityRemoveAbciApp.db_post_conditions
        assert "most_voted_tx_hash" in conds[FinishedWithFpmmLiquidityRemoveTxRound]

    def test_db_post_conditions_without_tx(self) -> None:
        """Post-condition for finished without tx is empty."""
        conds = OmenFpmmLiquidityRemoveAbciApp.db_post_conditions
        assert conds[FinishedWithoutFpmmLiquidityRemoveTxRound] == set()


class TestSynchronizedData:
    """Tests for SynchronizedData property accessors."""

    def _make_synced_data(self, data: dict) -> SynchronizedData:
        """Make a SynchronizedData instance backed by a simple mock DB."""
        from unittest.mock import MagicMock

        db = MagicMock()
        db.get_strict.side_effect = data.__getitem__
        sd = SynchronizedData(db=db)
        return sd

    def test_most_voted_tx_hash(self) -> None:
        """most_voted_tx_hash reads from db key."""
        sd = self._make_synced_data({"most_voted_tx_hash": "0xabc"})
        assert sd.most_voted_tx_hash == "0xabc"

    def test_tx_submitter(self) -> None:
        """tx_submitter reads from db key."""
        sd = self._make_synced_data({"tx_submitter": "omen_fpmm_liquidity_remove"})
        assert sd.tx_submitter == "omen_fpmm_liquidity_remove"

    def test_participant_to_fpmm_liquidity_remove_tx(self) -> None:
        """participant_to_fpmm_liquidity_remove_tx delegates to _get_deserialized.

        Patches CollectionRound.deserialize_collection so the real
        _get_deserialized method body runs (covering rounds.py:77-78, 93).
        """
        from unittest.mock import patch

        sd = self._make_synced_data(
            {"participant_to_fpmm_liquidity_remove_tx": {"raw": "data"}}
        )
        sentinel = object()
        with patch(
            "packages.valory.skills.omen_fpmm_liquidity_remove_abci."
            "rounds.CollectionRound.deserialize_collection",
            return_value=sentinel,
        ) as mock_deser:
            result = sd.participant_to_fpmm_liquidity_remove_tx
        assert result is sentinel
        mock_deser.assert_called_once_with({"raw": "data"})

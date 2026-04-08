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

"""Tests for the OmenCtRedeemTokensAbciApp FSM rounds."""

# pylint: disable=redefined-outer-name,too-few-public-methods,unused-argument
# pylint: disable=import-outside-toplevel

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
    DegenerateRound,
    get_name,
)
from packages.valory.skills.omen_ct_redeem_tokens_abci.payloads import (
    CtRedeemTokensPayload,
)
from packages.valory.skills.omen_ct_redeem_tokens_abci.rounds import (
    CtRedeemTokensRound,
    Event,
    FinishedWithCtRedeemTokensTxRound,
    FinishedWithoutCtRedeemTokensTxRound,
    OmenCtRedeemTokensAbciApp,
    SynchronizedData,
)

# ---------------------------------------------------------------------------
# SynchronizedData property tests
# ---------------------------------------------------------------------------


class TestSynchronizedData:
    """Test SynchronizedData properties."""

    @pytest.fixture
    def mocked_db(self) -> MagicMock:
        """Create a mocked database."""
        return MagicMock()

    @pytest.fixture
    def sync_data(self, mocked_db: MagicMock) -> SynchronizedData:
        """Create a SynchronizedData instance."""
        return SynchronizedData(db=mocked_db)

    def test_most_voted_tx_hash(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test most_voted_tx_hash property."""
        mocked_db.get_strict.return_value = "0xabc123"
        assert sync_data.most_voted_tx_hash == "0xabc123"

    def test_tx_submitter(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test tx_submitter property."""
        mocked_db.get_strict.return_value = "some_round_id"
        assert sync_data.tx_submitter == "some_round_id"

    @patch(
        "packages.valory.skills.omen_ct_redeem_tokens_abci.rounds.CollectionRound.deserialize_collection"
    )
    def test_participant_to_ct_redeem_tokens_tx(
        self,
        mock_deserialize: MagicMock,
        sync_data: SynchronizedData,
        mocked_db: MagicMock,
    ) -> None:
        """Test participant_to_ct_redeem_tokens_tx property with deserialization."""
        serialized = '{"agent_0": "payload_0"}'
        expected = {"agent_0": "payload_0"}
        mocked_db.get_strict.return_value = serialized
        mock_deserialize.return_value = expected
        result = sync_data.participant_to_ct_redeem_tokens_tx
        mock_deserialize.assert_called_once_with(serialized)
        assert result == expected


# ---------------------------------------------------------------------------
# CtRedeemTokensRound attribute tests
# ---------------------------------------------------------------------------


class TestCtRedeemTokensRound:
    """Tests for CtRedeemTokensRound class attributes."""

    def test_inherits_collect_same(self) -> None:
        """Test class hierarchy."""
        assert issubclass(CtRedeemTokensRound, CollectSameUntilThresholdRound)

    def test_payload_class(self) -> None:
        """Test payload class."""
        assert CtRedeemTokensRound.payload_class == CtRedeemTokensPayload

    def test_synchronized_data_class(self) -> None:
        """Test synchronized data class."""
        assert CtRedeemTokensRound.synchronized_data_class == SynchronizedData

    def test_done_event(self) -> None:
        """Test done event."""
        assert CtRedeemTokensRound.done_event == Event.DONE

    def test_none_event(self) -> None:
        """Test none event."""
        assert CtRedeemTokensRound.none_event == Event.NONE

    def test_no_majority_event(self) -> None:
        """Test no majority event."""
        assert CtRedeemTokensRound.no_majority_event == Event.NO_MAJORITY

    def test_selection_key(self) -> None:
        """Test selection key writes both tx_submitter and most_voted_tx_hash."""
        assert CtRedeemTokensRound.selection_key == (
            get_name(SynchronizedData.tx_submitter),
            get_name(SynchronizedData.most_voted_tx_hash),
        )

    def test_collection_key(self) -> None:
        """Test collection key."""
        assert CtRedeemTokensRound.collection_key == get_name(
            SynchronizedData.participant_to_ct_redeem_tokens_tx
        )


class TestCtRedeemTokensRoundEndBlock:
    """Tests for CtRedeemTokensRound default end_block behaviour.

    CtRedeemTokensRound uses the framework's default end_block via selection_key.
    Only the no_majority and majority_possible paths are tested here.
    """

    @pytest.fixture
    def setup_round(self) -> CtRedeemTokensRound:
        """Set up a CtRedeemTokensRound instance for testing."""
        context = MagicMock()
        synced_data = MagicMock(spec=SynchronizedData)
        synced_data.nb_participants = 4
        return CtRedeemTokensRound(synchronized_data=synced_data, context=context)

    def test_no_threshold_no_majority(self, setup_round: CtRedeemTokensRound) -> None:
        """Test no threshold and no majority possible."""
        with (
            patch.object(
                type(setup_round),
                "threshold_reached",
                new_callable=PropertyMock,
                return_value=False,
            ),
            patch.object(
                CtRedeemTokensRound,
                "is_majority_possible",
                return_value=False,
            ),
        ):
            result = setup_round.end_block()
            assert result is not None
            _, event = result
            assert event == Event.NO_MAJORITY

    def test_no_threshold_majority_possible(
        self, setup_round: CtRedeemTokensRound
    ) -> None:
        """Test returns None when majority is still possible."""
        with (
            patch.object(
                type(setup_round),
                "threshold_reached",
                new_callable=PropertyMock,
                return_value=False,
            ),
            patch.object(
                CtRedeemTokensRound,
                "is_majority_possible",
                return_value=True,
            ),
        ):
            assert setup_round.end_block() is None


# ---------------------------------------------------------------------------
# Final (Degenerate) Rounds
# ---------------------------------------------------------------------------


class TestFinalRounds:
    """Tests for degenerate (final) rounds."""

    def test_finished_with_ct_redeem_tx_round(self) -> None:
        """Test FinishedWithCtRedeemTokensTxRound is degenerate."""
        assert issubclass(FinishedWithCtRedeemTokensTxRound, DegenerateRound)

    def test_finished_without_ct_redeem_tx_round(self) -> None:
        """Test FinishedWithoutCtRedeemTokensTxRound is degenerate."""
        assert issubclass(FinishedWithoutCtRedeemTokensTxRound, DegenerateRound)


# ---------------------------------------------------------------------------
# OmenCtRedeemTokensAbciApp tests
# ---------------------------------------------------------------------------


@pytest.fixture
def abci_app() -> OmenCtRedeemTokensAbciApp:
    """Create an AbciApp instance."""
    synchronized_data = MagicMock(spec=SynchronizedData)
    logger = MagicMock()
    context = MagicMock()
    return OmenCtRedeemTokensAbciApp(synchronized_data, logger, context)


class TestAbciAppInitialization:
    """Test AbciApp initialization and configuration."""

    def test_initial_round_cls(self, abci_app: OmenCtRedeemTokensAbciApp) -> None:
        """Test initial round class."""
        assert abci_app.initial_round_cls is CtRedeemTokensRound

    def test_initial_states(self, abci_app: OmenCtRedeemTokensAbciApp) -> None:
        """Test initial states set."""
        expected = {CtRedeemTokensRound}
        assert abci_app.initial_states == expected

    def test_final_states(self, abci_app: OmenCtRedeemTokensAbciApp) -> None:
        """Test final states set."""
        expected = {
            FinishedWithCtRedeemTokensTxRound,
            FinishedWithoutCtRedeemTokensTxRound,
        }
        assert abci_app.final_states == expected


class TestCtRedeemTransitions:
    """Test CtRedeemTokensRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, FinishedWithCtRedeemTokensTxRound),
            (Event.NONE, FinishedWithoutCtRedeemTokensTxRound),
            (Event.NO_MAJORITY, FinishedWithoutCtRedeemTokensTxRound),
            (Event.ROUND_TIMEOUT, FinishedWithoutCtRedeemTokensTxRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: OmenCtRedeemTokensAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all CtRedeemTokensRound transitions."""
        tf = abci_app.transition_function[CtRedeemTokensRound]
        assert tf[event] == expected_next


class TestFinalStateTransitions:
    """Test final state rounds have empty transition functions."""

    @pytest.mark.parametrize(
        "final_round",
        [
            FinishedWithCtRedeemTokensTxRound,
            FinishedWithoutCtRedeemTokensTxRound,
        ],
    )
    def test_empty_transitions(
        self,
        abci_app: OmenCtRedeemTokensAbciApp,
        final_round: type,
    ) -> None:
        """Test final states have empty transition functions."""
        assert abci_app.transition_function[final_round] == {}


class TestCrossPeriodPersistedKeys:
    """Test cross period persisted keys."""

    def test_keys(self, abci_app: OmenCtRedeemTokensAbciApp) -> None:
        """Test cross period persisted keys are empty."""
        assert abci_app.cross_period_persisted_keys == set()


class TestEventToTimeout:
    """Test event_to_timeout mapping."""

    def test_round_timeout(self, abci_app: OmenCtRedeemTokensAbciApp) -> None:
        """Test ROUND_TIMEOUT is mapped to 120.0."""
        assert abci_app.event_to_timeout[Event.ROUND_TIMEOUT] == 120.0

    def test_only_round_timeout(self, abci_app: OmenCtRedeemTokensAbciApp) -> None:
        """Test that only ROUND_TIMEOUT is in event_to_timeout."""
        assert set(abci_app.event_to_timeout.keys()) == {Event.ROUND_TIMEOUT}


class TestDbPreConditions:
    """Test db pre conditions."""

    def test_pre_conditions_empty(self, abci_app: OmenCtRedeemTokensAbciApp) -> None:
        """Test db pre conditions are empty for initial state."""
        assert abci_app.db_pre_conditions[CtRedeemTokensRound] == set()


class TestDbPostConditions:
    """Test db post conditions."""

    def test_post_conditions_with_tx_hash(
        self,
        abci_app: OmenCtRedeemTokensAbciApp,
    ) -> None:
        """Test post conditions containing most_voted_tx_hash."""
        assert (
            get_name(SynchronizedData.most_voted_tx_hash)
            in abci_app.db_post_conditions[FinishedWithCtRedeemTokensTxRound]
        )

    def test_post_conditions_empty(
        self,
        abci_app: OmenCtRedeemTokensAbciApp,
    ) -> None:
        """Test post conditions empty for FinishedWithoutCtRedeemTokensTxRound."""
        assert (
            abci_app.db_post_conditions[FinishedWithoutCtRedeemTokensTxRound] == set()
        )

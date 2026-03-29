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

"""Tests for the OmenFundsRecovererAbciApp FSM rounds."""

import json
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
    DegenerateRound,
    get_name,
)
from packages.valory.skills.omen_funds_recoverer_abci.payloads import (
    BuildMultisendPayload,
    RecoveryTxsPayload,
)
from packages.valory.skills.omen_funds_recoverer_abci.rounds import (
    BuildMultisendRound,
    ClaimBondsRound,
    Event,
    FinishedWithRecoveryTxRound,
    FinishedWithoutRecoveryTxRound,
    OmenFundsRecovererAbciApp,
    RecoveryTxsRound,
    RedeemPositionsRound,
    RemoveLiquidityRound,
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

    def test_recovery_txs_default(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test recovery_txs property returns empty list by default."""
        mocked_db.get.return_value = "[]"
        assert sync_data.funds_recovery_txs == []

    def test_recovery_txs_with_data(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test recovery_txs property with stored JSON data."""
        txs = [{"to": "0xAddr", "data": "0x1234", "value": 0}]
        mocked_db.get.return_value = json.dumps(txs)
        assert sync_data.funds_recovery_txs == txs

    def test_recovery_txs_with_list_data(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test recovery_txs property when db returns a list directly."""
        txs = [{"to": "0xAddr", "data": "0x1234", "value": 0}]
        mocked_db.get.return_value = txs
        assert sync_data.funds_recovery_txs == txs

    def test_recovery_txs_multiple(
        self, sync_data: SynchronizedData, mocked_db: MagicMock
    ) -> None:
        """Test recovery_txs property with multiple transactions."""
        txs = [
            {"to": "0xAddr1", "data": "0xaa", "value": 0},
            {"to": "0xAddr2", "data": "0xbb", "value": 0},
            {"to": "0xAddr3", "data": "0xcc", "value": 0},
        ]
        mocked_db.get.return_value = json.dumps(txs)
        assert sync_data.funds_recovery_txs == txs

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
        "packages.valory.skills.omen_funds_recoverer_abci.rounds.CollectionRound.deserialize_collection"
    )
    def test_participant_to_funds_recovery_txs(
        self,
        mock_deserialize: MagicMock,
        sync_data: SynchronizedData,
        mocked_db: MagicMock,
    ) -> None:
        """Test participant_to_funds_recovery_txs property with deserialization."""
        serialized = '{"agent_0": "payload_0"}'
        expected = {"agent_0": "payload_0"}
        mocked_db.get_strict.return_value = serialized
        mock_deserialize.return_value = expected
        result = sync_data.participant_to_funds_recovery_txs
        mock_deserialize.assert_called_once_with(serialized)
        assert result == expected

    @patch(
        "packages.valory.skills.omen_funds_recoverer_abci.rounds.CollectionRound.deserialize_collection"
    )
    def test_participant_to_tx_prep(
        self,
        mock_deserialize: MagicMock,
        sync_data: SynchronizedData,
        mocked_db: MagicMock,
    ) -> None:
        """Test participant_to_tx_prep property with deserialization."""
        serialized = '{"agent_0": "payload_0"}'
        expected = {"agent_0": "payload_0"}
        mocked_db.get_strict.return_value = serialized
        mock_deserialize.return_value = expected
        result = sync_data.participant_to_tx_prep
        mock_deserialize.assert_called_once_with(serialized)
        assert result == expected


# ---------------------------------------------------------------------------
# RecoveryTxsRound attribute tests
# ---------------------------------------------------------------------------


class TestRecoveryTxsRound:
    """Tests for RecoveryTxsRound class attributes."""

    def test_inherits_collect_same(self) -> None:
        """Test class hierarchy."""
        assert issubclass(RecoveryTxsRound, CollectSameUntilThresholdRound)

    def test_payload_class(self) -> None:
        """Test payload class."""
        assert RecoveryTxsRound.payload_class == RecoveryTxsPayload

    def test_synchronized_data_class(self) -> None:
        """Test synchronized data class."""
        assert RecoveryTxsRound.synchronized_data_class == SynchronizedData

    def test_done_event(self) -> None:
        """Test done event."""
        assert RecoveryTxsRound.done_event == Event.DONE

    def test_none_event(self) -> None:
        """Test none event."""
        assert RecoveryTxsRound.none_event == Event.NONE

    def test_no_majority_event(self) -> None:
        """Test no majority event."""
        assert RecoveryTxsRound.no_majority_event == Event.NO_MAJORITY

    def test_selection_key(self) -> None:
        """Test selection key writes to funds_recovery_txs."""
        assert RecoveryTxsRound.selection_key == (
            get_name(SynchronizedData.funds_recovery_txs),
        )

    def test_collection_key(self) -> None:
        """Test collection key."""
        assert RecoveryTxsRound.collection_key == get_name(
            SynchronizedData.participant_to_funds_recovery_txs
        )


class TestRecoveryTxsRoundEndBlock:
    """Tests for RecoveryTxsRound default end_block behaviour.

    RecoveryTxsRound uses the framework's default end_block via selection_key.
    The accumulation logic is in the behaviours, not the round.
    Only no_majority and majority_possible paths are tested here.
    """

    @pytest.fixture
    def setup_round(self) -> RemoveLiquidityRound:
        """Set up a concrete RecoveryTxsRound subclass for testing."""
        context = MagicMock()
        synced_data = MagicMock(spec=SynchronizedData)
        synced_data.nb_participants = 4
        return RemoveLiquidityRound(synchronized_data=synced_data, context=context)

    def test_no_threshold_no_majority(self, setup_round: RemoveLiquidityRound) -> None:
        """Test no threshold and no majority possible."""
        with patch.object(
            type(setup_round),
            "threshold_reached",
            new_callable=PropertyMock,
            return_value=False,
        ), patch.object(
            RemoveLiquidityRound,
            "is_majority_possible",
            return_value=False,
        ):
            result = setup_round.end_block()
            assert result is not None
            _, event = result
            assert event == Event.NO_MAJORITY

    def test_no_threshold_majority_possible(
        self, setup_round: RemoveLiquidityRound
    ) -> None:
        """Test returns None when majority is still possible."""
        with patch.object(
            type(setup_round),
            "threshold_reached",
            new_callable=PropertyMock,
            return_value=False,
        ), patch.object(
            RemoveLiquidityRound,
            "is_majority_possible",
            return_value=True,
        ):
            assert setup_round.end_block() is None


# ---------------------------------------------------------------------------
# Concrete RecoveryTxsRound subclass tests
# ---------------------------------------------------------------------------


class TestRemoveLiquidityRound:
    """Tests for RemoveLiquidityRound attributes."""

    def test_inherits_recovery_txs_round(self) -> None:
        """Test class hierarchy."""
        assert issubclass(RemoveLiquidityRound, RecoveryTxsRound)

    def test_payload_class(self) -> None:
        """Test payload class inherited from RecoveryTxsRound."""
        assert RemoveLiquidityRound.payload_class == RecoveryTxsPayload


class TestRedeemPositionsRound:
    """Tests for RedeemPositionsRound attributes."""

    def test_inherits_recovery_txs_round(self) -> None:
        """Test class hierarchy."""
        assert issubclass(RedeemPositionsRound, RecoveryTxsRound)

    def test_payload_class(self) -> None:
        """Test payload class inherited from RecoveryTxsRound."""
        assert RedeemPositionsRound.payload_class == RecoveryTxsPayload


class TestClaimBondsRound:
    """Tests for ClaimBondsRound attributes."""

    def test_inherits_recovery_txs_round(self) -> None:
        """Test class hierarchy."""
        assert issubclass(ClaimBondsRound, RecoveryTxsRound)

    def test_payload_class(self) -> None:
        """Test payload class inherited from RecoveryTxsRound."""
        assert ClaimBondsRound.payload_class == RecoveryTxsPayload


# ---------------------------------------------------------------------------
# BuildMultisendRound attribute tests
# ---------------------------------------------------------------------------


class TestBuildMultisendRound:
    """Tests for BuildMultisendRound attributes."""

    def test_inherits_collect_same(self) -> None:
        """Test class hierarchy."""
        assert issubclass(BuildMultisendRound, CollectSameUntilThresholdRound)

    def test_payload_class(self) -> None:
        """Test payload class."""
        assert BuildMultisendRound.payload_class == BuildMultisendPayload

    def test_synchronized_data_class(self) -> None:
        """Test synchronized data class."""
        assert BuildMultisendRound.synchronized_data_class == SynchronizedData

    def test_done_event(self) -> None:
        """Test done event."""
        assert BuildMultisendRound.done_event == Event.DONE

    def test_none_event(self) -> None:
        """Test none event."""
        assert BuildMultisendRound.none_event == Event.NONE

    def test_no_majority_event(self) -> None:
        """Test no majority event."""
        assert BuildMultisendRound.no_majority_event == Event.NO_MAJORITY

    def test_selection_key(self) -> None:
        """Test selection key."""
        assert BuildMultisendRound.selection_key == (
            get_name(SynchronizedData.tx_submitter),
            get_name(SynchronizedData.most_voted_tx_hash),
        )

    def test_collection_key(self) -> None:
        """Test collection key."""
        assert BuildMultisendRound.collection_key == get_name(
            SynchronizedData.participant_to_tx_prep
        )

    def test_none_event(self) -> None:
        """Test none event routes to FinishedWithoutRecoveryTxRound."""
        assert BuildMultisendRound.none_event == Event.NONE


# ---------------------------------------------------------------------------
# Final (Degenerate) Rounds
# ---------------------------------------------------------------------------


class TestFinalRounds:
    """Tests for degenerate (final) rounds."""

    def test_finished_with_recovery_tx_round(self) -> None:
        """Test FinishedWithRecoveryTxRound is degenerate."""
        assert issubclass(FinishedWithRecoveryTxRound, DegenerateRound)

    def test_finished_without_recovery_tx_round(self) -> None:
        """Test FinishedWithoutRecoveryTxRound is degenerate."""
        assert issubclass(FinishedWithoutRecoveryTxRound, DegenerateRound)


# ---------------------------------------------------------------------------
# OmenFundsRecovererAbciApp tests
# ---------------------------------------------------------------------------


@pytest.fixture
def abci_app() -> OmenFundsRecovererAbciApp:
    """Create an AbciApp instance."""
    synchronized_data = MagicMock(spec=SynchronizedData)
    logger = MagicMock()
    context = MagicMock()
    return OmenFundsRecovererAbciApp(synchronized_data, logger, context)


class TestAbciAppInitialization:
    """Test AbciApp initialization and configuration."""

    def test_initial_round_cls(self, abci_app: OmenFundsRecovererAbciApp) -> None:
        """Test initial round class."""
        assert abci_app.initial_round_cls is RemoveLiquidityRound

    def test_initial_states(self, abci_app: OmenFundsRecovererAbciApp) -> None:
        """Test initial states set."""
        expected = {RemoveLiquidityRound}
        assert abci_app.initial_states == expected

    def test_final_states(self, abci_app: OmenFundsRecovererAbciApp) -> None:
        """Test final states set."""
        expected = {
            FinishedWithRecoveryTxRound,
            FinishedWithoutRecoveryTxRound,
        }
        assert abci_app.final_states == expected


class TestRemoveLiquidityTransitions:
    """Test RemoveLiquidityRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, RedeemPositionsRound),
            (Event.NO_MAJORITY, RedeemPositionsRound),
            (Event.ROUND_TIMEOUT, RedeemPositionsRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: OmenFundsRecovererAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all RemoveLiquidityRound transitions."""
        tf = abci_app.transition_function[RemoveLiquidityRound]
        assert tf[event] == expected_next


class TestRedeemPositionsTransitions:
    """Test RedeemPositionsRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, ClaimBondsRound),
            (Event.NO_MAJORITY, ClaimBondsRound),
            (Event.ROUND_TIMEOUT, ClaimBondsRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: OmenFundsRecovererAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all RedeemPositionsRound transitions."""
        tf = abci_app.transition_function[RedeemPositionsRound]
        assert tf[event] == expected_next


class TestClaimBondsTransitions:
    """Test ClaimBondsRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, BuildMultisendRound),
            (Event.NO_MAJORITY, BuildMultisendRound),
            (Event.ROUND_TIMEOUT, BuildMultisendRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: OmenFundsRecovererAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all ClaimBondsRound transitions."""
        tf = abci_app.transition_function[ClaimBondsRound]
        assert tf[event] == expected_next


class TestBuildMultisendTransitions:
    """Test BuildMultisendRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, FinishedWithRecoveryTxRound),
            (Event.NONE, FinishedWithoutRecoveryTxRound),
            (Event.NO_MAJORITY, FinishedWithoutRecoveryTxRound),
            (Event.ROUND_TIMEOUT, FinishedWithoutRecoveryTxRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: OmenFundsRecovererAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all BuildMultisendRound transitions."""
        tf = abci_app.transition_function[BuildMultisendRound]
        assert tf[event] == expected_next


class TestFinalStateTransitions:
    """Test final state rounds have empty transition functions."""

    @pytest.mark.parametrize(
        "final_round",
        [
            FinishedWithRecoveryTxRound,
            FinishedWithoutRecoveryTxRound,
        ],
    )
    def test_empty_transitions(
        self,
        abci_app: OmenFundsRecovererAbciApp,
        final_round: type,
    ) -> None:
        """Test final states have empty transition functions."""
        assert abci_app.transition_function[final_round] == {}


class TestCrossPeriodPersistedKeys:
    """Test cross period persisted keys."""

    def test_keys(self, abci_app: OmenFundsRecovererAbciApp) -> None:
        """Test cross period persisted keys are empty."""
        assert abci_app.cross_period_persisted_keys == set()


class TestEventToTimeout:
    """Test event_to_timeout mapping."""

    def test_round_timeout(self, abci_app: OmenFundsRecovererAbciApp) -> None:
        """Test ROUND_TIMEOUT is mapped to 30.0."""
        assert abci_app.event_to_timeout[Event.ROUND_TIMEOUT] == 30.0

    def test_only_round_timeout(self, abci_app: OmenFundsRecovererAbciApp) -> None:
        """Test that only ROUND_TIMEOUT is in event_to_timeout."""
        assert set(abci_app.event_to_timeout.keys()) == {Event.ROUND_TIMEOUT}


class TestDbPreConditions:
    """Test db pre conditions."""

    def test_pre_conditions_empty(self, abci_app: OmenFundsRecovererAbciApp) -> None:
        """Test db pre conditions are empty for initial state."""
        assert abci_app.db_pre_conditions[RemoveLiquidityRound] == set()


class TestDbPostConditions:
    """Test db post conditions."""

    def test_post_conditions_with_tx_hash(
        self,
        abci_app: OmenFundsRecovererAbciApp,
    ) -> None:
        """Test post conditions containing most_voted_tx_hash."""
        assert (
            get_name(SynchronizedData.most_voted_tx_hash)
            in abci_app.db_post_conditions[FinishedWithRecoveryTxRound]
        )

    def test_post_conditions_empty(
        self,
        abci_app: OmenFundsRecovererAbciApp,
    ) -> None:
        """Test post conditions that are empty for FinishedWithoutRecoveryTxRound."""
        assert abci_app.db_post_conditions[FinishedWithoutRecoveryTxRound] == set()

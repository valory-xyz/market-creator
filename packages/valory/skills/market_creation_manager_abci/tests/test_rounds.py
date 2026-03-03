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

"""Tests for the MarketCreationManagerAbciApp FSM transitions."""

from unittest.mock import MagicMock

import pytest

from packages.valory.skills.abstract_round_abci.base import get_name
from packages.valory.skills.market_creation_manager_abci.rounds import (
    MarketCreationManagerAbciApp,
)
from packages.valory.skills.market_creation_manager_abci.states.answer_questions import (
    AnswerQuestionsRound,
)
from packages.valory.skills.market_creation_manager_abci.states.approve_markets import (
    ApproveMarketsRound,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)
from packages.valory.skills.market_creation_manager_abci.states.collect_proposed_markets import (
    CollectProposedMarketsRound,
)
from packages.valory.skills.market_creation_manager_abci.states.collect_randomness import (
    CollectRandomnessRound,
)
from packages.valory.skills.market_creation_manager_abci.states.deposit_dai import (
    DepositDaiRound,
)
from packages.valory.skills.market_creation_manager_abci.states.final_states import (
    FinishedMarketCreationManagerRound,
    FinishedWithAnswerQuestionsRound,
    FinishedWithDepositDaiRound,
    FinishedWithGetPendingQuestionsRound,
    FinishedWithMechRequestRound,
    FinishedWithRedeemBondRound,
    FinishedWithRemoveFundingRound,
    FinishedWithoutTxRound,
)
from packages.valory.skills.market_creation_manager_abci.states.get_pending_questions import (
    GetPendingQuestionsRound,
)
from packages.valory.skills.market_creation_manager_abci.states.post_transaction import (
    PostTransactionRound,
)
from packages.valory.skills.market_creation_manager_abci.states.prepare_transaction import (
    PrepareTransactionRound,
)
from packages.valory.skills.market_creation_manager_abci.states.redeem_bond import (
    RedeemBondRound,
)
from packages.valory.skills.market_creation_manager_abci.states.remove_funding import (
    RemoveFundingRound,
)
from packages.valory.skills.market_creation_manager_abci.states.retrieve_approved_market import (
    RetrieveApprovedMarketRound,
)
from packages.valory.skills.market_creation_manager_abci.states.select_keeper import (
    SelectKeeperRound,
)
from packages.valory.skills.market_creation_manager_abci.states.sync_markets import (
    SyncMarketsRound,
)


@pytest.fixture
def abci_app() -> MarketCreationManagerAbciApp:
    """Create an AbciApp instance."""
    synchronized_data = MagicMock(spec=SynchronizedData)
    logger = MagicMock()
    context = MagicMock()
    return MarketCreationManagerAbciApp(synchronized_data, logger, context)


class TestAbciAppInitialization:
    """Test AbciApp initialization and configuration."""

    def test_initial_round_cls(self, abci_app: MarketCreationManagerAbciApp) -> None:
        """Test initial round class."""
        assert abci_app.initial_round_cls is CollectRandomnessRound

    def test_initial_states(self, abci_app: MarketCreationManagerAbciApp) -> None:
        """Test initial states set."""
        expected = {
            AnswerQuestionsRound,
            CollectRandomnessRound,
            DepositDaiRound,
            PostTransactionRound,
            SyncMarketsRound,
            GetPendingQuestionsRound,
        }
        assert abci_app.initial_states == expected

    def test_final_states(self, abci_app: MarketCreationManagerAbciApp) -> None:
        """Test final states set."""
        expected = {
            FinishedMarketCreationManagerRound,
            FinishedWithAnswerQuestionsRound,
            FinishedWithMechRequestRound,
            FinishedWithRemoveFundingRound,
            FinishedWithDepositDaiRound,
            FinishedWithGetPendingQuestionsRound,
            FinishedWithRedeemBondRound,
            FinishedWithoutTxRound,
        }
        assert abci_app.final_states == expected


class TestDepositDaiTransitions:
    """Test DepositDaiRound transitions."""

    def test_done(self, abci_app: MarketCreationManagerAbciApp) -> None:
        """Test DONE transition."""
        tf = abci_app.transition_function[DepositDaiRound]
        assert tf[Event.DONE] == FinishedWithDepositDaiRound

    def test_no_majority(self, abci_app: MarketCreationManagerAbciApp) -> None:
        """Test NO_MAJORITY transition."""
        tf = abci_app.transition_function[DepositDaiRound]
        assert tf[Event.NO_MAJORITY] == GetPendingQuestionsRound

    def test_none(self, abci_app: MarketCreationManagerAbciApp) -> None:
        """Test NONE transition."""
        tf = abci_app.transition_function[DepositDaiRound]
        assert tf[Event.NONE] == GetPendingQuestionsRound

    def test_round_timeout(self, abci_app: MarketCreationManagerAbciApp) -> None:
        """Test ROUND_TIMEOUT transition."""
        tf = abci_app.transition_function[DepositDaiRound]
        assert tf[Event.ROUND_TIMEOUT] == GetPendingQuestionsRound


class TestPostTransactionTransitions:
    """Test PostTransactionRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, FinishedWithoutTxRound),
            (Event.ERROR, DepositDaiRound),
            (Event.NO_MAJORITY, PostTransactionRound),
            (Event.DEPOSIT_DAI_DONE, GetPendingQuestionsRound),
            (Event.MECH_REQUEST_DONE, FinishedWithMechRequestRound),
            (Event.ANSWER_QUESTION_DONE, CollectRandomnessRound),
            (Event.REDEEM_BOND_DONE, CollectProposedMarketsRound),
            (Event.REMOVE_FUNDING_DONE, DepositDaiRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: MarketCreationManagerAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all PostTransactionRound transitions."""
        tf = abci_app.transition_function[PostTransactionRound]
        assert tf[event] == expected_next


class TestGetPendingQuestionsTransitions:
    """Test GetPendingQuestionsRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, FinishedWithGetPendingQuestionsRound),
            (Event.NO_TX, CollectRandomnessRound),
            (Event.NO_MAJORITY, CollectRandomnessRound),
            (Event.ERROR, CollectRandomnessRound),
            (Event.ROUND_TIMEOUT, CollectRandomnessRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: MarketCreationManagerAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all GetPendingQuestionsRound transitions."""
        tf = abci_app.transition_function[GetPendingQuestionsRound]
        assert tf[event] == expected_next


class TestAnswerQuestionsTransitions:
    """Test AnswerQuestionsRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, FinishedWithAnswerQuestionsRound),
            (Event.NO_MAJORITY, CollectRandomnessRound),
            (Event.NONE, CollectRandomnessRound),
            (Event.ROUND_TIMEOUT, CollectRandomnessRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: MarketCreationManagerAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all AnswerQuestionsRound transitions."""
        tf = abci_app.transition_function[AnswerQuestionsRound]
        assert tf[event] == expected_next


class TestCollectRandomnessTransitions:
    """Test CollectRandomnessRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, SelectKeeperRound),
            (Event.NO_MAJORITY, CollectRandomnessRound),
            (Event.NONE, CollectRandomnessRound),
            (Event.ROUND_TIMEOUT, CollectRandomnessRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: MarketCreationManagerAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all CollectRandomnessRound transitions."""
        tf = abci_app.transition_function[CollectRandomnessRound]
        assert tf[event] == expected_next


class TestSelectKeeperTransitions:
    """Test SelectKeeperRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, RedeemBondRound),
            (Event.NO_MAJORITY, CollectRandomnessRound),
            (Event.NONE, CollectRandomnessRound),
            (Event.ROUND_TIMEOUT, CollectRandomnessRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: MarketCreationManagerAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all SelectKeeperRound transitions."""
        tf = abci_app.transition_function[SelectKeeperRound]
        assert tf[event] == expected_next


class TestRedeemBondTransitions:
    """Test RedeemBondRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, FinishedWithRedeemBondRound),
            (Event.NO_MAJORITY, CollectProposedMarketsRound),
            (Event.NONE, CollectProposedMarketsRound),
            (Event.ROUND_TIMEOUT, CollectProposedMarketsRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: MarketCreationManagerAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all RedeemBondRound transitions."""
        tf = abci_app.transition_function[RedeemBondRound]
        assert tf[event] == expected_next


class TestCollectProposedMarketsTransitions:
    """Test CollectProposedMarketsRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, ApproveMarketsRound),
            (Event.MAX_APPROVED_MARKETS_REACHED, RetrieveApprovedMarketRound),
            (Event.MAX_RETRIES_REACHED, RetrieveApprovedMarketRound),
            (Event.SKIP_MARKET_APPROVAL, RetrieveApprovedMarketRound),
            (Event.NO_MAJORITY, RetrieveApprovedMarketRound),
            (Event.ROUND_TIMEOUT, RetrieveApprovedMarketRound),
            (Event.ERROR, RetrieveApprovedMarketRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: MarketCreationManagerAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all CollectProposedMarketsRound transitions."""
        tf = abci_app.transition_function[CollectProposedMarketsRound]
        assert tf[event] == expected_next


class TestApproveMarketsTransitions:
    """Test ApproveMarketsRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, RetrieveApprovedMarketRound),
            (Event.ROUND_TIMEOUT, RetrieveApprovedMarketRound),
            (Event.MAX_RETRIES_REACHED, RetrieveApprovedMarketRound),
            (Event.ERROR, RetrieveApprovedMarketRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: MarketCreationManagerAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all ApproveMarketsRound transitions."""
        tf = abci_app.transition_function[ApproveMarketsRound]
        assert tf[event] == expected_next


class TestRetrieveApprovedMarketTransitions:
    """Test RetrieveApprovedMarketRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, PrepareTransactionRound),
            (Event.NO_MAJORITY, FinishedWithoutTxRound),
            (Event.NONE, FinishedWithoutTxRound),
            (Event.ROUND_TIMEOUT, FinishedWithoutTxRound),
            (Event.DID_NOT_SEND, FinishedWithoutTxRound),
            (Event.ERROR, FinishedWithoutTxRound),
            (Event.NO_MARKETS_RETRIEVED, FinishedWithoutTxRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: MarketCreationManagerAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all RetrieveApprovedMarketRound transitions."""
        tf = abci_app.transition_function[RetrieveApprovedMarketRound]
        assert tf[event] == expected_next


class TestPrepareTransactionTransitions:
    """Test PrepareTransactionRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, FinishedMarketCreationManagerRound),
            (Event.NO_MAJORITY, FinishedWithoutTxRound),
            (Event.NONE, FinishedWithoutTxRound),
            (Event.ROUND_TIMEOUT, FinishedWithoutTxRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: MarketCreationManagerAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all PrepareTransactionRound transitions."""
        tf = abci_app.transition_function[PrepareTransactionRound]
        assert tf[event] == expected_next


class TestSyncMarketsTransitions:
    """Test SyncMarketsRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, RemoveFundingRound),
            (Event.NO_MAJORITY, DepositDaiRound),
            (Event.ERROR, DepositDaiRound),
            (Event.ROUND_TIMEOUT, DepositDaiRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: MarketCreationManagerAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all SyncMarketsRound transitions."""
        tf = abci_app.transition_function[SyncMarketsRound]
        assert tf[event] == expected_next


class TestRemoveFundingTransitions:
    """Test RemoveFundingRound transitions."""

    @pytest.mark.parametrize(
        "event,expected_next",
        [
            (Event.DONE, FinishedWithRemoveFundingRound),
            (Event.NONE, DepositDaiRound),
            (Event.NO_MAJORITY, DepositDaiRound),
            (Event.ROUND_TIMEOUT, DepositDaiRound),
            (Event.NO_TX, DepositDaiRound),
            (Event.ERROR, DepositDaiRound),
        ],
    )
    def test_transitions(
        self,
        abci_app: MarketCreationManagerAbciApp,
        event: Event,
        expected_next: type,
    ) -> None:
        """Test all RemoveFundingRound transitions."""
        tf = abci_app.transition_function[RemoveFundingRound]
        assert tf[event] == expected_next


class TestFinalStateTransitions:
    """Test final state rounds have empty transition functions."""

    @pytest.mark.parametrize(
        "final_round",
        [
            FinishedMarketCreationManagerRound,
            FinishedWithAnswerQuestionsRound,
            FinishedWithMechRequestRound,
            FinishedWithRemoveFundingRound,
            FinishedWithDepositDaiRound,
            FinishedWithGetPendingQuestionsRound,
            FinishedWithRedeemBondRound,
            FinishedWithoutTxRound,
        ],
    )
    def test_empty_transitions(
        self,
        abci_app: MarketCreationManagerAbciApp,
        final_round: type,
    ) -> None:
        """Test final states have empty transition functions."""
        assert abci_app.transition_function[final_round] == {}


class TestCrossPeriodPersistedKeys:
    """Test cross period persisted keys."""

    def test_keys(self, abci_app: MarketCreationManagerAbciApp) -> None:
        """Test cross period persisted keys."""
        assert abci_app.cross_period_persisted_keys == {
            get_name(SynchronizedData.proposed_markets_count),
            get_name(SynchronizedData.proposed_markets_data),
            get_name(SynchronizedData.approved_markets_count),
            get_name(SynchronizedData.approved_markets_timestamp),
            get_name(SynchronizedData.mech_responses),
        }


class TestDbPreConditions:
    """Test db pre conditions."""

    @pytest.mark.parametrize(
        "round_cls",
        [
            AnswerQuestionsRound,
            DepositDaiRound,
            GetPendingQuestionsRound,
            CollectRandomnessRound,
            PostTransactionRound,
            SyncMarketsRound,
        ],
    )
    def test_pre_conditions_empty(
        self,
        abci_app: MarketCreationManagerAbciApp,
        round_cls: type,
    ) -> None:
        """Test db pre conditions are empty for initial states."""
        assert abci_app.db_pre_conditions[round_cls] == set()


class TestDbPostConditions:
    """Test db post conditions."""

    @pytest.mark.parametrize(
        "final_round",
        [
            FinishedWithAnswerQuestionsRound,
            FinishedWithDepositDaiRound,
            FinishedWithRedeemBondRound,
            FinishedMarketCreationManagerRound,
            FinishedWithRemoveFundingRound,
        ],
    )
    def test_post_conditions_with_tx_hash(
        self,
        abci_app: MarketCreationManagerAbciApp,
        final_round: type,
    ) -> None:
        """Test post conditions containing most_voted_tx_hash."""
        assert (
            get_name(SynchronizedData.most_voted_tx_hash)
            in abci_app.db_post_conditions[final_round]
        )

    @pytest.mark.parametrize(
        "final_round",
        [
            FinishedWithMechRequestRound,
            FinishedWithGetPendingQuestionsRound,
            FinishedWithoutTxRound,
        ],
    )
    def test_post_conditions_empty(
        self,
        abci_app: MarketCreationManagerAbciApp,
        final_round: type,
    ) -> None:
        """Test post conditions that are empty."""
        assert abci_app.db_post_conditions[final_round] == set()

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

"""Tests for PostTransactionBehaviour."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import packages.valory.skills.mech_interact_abci.states.request as MechRequestStates
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.post_transaction import (
    PostTransactionBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    AnswerQuestionsRound,
    DepositDaiRound,
    RedeemBondRound,
    RedeemWinningsRound,
    RemoveFundingRound,
)
from packages.valory.skills.market_creation_manager_abci.states.post_transaction import (
    PostTransactionRound,
)


def _make_gen(return_value: Any) -> Any:
    """Create a no-yield generator returning the given value."""

    def gen(*args: Any, **kwargs: Any) -> Any:
        return return_value
        yield  # noqa: unreachable - makes this a generator function

    return gen


def _exhaust_gen(gen: Any) -> Any:
    """Exhaust a generator and return its value."""
    try:
        while True:
            next(gen)
    except StopIteration as e:
        return e.value


class TestPostTransactionBehaviour:
    """Tests for PostTransactionBehaviour."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.market_approval_server_url = "http://example.com"
        context_mock.params.market_approval_server_api_key = "test-key"
        context_mock.params.fpmm_deterministic_factory_contract = "0xFactory"
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.synchronized_data = MagicMock()
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        self.behaviour: Any = PostTransactionBehaviour(
            name="test", skill_context=context_mock
        )

    def test_get_payload_no_settled_tx(self) -> None:
        """Test get_payload when settled_tx_hash is None."""
        self.behaviour.synchronized_data.settled_tx_hash = None

        gen = self.behaviour.get_payload()
        result = _exhaust_gen(gen)

        assert result == PostTransactionRound.DONE_PAYLOAD

    def test_get_payload_mech_request_submitter(self) -> None:
        """Test get_payload when tx_submitter is MechRequestRound."""
        self.behaviour.synchronized_data.settled_tx_hash = "0xabc"
        self.behaviour.synchronized_data.tx_submitter = (
            MechRequestStates.MechRequestRound.auto_round_id()
        )

        gen = self.behaviour.get_payload()
        result = _exhaust_gen(gen)

        assert result == PostTransactionRound.MECH_REQUEST_DONE_PAYLOAD

    def test_get_payload_redeem_bond_submitter(self) -> None:
        """Test get_payload when tx_submitter is RedeemBondRound."""
        self.behaviour.synchronized_data.settled_tx_hash = "0xabc"
        self.behaviour.synchronized_data.tx_submitter = RedeemBondRound.auto_round_id()

        gen = self.behaviour.get_payload()
        result = _exhaust_gen(gen)

        assert result == PostTransactionRound.REDEEM_BOND_DONE_PAYLOAD

    def test_get_payload_deposit_dai_submitter(self) -> None:
        """Test get_payload when tx_submitter is DepositDaiRound."""
        self.behaviour.synchronized_data.settled_tx_hash = "0xabc"
        self.behaviour.synchronized_data.tx_submitter = DepositDaiRound.auto_round_id()

        gen = self.behaviour.get_payload()
        result = _exhaust_gen(gen)

        assert result == PostTransactionRound.DEPOSIT_DAI_DONE_PAYLOAD

    def test_get_payload_answer_questions_submitter(self) -> None:
        """Test get_payload when tx_submitter is AnswerQuestionsRound."""
        self.behaviour.synchronized_data.settled_tx_hash = "0xabc"
        self.behaviour.synchronized_data.tx_submitter = (
            AnswerQuestionsRound.auto_round_id()
        )

        gen = self.behaviour.get_payload()
        result = _exhaust_gen(gen)

        assert result == PostTransactionRound.ANSWER_QUESTION_DONE_PAYLOAD

    def test_get_payload_remove_funding_submitter(self) -> None:
        """Test get_payload when tx_submitter is RemoveFundingRound."""
        self.behaviour.synchronized_data.settled_tx_hash = "0xabc"
        self.behaviour.synchronized_data.tx_submitter = (
            RemoveFundingRound.auto_round_id()
        )

        gen = self.behaviour.get_payload()
        result = _exhaust_gen(gen)

        assert result == PostTransactionRound.REMOVE_FUNDING_DONE_PAYLOAD

    def test_get_payload_redeem_winnings_submitter(self) -> None:
        """Test get_payload when tx_submitter is RedeemWinningsRound."""
        self.behaviour.synchronized_data.settled_tx_hash = "0xabc"
        self.behaviour.synchronized_data.tx_submitter = (
            RedeemWinningsRound.auto_round_id()
        )

        gen = self.behaviour.get_payload()
        result = _exhaust_gen(gen)

        assert result == PostTransactionRound.REDEEM_WINNINGS_DONE_PAYLOAD

    def test_get_payload_no_approved_question_data(self) -> None:
        """Test get_payload when is_approved_question_data_set is False."""
        self.behaviour.synchronized_data.settled_tx_hash = "0xabc"
        self.behaviour.synchronized_data.tx_submitter = "some_other_round"
        self.behaviour.synchronized_data.is_approved_question_data_set = False

        gen = self.behaviour.get_payload()
        result = _exhaust_gen(gen)

        assert result == PostTransactionRound.DONE_PAYLOAD

    def test_get_payload_no_market_id(self) -> None:
        """Test get_payload when approved_question_data has no 'id'."""
        self.behaviour.synchronized_data.settled_tx_hash = "0xabc"
        self.behaviour.synchronized_data.tx_submitter = "some_other_round"
        self.behaviour.synchronized_data.is_approved_question_data_set = True
        self.behaviour.synchronized_data.approved_question_data = {
            "title": "some market"
        }

        gen = self.behaviour.get_payload()
        result = _exhaust_gen(gen)

        assert result == PostTransactionRound.DONE_PAYLOAD

    def test_get_payload_non_prepare_tx_submitter(self) -> None:
        """Test get_payload when tx_submitter is not PrepareTransactionRound."""
        self.behaviour.synchronized_data.settled_tx_hash = "0xabc"
        self.behaviour.synchronized_data.tx_submitter = "some_other_round"
        self.behaviour.synchronized_data.is_approved_question_data_set = True
        self.behaviour.synchronized_data.approved_question_data = {"id": "market_1"}

        gen = self.behaviour.get_payload()
        result = _exhaust_gen(gen)

        assert result == PostTransactionRound.DONE_PAYLOAD

    def test_get_fpmm_id_success(self) -> None:
        """Test _get_fpmm_id with successful contract API response."""
        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.STATE
        mock_resp.state.body = {"data": {"fixed_product_market_maker": "0xFPMM123"}}

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_fpmm_id("0xTxHash")
            result = _exhaust_gen(gen)

        assert result == "0xFPMM123"

    def test_get_fpmm_id_failure(self) -> None:
        """Test _get_fpmm_id when contract API returns wrong performative."""
        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_fpmm_id("0xTxHash")
            result = _exhaust_gen(gen)

        assert result is None

    def test_mark_market_as_done_success(self) -> None:
        """Test _mark_market_as_done when both HTTP PUTs return 200."""
        mock_resp_1 = MagicMock()
        mock_resp_1.status_code = 200
        mock_resp_1.body = json.dumps({"status": "ok"}).encode()

        mock_resp_2 = MagicMock()
        mock_resp_2.status_code = 200
        mock_resp_2.body = json.dumps({"status": "ok"}).encode()

        call_count = 0

        def mock_http_gen(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_resp_1
            return mock_resp_2
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_http_response",
            new=mock_http_gen,
        ):
            gen = self.behaviour._mark_market_as_done("market_1", "0xFPMM")
            result = _exhaust_gen(gen)

        assert result is None

    def test_mark_market_as_done_first_put_fails(self) -> None:
        """Test _mark_market_as_done when first PUT returns 400."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.body = b"Bad Request"

        with patch.object(
            self.behaviour,
            "get_http_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._mark_market_as_done("market_1", "0xFPMM")
            result = _exhaust_gen(gen)

        assert result is not None

    def test_mark_market_as_done_second_put_fails(self) -> None:
        """Test _mark_market_as_done when first PUT OK, second PUT fails."""
        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.body = json.dumps({"status": "ok"}).encode()

        mock_resp_fail = MagicMock()
        mock_resp_fail.status_code = 400
        mock_resp_fail.body = b"Bad Request"

        call_count = 0

        def mock_http_gen(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_resp_ok
            return mock_resp_fail
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_http_response",
            new=mock_http_gen,
        ):
            gen = self.behaviour._mark_market_as_done("market_1", "0xFPMM")
            result = _exhaust_gen(gen)

        assert result is not None

    def test_handle_market_creation_fpmm_none(self) -> None:
        """Test _handle_market_creation when _get_fpmm_id returns None."""
        with patch.object(
            self.behaviour,
            "_get_fpmm_id",
            new=_make_gen(None),
        ):
            gen = self.behaviour._handle_market_creation("market_1", "0xTx")
            result = _exhaust_gen(gen)

        assert result == PostTransactionRound.ERROR_PAYLOAD

    def test_handle_market_creation_mark_done_error(self) -> None:
        """Test _handle_market_creation when _mark_market_as_done returns error."""
        with patch.object(
            self.behaviour,
            "_get_fpmm_id",
            new=_make_gen("0xFPMM123"),
        ), patch.object(
            self.behaviour,
            "_mark_market_as_done",
            new=_make_gen("some error"),
        ):
            gen = self.behaviour._handle_market_creation("market_1", "0xTx")
            result = _exhaust_gen(gen)

        assert result == PostTransactionRound.ERROR_PAYLOAD

    def test_handle_market_creation_success(self) -> None:
        """Test _handle_market_creation happy path."""
        with patch.object(
            self.behaviour,
            "_get_fpmm_id",
            new=_make_gen("0xFPMM123"),
        ), patch.object(
            self.behaviour,
            "_mark_market_as_done",
            new=_make_gen(None),
        ):
            gen = self.behaviour._handle_market_creation("market_1", "0xTx")
            result = _exhaust_gen(gen)

        assert result == PostTransactionRound.DONE_PAYLOAD

    def test_async_act(self) -> None:
        """Test async_act wraps get_payload correctly."""
        with patch.object(
            self.behaviour,
            "get_payload",
            new=_make_gen(PostTransactionRound.DONE_PAYLOAD),
        ), patch.object(
            self.behaviour, "send_a2a_transaction", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "wait_until_round_end", new=_make_gen(None)
        ), patch.object(
            self.behaviour, "set_done"
        ) as mock_set_done:
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)
            mock_set_done.assert_called_once()

    def test_get_payload_prepare_tx_submitter(self) -> None:
        """Test get_payload when tx_submitter is PrepareTransactionRound."""
        from packages.valory.skills.market_creation_manager_abci.rounds import (
            PrepareTransactionRound,
        )

        self.behaviour.synchronized_data.settled_tx_hash = "0xabc"
        self.behaviour.synchronized_data.tx_submitter = (
            PrepareTransactionRound.auto_round_id()
        )
        self.behaviour.synchronized_data.is_approved_question_data_set = True
        self.behaviour.synchronized_data.approved_question_data = {"id": "market_1"}

        with patch.object(
            self.behaviour,
            "_handle_market_creation",
            new=_make_gen(PostTransactionRound.DONE_PAYLOAD),
        ):
            gen = self.behaviour.get_payload()
            result = _exhaust_gen(gen)

        assert result == PostTransactionRound.DONE_PAYLOAD

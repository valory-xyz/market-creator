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

"""Tests for RealitioWithdrawBondBehaviour."""

# Standard pytest test-file conventions that pylint flags as code smells.
# These disables match the idiomatic patterns used across the OA
# ecosystem for setup_method-based test classes, protected-member
# patching, and fixture-heavy test scaffolding.
# pylint: disable=protected-access,attribute-defined-outside-init
# pylint: disable=unused-argument,import-outside-toplevel
# pylint: disable=too-many-public-methods,too-many-lines
# pylint: disable=unsubscriptable-object,use-implicit-booleaness-not-comparison
# pylint: disable=unpacking-non-sequence

import contextlib
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from packages.valory.skills.omen_realitio_withdraw_bond_abci.behaviours.base import (
    ETHER_VALUE,
)
from packages.valory.skills.omen_realitio_withdraw_bond_abci.behaviours.withdraw_bond import (
    RealitioWithdrawBondBehaviour,
    TX_SUBMITTER,
)
from packages.valory.skills.omen_realitio_withdraw_bond_abci.tests.behaviours.conftest import (
    exhaust_gen,
    make_contract_error_response,
    make_contract_state_response,
    make_gen,
)


class TestRealitioWithdrawBondBehaviour:
    """Tests for RealitioWithdrawBondBehaviour."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.realitio_contract = "0xRealitio"
        context_mock.params.realitio_withdraw_bond_batch_size = 10
        context_mock.params.min_realitio_withdraw_balance = 10000000000000000000
        context_mock.params.multisend_address = "0xMultisend"
        context_mock.state.round_sequence = MagicMock()
        context_mock.state.round_sequence.last_round_transition_timestamp.timestamp.return_value = (
            1700100000
        )
        context_mock.state.synchronized_data = MagicMock()
        context_mock.state.synchronized_data.safe_contract_address = "0xSafe"
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.realitio_subgraph = MagicMock()
        context_mock.realitio_subgraph.get_spec.return_value = {
            "method": "POST",
            "url": "https://realitio.example.com",
        }
        self.behaviour: Any = RealitioWithdrawBondBehaviour(
            name="test", skill_context=context_mock
        )

    # ─── _get_claim_params (verbatim port from baseline) ─────────────────────

    def test_get_claim_params_success(self) -> None:
        """Test _get_claim_params transforms raw events into the claimWinnings 4-tuple."""
        # Two chronological entries: oldest first.
        answered = [
            {
                "args": {
                    "user": "0xUserOld",
                    "bond": 100,
                    "answer": b"\x00" * 32,
                    "history_hash": b"\xaa" * 32,
                }
            },
            {
                "args": {
                    "user": "0xUserNew",
                    "bond": 200,
                    "answer": b"\x01" + b"\x00" * 31,
                    "history_hash": b"\xbb" * 32,
                }
            },
        ]
        resp = make_contract_state_response({"answered": answered})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._get_claim_params(b"\x01" * 32, from_block=12345)
            result = exhaust_gen(gen)
        history_hashes, addrs, bonds, answers = result
        assert addrs == ["0xUserNew", "0xUserOld"]
        assert bonds == [200, 100]
        assert answers == [b"\x01" + b"\x00" * 31, b"\x00" * 32]
        # The newest entry's prior hash is the older entry's stored
        # hash; the oldest entry's prior hash is ZERO_BYTES32.
        assert history_hashes == [b"\xaa" * 32, b"\x00" * 32]

    @pytest.mark.parametrize(
        "description,response_body",
        [
            ("contract error", None),
            ("body contains error key", {"error": "something went wrong"}),
            ("empty answers list", {"answered": []}),
            ("answered is None", {"answered": None}),
        ],
    )
    def test_get_claim_params_returns_none(
        self, description: str, response_body: Any
    ) -> None:
        """Test _get_claim_params returns None on various failure modes."""
        if response_body is None:
            resp = make_contract_error_response()
        else:
            resp = make_contract_state_response(response_body)
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._get_claim_params(b"\x01" * 32, from_block=12345)
            result = exhaust_gen(gen)
        assert result is None

    # ─── _simulate_claim ─────────────────────────────────────────────────────

    def test_simulate_claim_success(self) -> None:
        """Test _simulate_claim returns True when simulation succeeds."""
        resp = make_contract_state_response({"data": True})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._simulate_claim(b"\x01" * 32, [{"p": "v"}])
            result = exhaust_gen(gen)
        assert result is True

    def test_simulate_claim_failure(self) -> None:
        """Test _simulate_claim returns False when simulation fails."""
        resp = make_contract_state_response({"data": False})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._simulate_claim(b"\x01" * 32, [{"p": "v"}])
            result = exhaust_gen(gen)
        assert result is False

    def test_simulate_claim_error(self) -> None:
        """Test _simulate_claim returns False on contract error."""
        resp = make_contract_error_response()
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._simulate_claim(b"\x01" * 32, [{"p": "v"}])
            result = exhaust_gen(gen)
        assert result is False

    # ─── _build_claim_tx ─────────────────────────────────────────────────────

    def test_build_claim_tx_success(self) -> None:
        """Test _build_claim_tx builds tx dict on success."""
        resp = make_contract_state_response({"data": "0xClaimData"})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._build_claim_tx(b"\x01" * 32, [{"p": "v"}])
            result = exhaust_gen(gen)
        assert result is not None
        assert result["to"] == "0xRealitio"
        assert result["data"] == "0xClaimData"
        assert result["value"] == ETHER_VALUE

    def test_build_claim_tx_with_bytes_data(self) -> None:
        """Test _build_claim_tx when contract returns bytes data."""
        resp = make_contract_state_response({"data": b"\xef\x01"})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._build_claim_tx(b"\x01" * 32, [{"p": "v"}])
            result = exhaust_gen(gen)
        assert result is not None
        assert result["data"] == "ef01"

    def test_build_claim_tx_error(self) -> None:
        """Test _build_claim_tx returns None on error."""
        resp = make_contract_error_response()
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._build_claim_tx(b"\x01" * 32, [{"p": "v"}])
            result = exhaust_gen(gen)
        assert result is None

    # ─── _maybe_build_withdraw_tx ────────────────────────────────────────────

    def test_maybe_build_withdraw_tx_below_threshold(self) -> None:
        """Test _maybe_build_withdraw_tx returns None when balance below threshold."""
        # balance of 100 wei is below min_realitio_withdraw_balance threshold
        resp = make_contract_state_response({"data": 100})
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._maybe_build_withdraw_tx()
            result = exhaust_gen(gen)
        assert result is None

    def test_maybe_build_withdraw_tx_above_threshold(self) -> None:
        """Test _maybe_build_withdraw_tx builds withdraw tx when above threshold."""
        balance_resp = make_contract_state_response({"data": 20000000000000000000})
        withdraw_resp = make_contract_state_response({"data": "0xWithdrawData"})

        call_count = 0

        def mock_contract_gen(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return balance_resp
            return withdraw_resp
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=mock_contract_gen,
        ):
            gen = self.behaviour._maybe_build_withdraw_tx()
            result = exhaust_gen(gen)

        assert result is not None
        assert result["to"] == "0xRealitio"
        assert result["data"] == "0xWithdrawData"

    def test_maybe_build_withdraw_tx_balance_error(self) -> None:
        """Test _maybe_build_withdraw_tx returns None on balance query error."""
        resp = make_contract_error_response()
        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=make_gen(resp),
        ):
            gen = self.behaviour._maybe_build_withdraw_tx()
            result = exhaust_gen(gen)
        assert result is None

    def test_maybe_build_withdraw_tx_withdraw_error(self) -> None:
        """Test _maybe_build_withdraw_tx returns None when withdraw tx build fails."""
        balance_resp = make_contract_state_response({"data": 20000000000000000000})
        error_resp = make_contract_error_response()

        call_count = 0

        def mock_contract_gen(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return balance_resp
            return error_resp
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=mock_contract_gen,
        ):
            gen = self.behaviour._maybe_build_withdraw_tx()
            result = exhaust_gen(gen)
        assert result is None

    # ─── async_act ───────────────────────────────────────────────────────────

    def test_async_act_with_tx(self) -> None:
        """async_act produces a payload with tx_hash + tx_submitter when there's work."""
        captured_payload: Dict[str, Any] = {}

        def fake_send(payload: Any) -> Any:
            captured_payload["payload"] = payload
            return None
            yield  # noqa

        with (
            patch.object(
                self.behaviour, "_prepare_multisend", new=make_gen("0xdeadbeef")
            ),
            patch.object(self.behaviour, "send_a2a_transaction", new=fake_send),
            patch.object(self.behaviour, "wait_until_round_end", new=make_gen(None)),
            patch.object(self.behaviour, "set_done") as mock_set_done,
        ):
            gen = self.behaviour.async_act()
            exhaust_gen(gen)
            mock_set_done.assert_called_once()

        payload = captured_payload["payload"]
        assert payload.tx_hash == "0xdeadbeef"
        assert payload.tx_submitter == TX_SUBMITTER

    def test_async_act_without_tx(self) -> None:
        """async_act produces a payload with both fields None when nothing to do."""
        captured_payload: Dict[str, Any] = {}

        def fake_send(payload: Any) -> Any:
            captured_payload["payload"] = payload
            return None
            yield  # noqa

        with (
            patch.object(self.behaviour, "_prepare_multisend", new=make_gen(None)),
            patch.object(self.behaviour, "send_a2a_transaction", new=fake_send),
            patch.object(self.behaviour, "wait_until_round_end", new=make_gen(None)),
            patch.object(self.behaviour, "set_done") as mock_set_done,
        ):
            gen = self.behaviour.async_act()
            exhaust_gen(gen)
            mock_set_done.assert_called_once()

        payload = captured_payload["payload"]
        assert payload.tx_hash is None
        assert payload.tx_submitter is None

    # ─── _prepare_multisend (the pipeline) ───────────────────────────────────

    def test_prepare_multisend_no_responses_no_withdraw(self) -> None:
        """_prepare_multisend returns None when nothing to do."""
        with (
            patch.object(self.behaviour, "_get_claimable_responses", new=make_gen([])),
            patch.object(
                self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(None)
            ),
        ):
            gen = self.behaviour._prepare_multisend()
            result = exhaust_gen(gen)
        assert result is None

    def test_prepare_multisend_no_responses_with_withdraw(self) -> None:
        """_prepare_multisend wraps just the withdraw tx in a multisend."""
        withdraw_tx = {"to": "0xR", "data": "0xw", "value": 0}
        captured_txs: Dict[str, Any] = {}

        def fake_to_multisend(txs: List[Dict[str, Any]]) -> Any:
            captured_txs["txs"] = txs
            return "0xmultihash"
            yield  # noqa

        with (
            patch.object(self.behaviour, "_get_claimable_responses", new=make_gen([])),
            patch.object(
                self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(withdraw_tx)
            ),
            patch.object(self.behaviour, "_to_multisend", new=fake_to_multisend),
        ):
            gen = self.behaviour._prepare_multisend()
            result = exhaust_gen(gen)
        assert result == "0xmultihash"
        assert captured_txs["txs"] == [withdraw_tx]

    def test_prepare_multisend_claim_and_withdraw_ordering(self) -> None:
        """Withdraw is FIRST in the multisend, claims follow (Fix A from claim_bonds_fix.md)."""
        responses = [
            {"question": {"id": "0xabcd", "createdBlock": "12345"}, "bond": "100"}
        ]
        claim_tx = {"to": "0xR", "data": "0xclaim", "value": 0}
        withdraw_tx = {"to": "0xR", "data": "0xw", "value": 0}
        captured_txs: Dict[str, Any] = {}

        def fake_to_multisend(txs: List[Dict[str, Any]]) -> Any:
            captured_txs["txs"] = txs
            return "0xmultihash"
            yield  # noqa

        with (
            patch.object(
                self.behaviour, "_get_claimable_responses", new=make_gen(responses)
            ),
            patch.object(
                self.behaviour, "_get_claim_params", new=make_gen([{"p": "v"}])
            ),
            patch.object(self.behaviour, "_simulate_claim", new=make_gen(True)),
            patch.object(self.behaviour, "_build_claim_tx", new=make_gen(claim_tx)),
            patch.object(
                self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(withdraw_tx)
            ),
            patch.object(self.behaviour, "_to_multisend", new=fake_to_multisend),
        ):
            gen = self.behaviour._prepare_multisend()
            result = exhaust_gen(gen)
        assert result == "0xmultihash"
        assert len(captured_txs["txs"]) == 2
        # Withdraw is built first so it gets queued even if the claim
        # loop is slow or partially fails (Fix A).
        assert captured_txs["txs"][0] == withdraw_tx
        assert captured_txs["txs"][1] == claim_tx

    def test_prepare_multisend_to_multisend_failure(self) -> None:
        """_prepare_multisend returns None when the multisend wrap fails."""
        withdraw_tx = {"to": "0xR", "data": "0xw", "value": 0}
        with (
            patch.object(self.behaviour, "_get_claimable_responses", new=make_gen([])),
            patch.object(
                self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(withdraw_tx)
            ),
            patch.object(self.behaviour, "_to_multisend", new=make_gen(None)),
        ):
            gen = self.behaviour._prepare_multisend()
            result = exhaust_gen(gen)
        assert result is None

    @pytest.mark.parametrize(
        "description,claim_params,simulate_ok,build_tx",
        [
            ("claim params fail", None, None, None),
            ("simulation fail", [{"p": "v"}], False, None),
            ("build claim tx fail", [{"p": "v"}], True, None),
        ],
    )
    def test_prepare_multisend_single_claim_failure(
        self,
        description: str,
        claim_params: Any,
        simulate_ok: Any,
        build_tx: Any,
    ) -> None:
        """_prepare_multisend skips claims that fail in the chain.

        With no withdraw and the only claim failing at some step, the
        result is None (no txs to wrap).

        :param description: parametrized scenario name.
        :param claim_params: mocked _get_claim_params return value.
        :param simulate_ok: mocked _simulate_claiming return value.
        :param build_tx: mocked _build_claim_tx return value.
        """
        responses = [
            {"question": {"id": "0xabcd", "createdBlock": "12345"}, "bond": "100"}
        ]

        patches = [
            patch.object(
                self.behaviour, "_get_claimable_responses", new=make_gen(responses)
            ),
            patch.object(
                self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(None)
            ),
            patch.object(
                self.behaviour, "_get_claim_params", new=make_gen(claim_params)
            ),
        ]
        # Only add patches for steps that are actually reached.
        if claim_params is not None:
            patches.append(
                patch.object(
                    self.behaviour, "_simulate_claim", new=make_gen(simulate_ok)
                )
            )
        if simulate_ok:
            patches.append(
                patch.object(self.behaviour, "_build_claim_tx", new=make_gen(build_tx))
            )

        with patches[0]:
            with contextlib.ExitStack() as stack:
                for p in patches[1:]:
                    stack.enter_context(p)
                gen = self.behaviour._prepare_multisend()
                result = exhaust_gen(gen)
        assert result is None

    # ─── _build_claim_txs (batching, dedup) ──────────────────────────────────

    def test_build_claim_txs_batch_size_limit(self) -> None:
        """_build_claim_txs stops after reaching realitio_withdraw_bond_batch_size."""
        self.behaviour.context.params.realitio_withdraw_bond_batch_size = 1
        responses = [
            {"question": {"id": "0xaaaa", "createdBlock": "111"}, "bond": "100"},
            {"question": {"id": "0xbbbb", "createdBlock": "222"}, "bond": "200"},
        ]
        claim_tx = {"to": "0xR", "data": "0xclaim", "value": 0}

        with (
            patch.object(
                self.behaviour, "_get_claimable_responses", new=make_gen(responses)
            ),
            patch.object(
                self.behaviour, "_get_claim_params", new=make_gen([{"p": "v"}])
            ),
            patch.object(self.behaviour, "_simulate_claim", new=make_gen(True)),
            patch.object(self.behaviour, "_build_claim_tx", new=make_gen(claim_tx)),
        ):
            gen = self.behaviour._build_claim_txs()
            result = exhaust_gen(gen)
        # Only 1 tx even though there are 2 responses.
        assert len(result) == 1

    def test_build_claim_txs_deduplicates_by_question_id(self) -> None:
        """Multiple responses on the same question produce at most one claim tx (Fix F)."""
        responses = [
            {"question": {"id": "0xaaaa", "createdBlock": "111"}, "bond": "100"},
            {"question": {"id": "0xaaaa", "createdBlock": "111"}, "bond": "200"},
            {"question": {"id": "0xbbbb", "createdBlock": "222"}, "bond": "300"},
        ]
        claim_tx = {"to": "0xR", "data": "0xclaim", "value": 0}
        call_count = 0

        def counting_try_build(_: Any) -> Any:
            nonlocal call_count
            call_count += 1
            return claim_tx
            yield  # noqa

        with (
            patch.object(
                self.behaviour, "_get_claimable_responses", new=make_gen(responses)
            ),
            patch.object(
                self.behaviour, "_try_build_single_claim", new=counting_try_build
            ),
        ):
            gen = self.behaviour._build_claim_txs()
            result = exhaust_gen(gen)
        assert len(result) == 2
        # _try_build_single_claim was only called once per UNIQUE
        # question, not three times.
        assert call_count == 2

    def test_build_claim_txs_skips_responses_without_question_id(self) -> None:
        """Malformed subgraph responses missing question.id are skipped."""
        responses = [
            {"question": {}, "bond": "100"},  # missing id
            {"question": {"id": "0xbbbb", "createdBlock": "222"}, "bond": "200"},
        ]
        claim_tx = {"to": "0xR", "data": "0xclaim", "value": 0}
        seen_qids: list = []

        def record_try_build(resp: Any) -> Any:
            seen_qids.append(resp["question"].get("id"))
            return claim_tx
            yield  # noqa

        with (
            patch.object(
                self.behaviour, "_get_claimable_responses", new=make_gen(responses)
            ),
            patch.object(
                self.behaviour, "_try_build_single_claim", new=record_try_build
            ),
        ):
            gen = self.behaviour._build_claim_txs()
            result = exhaust_gen(gen)
        assert len(result) == 1
        assert seen_qids == ["0xbbbb"]

    def test_build_claim_txs_empty_when_no_responses(self) -> None:
        """_build_claim_txs returns empty list when subgraph yields no responses."""
        with patch.object(self.behaviour, "_get_claimable_responses", new=make_gen([])):
            gen = self.behaviour._build_claim_txs()
            result = exhaust_gen(gen)
        assert result == []

    # ─── _get_claimable_responses (subgraph filter, query shape) ─────────────

    def test_get_claimable_responses_query_excludes_already_claimed(self) -> None:
        """Rendered query excludes questions whose historyHash is zero (Fix E)."""
        captured_query: Dict[str, str] = {}

        def mock_subgraph(*args: Any, **kwargs: Any) -> Any:
            captured_query["q"] = kwargs.get("query", "")
            return {"data": {"responses": []}}
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_realitio_subgraph_result",
            new=mock_subgraph,
        ):
            gen = self.behaviour._get_claimable_responses()
            exhaust_gen(gen)
        # The filter must be present so already-claimed questions drop
        # out of the result set — without it the skill would deadlock
        # after the first successful batch.
        assert "historyHash_not" in captured_query["q"]
        assert (
            "0x0000000000000000000000000000000000000000000000000000000000000000"
            in captured_query["q"]
        )

    def test_get_claimable_responses_empty(self) -> None:
        """_get_claimable_responses returns empty list when subgraph returns no data."""
        subgraph_response: dict = {"data": {"responses": []}}
        with patch.object(
            self.behaviour,
            "get_realitio_subgraph_result",
            new=make_gen(subgraph_response),
        ):
            gen = self.behaviour._get_claimable_responses()
            result = exhaust_gen(gen)
        assert result == []

    def test_get_claimable_responses_returns_batch(self) -> None:
        """_get_claimable_responses returns the items from a single subgraph call."""
        responses_data = [
            {
                "id": "resp1",
                "question": {"id": "0xq1"},
                "bond": "100",
                "answer": "0x01",
            },
            {
                "id": "resp2",
                "question": {"id": "0xq2"},
                "bond": "200",
                "answer": "0x00",
            },
        ]
        subgraph_response = {"data": {"responses": responses_data}}
        call_count = 0

        def mock_subgraph(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            return subgraph_response
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_realitio_subgraph_result",
            new=mock_subgraph,
        ):
            gen = self.behaviour._get_claimable_responses()
            result = exhaust_gen(gen)
        # Single call only — no pagination loop.
        assert call_count == 1
        assert len(result) == 2
        assert result[0]["id"] == "resp1"
        assert result[1]["id"] == "resp2"

    def test_get_claimable_responses_query_uses_batch_size(self) -> None:
        """Test the rendered query interpolates the renamed batch_size param as `first:`."""
        self.behaviour.context.params.realitio_withdraw_bond_batch_size = 7
        captured_query: Dict[str, str] = {}

        def mock_subgraph(*args: Any, **kwargs: Any) -> Any:
            captured_query["q"] = kwargs.get("query", "")
            return {"data": {"responses": []}}
            yield  # noqa

        with patch.object(
            self.behaviour,
            "get_realitio_subgraph_result",
            new=mock_subgraph,
        ):
            gen = self.behaviour._get_claimable_responses()
            exhaust_gen(gen)
        assert "first: 7" in captured_query["q"]
        assert "orderDirection: desc" in captured_query["q"]

    def test_get_claimable_responses_subgraph_failure(self) -> None:
        """_get_claimable_responses returns empty on subgraph failure."""
        with patch.object(
            self.behaviour,
            "get_realitio_subgraph_result",
            new=make_gen(None),
        ):
            gen = self.behaviour._get_claimable_responses()
            result = exhaust_gen(gen)
        assert result == []

    # ─── _try_build_single_claim (per-question from_block, missing field) ────

    def test_try_build_single_claim_missing_created_block(self) -> None:
        """A response without createdBlock is skipped without any contract calls."""
        resp = {"question": {"id": "0xabcd"}, "bond": "100"}
        # Patch _get_claim_params to fail loudly if it gets called.
        with patch.object(
            self.behaviour, "_get_claim_params", side_effect=AssertionError
        ):
            gen = self.behaviour._try_build_single_claim(resp)
            result = exhaust_gen(gen)
        assert result is None

    def test_try_build_single_claim_passes_per_question_from_block(self) -> None:
        """from_block is derived as max(0, createdBlock - 1) and forwarded (Fix C)."""
        resp = {
            "question": {"id": "0xabcd", "createdBlock": "12345"},
            "bond": "100",
        }
        captured: Dict[str, int] = {}

        def fake_get_claim_params(question_id: bytes, from_block: int) -> Any:
            captured["from_block"] = from_block
            return [{"p": "v"}]
            yield  # noqa

        with (
            patch.object(
                self.behaviour, "_get_claim_params", new=fake_get_claim_params
            ),
            patch.object(self.behaviour, "_simulate_claim", new=make_gen(True)),
            patch.object(
                self.behaviour,
                "_build_claim_tx",
                new=make_gen({"to": "0xR", "data": "0x", "value": 0}),
            ),
        ):
            gen = self.behaviour._try_build_single_claim(resp)
            exhaust_gen(gen)
        assert captured["from_block"] == 12344  # 12345 - 1

    def test_try_build_single_claim_from_block_clamped_at_zero(self) -> None:
        """createdBlock=0 (edge case) clamps to from_block=0, never negative."""
        resp = {
            "question": {"id": "0xabcd", "createdBlock": "0"},
            "bond": "100",
        }
        captured: Dict[str, int] = {}

        def fake_get_claim_params(question_id: bytes, from_block: int) -> Any:
            captured["from_block"] = from_block
            return None
            yield  # noqa

        with patch.object(
            self.behaviour, "_get_claim_params", new=fake_get_claim_params
        ):
            gen = self.behaviour._try_build_single_claim(resp)
            exhaust_gen(gen)
        assert captured["from_block"] == 0

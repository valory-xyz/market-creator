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

"""Tests for ClaimBondsBehaviour."""

import contextlib
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from packages.valory.skills.omen_funds_recoverer_abci.behaviours.base import ETHER_VALUE
from packages.valory.skills.omen_funds_recoverer_abci.behaviours.claim_bonds import (
    ClaimBondsBehaviour,
    ZERO_BYTES32,
    _assemble_claim_params,
)
from packages.valory.skills.omen_funds_recoverer_abci.tests.behaviours.conftest import (
    exhaust_gen,
    make_contract_error_response,
    make_contract_state_response,
    make_gen,
)


class TestClaimBondsBehaviour:
    """Tests for ClaimBondsBehaviour."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.params.realitio_contract = "0xRealitio"
        context_mock.params.claim_bonds_batch_size = 10
        context_mock.params.min_balance_withdraw_realitio = 10000000000000000000
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
        self.behaviour: Any = ClaimBondsBehaviour(
            name="test", skill_context=context_mock
        )

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
        # Result is the (history_hashes, addrs, bonds, answers) 4-tuple
        # in REVERSE chronological order (newest at index 0).
        history_hashes, addrs, bonds, answers = result
        assert addrs == ["0xUserNew", "0xUserOld"]
        assert bonds == [200, 100]
        assert answers == [b"\x01" + b"\x00" * 31, b"\x00" * 32]
        # For the newest entry, history_hashes[0] is the older entry's
        # stored hash. For the oldest entry, it's ZERO_BYTES32.
        assert history_hashes == [b"\xaa" * 32, ZERO_BYTES32]

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

    def test_maybe_build_withdraw_tx_below_threshold(self) -> None:
        """Test _maybe_build_withdraw_tx returns None when balance below threshold."""
        # balance of 100 wei is below min_balance_withdraw_realitio threshold
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

    def test_async_act(self) -> None:
        """Test async_act wraps _build_claim_bonds_txs correctly."""
        self.behaviour.synchronized_data.funds_recovery_txs = []
        with (
            patch.object(
                self.behaviour,
                "_build_claim_bonds_txs",
                new=make_gen([]),
            ),
            patch.object(self.behaviour, "send_a2a_transaction", new=make_gen(None)),
            patch.object(self.behaviour, "wait_until_round_end", new=make_gen(None)),
            patch.object(self.behaviour, "set_done") as mock_set_done,
        ):
            gen = self.behaviour.async_act()
            exhaust_gen(gen)
            mock_set_done.assert_called_once()

    def test_build_claim_bonds_txs_no_responses_no_withdraw(self) -> None:
        """Test _build_claim_bonds_txs with no claimable responses and no withdraw."""
        with (
            patch.object(self.behaviour, "_get_claimable_responses", new=make_gen([])),
            patch.object(
                self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(None)
            ),
        ):
            gen = self.behaviour._build_claim_bonds_txs()
            result = exhaust_gen(gen)
        assert not result

    def test_build_claim_bonds_txs_no_responses_with_withdraw(self) -> None:
        """Test _build_claim_bonds_txs with no claims but a withdraw tx."""
        withdraw_tx = {"to": "0xR", "data": "0xw", "value": 0}
        with (
            patch.object(self.behaviour, "_get_claimable_responses", new=make_gen([])),
            patch.object(
                self.behaviour, "_maybe_build_withdraw_tx", new=make_gen(withdraw_tx)
            ),
        ):
            gen = self.behaviour._build_claim_bonds_txs()
            result = exhaust_gen(gen)
        assert len(result) == 1
        assert result[0] == withdraw_tx

    def test_build_claim_bonds_txs_claim_and_withdraw(self) -> None:
        """Test _build_claim_bonds_txs with one claim and a withdraw tx."""
        responses = [
            {"question": {"id": "0xabcd", "createdBlock": "12345"}, "bond": "100"}
        ]
        claim_tx = {"to": "0xR", "data": "0xclaim", "value": 0}
        withdraw_tx = {"to": "0xR", "data": "0xw", "value": 0}

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
        ):
            gen = self.behaviour._build_claim_bonds_txs()
            result = exhaust_gen(gen)
        assert len(result) == 2
        # Withdraw is built first so it gets queued even if the claim loop
        # is slow or partially fails.
        assert result[0] == withdraw_tx
        assert result[1] == claim_tx

    @pytest.mark.parametrize(
        "description,claim_params,simulate_ok,build_tx",
        [
            ("claim params fail", None, None, None),
            ("simulation fail", [{"p": "v"}], False, None),
            ("build claim tx fail", [{"p": "v"}], True, None),
        ],
    )
    def test_build_claim_bonds_txs_single_claim_failure(
        self,
        description: str,
        claim_params: Any,
        simulate_ok: Any,
        build_tx: Any,
    ) -> None:
        """Test _build_claim_bonds_txs skips when a step in the claim chain fails."""
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
                gen = self.behaviour._build_claim_bonds_txs()
                result = exhaust_gen(gen)
        assert not result

    def test_build_claim_txs_batch_size_limit(self) -> None:
        """Test _build_claim_txs stops after reaching batch_size."""
        self.behaviour.context.params.claim_bonds_batch_size = 1
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
        # Only 1 tx even though there are 2 responses
        assert len(result) == 1

    def test_build_claim_txs_deduplicates_by_question_id(self) -> None:
        """Multiple responses on the same question produce at most one claim tx."""
        # Three responses, two of them on the same question
        # (0xaaaa). After dedup the skill should only build claim txs
        # for two unique questions.
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
        # _try_build_single_claim was only called once per UNIQUE question,
        # not three times.
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

    def test_get_claimable_responses_query_excludes_already_claimed(self) -> None:
        """The rendered query excludes questions whose historyHash is zero."""
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
        """from_block is derived as max(0, createdBlock - 1) and forwarded to _get_claim_params."""
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

    def test_get_claimable_responses_empty(self) -> None:
        """Test _get_claimable_responses returns empty list when subgraph returns no data."""
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
        """Test _get_claimable_responses returns the items from a single subgraph call."""
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
        """Test the rendered query interpolates claim_bonds_batch_size as `first:`."""
        self.behaviour.context.params.claim_bonds_batch_size = 7
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
        """Test _get_claimable_responses returns empty on subgraph failure."""
        with patch.object(
            self.behaviour,
            "get_realitio_subgraph_result",
            new=make_gen(None),
        ):
            gen = self.behaviour._get_claimable_responses()
            result = exhaust_gen(gen)
        assert result == []


class TestAssembleClaimParams:
    """Tests for the _assemble_claim_params helper.

    These exercise the calldata-shape requirement of
    Realitio.claimWinnings: arrays must be in REVERSE chronological
    order (newest first), parallel and equal length, with
    history_hashes[i] holding the stored hash of the previous (older)
    chronological entry, or ZERO_BYTES32 for the very first entry.
    """

    @staticmethod
    def _entry(
        user: str, bond: int, answer: bytes, history_hash: bytes
    ) -> Dict[str, Any]:
        return {
            "args": {
                "user": user,
                "bond": bond,
                "answer": answer,
                "history_hash": history_hash,
            }
        }

    def test_single_entry(self) -> None:
        """A 1-entry history yields a 1-element 4-tuple with ZERO_BYTES32."""
        ans = b"\x01" + b"\x00" * 31
        hh = b"\xaa" * 32
        result = _assemble_claim_params([self._entry("0xUserA", 100, ans, hh)])
        history_hashes, addrs, bonds, answers = result
        assert addrs == ["0xUserA"]
        assert bonds == [100]
        assert answers == [ans]
        # Only one entry → its prior hash is the zero-bytes32 sentinel.
        assert history_hashes == [ZERO_BYTES32]

    def test_three_entries_reverse_order_and_hash_chain(self) -> None:
        """Three chronological entries → reversed arrays + correct hash chain."""
        e1 = self._entry("0xUser1", 100, b"\x00" * 32, b"\x11" * 32)
        e2 = self._entry("0xUser2", 200, b"\x01" + b"\x00" * 31, b"\x22" * 32)
        e3 = self._entry("0xUser3", 400, b"\x00" * 32, b"\x33" * 32)
        history_hashes, addrs, bonds, answers = _assemble_claim_params([e1, e2, e3])
        # Reverse-chronological: newest (e3) at index 0, oldest (e1) at index 2.
        assert addrs == ["0xUser3", "0xUser2", "0xUser1"]
        assert bonds == [400, 200, 100]
        assert answers == [
            b"\x00" * 32,
            b"\x01" + b"\x00" * 31,
            b"\x00" * 32,
        ]
        # history_hashes[i] is the stored hash of the entry one older
        # than entry i (in reverse order), or ZERO_BYTES32 for the
        # oldest entry.
        assert history_hashes == [
            b"\x22" * 32,  # before e3 was posted, the chain ended at e2.history_hash
            b"\x11" * 32,  # before e2 was posted, the chain ended at e1.history_hash
            ZERO_BYTES32,  # before e1 was posted, the chain was empty
        ]

    def test_bond_coerced_to_int(self) -> None:
        """A string bond from JSON deserialization is coerced to int."""
        e = self._entry("0xUser", 0, b"\x00" * 32, b"\x11" * 32)
        e["args"]["bond"] = "1234567890"  # subgraph/JSON path returns strings
        _, _, bonds, _ = _assemble_claim_params([e])
        assert bonds == [1234567890]
        assert isinstance(bonds[0], int)

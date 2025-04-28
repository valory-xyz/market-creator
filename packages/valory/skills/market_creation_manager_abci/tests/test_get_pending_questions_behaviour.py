# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#  Copyright 2023-2024 Valory AG
#  Licensed under the Apache License 2.0
# ------------------------------------------------------------------------------

"""Unit tests for `GetPendingQuestionsBehaviour`."""

from dataclasses import asdict
import json
import random
from types import SimpleNamespace
from typing import List, Dict

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from packages.valory.protocols.ledger_api import LedgerApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.get_pending_questions import (
    GetPendingQuestionsBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    GetPendingQuestionsPayload,
    GetPendingQuestionsRound,
)
from packages.valory.skills.mech_interact_abci.states.base import MechMetadata


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def gen_side_effect(resp):
    """Return a generator *function* that yields then returns `resp`."""
    def _g(*_a, **_kw):
        yield
        return resp
    return _g


def dummy_ctx():
    ctx = MagicMock()
    ctx.agent_address = "agent_address"
    ctx.logger = MagicMock()
    bm = MagicMock()
    ctx.benchmark_tool = bm
    bm.measure.return_value.local.return_value.__enter__ = MagicMock()
    bm.measure.return_value.local.return_value.__exit__ = MagicMock()
    bm.measure.return_value.consensus.return_value.__enter__ = MagicMock()
    bm.measure.return_value.consensus.return_value.__exit__ = MagicMock()
    return ctx


# --------------------------------------------------------------------------- #
# Dummy behaviour                                                             #
# --------------------------------------------------------------------------- #
class DummyGetPendingQuestionsBehaviour(GetPendingQuestionsBehaviour):
    """Concrete but lightweight behaviour for unit tests."""

    matching_round = GetPendingQuestionsRound

    def __init__(self):
        self._params = SimpleNamespace(
            realitio_answer_question_bond=1_000_000_000_000_000,
            answer_retry_intervals=[60, 300, 1800],
            questions_to_close_batch_size=5,
            multisend_batch_size=10,
            mech_tool_resolve_market="resolve_market_tool",
        )
        self._synchronized_data = SimpleNamespace(safe_contract_address="0xSAFE")
        self._shared_state = SimpleNamespace(
            questions_responded=set(),
            questions_requested_mech={},
        )
        self._timestamp = 1_713_900_000
        self._behaviour_id = "get_pending_questions"

    # concrete property overrides
    @property
    def params(self):
        return self._params

    @property
    def shared_state(self):
        return self._shared_state

    @property
    def synchronized_data(self):
        return self._synchronized_data

    @property
    def last_synced_timestamp(self):
        return self._timestamp

    @last_synced_timestamp.setter
    def last_synced_timestamp(self, v):
        self._timestamp = v

    @property
    def behaviour_id(self):
        return self._behaviour_id

    @behaviour_id.setter
    def behaviour_id(self, v):
        self._behaviour_id = v


# --------------------------------------------------------------------------- #
# Fixture                                                                     #
# --------------------------------------------------------------------------- #
@pytest.fixture
def behaviour():
    beh = DummyGetPendingQuestionsBehaviour()
    ctx_patch = patch.object(
        DummyGetPendingQuestionsBehaviour, "context", new_callable=PropertyMock
    )
    mock_ctx_prop = ctx_patch.start()
    mock_ctx_prop.return_value = dummy_ctx()
    beh.set_done = MagicMock()
    yield beh
    ctx_patch.stop()


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #
class TestGetPendingQuestionsBehaviour:
    """Suite."""

    # ---------- _get_unanswered_questions --------------------------------- #
    @pytest.mark.parametrize(
        "response",
        [
            {"data": {"fixedProductMarketMakers": []}},
            None,
        ],
    )
    def test_get_unanswered_questions_empty(self, behaviour, response):
        behaviour.get_subgraph_result = MagicMock(
            side_effect=gen_side_effect(response)
        )
        gen = behaviour._get_unanswered_questions()
        # exhaust generator
        result = None
        try:
            while True:
                result = next(gen)
        except StopIteration as stp:
            result = stp.value
        assert result == []

    def test_get_unanswered_questions_with_data(self, behaviour):
        questions = [
            {"id": "0xM1", "title": "A", "question": {"id": "0xQ1"}},
            {"id": "0xM2", "title": "B", "question": {"id": "0xQ2"}},
        ]
        behaviour.get_subgraph_result = MagicMock(
            side_effect=gen_side_effect({"data": {"fixedProductMarketMakers": questions}})
        )
        gen = behaviour._get_unanswered_questions()
        next(gen)
        with pytest.raises(StopIteration) as stp:
            next(gen)
        assert stp.value.value == questions

    # ---------- _get_balance --------------------------------------------- #
    def test_get_balance_success(self, behaviour):
        resp = MagicMock()
        resp.performative = LedgerApiMessage.Performative.STATE
        resp.state.body = {"get_balance_result": 5}
        behaviour.get_ledger_api_response = MagicMock(side_effect=gen_side_effect(resp))
        gen = behaviour._get_balance("x")
        next(gen)
        with pytest.raises(StopIteration) as stp:
            next(gen)
        assert stp.value.value == 5

    # ---------- _eligible_questions_to_answer ---------------------------- #
    @pytest.mark.parametrize(
        "retries, expect",
        [
            # brand-new → eligible
            ({}, ["0xq1"]),
            # very old retry (timestamp 0) → eligible
            ({"0xq1": {"question": {}, "retries": [0]}}, ["0xq1"]),
            # retry 30 s ago (< 60 s) → **not** eligible
            (
                {"0xq1": {"question": {}, "retries": [1_713_900_000 - 30]}},
                [],
            ),
            # retry 100 s ago (> 60 s but < 300 s) → still not eligible
            (
                {"0xq1": {"question": {}, "retries": [1_713_900_000 - 100]}},
                [],
            ),
        ],
    )
    def test_eligible_questions_core(self, behaviour, retries, expect, monkeypatch):
        monkeypatch.setattr(random, "sample", lambda l, k: l[:k])
        qs = [{"id": "x", "title": "t", "question": {"id": "0xQ1"}}]
        behaviour.shared_state.questions_requested_mech = retries
        res = behaviour._eligible_questions_to_answer(qs)
        assert res == expect[: behaviour.params.multisend_batch_size]

    # ---------- get_payload paths ---------------------------------------- #
    @pytest.mark.parametrize(
        "unanswered, eligible, balance, expect",
        [
            (None, [], None, GetPendingQuestionsRound.ERROR_PAYLOAD),
            ([], [], None, GetPendingQuestionsRound.NO_TX_PAYLOAD),
            ([{"question": {"id": "0xQ1"}, "title": "T"}], [], None,
             GetPendingQuestionsRound.NO_TX_PAYLOAD),
            ([{"question": {"id": "0xQ1"}, "title": "T"}], ["0xq1"], None,
             GetPendingQuestionsRound.NO_TX_PAYLOAD),
        ],
    )
    def test_get_payload_minimal_paths(
        self, behaviour, unanswered, eligible, balance, expect, monkeypatch
    ):
        monkeypatch.setattr(
            behaviour,
            "_get_unanswered_questions",
            MagicMock(side_effect=gen_side_effect(unanswered)),
        )
        monkeypatch.setattr(
            behaviour, "_eligible_questions_to_answer", MagicMock(return_value=eligible)
        )
        monkeypatch.setattr(
            behaviour, "_get_balance", MagicMock(side_effect=gen_side_effect(balance))
        )
        gen = behaviour.get_payload()
        result = None
        try:
            while True:
                result = next(gen)
        except StopIteration as stp:
            result = stp.value
        assert result == expect

    # ---------- async_act happy path ------------------------------------- #
    def test_async_act(self, behaviour, monkeypatch):
        payload_json = json.dumps(
            [asdict(MechMetadata(nonce="0xq1", tool="tool", prompt="p"))],
            sort_keys=True,
        )
        monkeypatch.setattr(
            behaviour, "get_payload", MagicMock(side_effect=gen_side_effect(payload_json))
        )
        monkeypatch.setattr(
            behaviour, "send_a2a_transaction", MagicMock(side_effect=gen_side_effect(None))
        )
        monkeypatch.setattr(
            behaviour, "wait_until_round_end", MagicMock(side_effect=gen_side_effect(None))
        )
        gen = behaviour.async_act()
        while True:
            try:
                next(gen)
            except StopIteration:
                break

        behaviour.set_done.assert_called_once()
        behaviour.send_a2a_transaction.assert_called_once()
        args, _ = behaviour.send_a2a_transaction.call_args
        assert isinstance(args[0], GetPendingQuestionsPayload)
        
    
    
    # ---------- get_payload SUCCESS path --------------------------------- #
    def test_get_payload_success(self, behaviour, monkeypatch):
        """Payload is created when balance is sufficient and mech requests generated."""

        # prepare unanswered questions
        unanswered = [
            {"id": "0xM1", "title": "T1", "question": {"id": "0xq1", "title": "T1"}},
            {"id": "0xM2", "title": "T2", "question": {"id": "0xq2", "title": "T2"}},
        ]
        eligible = ["0xq1", "0xq2"]

        monkeypatch.setattr(
            behaviour,
            "_get_unanswered_questions",
            MagicMock(side_effect=gen_side_effect(unanswered)),
        )
        monkeypatch.setattr(
            behaviour,
            "_eligible_questions_to_answer",
            MagicMock(return_value=eligible),
        )

        big_balance = behaviour.params.realitio_answer_question_bond * 10 * len(eligible)
        monkeypatch.setattr(
            behaviour, "_get_balance", MagicMock(side_effect=gen_side_effect(big_balance))
        )

        # 🚨 Important: now title is included in question
        behaviour.shared_state.questions_requested_mech = {
            "0xq1": {"question": {"id": "0xq1", "title": "T1"}, "retries": []},
            "0xq2": {"question": {"id": "0xq2", "title": "T2"}, "retries": []},
        }

        # run generator to completion
        gen = behaviour.get_payload()
        while True:
            try:
                next(gen)
            except StopIteration as e:
                payload = e.value
                break

        assert isinstance(payload, str)
        assert payload not in (GetPendingQuestionsRound.ERROR_PAYLOAD, GetPendingQuestionsRound.NO_TX_PAYLOAD)

    # ---------- async_act with ERROR_PAYLOAD ----------------------------- #
    def test_async_act_error_payload(self, behaviour, monkeypatch):
        """When get_payload returns ERROR_PAYLOAD, it is still sent."""

        monkeypatch.setattr(
            behaviour,
            "get_payload",
            MagicMock(side_effect=gen_side_effect(GetPendingQuestionsRound.ERROR_PAYLOAD)),
        )
        send_mock = MagicMock(side_effect=gen_side_effect(None))
        monkeypatch.setattr(behaviour, "send_a2a_transaction", send_mock)
        monkeypatch.setattr(
            behaviour, "wait_until_round_end", MagicMock(side_effect=gen_side_effect(None))
        )

        gen = behaviour.async_act()
        while True:
            try:
                next(gen)
            except StopIteration:
                break

        behaviour.set_done.assert_called_once()

        # New expectation: it should be called exactly once
        send_mock.assert_called_once()
        # Optionally check the payload content
        sent_payload = send_mock.call_args[0][0]
        assert sent_payload.content == GetPendingQuestionsRound.ERROR_PAYLOAD
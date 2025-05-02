# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2024 Valory AG
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

"""Tests for the AnswerQuestionsBehaviour."""

import json
import pytest
from unittest.mock import MagicMock, PropertyMock, patch

from packages.valory.skills.market_creation_manager_abci.behaviours.answer_questions import (
    AnswerQuestionsBehaviour,
    ANSWER_YES,
    ANSWER_NO,
    ANSWER_INVALID,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    AnswerQuestionsRound,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    AnswerQuestionsPayload,
)
from packages.valory.protocols.contract_api.message import ContractApiMessage
from packages.valory.skills.mech_interact_abci.states.base import (
    MechInteractionResponse,
)

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------


def gen_side_effect(resp):
    """Yield the response (and only that)."""

    def _g(*args, **kwargs):
        yield resp

    return _g()


def dummy_ctx() -> MagicMock:
    """Return a dummy context."""
    ctx = MagicMock()
    ctx.agent_address = "agent_address"
    ctx.logger = MagicMock()
    ctx.benchmark_tool = MagicMock()
    ctx.benchmark_tool.measure.return_value.local.return_value.__enter__ = MagicMock()
    ctx.benchmark_tool.measure.return_value.local.return_value.__exit__ = MagicMock()
    ctx.benchmark_tool.measure.return_value.consensus.return_value.__enter__ = (
        MagicMock()
    )
    ctx.benchmark_tool.measure.return_value.consensus.return_value.__exit__ = (
        MagicMock()
    )
    return ctx


class DummySharedState:
    def __init__(self):
        self.questions_responded = set()
        self.questions_requested_mech = {}


class DummySynchronizedData:
    def __init__(self):
        self.mech_responses = []


class DummyParams:
    def __init__(self):
        self.realitio_contract = "0xREALITIO"
        self.realitio_answer_question_bond = 1000000000000000
        self.answer_retry_intervals = [60, 300, 1800]
        self.questions_to_close_batch_size = 5
        self.multisend_address = "0xMULTI"


class DummyAnswerQuestionsBehaviour(AnswerQuestionsBehaviour):
    """Minimal subclass for testing."""

    def __init__(self):
        self._params = DummyParams()
        self._synchronized_data = DummySynchronizedData()
        self._shared_state = DummySharedState()
        self.get_contract_api_response = MagicMock()
        self._to_multisend = MagicMock()
        self.send_a2a_transaction = MagicMock()
        self.wait_until_round_end = MagicMock()
        self.set_done = MagicMock()

    @property
    def behaviour_id(self) -> str:
        return "answer_questions"

    @property
    def params(self):
        return self._params

    @property
    def synchronized_data(self):
        return self._synchronized_data

    @property
    def shared_state(self):
        return self._shared_state


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def behaviour(monkeypatch):
    """Yield a DummyAnswerQuestionsBehaviour with context monkeypatched."""
    beh = DummyAnswerQuestionsBehaviour()
    ctx_patch = patch.object(
        DummyAnswerQuestionsBehaviour, "context", new_callable=PropertyMock
    )
    mock_ctx_prop = ctx_patch.start()
    mock_ctx_prop.return_value = dummy_ctx()
    yield beh
    ctx_patch.stop()


# ------------------------------------------------------------------------------
# Tests for utility methods
# ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "result,expected",
    [
        (
            json.dumps(
                {"is_valid": True, "is_determinable": True, "has_occurred": True}
            ),
            ANSWER_YES,
        ),
        (
            json.dumps(
                {"is_valid": True, "is_determinable": True, "has_occurred": False}
            ),
            ANSWER_NO,
        ),
        (
            json.dumps(
                {"is_valid": False, "is_determinable": True, "has_occurred": False}
            ),
            ANSWER_INVALID,
        ),
        (
            json.dumps(
                {"is_valid": True, "is_determinable": False, "has_occurred": False}
            ),
            None,
        ),
        (None, None),
        ("invalid_json", None),
    ],
)
def test_parse_mech_response(behaviour, result, expected):
    """Test _parse_mech_response for various cases."""
    resp = MechInteractionResponse(nonce="q1", result=result)
    assert behaviour._parse_mech_response(resp) == expected


# ------------------------------------------------------------------------------
# Tests for _get_payload
# ------------------------------------------------------------------------------


def test_get_payload_no_responses(behaviour):
    """Test _get_payload when there are no responses."""
    behaviour.synchronized_data.mech_responses = []
    g = behaviour._get_payload()
    with pytest.raises(StopIteration) as stp:
        next(g)
    assert stp.value.value == AnswerQuestionsRound.NO_TX_PAYLOAD


def test_get_payload_already_responded(behaviour):
    """Test _get_payload when question is already responded."""
    resp = MechInteractionResponse(
        nonce="q1",
        result=json.dumps(
            {"is_valid": True, "is_determinable": True, "has_occurred": True}
        ),
    )
    behaviour.synchronized_data.mech_responses = [resp]
    behaviour.shared_state.questions_responded = {"q1"}
    g = behaviour._get_payload()
    with pytest.raises(StopIteration) as stp:
        next(g)
    assert stp.value.value == AnswerQuestionsRound.NO_TX_PAYLOAD


def test_get_payload_success(behaviour):
    """Test _get_payload successful flow."""
    resp = MechInteractionResponse(
        nonce="q1",
        result=json.dumps(
            {"is_valid": True, "is_determinable": True, "has_occurred": True}
        ),
    )
    behaviour.synchronized_data.mech_responses = [resp]
    behaviour.shared_state.questions_requested_mech = {
        "q1": {"question": "test", "retries": [0]}
    }

    tx = {"to": "0xREALITIO", "value": 1, "data": b"data"}
    behaviour._get_answer_tx = MagicMock(side_effect=[gen_side_effect(tx)])
    behaviour._to_multisend = MagicMock(side_effect=[gen_side_effect(["0xMULTI"])])

    g = behaviour._get_payload()

    # Consume until generator is exhausted
    result = None
    try:
        while True:
            result = next(g)
    except StopIteration as exc:
        result = exc.value

    assert result == "0xMULTI"


def test_get_payload_multisend_failure(behaviour):
    """Test _get_payload when multisend fails."""
    resp = MechInteractionResponse(
        nonce="q1",
        result=json.dumps(
            {"is_valid": True, "is_determinable": True, "has_occurred": True}
        ),
    )
    behaviour.synchronized_data.mech_responses = [resp]
    behaviour.shared_state.questions_requested_mech = {
        "q1": {"question": "test", "retries": [0]}
    }

    behaviour._get_answer_tx = MagicMock(
        return_value=gen_side_effect({"to": "0xREALITIO", "value": 1, "data": b"data"})
    )

    def _to_multisend_failure(*args, **kwargs):
        if False:
            yield
        return None

    behaviour._to_multisend = _to_multisend_failure

    g = behaviour._get_payload()

    # Consume all yields in the generator by calling next() until StopIteration
    result = None
    try:
        while True:
            result = next(g)
    except StopIteration as exc:
        result = exc.value

    # First yield will be tx, second (final) yield will be ERROR_PAYLOAD
    assert result == AnswerQuestionsRound.ERROR_PAYLOAD


# ------------------------------------------------------------------------------
# Tests for async_act
# ------------------------------------------------------------------------------


def test_async_act(behaviour):
    """Test full async_act."""
    behaviour._get_payload = MagicMock(return_value=iter(["0xMULTI"]))
    behaviour.send_a2a_transaction = MagicMock(return_value=iter([None]))
    behaviour.wait_until_round_end = MagicMock(return_value=iter([None]))
    behaviour.set_done = MagicMock()

    list(behaviour.async_act())

    behaviour._get_payload.assert_called_once()
    behaviour.send_a2a_transaction.assert_called_once()
    behaviour.wait_until_round_end.assert_called_once()
    behaviour.set_done.assert_called_once()
    args, _ = behaviour.send_a2a_transaction.call_args
    payload = args[0]
    assert isinstance(payload, AnswerQuestionsPayload)
    assert payload.content == "0xMULTI"


# ------------------------------------------------------------------------------
# Tests for _get_answer_tx
# ------------------------------------------------------------------------------


def test_get_answer_tx_success_and_error(behaviour):
    """Test _get_answer_tx for success and error responses."""
    success_resp = MagicMock()
    success_resp.performative = ContractApiMessage.Performative.STATE
    success_resp.state.body = {"data": b"data"}

    error_resp = MagicMock()
    error_resp.performative = ContractApiMessage.Performative.ERROR

    behaviour.get_contract_api_response = MagicMock(
        side_effect=[gen_side_effect(success_resp), gen_side_effect(error_resp)]
    )

    qid = "0x" + "00" * 32
    ans = "0x" + "00" * 32

    # First call - success
    g = behaviour._get_answer_tx(qid, ans)
    results = list(g)
    assert isinstance(results[-1], dict)
    assert results[-1]["data"] == b"data"

    # Second call - error
    g = behaviour._get_answer_tx(qid, ans)
    results = list(g)
    assert results[-1] is None

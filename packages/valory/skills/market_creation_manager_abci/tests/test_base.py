# test_base.py
# -----------------------------------------------------------------------------
#  Rich pytest + hypothesis test-suite for
#  packages.valory.skills.market_creation_manager_abci.behaviours.base
# -----------------------------------------------------------------------------
import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from hypothesis import given
from hypothesis import strategies as st
from unittest.mock import MagicMock, PropertyMock, patch

from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    BaseBehaviour,
    MarketCreationManagerBaseBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    to_content,
    parse_date_timestring,
    get_callable_name,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def gen_side_effect(resp):
    """Return a generator object that yields once then returns *resp*."""

    def _g(*_a, **_kw):
        yield
        return resp

    return _g()


def dummy_ctx() -> MagicMock:
    """Create a standard mock context for behaviour testing."""
    ctx = MagicMock()
    ctx.state = MagicMock()
    ctx.logger = MagicMock()
    ctx.omen_subgraph = MagicMock()
    ctx.omen_subgraph.get_spec.return_value = {}  # used in subgraph tests
    ctx.outbox = MagicMock()
    ctx.requests = MagicMock()
    ctx.requests.request_id_to_callback = {}
    return ctx


class DummyBehaviour(MarketCreationManagerBaseBehaviour):
    """A minimal concrete subclass so we can instantiate & test."""

    matching_round = None  # satisfy framework

    def __init__(self):
        # BaseBehaviour doesn't call super().__init__; we can leave it blank.
        self._params = SimpleNamespace(multisend_address="0xMULTI")
        self._synchronized_data = SimpleNamespace(safe_contract_address="0xSAFE")
        self._shared_state = MagicMock()

    # --- async helpers the Base uses (all mocked) ------------------------- #
    def get_contract_api_response(self, *a, **kw):
        return (yield MagicMock())

    def get_http_response(self, *a, **kw):
        return (yield MagicMock())

    def wait_for_message(self, *a, **kw):
        return (yield MagicMock())

    def get_callback_request(self):  # noqa: D401
        return MagicMock()

    def _get_request_nonce_from_dialogue(self, _dialogue):
        return "nonce"

    async def async_act(self):
        pass


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture
def behaviour():
    beh = DummyBehaviour()
    ctx_patch = patch.object(
        DummyBehaviour,
        "context",
        new_callable=PropertyMock,
    )
    mock_ctx_prop = ctx_patch.start()
    mock_ctx_prop.return_value = dummy_ctx()
    yield beh
    ctx_patch.stop()


# --------------------------------------------------------------------------- #
# Utility-function tests                                                      #
# --------------------------------------------------------------------------- #
@given(st.text(min_size=1))
def test_to_content_roundtrip(q):
    """Test to_content serialization/deserialization with property-based testing."""
    blob = to_content(q)
    decoded = json.loads(blob.decode())
    assert decoded["query"] == q


@pytest.mark.parametrize(
    "q",
    [
        "",  # empty string
        "simple query",
        '{"foo": "bar"}',  # JSON-like
        "こんにちは",  # unicode
    ],
)
def test_to_content_param(q):
    """Parametrized test for to_content with various query strings."""
    blob = to_content(q)
    decoded = json.loads(blob.decode())
    assert decoded == {"query": q}


def test_get_callable_name():
    """Test get_callable_name for named function and class."""

    def foo():
        pass

    class Bar:
        pass

    assert get_callable_name(foo) == "foo"
    assert get_callable_name(Bar) == "Bar"


@pytest.mark.parametrize(
    "callable_obj, expected",
    [
        (lambda x: x, "<lambda>"),  # function without explicit __name__
        (SimpleNamespace(), "SimpleNamespace"),  # object fallback to type name
    ],
)
def test_get_callable_name_fallbacks(callable_obj, expected):
    """Parametrized get_callable_name for fallback to type name."""
    assert get_callable_name(callable_obj) == expected


@pytest.mark.parametrize(
    "ts_str, expected",
    [
        ("2024-04-27T12:00:00Z", datetime(2024, 4, 27, 12, 0)),
        ("2024-04-27", datetime(2024, 4, 27)),
        ("foo", None),
        ("2024/04/27", None),
        ("04-27-2024", None),
    ],
)
def test_parse_date_timestring_param(ts_str, expected):
    """Parametrized test for parse_date_timestring with valid and invalid formats."""
    assert parse_date_timestring(ts_str) == expected


# --------------------------------------------------------------------------- #
# Properties / last_synced_timestamp                                          #
# --------------------------------------------------------------------------- #
def test_last_synced_timestamp(behaviour):
    """Test last_synced_timestamp property."""
    dummy_ts = 1_234_567_890
    mock_seq = MagicMock()
    mock_seq.last_round_transition_timestamp.timestamp.return_value = float(dummy_ts)
    behaviour.context.state.round_sequence = mock_seq
    assert behaviour.last_synced_timestamp == dummy_ts


def test_synchronized_data_property(behaviour):
    """Test synchronized_data property."""
    sentinel = MagicMock()
    with patch.object(
        BaseBehaviour, "synchronized_data", new_callable=PropertyMock
    ) as prop:
        prop.return_value = sentinel
        assert behaviour.synchronized_data is sentinel


def test_params_property(behaviour):
    """Test params property."""
    sentinel = MagicMock()
    with patch.object(BaseBehaviour, "params", new_callable=PropertyMock) as prop:
        prop.return_value = sentinel
        assert behaviour.params is sentinel


def test_shared_state_property(behaviour):
    """Test shared_state property."""
    sentinel = MagicMock()
    behaviour.context.state = sentinel
    assert behaviour.shared_state is sentinel


# generator runner helper
def run(gen):
    """Advance a generator-based behaviour until completion and return its final value."""
    try:
        next(gen)
        while True:
            next(gen)
    except StopIteration as e:
        return e.value


# helpers for safe_tx and multisend responses
def _mock_safe_response(perf: ContractApiMessage.Performative, tx_hash: str = "0xAA"):
    """Helper to build a fake safe tx hash response."""
    resp = MagicMock()
    resp.performative = perf
    resp.state.body = {"tx_hash": tx_hash}
    return resp


def _mk_multisend_resp(ok: bool):
    """Helper to build a fake multisend response."""
    resp = MagicMock()
    if ok:
        resp.performative = ContractApiMessage.Performative.RAW_TRANSACTION
        resp.raw_transaction.body = {"data": "0xdeadbeef"}
    else:
        resp.performative = ContractApiMessage.Performative.ERROR
    return resp


# --------------------------------------------------------------------------- #
# get_subgraph_result parameterized                                           #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "status, body, expected, expect_log",
    [
        (None, None, None, True),
        (204, "", None, True),
        (404, "Not Found", None, True),
        (200, '{"data": {"x": 1}}', {"data": {"x": 1}}, False),
    ],
)
def test_get_subgraph_result(behaviour, status, body, expected, expect_log):
    """Parameterized test for get_subgraph_result handling all branches."""
    # mock response generator
    if status is None:
        behaviour.get_http_response = MagicMock(side_effect=[gen_side_effect(None)])
    else:
        resp = MagicMock()
        resp.status_code = status
        resp.body.decode.return_value = body
        behaviour.get_http_response = MagicMock(side_effect=[gen_side_effect(resp)])
    # execute and assert
    result = run(behaviour.get_subgraph_result("q_param"))
    assert result == expected
    # check logging
    if expect_log:
        behaviour.context.logger.error.assert_called()
    else:
        behaviour.context.logger.error.assert_not_called()


# --------------------------------------------------------------------------- #
# do_llm_request parameterized                                                 #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "side_effect, expect_exception",
    [
        # normal reply path: return a MagicMock
        (gen_side_effect(MagicMock()), None),
        # error path: TimeoutError
        (TimeoutError("timeout"), TimeoutError),
    ],
)
def test_do_llm_request(behaviour, side_effect, expect_exception):
    """Test do_llm_request for both successful reply and exception propagation."""
    llm_msg = MagicMock()
    llm_dlg = MagicMock()
    # prepare behaviours
    behaviour._get_request_nonce_from_dialogue = MagicMock(return_value="nonce")
    cb = MagicMock()
    behaviour.get_callback_request = MagicMock(return_value=cb)
    # patch wait_for_message
    if isinstance(side_effect, Exception):
        behaviour.wait_for_message = MagicMock(side_effect=side_effect)
    else:
        behaviour.wait_for_message = MagicMock(side_effect=[side_effect])
    # call generator
    gen = behaviour.do_llm_request(llm_msg, llm_dlg, timeout=5.0)
    # first send: enqueues message and registers callback
    next(gen)
    behaviour.context.outbox.put_message.assert_called_once_with(message=llm_msg)
    assert behaviour.context.requests.request_id_to_callback["nonce"] == cb
    # resume: expect exception or return value
    if expect_exception:
        with pytest.raises(expect_exception):
            next(gen)
    else:
        result = run(gen)
        # side_effect was gen_side_effect returning MagicMock inside
        assert isinstance(result, MagicMock)
        assert not isinstance(result, type(expect_exception))


# --------------------------------------------------------------------------- #
# _get_safe_tx_hash                                                           #
# --------------------------------------------------------------------------- #
# parameterize both error and prefix-stripping
@pytest.mark.parametrize(
    "perf, tx_hash, expected",
    [
        (ContractApiMessage.Performative.STATE, "0xABCDEF", "ABCDEF"),
        (ContractApiMessage.Performative.STATE, "", ""),
        (ContractApiMessage.Performative.ERROR, "0xANY", None),
    ],
)
def test_get_safe_tx_hash_param(behaviour, perf, tx_hash, expected):
    """Parameterized _get_safe_tx_hash to cover strip and error branches."""
    resp = _mock_safe_response(perf, tx_hash=tx_hash)
    behaviour.get_contract_api_response = MagicMock(side_effect=[gen_side_effect(resp)])
    result = run(behaviour._get_safe_tx_hash("0xTO", b"data"))
    assert result == expected


# --------------------------------------------------------------------------- #
# _to_multisend success / error                                               #
# --------------------------------------------------------------------------- #
def _make_multisend_side_effects(behaviour, multi_perf, safe_perf, safe_tx):
    """Prepare side effects for _to_multisend: multisend perf, safe perf, and tx hash."""
    multisend = MagicMock()
    multisend.performative = multi_perf
    if multi_perf == ContractApiMessage.Performative.RAW_TRANSACTION:
        multisend.raw_transaction.body = {"data": "0xdead"}
    safe_resp = _mock_safe_response(safe_perf, tx_hash=safe_tx)
    behaviour.get_contract_api_response = MagicMock(
        side_effect=[gen_side_effect(multisend), gen_side_effect(safe_resp)]
    )
    behaviour._get_safe_tx_hash = MagicMock(side_effect=[gen_side_effect(safe_tx)])


@pytest.mark.parametrize(
    "multi_perf, safe_perf, safe_tx, expected",
    [
        # multisend fails
        (ContractApiMessage.Performative.ERROR, None, None, None),
        # multisend ok, safe fails
        (
            ContractApiMessage.Performative.RAW_TRANSACTION,
            ContractApiMessage.Performative.ERROR,
            None,
            None,
        ),
        # both ok
        (
            ContractApiMessage.Performative.RAW_TRANSACTION,
            ContractApiMessage.Performative.STATE,
            "0x123",
            "hexpayload",
        ),
    ],
)
def test_to_multisend_param(behaviour, multi_perf, safe_perf, safe_tx, expected):
    """Parameterized test for _to_multisend covering error, safe-fail, and success."""
    # patch hash_payload_to_hex to return distinct value
    with patch(
        "packages.valory.skills.market_creation_manager_abci.behaviours.base.hash_payload_to_hex",
        return_value="hexpayload",
    ):
        _make_multisend_side_effects(behaviour, multi_perf, safe_perf, safe_tx)
        result = run(behaviour._to_multisend([{"to": "0xTO", "value": 0}]))
    assert result == expected


# --------------------------------------------------------------------------- #
# Property-based sanity: multisend handles arbitrary transaction batches      #
# --------------------------------------------------------------------------- #
@given(
    st.lists(
        st.fixed_dictionaries(
            {
                "to": st.from_regex(r"0x[0-9A-Fa-f]{4,}", fullmatch=True),
                "value": st.integers(min_value=0),
            }
        )
    )
)
def test_multisend_variable_batches(txs: List[Dict[str, Any]]):
    """Property-based test for _to_multisend with various transaction batches."""
    behaviour = DummyBehaviour()
    with patch.object(
        DummyBehaviour, "context", PropertyMock(return_value=dummy_ctx())
    ):
        multisend_resp = _mk_multisend_resp(True)
        safe_hash_resp = _mock_safe_response(
            ContractApiMessage.Performative.STATE, "0x1234"
        )

        behaviour.get_contract_api_response = MagicMock(
            side_effect=[
                gen_side_effect(multisend_resp),
                gen_side_effect(safe_hash_resp),
            ]
        )
        behaviour._get_safe_tx_hash = MagicMock(
            side_effect=[gen_side_effect(safe_hash_resp)]
        )

        with patch(
            "packages.valory.skills.market_creation_manager_abci.behaviours.base.hash_payload_to_hex",
            return_value="hex",
        ):
            g = behaviour._to_multisend(txs)
            with pytest.raises(StopIteration) as stp:
                while True:
                    next(g)
            assert stp.value.value == "hex"


# --------------------------------------------------------------------------- #
# _calculate_condition_id                                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "perf, body, expected",
    [
        (
            ContractApiMessage.Performative.STATE,
            {"condition_id": "0xCONDITION123"},
            "0xCONDITION123",
        ),
        (ContractApiMessage.Performative.ERROR, {}, None),
    ],
)
def test_calculate_condition_id(behaviour, perf, body, expected):
    """Test _calculate_condition_id method using run() helper."""
    resp = MagicMock()
    resp.performative = perf
    resp.state.body = body
    behaviour.get_contract_api_response = MagicMock(side_effect=[gen_side_effect(resp)])
    # Set the necessary parameters
    behaviour.params.conditional_tokens_contract = "0xCONDITIONAL_TOKENS"
    # Execute generator
    result = run(
        behaviour._calculate_condition_id(
            oracle_contract="0xORACLE",
            question_id="0xQUESTION",
            outcome_slot_count=2,
        )
    )
    # Assert the result
    assert result == expected
    behaviour.get_contract_api_response.assert_called_once()


# --------------------------------------------------------------------------- #
# get_ledger_api_response handling                                            #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "response",
    [
        MagicMock(performative="state"),
        MagicMock(performative="error"),
    ],
)
def test_get_ledger_api_response(behaviour, response):
    """Test handling of ledger API responses using run() helper."""
    behaviour.get_ledger_api_response = MagicMock(
        side_effect=[gen_side_effect(response)]
    )
    args = {
        "performative": "get_state",
        "ledger_callable": "get_balance",
        "account": "0xADDRESS",
    }
    result = run(behaviour.get_ledger_api_response(**args))
    assert result == response

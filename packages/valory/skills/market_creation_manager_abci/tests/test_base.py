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
from packages.valory.skills.abstract_round_abci.behaviours import BaseBehaviour
from packages.valory.skills.market_creation_manager_abci.behaviours import base


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
    ctx = MagicMock()
    ctx.state = MagicMock()
    ctx.logger = MagicMock()
    ctx.omen_subgraph = MagicMock()
    ctx.omen_subgraph.get_spec.return_value = {}
    ctx.outbox = MagicMock()
    ctx.requests = MagicMock()
    ctx.requests.request_id_to_callback = {}
    return ctx


class DummyBehaviour(base.MarketCreationManagerBaseBehaviour):
    matching_round = None  # satisfy framework

    def __init__(self):
        self._params = SimpleNamespace(multisend_address="0xMULTI")
        self._synchronized_data = SimpleNamespace(safe_contract_address="0xSAFE")
        self._shared_state = MagicMock()

    # minimal overrides – everything mocked
    def get_contract_api_response(self, *a, **kw):
        return (yield MagicMock())

    def get_http_response(self, *a, **kw):
        return (yield MagicMock())

    def wait_for_message(self, *a, **kw):
        return (yield MagicMock())

    def get_callback_request(self):  # noqa: D401
        return MagicMock()

    def _get_request_nonce_from_dialogue(self, *_):
        return "nonce"

    async def async_act(self):  # pragma: no cover
        pass


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def behaviour(monkeypatch):
    """Provide a behaviour instance whose `.context` is patched globally."""
    beh = DummyBehaviour()
    ctx_patch = patch.object(DummyBehaviour, "context", new_callable=PropertyMock)
    monkeypatch.experimental_ctx_patch = ctx_patch  # to stop later
    mock_ctx_prop = ctx_patch.start()
    mock_ctx_prop.return_value = dummy_ctx()
    yield beh
    ctx_patch.stop()


# --------------------------------------------------------------------------- #
# Utility-function tests (Hypothesis)                                         #
# --------------------------------------------------------------------------- #
@given(st.text(min_size=1))
def test_to_content_roundtrip(q):
    blob = base.to_content(q)
    decoded = json.loads(blob.decode())
    assert decoded["query"] == q


VALID_TS = datetime(2024, 4, 27, 12, 0)
@pytest.mark.parametrize(
    "ts_str, expected",
    [
        ("2024-04-27T12:00:00Z", VALID_TS),
        ("2024-04-27", datetime(2024, 4, 27)),
        ("bogus", None),
    ],
)
def test_parse_date(ts_str, expected):
    assert base.parse_date_timestring(ts_str) == expected


def test_get_callable_name():
    class Foo:  # noqa: D401
        pass
    def bar():  # noqa: D401
        pass
    assert base.get_callable_name(Foo()) == "Foo"
    assert base.get_callable_name(bar) == "bar"


# --------------------------------------------------------------------------- #
# Properties / last_synced_timestamp                                          #
# --------------------------------------------------------------------------- #
def test_last_synced_timestamp(behaviour):
    dummy_ts = 1_650_000_000
    mock_seq = MagicMock()
    mock_seq.last_round_transition_timestamp.timestamp.return_value = float(dummy_ts)
    behaviour.context.state.round_sequence = mock_seq
    assert behaviour.last_synced_timestamp == dummy_ts


# Test property methods that aren't in the pytest version
def test_synchronized_data_property(behaviour):
    sentinel = MagicMock()
    with patch.object(BaseBehaviour, "synchronized_data", new_callable=PropertyMock) as prop:
        prop.return_value = sentinel
        assert behaviour.synchronized_data is sentinel


def test_params_property(behaviour):
    sentinel = MagicMock()
    with patch.object(BaseBehaviour, "params", new_callable=PropertyMock) as prop:
        prop.return_value = sentinel
        assert behaviour.params is sentinel


def test_shared_state_property(behaviour):
    sentinel = MagicMock()
    behaviour.context.state = sentinel
    assert behaviour.shared_state is sentinel


# --------------------------------------------------------------------------- #
# _get_safe_tx_hash                                                           #
# --------------------------------------------------------------------------- #
def _mock_safe_response(perf: ContractApiMessage.Performative, tx_hash="0xAA"):
    resp = MagicMock()
    resp.performative = perf
    resp.state.body = {"tx_hash": tx_hash}
    return resp


@pytest.mark.parametrize("perf, expect_none", [
    (ContractApiMessage.Performative.STATE, False),
    (ContractApiMessage.Performative.ERROR, True),
])
def test_get_safe_tx_hash(behaviour, perf, expect_none):
    behaviour.get_contract_api_response = MagicMock(
        side_effect=[gen_side_effect(_mock_safe_response(perf))],
    )
    g = behaviour._get_safe_tx_hash("0xTO", b"data")
    next(g)
    with pytest.raises(StopIteration) as stp:
        next(g)
    assert (stp.value.value is None) == expect_none


# --------------------------------------------------------------------------- #
# _to_multisend success / error                                               #
# --------------------------------------------------------------------------- #
def _mk_multisend_resp(ok: bool):
    resp = MagicMock()
    if ok:
        resp.performative = ContractApiMessage.Performative.RAW_TRANSACTION
        resp.raw_transaction.body = {"data": "0xdeadbeef"}
    else:
        resp.performative = ContractApiMessage.Performative.ERROR
    return resp


@pytest.mark.parametrize("multi_ok", [True, False])
def test_to_multisend_single(behaviour, multi_ok):
    multisend_resp = _mk_multisend_resp(multi_ok)
    safe_hash_resp = _mock_safe_response(ContractApiMessage.Performative.STATE, "0x1234")

    behaviour.get_contract_api_response = MagicMock(
        side_effect=[
            gen_side_effect(multisend_resp),
            gen_side_effect(safe_hash_resp),
        ]
    )
    behaviour._get_safe_tx_hash = MagicMock(side_effect=[gen_side_effect(safe_hash_resp)])
    txs = [{"to": "0xTO", "value": 0}]

    with patch(
        "packages.valory.skills.market_creation_manager_abci.behaviours.base.hash_payload_to_hex",
        return_value="payload_hex",
    ):
        g = behaviour._to_multisend(txs)
        with pytest.raises(StopIteration) as stp:
            while True:            # advance until it stops
                next(g)

    if multi_ok:
        assert stp.value.value == "payload_hex"
    else:
        assert stp.value.value is None


# --------------------------------------------------------------------------- #
# get_subgraph_result (200, 404, None)                                        #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("status, body, expect_none", [
    (200, '{"data": {"x": 1}}', False),
    (404, 'Not Found', True),
])
def test_subgraph(behaviour, status, body, expect_none):
    resp = MagicMock()
    resp.status_code = status
    resp.body.decode.return_value = body
    behaviour.get_http_response = MagicMock(side_effect=[gen_side_effect(resp)])
    g = behaviour.get_subgraph_result("query")
    next(g)
    with pytest.raises(StopIteration) as stp:
        next(g)
    if expect_none:
        assert stp.value.value is None
        behaviour.context.logger.error.assert_called()
    else:
        assert stp.value.value == json.loads(body)


def test_subgraph_none_response(behaviour):
    behaviour.get_http_response = MagicMock(side_effect=[gen_side_effect(None)])
    g = behaviour.get_subgraph_result("q")
    next(g)
    with pytest.raises(StopIteration):
        next(g)
    behaviour.context.logger.error.assert_called()


# --------------------------------------------------------------------------- #
# do_llm_request                                                              #
# --------------------------------------------------------------------------- #
def test_do_llm_request(behaviour):
    reply = MagicMock()
    behaviour.wait_for_message = MagicMock(
        side_effect=[gen_side_effect(reply)]
    )
    g = behaviour.do_llm_request(MagicMock(), MagicMock())
    next(g)
    with pytest.raises(StopIteration) as stp:
        next(g)
    assert stp.value.value is reply


# --------------------------------------------------------------------------- #
# _calculate_condition_id (basic positive)                                    #
# --------------------------------------------------------------------------- #
def test_calculate_condition_id(behaviour):
    resp = MagicMock()
    resp.performative = ContractApiMessage.Performative.STATE
    resp.state.body = {"condition_id": "COND1"}
    behaviour.get_contract_api_response = MagicMock(
        side_effect=[gen_side_effect(resp)]
    )
    behaviour.params.conditional_tokens_contract = "0xTOKEN"
    g = behaviour._calculate_condition_id("0xORACLE", "0xQUESTION")
    next(g)
    with pytest.raises(StopIteration) as stp:
        next(g)
    assert stp.value.value == "COND1"
    behaviour.get_contract_api_response.assert_called_once()


# --------------------------------------------------------------------------- #
# Property-based sanity: multisend handles arbitrary transaction batches      #
# --------------------------------------------------------------------------- #
#  We create a **fresh behaviour** inside the test, so we don't rely on the
#  function-scoped fixture across Hypothesis examples (avoids health-check).
@given(
    st.lists(
        st.fixed_dictionaries(
            {"to": st.from_regex(r"0x[0-9A-Fa-f]{4,}", fullmatch=True), "value": st.integers(min_value=0)}
        )
    )
)
def test_multisend_variable_batches(txs: List[Dict[str, Any]]):
    behaviour = DummyBehaviour()
    with patch.object(DummyBehaviour, "context", PropertyMock(return_value=dummy_ctx())):
        multisend_resp = _mk_multisend_resp(True)
        safe_hash_resp = _mock_safe_response(ContractApiMessage.Performative.STATE, "0x1234")

        behaviour.get_contract_api_response = MagicMock(
            side_effect=[
                gen_side_effect(multisend_resp),
                gen_side_effect(safe_hash_resp),
            ]
        )
        behaviour._get_safe_tx_hash = MagicMock(side_effect=[gen_side_effect(safe_hash_resp)])

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
# get_ledger_api_response handling                                            #
# --------------------------------------------------------------------------- #
def test_get_ledger_api_response(behaviour):
    """Test handling of ledger API responses.
    
    This test is critical for behaviours like DepositDaiBehaviour and RedeemBondBehaviour.
    """
    # Mock responses for success and error cases
    valid_response = MagicMock()
    valid_response.performative = "state"
    
    error_response = MagicMock()
    error_response.performative = "error"
    
    # Set up the mock to return different responses for testing
    behaviour.get_ledger_api_response = MagicMock(
        side_effect=[
            gen_side_effect(valid_response),
            gen_side_effect(error_response)
        ]
    )
    
    # Test valid response
    g = behaviour.get_ledger_api_response(
        performative="get_state",
        ledger_callable="get_balance",
        account="0xADDRESS"
    )
    next(g)  # Start the generator
    with pytest.raises(StopIteration) as stop:
        next(g)  # Should raise StopIteration with value
    assert stop.value.value == valid_response
    
    # Test error response
    g = behaviour.get_ledger_api_response(
        performative="get_state",
        ledger_callable="get_balance",
        account="0xADDRESS"
    )
    next(g)  # Start the generator
    with pytest.raises(StopIteration) as stop:
        next(g)  # Should raise StopIteration with value
    assert stop.value.value == error_response
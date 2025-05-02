import json
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    FPMM_POOL_MEMBERSHIPS_QUERY,
    FPMM_QUERY,
    OPEN_FPMM_QUERY,
    to_content,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.base import MarketCreationManagerBaseBehaviour

# use dummy behaviour subclass for testing
class DummyGraphBehaviour(MarketCreationManagerBaseBehaviour):
    matching_round = None
    def __init__(self):
        self._params = SimpleNamespace(multisend_address="0xMULTI")
        self._synchronized_data = SimpleNamespace(safe_contract_address="0xSAFE")
        self._shared_state = MagicMock()
    def get_http_response(self, **kwargs):
        yield
        return MagicMock()
    def get_contract_api_response(self, *a, **kw):
        yield
        return MagicMock()
    def wait_for_message(self, *a, **kw):
        yield
        return MagicMock()

@pytest.fixture(autouse=True)
def dummy_ctx_patch(monkeypatch):
    """Patch context on DummyGraphBehaviour to provide omen_subgraph spec"""
    spec = {
        'url': 'https://api.thegraph.com/subgraphs/name/protofire/omen-xdai',
        'method': 'POST',
        'headers': {'Content-Type': 'application/json'},
        'parameters': {},
    }
    patcher = patch.object(
        DummyGraphBehaviour,
        "context",
        new_callable=PropertyMock,
        return_value=SimpleNamespace(
            omen_subgraph=SimpleNamespace(get_spec=lambda: spec),
            logger=MagicMock(),
        ),
    )
    mocked = patcher.start()
    yield
    patcher.stop()

@pytest.mark.parametrize(
    "template, args_dict",
    [
        (FPMM_POOL_MEMBERSHIPS_QUERY, {'creator': '0xCREATOR'}),
        (FPMM_QUERY, {'creator': '0xCREATOR', 'openingTimestamp_gte': '10', 'openingTimestamp_lte': '20'}),
        (OPEN_FPMM_QUERY, {'creator': '0xCREATOR', 'current_timestamp': '30'}),
    ],
)
def test_graph_query_payload_and_spec(template, args_dict):
    """Ensure GraphQL templates are rendered and passed as HTTP payload correctly."""
    beh = DummyGraphBehaviour()
    # spy on get_http_response
    beh.get_http_response = MagicMock(side_effect=[beh.get_http_response(**{})])
    # run generator until first yield to capture call
    gen = beh.get_subgraph_result("irrelevant")
    # advance into GET_HTTP_RESPONSE
    next(gen)
    # extract call args
    call = beh.get_http_response.call_args.kwargs
    # verify spec keys passed
    assert call['url'] == 'https://api.thegraph.com/subgraphs/name/protofire/omen-xdai'
    assert call['method'] == 'POST'
    assert call['headers'] == {'Content-Type': 'application/json'}
    assert call['parameters'] == {}
    # verify content payload
    content = call['content']
    # decode JSON wrapper
    wrapper = json.loads(content.decode())
    rendered = template.substitute(**args_dict)
    assert wrapper['query'].strip() == rendered.strip()

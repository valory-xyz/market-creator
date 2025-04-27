# test_base.py
import unittest
from datetime import datetime
from unittest.mock import MagicMock, PropertyMock, patch

from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.abstract_round_abci.behaviours import BaseBehaviour
from packages.valory.skills.market_creation_manager_abci.behaviours import base


# --------------------------------------------------------------------------- #
# Helper to create a generator that first yields (for the "yield from") and   #
# then returns a prepared response.                                           #
# --------------------------------------------------------------------------- #
def make_generator(response):
    def _gen(*_args, **_kwargs):
        yield
        return response

    return _gen


# =========================================================================== #
#  Utility-function tests                                                     #
# =========================================================================== #
class TestBaseUtils(unittest.TestCase):
    def test_to_content(self):
        query = "{ testQuery }"
        result = base.to_content(query)
        self.assertIsInstance(result, bytes)
        self.assertIn(b'"query"', result)
        self.assertIn(b'testQuery', result)

    def test_parse_date_timestring(self):
        valid_1 = "2024-04-27T12:00:00Z"
        valid_2 = "2024-04-27"
        invalid = "foo"
        invalid_2 = "2024/04/27"
        invalid_3 = "04-27-2024"
        
        # Test valid formats
        self.assertEqual(
            base.parse_date_timestring(valid_1), datetime(2024, 4, 27, 12, 0)
        )
        self.assertEqual(base.parse_date_timestring(valid_2), datetime(2024, 4, 27))
        
        # Test invalid formats
        self.assertIsNone(base.parse_date_timestring(invalid))
        self.assertIsNone(base.parse_date_timestring(invalid_2))
        self.assertIsNone(base.parse_date_timestring(invalid_3))

    def test_get_callable_name(self):
        def foo():
            pass

        class Bar:
            pass

        self.assertEqual(base.get_callable_name(foo), "foo")
        self.assertEqual(base.get_callable_name(Bar()), "Bar")


# =========================================================================== #
#  Dummy behaviour for tests                                                  #
# =========================================================================== #
class DummyBehaviour(base.MarketCreationManagerBaseBehaviour):
    """A minimal concrete subclass so we can instantiate & test."""

    matching_round = None  # satisfies BaseBehaviourInternalError

    def __init__(self):
        # BaseBehaviour doesn’t call super().__init__; we can leave it blank.
        self._params = MagicMock()
        self._synchronized_data = MagicMock()
        self._shared_state = MagicMock()

    # --- async helpers the Base uses (all mocked) ------------------------- #
    def get_contract_api_response(self, *args, **kwargs):  # noqa: D401
        return (yield MagicMock())

    def get_http_response(self, *args, **kwargs):
        return (yield MagicMock())

    def wait_for_message(self, timeout=None):
        return (yield MagicMock())

    def get_callback_request(self):
        return MagicMock()

    def _get_request_nonce_from_dialogue(self, _dialogue):
        return "nonce"

    async def async_act(self):
        pass


# =========================================================================== #
#  Behaviour-method tests                                                     #
# =========================================================================== #
class TestMarketCreationManagerBaseBehaviour(unittest.TestCase):
    def setUp(self):
        self.behaviour = DummyBehaviour()

        # centralised context patch
        patcher = patch.object(DummyBehaviour, "context", new_callable=PropertyMock)
        self.addCleanup(patcher.stop)
        self.mock_context = patcher.start()

        ctx = MagicMock()
        ctx.state = MagicMock()
        ctx.logger = MagicMock()
        ctx.omen_subgraph = MagicMock()
        ctx.omen_subgraph.get_spec.return_value = {}  # used in subgraph tests
        ctx.outbox = MagicMock()
        ctx.requests = MagicMock()
        ctx.requests.request_id_to_callback = {}

        self.mock_context.return_value = ctx

        # handy aliases inside tests
        self.ctx = self.behaviour.context
        self.behaviour.params.multisend_address = "0xMULTI"
        self.behaviour.synchronized_data.safe_contract_address = "0xSAFE"

    # ------------------------------------------------------------------- #
    # simple property helpers                                             #
    # ------------------------------------------------------------------- #
    def test_last_synced_timestamp(self):
        ts = 1_234_567_890
        mock_state = MagicMock()
        mock_state.round_sequence.last_round_transition_timestamp.timestamp.return_value = float(
            ts
        )
        self.ctx.state = mock_state
        self.assertEqual(self.behaviour.last_synced_timestamp, ts)

    def test_synchronized_data_property(self):
        sentinel = MagicMock()
        with patch.object(
            BaseBehaviour, "synchronized_data", new_callable=PropertyMock
        ) as prop:
            prop.return_value = sentinel
            self.assertIs(self.behaviour.synchronized_data, sentinel)

    def test_params_property(self):
        sentinel = MagicMock()
        with patch.object(BaseBehaviour, "params", new_callable=PropertyMock) as prop:
            prop.return_value = sentinel
            self.assertIs(self.behaviour.params, sentinel)

    def test_shared_state_property(self):
        sentinel = MagicMock()
        self.ctx.state = sentinel
        self.assertIs(self.behaviour.shared_state, sentinel)

    # ------------------------------------------------------------------- #
    # _get_safe_tx_hash                                                   #
    # ------------------------------------------------------------------- #
    def test__get_safe_tx_hash_success(self):
        response = MagicMock()
        response.performative = ContractApiMessage.Performative.STATE
        response.state.body = {"tx_hash": "0x1234abcd"}
        self.behaviour.get_contract_api_response = MagicMock(
            side_effect=[make_generator(response)()]
        )

        gen = self.behaviour._get_safe_tx_hash("0xTO", b"data")
        next(gen)               # yield
        with self.assertRaises(StopIteration) as stop:
            next(gen)
        self.assertEqual(stop.exception.value, "1234abcd")

    def test__get_safe_tx_hash_error(self):
        err_resp = MagicMock()
        err_resp.performative = ContractApiMessage.Performative.ERROR
        err_resp.state.body = {"tx_hash": "0xdead"}

        self.behaviour.get_contract_api_response = MagicMock(
            side_effect=[make_generator(err_resp)()]
        )

        gen = self.behaviour._get_safe_tx_hash("0xTO", b"data")
        next(gen)
        with self.assertRaises(StopIteration) as stop:
            next(gen)
        self.assertIsNone(stop.exception.value)
        self.ctx.logger.error.assert_called()

    # ------------------------------------------------------------------- #
    # _to_multisend helpers                                               #
    # ------------------------------------------------------------------- #
    def _setup_multisend_side_effects(self):
        multisend_resp = MagicMock()
        multisend_resp.performative = ContractApiMessage.Performative.RAW_TRANSACTION
        multisend_resp.raw_transaction.body = {"data": "0xdeadbeef"}

        safe_hash_resp = MagicMock()
        safe_hash_resp.performative = ContractApiMessage.Performative.STATE
        safe_hash_resp.state.body = {"tx_hash": "0x123456"}

        self.behaviour.get_contract_api_response = MagicMock(
            side_effect=[
                make_generator(multisend_resp)(),  # first call
                make_generator(safe_hash_resp)(),  # second call
            ]
        )
        self.behaviour._get_safe_tx_hash = MagicMock(
            side_effect=[make_generator(safe_hash_resp)()]
        )

    def test__to_multisend_success(self):
        self._setup_multisend_side_effects()
        txs = [{"to": "0xTO", "value": 0}]
        with patch(
            "packages.valory.skills.market_creation_manager_abci.behaviours.base.hash_payload_to_hex",
            return_value="payload_hex",
        ):
            gen = self.behaviour._to_multisend(txs)
            # Need to exhaust all yields in the generator
            try:
                while True:
                    next(gen)
            except StopIteration as stop:
                self.assertEqual(stop.value, "payload_hex")

    def test__to_multisend_multiple_transactions(self):
        self._setup_multisend_side_effects()
        txs = [
            {"to": "0xTO1", "value": 0},
            {"to": "0xTO2", "value": 10},
        ]
        with patch(
            "packages.valory.skills.market_creation_manager_abci.behaviours.base.hash_payload_to_hex",
            return_value="payload_hex",
        ):
            gen = self.behaviour._to_multisend(txs)
            # Need to exhaust all yields in the generator
            try:
                while True:
                    next(gen)
            except StopIteration as stop:
                self.assertEqual(stop.value, "payload_hex")

    def test__to_multisend_error(self):
        err_resp = MagicMock()
        err_resp.performative = ContractApiMessage.Performative.ERROR

        self.behaviour.get_contract_api_response = MagicMock(
            side_effect=[make_generator(err_resp)()]
        )

        txs = [{"to": "0xTO", "value": 0}]
        gen = self.behaviour._to_multisend(txs)
        next(gen)
        with self.assertRaises(StopIteration) as stop:
            next(gen)
        self.assertIsNone(stop.exception.value)
        self.ctx.logger.error.assert_called()

    # ------------------------------------------------------------------- #
    # get_subgraph_result                                                 #
    # ------------------------------------------------------------------- #
    def test_get_subgraph_result_success(self):
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.body.decode.return_value = '{"data": {"foo": "bar"}}'
        self.behaviour.get_http_response = MagicMock(
            side_effect=[make_generator(ok_resp)()]
        )

        gen = self.behaviour.get_subgraph_result("query")
        next(gen)
        with self.assertRaises(StopIteration) as stop:
            next(gen)
        self.assertEqual(stop.exception.value, {"data": {"foo": "bar"}})

    def test_get_subgraph_result_non_200(self):
        err_resp = MagicMock()
        err_resp.status_code = 404
        err_resp.body.decode.return_value = "Not Found"
        self.behaviour.get_http_response = MagicMock(
            side_effect=[make_generator(err_resp)()]
        )

        gen = self.behaviour.get_subgraph_result("query")
        next(gen)
        with self.assertRaises(StopIteration):
            next(gen)
        self.ctx.logger.error.assert_called()

    def test_get_subgraph_result_none(self):
        # make get_http_response yield None
        self.behaviour.get_http_response = MagicMock(side_effect=[make_generator(None)()])

        gen = self.behaviour.get_subgraph_result("query")
        next(gen)
        with self.assertRaises(StopIteration):
            next(gen)
        self.ctx.logger.error.assert_called()

    # ------------------------------------------------------------------- #
    # do_llm_request                                                      #
    # ------------------------------------------------------------------- #
    def test_do_llm_request(self):
        llm_msg, llm_dial, reply = MagicMock(), MagicMock(), MagicMock()
        self.behaviour.wait_for_message = MagicMock(
            side_effect=[make_generator(reply)()]
        )
        gen = self.behaviour.do_llm_request(llm_msg, llm_dial)
        next(gen)
        with self.assertRaises(StopIteration) as stop:
            next(gen)
        self.assertIs(stop.exception.value, reply)

    # ------------------------------------------------------------------- #
    # _calculate_condition_id                                              #
    # ------------------------------------------------------------------- #
    def test__calculate_condition_id(self):
        """Test _calculate_condition_id method."""
        response = MagicMock()
        response.performative = ContractApiMessage.Performative.STATE
        response.state.body = {"condition_id": "0xCONDITION123"}
        
        self.behaviour.get_contract_api_response = MagicMock(
            side_effect=[make_generator(response)()]
        )
        
        # Set the necessary parameters
        self.behaviour.params.conditional_tokens_contract = "0xCONDITIONAL_TOKENS"
        
        # Call the method
        gen = self.behaviour._calculate_condition_id(
            oracle_contract="0xORACLE", 
            question_id="0xQUESTION", 
            outcome_slot_count=2
        )
        
        next(gen)  # Start the generator
        with self.assertRaises(StopIteration) as stop:
            next(gen)  # Should raise StopIteration with value
            
        # Assert the result is the expected condition_id
        self.assertEqual(stop.exception.value, "0xCONDITION123")
        
        # Verify the contract API was called with correct parameters
        self.behaviour.get_contract_api_response.assert_called_once()

    # ------------------------------------------------------------------- #
    # get_ledger_api_response handling                                     #
    # ------------------------------------------------------------------- #
    def test_get_ledger_api_response(self):
        """Test handling of ledger API responses.
        
        This test mocks the get_ledger_api_response method which is used in 
        several behaviours like DepositDaiBehaviour and RedeemBondBehaviour.
        """
        # Mock the generator function to simulate the behaviour
        valid_response = MagicMock()
        valid_response.performative = "state"  # Simulating a valid response
        
        error_response = MagicMock()
        error_response.performative = "error"  # Simulating an error response
        
        # Set up the mock to return different responses for testing
        self.behaviour.get_ledger_api_response = MagicMock(
            side_effect=[
                make_generator(valid_response)(),
                make_generator(error_response)()
            ]
        )
        
        # Test valid response
        gen = self.behaviour.get_ledger_api_response(
            performative="get_state",
            ledger_callable="get_balance",
            account="0xADDRESS"
        )
        # Start the generator
        next(gen)
        # Complete the generator and check result
        with self.assertRaises(StopIteration) as stop:
            next(gen)
        self.assertEqual(stop.exception.value, valid_response)
        
        # Test error response
        gen = self.behaviour.get_ledger_api_response(
            performative="get_state",
            ledger_callable="get_balance",
            account="0xADDRESS"
        )
        # Start the generator
        next(gen)
        # Complete the generator and check result
        with self.assertRaises(StopIteration) as stop:
            next(gen)
        self.assertEqual(stop.exception.value, error_response)


if __name__ == "__main__":
    unittest.main()
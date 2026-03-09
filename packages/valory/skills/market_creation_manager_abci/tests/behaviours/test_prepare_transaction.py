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

"""Tests for market_creation_manager_abci PrepareTransactionBehaviour."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from packages.valory.skills.market_creation_manager_abci.behaviours.prepare_transaction import (
    PrepareTransactionBehaviour,
)

CURRENT_FILE_PATH = Path(__file__).resolve()
PACKAGE_DIR = CURRENT_FILE_PATH.parents[2]
_ONE_DAY = 86400


class TestPrepareTransactionBehaviourMethods:
    """Test PrepareTransactionBehaviour helper methods."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        context_mock.params.realitio_contract = (
            "0x1234567890123456789012345678901234567890"
        )
        context_mock.params.arbitrator_contract = (
            "0x2234567890123456789012345678901234567890"
        )
        self.behaviour = PrepareTransactionBehaviour(
            name="test", skill_context=context_mock
        )

    def test_calculate_time_parameters(self) -> None:
        """Test _calculate_time_parameters using real behaviour method."""
        resolution_time = 1704067200
        timeout_days = 7

        opening_time, timeout_seconds = self.behaviour._calculate_time_parameters(
            resolution_time, timeout_days
        )

        assert opening_time == resolution_time + _ONE_DAY
        assert timeout_seconds == timeout_days * _ONE_DAY

    def test_matching_round(self) -> None:
        """Test that matching_round is correctly set."""
        from packages.valory.skills.market_creation_manager_abci.rounds import (
            PrepareTransactionRound,
        )

        assert self.behaviour.matching_round == PrepareTransactionRound


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


class TestPrepareTransactionBehaviourGenerators:
    """Test PrepareTransactionBehaviour generator methods."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        context_mock = MagicMock()
        context_mock.logger = MagicMock()
        context_mock.params = MagicMock()
        context_mock.state.round_sequence = MagicMock()
        context_mock.benchmark_tool = MagicMock()
        context_mock.agent_address = "0x1234567890123456789012345678901234567890"
        context_mock.params.realitio_contract = "0xRealitio"
        context_mock.params.arbitrator_contract = "0xArbitrator"
        context_mock.params.conditional_tokens_contract = "0xConditionalTokens"
        context_mock.params.realitio_oracle_proxy_contract = "0xOracleProxy"
        context_mock.params.fpmm_deterministic_factory_contract = "0xFactory"
        context_mock.params.collateral_tokens_contract = "0xCollateral"
        context_mock.params.multisend_address = "0xMultisend"
        context_mock.params.realitio_answer_question_bounty = 100
        context_mock.params.initial_funds = 1000
        context_mock.params.market_fee = 20
        context_mock.params.market_timeout = 7
        self.behaviour = PrepareTransactionBehaviour(
            name="test", skill_context=context_mock
        )

    def test_calculate_question_id(self) -> None:
        """Test _calculate_question_id returns question_id from body."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.STATE
        mock_resp.state.body = {"question_id": "0xQuestion123"}

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._calculate_question_id(
                question_data={
                    "question": "Test?",
                    "answers": "Yes,No",
                    "topic": "test",
                    "language": "en",
                },
                opening_timestamp=1700000000,
                timeout=604800,
            )
            result = _exhaust_gen(gen)

        assert result == "0xQuestion123"

    def test_prepare_ask_question_mstx_success(self) -> None:
        """Test _prepare_ask_question_mstx with successful response."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.STATE
        mock_resp.state.body = {"data": b"\x01"}

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._prepare_ask_question_mstx(
                question_data={
                    "question": "Test?",
                    "answers": "Yes,No",
                    "topic": "test",
                    "language": "en",
                },
                opening_timestamp=1700000000,
                timeout=604800,
            )
            result = _exhaust_gen(gen)

        assert result is not None
        assert result["to"] == "0xRealitio"
        assert result["value"] == 100

    def test_prepare_ask_question_mstx_error(self) -> None:
        """Test _prepare_ask_question_mstx with error response."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._prepare_ask_question_mstx(
                question_data={},
                opening_timestamp=1700000000,
                timeout=604800,
            )
            result = _exhaust_gen(gen)

        assert result is None

    def test_prepare_prepare_condition_mstx_success(self) -> None:
        """Test _prepare_prepare_condition_mstx with successful response."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.STATE
        mock_resp.state.body = {"data": b"\x02"}

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._prepare_prepare_condition_mstx(
                question_id="0xQ1",
            )
            result = _exhaust_gen(gen)

        assert result is not None
        assert result["to"] == "0xConditionalTokens"

    def test_prepare_prepare_condition_mstx_error(self) -> None:
        """Test _prepare_prepare_condition_mstx with error response."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._prepare_prepare_condition_mstx(
                question_id="0xQ1",
            )
            result = _exhaust_gen(gen)

        assert result is None

    def test_prepare_create_fpmm_mstx_success(self) -> None:
        """Test _prepare_create_fpmm_mstx with successful response."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.STATE
        mock_resp.state.body = {"data": b"\x03", "value": 5000}

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._prepare_create_fpmm_mstx(
                condition_id="0xCond1",
                initial_funds=1000,
                market_fee=20,
            )
            result = _exhaust_gen(gen)

        assert result is not None
        assert result["to"] == "0xFactory"
        assert result["approval_amount"] == 5000

    def test_prepare_create_fpmm_mstx_error(self) -> None:
        """Test _prepare_create_fpmm_mstx with error response."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._prepare_create_fpmm_mstx(
                condition_id="0xCond1",
                initial_funds=1000,
                market_fee=20,
            )
            result = _exhaust_gen(gen)

        assert result is None

    def test_get_approve_tx_success(self) -> None:
        """Test _get_approve_tx with successful response."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.STATE
        mock_resp.state.body = {"data": b"\x04"}

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_approve_tx(amount=5000)
            result = _exhaust_gen(gen)

        assert result is not None
        assert result["to"] == "0xCollateral"

    def test_get_approve_tx_error(self) -> None:
        """Test _get_approve_tx with error response."""
        from packages.valory.protocols.contract_api import ContractApiMessage

        mock_resp = MagicMock()
        mock_resp.performative = ContractApiMessage.Performative.ERROR

        with patch.object(
            self.behaviour,
            "get_contract_api_response",
            new=_make_gen(mock_resp),
        ):
            gen = self.behaviour._get_approve_tx(amount=5000)
            result = _exhaust_gen(gen)

        assert result is None

    def test_async_act_happy_path(self) -> None:
        """Test async_act happy path where all steps succeed."""
        mock_synced = MagicMock()
        mock_synced.approved_question_data = {
            "question": "Will X?",
            "answers": "Yes,No",
            "topic": "crypto",
            "language": "en",
            "resolution_time": "1700000000",
        }
        mock_synced.safe_contract_address = "0xSafe"

        def multi_calc_question_id(*args: Any, **kwargs: Any) -> Any:
            return "0xQuestionId"
            yield  # noqa

        def multi_ask_question(*args: Any, **kwargs: Any) -> Any:
            return {"to": "0xR", "data": b"\x01", "value": 100}
            yield  # noqa

        def multi_prepare_condition(*args: Any, **kwargs: Any) -> Any:
            return {"to": "0xCT", "data": b"\x02", "value": 0}
            yield  # noqa

        def multi_calc_condition(*args: Any, **kwargs: Any) -> Any:
            return "0xCondId"
            yield  # noqa

        def multi_create_fpmm(*args: Any, **kwargs: Any) -> Any:
            return {"to": "0xF", "data": b"\x03", "value": 0, "approval_amount": 5000}
            yield  # noqa

        def multi_approve(*args: Any, **kwargs: Any) -> Any:
            return {"to": "0xC", "data": b"\x04", "value": 0}
            yield  # noqa

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            self.behaviour, "_calculate_question_id", new=multi_calc_question_id
        ), patch.object(
            self.behaviour, "_prepare_ask_question_mstx", new=multi_ask_question
        ), patch.object(
            self.behaviour,
            "_prepare_prepare_condition_mstx",
            new=multi_prepare_condition,
        ), patch.object(
            self.behaviour, "_calculate_condition_id", new=multi_calc_condition
        ), patch.object(
            self.behaviour, "_prepare_create_fpmm_mstx", new=multi_create_fpmm
        ), patch.object(
            self.behaviour, "_get_approve_tx", new=multi_approve
        ), patch.object(
            self.behaviour, "_to_multisend", new=_make_gen("0xTxHash")
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

    def test_async_act_ask_question_none(self) -> None:
        """Test async_act when _prepare_ask_question_mstx returns None."""
        mock_synced = MagicMock()
        mock_synced.approved_question_data = {
            "question": "Will X?",
            "answers": "Yes,No",
            "topic": "crypto",
            "language": "en",
            "resolution_time": "1700000000",
        }
        mock_synced.safe_contract_address = "0xSafe"

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            self.behaviour, "_calculate_question_id", new=_make_gen("0xQid")
        ), patch.object(
            self.behaviour, "_prepare_ask_question_mstx", new=_make_gen(None)
        ):
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)

    def test_async_act_prepare_condition_none(self) -> None:
        """Test async_act when _prepare_prepare_condition_mstx returns None."""
        mock_synced = MagicMock()
        mock_synced.approved_question_data = {
            "question": "Will X?",
            "answers": "Yes,No",
            "topic": "crypto",
            "language": "en",
            "resolution_time": "1700000000",
        }
        mock_synced.safe_contract_address = "0xSafe"

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            self.behaviour, "_calculate_question_id", new=_make_gen("0xQid")
        ), patch.object(
            self.behaviour,
            "_prepare_ask_question_mstx",
            new=_make_gen({"to": "0xR", "data": b"\x01", "value": 100}),
        ), patch.object(
            self.behaviour, "_prepare_prepare_condition_mstx", new=_make_gen(None)
        ):
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)

    def test_async_act_condition_id_none(self) -> None:
        """Test async_act when _calculate_condition_id returns None."""
        mock_synced = MagicMock()
        mock_synced.approved_question_data = {
            "question": "Will X?",
            "answers": "Yes,No",
            "topic": "crypto",
            "language": "en",
            "resolution_time": "1700000000",
        }
        mock_synced.safe_contract_address = "0xSafe"

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            self.behaviour, "_calculate_question_id", new=_make_gen("0xQid")
        ), patch.object(
            self.behaviour,
            "_prepare_ask_question_mstx",
            new=_make_gen({"to": "0xR", "data": b"\x01", "value": 100}),
        ), patch.object(
            self.behaviour,
            "_prepare_prepare_condition_mstx",
            new=_make_gen({"to": "0xCT", "data": b"\x02", "value": 0}),
        ), patch.object(
            self.behaviour, "_calculate_condition_id", new=_make_gen(None)
        ):
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)

    def test_async_act_create_fpmm_none(self) -> None:
        """Test async_act when _prepare_create_fpmm_mstx returns None."""
        mock_synced = MagicMock()
        mock_synced.approved_question_data = {
            "question": "Will X?",
            "answers": "Yes,No",
            "topic": "crypto",
            "language": "en",
            "resolution_time": "1700000000",
        }
        mock_synced.safe_contract_address = "0xSafe"

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            self.behaviour, "_calculate_question_id", new=_make_gen("0xQid")
        ), patch.object(
            self.behaviour,
            "_prepare_ask_question_mstx",
            new=_make_gen({"to": "0xR", "data": b"\x01", "value": 100}),
        ), patch.object(
            self.behaviour,
            "_prepare_prepare_condition_mstx",
            new=_make_gen({"to": "0xCT", "data": b"\x02", "value": 0}),
        ), patch.object(
            self.behaviour, "_calculate_condition_id", new=_make_gen("0xCondId")
        ), patch.object(
            self.behaviour, "_prepare_create_fpmm_mstx", new=_make_gen(None)
        ):
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)

    def test_async_act_approve_tx_none(self) -> None:
        """Test async_act when _get_approve_tx returns None."""
        mock_synced = MagicMock()
        mock_synced.approved_question_data = {
            "question": "Will X?",
            "answers": "Yes,No",
            "topic": "crypto",
            "language": "en",
            "resolution_time": "1700000000",
        }
        mock_synced.safe_contract_address = "0xSafe"

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            self.behaviour, "_calculate_question_id", new=_make_gen("0xQid")
        ), patch.object(
            self.behaviour,
            "_prepare_ask_question_mstx",
            new=_make_gen({"to": "0xR", "data": b"\x01", "value": 100}),
        ), patch.object(
            self.behaviour,
            "_prepare_prepare_condition_mstx",
            new=_make_gen({"to": "0xCT", "data": b"\x02", "value": 0}),
        ), patch.object(
            self.behaviour, "_calculate_condition_id", new=_make_gen("0xCondId")
        ), patch.object(
            self.behaviour,
            "_prepare_create_fpmm_mstx",
            new=_make_gen(
                {"to": "0xF", "data": b"\x03", "value": 0, "approval_amount": 5000}
            ),
        ), patch.object(
            self.behaviour, "_get_approve_tx", new=_make_gen(None)
        ):
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)

    def test_async_act_multisend_none(self) -> None:
        """Test async_act when _to_multisend returns None."""
        mock_synced = MagicMock()
        mock_synced.approved_question_data = {
            "question": "Will X?",
            "answers": "Yes,No",
            "topic": "crypto",
            "language": "en",
            "resolution_time": "1700000000",
        }
        mock_synced.safe_contract_address = "0xSafe"

        with patch.object(
            type(self.behaviour),
            "synchronized_data",
            new_callable=lambda: property(lambda self: mock_synced),
        ), patch.object(
            self.behaviour, "_calculate_question_id", new=_make_gen("0xQid")
        ), patch.object(
            self.behaviour,
            "_prepare_ask_question_mstx",
            new=_make_gen({"to": "0xR", "data": b"\x01", "value": 100}),
        ), patch.object(
            self.behaviour,
            "_prepare_prepare_condition_mstx",
            new=_make_gen({"to": "0xCT", "data": b"\x02", "value": 0}),
        ), patch.object(
            self.behaviour, "_calculate_condition_id", new=_make_gen("0xCondId")
        ), patch.object(
            self.behaviour,
            "_prepare_create_fpmm_mstx",
            new=_make_gen(
                {"to": "0xF", "data": b"\x03", "value": 0, "approval_amount": 5000}
            ),
        ), patch.object(
            self.behaviour,
            "_get_approve_tx",
            new=_make_gen({"to": "0xC", "data": b"\x04", "value": 0}),
        ), patch.object(
            self.behaviour, "_to_multisend", new=_make_gen(None)
        ):
            gen = self.behaviour.async_act()
            _exhaust_gen(gen)

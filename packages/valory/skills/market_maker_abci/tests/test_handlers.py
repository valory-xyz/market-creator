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

"""Tests for the market_maker_abci handlers."""

import json
import re
from datetime import datetime
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from packages.valory.skills.abstract_round_abci.handlers import ABCIRoundHandler
from packages.valory.skills.abstract_round_abci.handlers import (
    ContractApiHandler as BaseContractApiHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import (
    HttpHandler as BaseHttpHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import (
    IpfsHandler as BaseIpfsHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import (
    LedgerApiHandler as BaseLedgerApiHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import (
    SigningHandler as BaseSigningHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import (
    TendermintHandler as BaseTendermintHandler,
)
from packages.valory.skills.market_creation_manager_abci.handlers import (
    LlmHandler as BaseLlmHandler,
)
from packages.valory.skills.market_maker_abci.handlers import (
    ContractApiHandler,
    HttpCode,
    HttpHandler,
    HttpMethod,
    IpfsHandler,
    LedgerApiHandler,
    LlmHandler,
    MarketCreatorABCIRoundHandler,
    SigningHandler,
    TendermintHandler,
)


def _make_http_handler(
    endpoint: str = "http://localhost:8080/api",
) -> HttpHandler:
    """Create an HttpHandler with a mocked context, bypassing property restrictions."""
    context = MagicMock()
    context.params.service_endpoint_base = endpoint
    handler = HttpHandler.__new__(HttpHandler)
    handler._context = context
    handler._skill_context = context
    handler.setup()
    return handler


class TestHandlerAliases:
    """Test handler module-level aliases."""

    def test_abci_round_handler(self) -> None:
        """Test MarketCreatorABCIRoundHandler alias."""
        assert MarketCreatorABCIRoundHandler is ABCIRoundHandler

    def test_signing_handler(self) -> None:
        """Test SigningHandler alias."""
        assert SigningHandler is BaseSigningHandler

    def test_ledger_api_handler(self) -> None:
        """Test LedgerApiHandler alias."""
        assert LedgerApiHandler is BaseLedgerApiHandler

    def test_contract_api_handler(self) -> None:
        """Test ContractApiHandler alias."""
        assert ContractApiHandler is BaseContractApiHandler

    def test_tendermint_handler(self) -> None:
        """Test TendermintHandler alias."""
        assert TendermintHandler is BaseTendermintHandler

    def test_ipfs_handler(self) -> None:
        """Test IpfsHandler alias."""
        assert IpfsHandler is BaseIpfsHandler

    def test_llm_handler(self) -> None:
        """Test LlmHandler alias."""
        assert LlmHandler is BaseLlmHandler


class TestHttpCode:
    """Test HttpCode enum."""

    def test_ok_code(self) -> None:
        """Test OK code."""
        assert HttpCode.OK_CODE.value == 200

    def test_not_found_code(self) -> None:
        """Test not found code."""
        assert HttpCode.NOT_FOUND_CODE.value == 404

    def test_bad_request_code(self) -> None:
        """Test bad request code."""
        assert HttpCode.BAD_REQUEST_CODE.value == 400

    def test_not_ready(self) -> None:
        """Test not ready code."""
        assert HttpCode.NOT_READY.value == 503


class TestHttpMethod:
    """Test HttpMethod enum."""

    def test_get(self) -> None:
        """Test GET."""
        assert HttpMethod.GET.value == "get"

    def test_head(self) -> None:
        """Test HEAD."""
        assert HttpMethod.HEAD.value == "head"

    def test_post(self) -> None:
        """Test POST."""
        assert HttpMethod.POST.value == "post"


class TestHttpHandler:
    """Test HttpHandler class."""

    @pytest.fixture
    def handler(self) -> HttpHandler:
        """Create an HttpHandler instance for testing."""
        return _make_http_handler("http://myservice.example.com:8080/api")

    def test_setup_creates_handler_url_regex(self, handler: HttpHandler) -> None:
        """Test that setup creates handler_url_regex."""
        assert hasattr(handler, "handler_url_regex")
        assert handler.handler_url_regex is not None

    def test_setup_creates_routes(self, handler: HttpHandler) -> None:
        """Test that setup creates routes."""
        assert hasattr(handler, "routes")
        assert isinstance(handler.routes, dict)
        # POST routes are empty
        post_routes = handler.routes[("post",)]
        assert post_routes == []
        # GET/HEAD routes have healthcheck
        get_head_routes = handler.routes[("get", "head")]
        assert len(get_head_routes) == 1

    def test_setup_creates_json_content_header(self, handler: HttpHandler) -> None:
        """Test that setup creates json_content_header."""
        assert handler.json_content_header == "Content-Type: application/json\n"

    def test_handler_url_regex_matches_localhost(self, handler: HttpHandler) -> None:
        """Test URL regex matches localhost."""
        assert re.match(handler.handler_url_regex, "http://localhost:8000/healthcheck")

    def test_handler_url_regex_matches_127(self, handler: HttpHandler) -> None:
        """Test URL regex matches 127.0.0.1."""
        assert re.match(handler.handler_url_regex, "http://127.0.0.1:8000/healthcheck")

    def test_handler_url_regex_matches_custom_hostname(
        self, handler: HttpHandler
    ) -> None:
        """Test URL regex matches the custom hostname."""
        assert re.match(
            handler.handler_url_regex,
            "http://myservice.example.com:8080/healthcheck",
        )


class TestHttpHandlerGetHandler:
    """Test HttpHandler._get_handler method."""

    @pytest.fixture
    def handler(self) -> HttpHandler:
        """Create an HttpHandler instance for testing."""
        return _make_http_handler("http://localhost:8080/api")

    def test_get_handler_health_get(self, handler: HttpHandler) -> None:
        """Test _get_handler matches healthcheck for GET."""
        fn, kwargs = handler._get_handler("http://localhost:8080/healthcheck", "get")
        assert fn is not None
        assert fn == handler._handle_get_health

    def test_get_handler_health_head(self, handler: HttpHandler) -> None:
        """Test _get_handler matches healthcheck for HEAD."""
        fn, kwargs = handler._get_handler("http://localhost:8080/healthcheck", "head")
        assert fn is not None
        assert fn == handler._handle_get_health

    def test_get_handler_unknown_url_returns_none(self, handler: HttpHandler) -> None:
        """Test _get_handler returns None for non-matching URL."""
        fn, kwargs = handler._get_handler("http://unknown.host.com/something", "get")
        assert fn is None

    def test_get_handler_post_no_routes(self, handler: HttpHandler) -> None:
        """Test _get_handler returns bad_request for matched URL with no POST routes."""
        fn, kwargs = handler._get_handler("http://localhost:8080/healthcheck", "post")
        assert fn == handler._handle_bad_request

    def test_get_handler_unmatched_route_returns_bad_request(
        self, handler: HttpHandler
    ) -> None:
        """Test _get_handler returns bad_request for matched base URL, unmatched route."""
        fn, kwargs = handler._get_handler("http://localhost:8080/unknown_path", "get")
        assert fn == handler._handle_bad_request


class TestHttpHandlerHandle:
    """Test HttpHandler.handle method."""

    @pytest.fixture
    def handler(self) -> HttpHandler:
        """Create an HttpHandler instance for testing."""
        return _make_http_handler("http://localhost:8080/api")

    def test_handle_non_request_calls_super(self, handler: HttpHandler) -> None:
        """Test that non-REQUEST performative calls super."""
        from packages.valory.protocols.http import HttpMessage

        msg = MagicMock(spec=HttpMessage)
        msg.performative = HttpMessage.Performative.RESPONSE
        msg.sender = "some_sender"

        with patch.object(BaseHttpHandler, "handle") as mock_super:
            handler.handle(msg)
            mock_super.assert_called_once_with(msg)

    def test_handle_wrong_sender_calls_super(self, handler: HttpHandler) -> None:
        """Test that wrong sender calls super."""
        from packages.valory.protocols.http import HttpMessage

        msg = MagicMock(spec=HttpMessage)
        msg.performative = HttpMessage.Performative.REQUEST
        msg.sender = "wrong_sender"

        with patch.object(BaseHttpHandler, "handle") as mock_super:
            handler.handle(msg)
            mock_super.assert_called_once_with(msg)

    def test_handle_no_handler_match_calls_super(self, handler: HttpHandler) -> None:
        """Test that no URL handler match calls super."""
        from packages.valory.connections.http_server.connection import (
            PUBLIC_ID as HTTP_SERVER_PUBLIC_ID,
        )
        from packages.valory.protocols.http import HttpMessage

        msg = MagicMock(spec=HttpMessage)
        msg.performative = HttpMessage.Performative.REQUEST
        msg.sender = str(HTTP_SERVER_PUBLIC_ID.without_hash())
        msg.url = "http://unknown-host.com/something"
        msg.method = "get"

        with patch.object(BaseHttpHandler, "handle") as mock_super:
            handler.handle(msg)
            mock_super.assert_called_once_with(msg)


class TestHttpHandlerBadRequest:
    """Test HttpHandler._handle_bad_request."""

    def test_bad_request_sends_400(self) -> None:
        """Test bad request sends 400 response."""
        handler = _make_http_handler()

        http_msg = MagicMock()
        http_msg.version = "1.1"
        http_msg.headers = "Host: localhost"

        http_dialogue = MagicMock()
        http_response = MagicMock()
        http_dialogue.reply.return_value = http_response

        handler._handle_bad_request(http_msg, http_dialogue)

        http_dialogue.reply.assert_called_once()
        call_kwargs = http_dialogue.reply.call_args
        assert call_kwargs.kwargs["status_code"] == 400
        handler.context.outbox.put_message.assert_called_once()


class TestHttpHandlerSendOkResponse:
    """Test HttpHandler._send_ok_response."""

    def test_send_ok_response(self) -> None:
        """Test OK response sends 200 with JSON data."""
        handler = _make_http_handler()

        http_msg = MagicMock()
        http_msg.version = "1.1"
        http_msg.headers = "Host: localhost"

        http_dialogue = MagicMock()
        http_response = MagicMock()
        http_dialogue.reply.return_value = http_response

        data = {"key": "value"}
        handler._send_ok_response(http_msg, http_dialogue, data)

        http_dialogue.reply.assert_called_once()
        call_kwargs = http_dialogue.reply.call_args
        assert call_kwargs.kwargs["status_code"] == 200
        assert call_kwargs.kwargs["body"] == json.dumps(data).encode("utf-8")
        handler.context.outbox.put_message.assert_called_once()


class TestHttpHandlerGetHealth:
    """Test HttpHandler._handle_get_health."""

    def test_health_no_last_transition(self) -> None:
        """Test health response when no last transition timestamp."""
        handler = _make_http_handler()
        context = handler.context
        context.params.reset_pause_duration = 60

        # Mock state
        round_sequence = MagicMock()
        round_sequence._last_round_transition_timestamp = None
        round_sequence._abci_app = None
        context.state.round_sequence = round_sequence

        # Mock synchronized_data
        with patch.object(
            HttpHandler,
            "synchronized_data",
            new_callable=PropertyMock,
        ) as mock_sync:
            mock_sync.return_value = MagicMock(period_count=5)

            http_msg = MagicMock()
            http_dialogue = MagicMock()
            http_response = MagicMock()
            http_dialogue.reply.return_value = http_response

            handler._handle_get_health(http_msg, http_dialogue)

            # Should call _send_ok_response
            http_dialogue.reply.assert_called_once()
            call_kwargs = http_dialogue.reply.call_args
            body = json.loads(call_kwargs.kwargs["body"].decode("utf-8"))

            assert body["seconds_since_last_transition"] is None
            assert body["is_tm_healthy"] is True  # not is_tm_unhealthy (None)
            assert body["period"] == 5
            assert body["rounds"] is None
            assert body["is_transitioning_fast"] is None

    def test_health_with_last_transition(self) -> None:
        """Test health response when last transition exists."""
        handler = _make_http_handler()
        context = handler.context
        context.params.reset_pause_duration = 60

        # Mock state
        round_sequence = MagicMock()
        timestamp = datetime.now()
        round_sequence._last_round_transition_timestamp = timestamp
        round_sequence.block_stall_deadline_expired = False

        # Mock abci_app
        current_round = MagicMock()
        current_round.round_id = "CurrentRound"
        prev_round_1 = MagicMock()
        prev_round_1.round_id = "PrevRound1"
        round_sequence._abci_app.current_round = current_round
        round_sequence._abci_app._previous_rounds = [prev_round_1]

        context.state.round_sequence = round_sequence

        with patch.object(
            HttpHandler,
            "synchronized_data",
            new_callable=PropertyMock,
        ) as mock_sync:
            mock_sync.return_value = MagicMock(period_count=10)

            http_msg = MagicMock()
            http_dialogue = MagicMock()
            http_response = MagicMock()
            http_dialogue.reply.return_value = http_response

            handler._handle_get_health(http_msg, http_dialogue)

            http_dialogue.reply.assert_called_once()
            call_kwargs = http_dialogue.reply.call_args
            body = json.loads(call_kwargs.kwargs["body"].decode("utf-8"))

            assert body["seconds_since_last_transition"] is not None
            assert isinstance(body["seconds_since_last_transition"], float)
            assert body["period"] == 10
            assert body["rounds"] is not None
            assert "CurrentRound" in body["rounds"]

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

"""Tests for the handlers of the MarketCreationManagerAbciApp."""

from unittest.mock import MagicMock

import pytest
from aea.configurations.data_types import PublicId

from packages.valory.protocols.llm import LlmMessage
from packages.valory.skills.abstract_round_abci.handlers import (
    ABCIRoundHandler as BaseABCIRoundHandler,
)
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
    ABCIHandler,
    ContractApiHandler,
    HttpHandler,
    IpfsHandler,
    LedgerApiHandler,
    LlmHandler,
    SigningHandler,
    TendermintHandler,
)


def test_handler_aliases() -> None:
    """Test that all handler aliases point to the correct base classes."""
    assert ABCIHandler is BaseABCIRoundHandler
    assert HttpHandler is BaseHttpHandler
    assert SigningHandler is BaseSigningHandler
    assert LedgerApiHandler is BaseLedgerApiHandler
    assert ContractApiHandler is BaseContractApiHandler
    assert TendermintHandler is BaseTendermintHandler
    assert IpfsHandler is BaseIpfsHandler


@pytest.mark.parametrize(
    "handler_cls, base_handler_cls",
    [
        (ABCIHandler, BaseABCIRoundHandler),
        (HttpHandler, BaseHttpHandler),
        (SigningHandler, BaseSigningHandler),
        (LedgerApiHandler, BaseLedgerApiHandler),
        (ContractApiHandler, BaseContractApiHandler),
        (TendermintHandler, BaseTendermintHandler),
        (IpfsHandler, BaseIpfsHandler),
    ],
)
def test_handler_isinstance(handler_cls, base_handler_cls) -> None:
    """Test that handler aliases are the same class as their base."""
    assert handler_cls is base_handler_cls


class TestLlmHandler:
    """Tests for LlmHandler."""

    def test_supported_protocol(self) -> None:
        """Test that LlmHandler has the correct SUPPORTED_PROTOCOL."""
        assert LlmHandler.SUPPORTED_PROTOCOL == LlmMessage.protocol_id

    def test_allowed_response_performatives(self) -> None:
        """Test that LlmHandler has the correct allowed_response_performatives."""
        expected = frozenset(
            {
                LlmMessage.Performative.REQUEST,
                LlmMessage.Performative.RESPONSE,
            }
        )
        assert LlmHandler.allowed_response_performatives == expected

    def test_instantiation(self) -> None:
        """Test that LlmHandler can be instantiated."""
        handler = LlmHandler(
            name="llm_handler",
            skill_context=MagicMock(skill_id=PublicId.from_str("dummy/skill:0.1.0")),
        )
        assert handler is not None
        assert handler.SUPPORTED_PROTOCOL == LlmMessage.protocol_id

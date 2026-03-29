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

"""Tests for the handlers of the OmenFundsRecovererAbciApp."""

import pytest

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
from packages.valory.skills.omen_funds_recoverer_abci.handlers import (
    ABCIHandler,
    ContractApiHandler,
    HttpHandler,
    IpfsHandler,
    LedgerApiHandler,
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
def test_handler_isinstance(handler_cls: type, base_handler_cls: type) -> None:
    """Test that handler aliases are the same class as their base."""
    assert handler_cls is base_handler_cls

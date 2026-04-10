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

"""Tests for handlers in the omen_fpmm_remove_liquidity_abci skill."""

import packages.valory.skills.omen_fpmm_remove_liquidity_abci.handlers as handlers_module
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


class TestHandlers:
    """Tests that all handler aliases are correctly exported."""

    def test_abci_handler_alias(self) -> None:
        """Test that ABCIHandler in skill is the base ABCIRoundHandler."""
        assert handlers_module.ABCIHandler is BaseABCIRoundHandler

    def test_http_handler_alias(self) -> None:
        """Test that HttpHandler is correctly re-exported."""
        assert handlers_module.HttpHandler is BaseHttpHandler

    def test_signing_handler_alias(self) -> None:
        """Test that SigningHandler is correctly re-exported."""
        assert handlers_module.SigningHandler is BaseSigningHandler

    def test_ledger_api_handler_alias(self) -> None:
        """Test that ledgerApiHandler is correctly re-exported."""
        assert handlers_module.LedgerApiHandler is BaseLedgerApiHandler

    def test_contract_api_handler_alias(self) -> None:
        """Test that contractApiHandler is correctly re-exported."""
        assert handlers_module.ContractApiHandler is BaseContractApiHandler

    def test_tendermint_handler_alias(self) -> None:
        """Test that TendermintHandler is correctly re-exported."""
        assert handlers_module.TendermintHandler is BaseTendermintHandler

    def test_ipfs_handler_alias(self) -> None:
        """Test that IpfsHandler is correctly re-exported."""
        assert handlers_module.IpfsHandler is BaseIpfsHandler

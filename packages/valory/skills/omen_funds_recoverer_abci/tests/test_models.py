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

"""Tests for the omen_funds_recoverer_abci models."""

# pylint: disable=protected-access,too-few-public-methods

from unittest.mock import MagicMock, patch

from packages.valory.skills.abstract_round_abci.models import BaseParams
from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.omen_funds_recoverer_abci.models import (
    BenchmarkTool,
    OmenFundsRecovererParams,
    Requests,
    SharedState,
)
from packages.valory.skills.omen_funds_recoverer_abci.rounds import (
    OmenFundsRecovererAbciApp,
)


class TestModelAliases:
    """Test module-level model aliases."""

    def test_requests_alias(self) -> None:
        """Test Requests is aliased correctly."""
        assert Requests is BaseRequests

    def test_benchmark_tool_alias(self) -> None:
        """Test BenchmarkTool is aliased correctly."""
        assert BenchmarkTool is BaseBenchmarkTool


class TestSharedState:
    """Test SharedState."""

    def test_abci_app_cls(self) -> None:
        """Test abci_app_cls is set correctly."""
        assert SharedState.abci_app_cls is OmenFundsRecovererAbciApp

    def test_init(self) -> None:
        """Test SharedState __init__ calls super().__init__."""
        mock_context = MagicMock()
        with patch(
            "packages.valory.skills.abstract_round_abci.models.SharedState.__init__",
            return_value=None,
        ):
            obj = SharedState.__new__(SharedState)
            SharedState.__init__(obj, skill_context=mock_context)


class TestOmenFundsRecovererParams:
    """Test OmenFundsRecovererParams."""

    def test_is_subclass(self) -> None:
        """Test it is a subclass of BaseParams."""
        assert issubclass(OmenFundsRecovererParams, BaseParams)

    def test_init_parses_all_params(self) -> None:
        """Test that __init__ parses all required parameters via _ensure."""
        mock_self = MagicMock(spec=OmenFundsRecovererParams)
        mock_self._ensure = MagicMock(
            side_effect=lambda key, kwargs, type_=None: kwargs.pop(key)
        )
        kwargs = {
            "liquidity_removal_lead_time": 86400,
            "remove_liquidity_batch_size": 3,
            "redeem_positions_batch_size": 5,
            "claim_bonds_batch_size": 10,
            "min_balance_withdraw_realitio": 10**19,
            "realitio_contract": "0xRealitio",
            "realitio_oracle_proxy_contract": "0xRealitioProxy",
            "conditional_tokens_contract": "0xCT",
            "collateral_tokens_contract": "0xCollateral",
        }
        with patch.object(BaseParams, "__init__", return_value=None):
            OmenFundsRecovererParams.__init__(mock_self, **kwargs)
        assert mock_self.liquidity_removal_lead_time == 86400
        assert mock_self.remove_liquidity_batch_size == 3
        assert mock_self.redeem_positions_batch_size == 5
        assert mock_self.claim_bonds_batch_size == 10
        assert mock_self.min_balance_withdraw_realitio == 10**19
        assert mock_self.realitio_contract == "0xRealitio"
        assert mock_self.realitio_oracle_proxy_contract == "0xRealitioProxy"
        assert mock_self.conditional_tokens_contract == "0xCT"
        assert mock_self.collateral_tokens_contract == "0xCollateral"

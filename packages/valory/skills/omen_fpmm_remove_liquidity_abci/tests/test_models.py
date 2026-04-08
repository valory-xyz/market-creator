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

"""Tests for models in the omen_fpmm_remove_liquidity_abci skill."""

# pylint: disable=protected-access,import-outside-toplevel

from unittest.mock import MagicMock

from packages.valory.skills.omen_fpmm_remove_liquidity_abci.models import (
    BenchmarkTool,
    FpmmRemoveLiquidityParams,
    OmenSubgraph,
    Requests,
    SharedState,
)
from packages.valory.skills.omen_fpmm_remove_liquidity_abci.rounds import (
    OmenFpmmRemoveLiquidityAbciApp,
)


class TestSharedState:
    """Tests for SharedState."""

    def test_abci_app_cls(self) -> None:
        """abci_app_cls is OmenFpmmRemoveLiquidityAbciApp."""
        assert SharedState.abci_app_cls is OmenFpmmRemoveLiquidityAbciApp

    def test_init_delegates_to_base(self) -> None:
        """__init__ delegates to BaseSharedState.__init__ with the same kwargs."""
        from unittest.mock import patch

        from packages.valory.skills.abstract_round_abci.models import (
            SharedState as BaseSharedState,
        )

        instance = SharedState.__new__(SharedState)
        skill_context = MagicMock()
        with patch.object(BaseSharedState, "__init__", return_value=None) as mock_init:
            SharedState.__init__(instance, skill_context=skill_context)
        mock_init.assert_called_once()
        assert mock_init.call_args.kwargs["skill_context"] is skill_context


class TestFpmmRemoveLiquidityParams:
    """Tests for FpmmRemoveLiquidityParams."""

    def test_is_subclass_of_base_params(self) -> None:
        """Test that FpmmRemoveLiquidityParams is a subclass of BaseParams."""
        from packages.valory.skills.abstract_round_abci.models import BaseParams

        assert issubclass(FpmmRemoveLiquidityParams, BaseParams)

    def test_init_parses_all_params(self) -> None:
        """__init__ parses all four skill-specific params via _ensure, then calls super."""
        from unittest.mock import patch

        from packages.valory.skills.abstract_round_abci.models import BaseParams

        mock_self = MagicMock(spec=FpmmRemoveLiquidityParams)
        mock_self._ensure = MagicMock(
            side_effect=lambda key, kwargs, type_=None: kwargs.pop(key)
        )
        kwargs = {
            "liquidity_removal_lead_time": 86400,
            "fpmm_remove_liquidity_batch_size": 3,
            "conditional_tokens_contract": "0xCT",
            "collateral_tokens_contract": "0xCollateral",
        }
        with patch.object(BaseParams, "__init__", return_value=None):
            FpmmRemoveLiquidityParams.__init__(mock_self, **kwargs)

        assert mock_self.liquidity_removal_lead_time == 86400
        assert mock_self.fpmm_remove_liquidity_batch_size == 3
        assert mock_self.conditional_tokens_contract == "0xCT"
        assert mock_self.collateral_tokens_contract == "0xCollateral"


class TestModelAliases:
    """Tests that Requests and BenchmarkTool are properly aliased."""

    def test_requests_alias(self) -> None:
        """Test that Requests is the base Requests class."""
        from packages.valory.skills.abstract_round_abci.models import (
            Requests as BaseRequests,
        )

        assert Requests is BaseRequests

    def test_benchmark_tool_alias(self) -> None:
        """Test that BenchmarkTool is the base BenchmarkTool class."""
        from packages.valory.skills.abstract_round_abci.models import (
            BenchmarkTool as BaseBenchmarkTool,
        )

        assert BenchmarkTool is BaseBenchmarkTool

    def test_omen_subgraph_is_api_specs(self) -> None:
        """Test that OmenSubgraph inherits from ApiSpecs."""
        from packages.valory.skills.abstract_round_abci.models import ApiSpecs

        assert issubclass(OmenSubgraph, ApiSpecs)

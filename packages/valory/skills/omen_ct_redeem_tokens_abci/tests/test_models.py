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

"""Tests for the omen_ct_redeem_tokens_abci models."""

from unittest.mock import MagicMock, patch

from packages.valory.skills.abstract_round_abci.models import BaseParams
from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.omen_ct_redeem_tokens_abci.models import (
    BenchmarkTool,
    CtRedeemTokensParams,
    Requests,
    SharedState,
)
from packages.valory.skills.omen_ct_redeem_tokens_abci.rounds import (
    OmenCtRedeemTokensAbciApp,
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
        assert SharedState.abci_app_cls is OmenCtRedeemTokensAbciApp

    def test_ignored_ct_positions_initialized(self) -> None:
        """Test ignored_ct_positions is initialized to empty set."""
        state = SharedState.__new__(SharedState)
        # Call our __init__ directly, patching the parent so it doesn't
        # require a full AEA context.
        with patch(
            "packages.valory.skills.omen_ct_redeem_tokens_abci.models.BaseSharedState.__init__"
        ):
            state.__init__(skill_context=MagicMock())  # type: ignore
        assert hasattr(state, "ignored_ct_positions")
        assert state.ignored_ct_positions == set()


class TestCtRedeemTokensParams:
    """Test CtRedeemTokensParams."""

    def test_is_subclass(self) -> None:
        """Test it is a subclass of BaseParams."""
        assert issubclass(CtRedeemTokensParams, BaseParams)

    def test_init_parses_all_params(self) -> None:
        """Test that __init__ parses all required parameters via _ensure."""
        mock_self = MagicMock(spec=CtRedeemTokensParams)
        mock_self._ensure = MagicMock(
            side_effect=lambda key, kwargs, type_=None: kwargs.pop(key)
        )
        kwargs = {
            "ct_redeem_tokens_batch_size": 5,
            "ct_redeem_tokens_min_payout": 0,
            "conditional_tokens_contract": "0xCT",
            "realitio_oracle_proxy_contract": "0xRealitioProxy",
            "collateral_tokens_contract": "0xCollateral",
        }
        with patch.object(BaseParams, "__init__", return_value=None):
            CtRedeemTokensParams.__init__(mock_self, **kwargs)
        assert mock_self.ct_redeem_tokens_batch_size == 5
        assert mock_self.ct_redeem_tokens_min_payout == 0
        assert mock_self.conditional_tokens_contract == "0xCT"
        assert mock_self.realitio_oracle_proxy_contract == "0xRealitioProxy"
        assert mock_self.collateral_tokens_contract == "0xCollateral"

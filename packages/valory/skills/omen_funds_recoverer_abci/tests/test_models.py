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

from unittest.mock import MagicMock

import pytest

from packages.valory.skills.abstract_round_abci.models import (
    ApiSpecs,
    BaseParams,
)
from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.abstract_round_abci.models import (
    SharedState as BaseSharedState,
)
from packages.valory.skills.omen_funds_recoverer_abci.models import (
    BenchmarkTool,
    ConditionalTokensSubgraph,
    OmenFundsRecovererParams,
    OmenSubgraph,
    RealitioSubgraph,
    Requests,
    SharedState,
)
from packages.valory.skills.omen_funds_recoverer_abci.rounds import (
    OmenFundsRecovererAbciApp,
)


class TestModelAliases:
    """Test module-level model aliases."""

    def test_requests_alias(self) -> None:
        """Test Requests alias."""
        assert Requests is BaseRequests

    def test_benchmark_tool_alias(self) -> None:
        """Test BenchmarkTool alias."""
        assert BenchmarkTool is BaseBenchmarkTool


class TestSharedState:
    """Test SharedState class."""

    def test_inherits_base_shared_state(self) -> None:
        """Test inheritance."""
        assert issubclass(SharedState, BaseSharedState)

    def test_abci_app_cls(self) -> None:
        """Test abci_app_cls is set."""
        assert SharedState.abci_app_cls == OmenFundsRecovererAbciApp

    def test_init(self) -> None:
        """Test that SharedState can be instantiated with mock skill_context."""
        context = MagicMock()
        context.is_abstract_component = True
        state = SharedState(skill_context=context, name="state")
        assert state is not None


class TestSubgraphModels:
    """Test subgraph model classes."""

    def test_omen_subgraph_inherits_api_specs(self) -> None:
        """Test OmenSubgraph inherits from ApiSpecs."""
        assert issubclass(OmenSubgraph, ApiSpecs)

    def test_conditional_tokens_subgraph_inherits_api_specs(self) -> None:
        """Test ConditionalTokensSubgraph inherits from ApiSpecs."""
        assert issubclass(ConditionalTokensSubgraph, ApiSpecs)

    def test_realitio_subgraph_inherits_api_specs(self) -> None:
        """Test RealitioSubgraph inherits from ApiSpecs."""
        assert issubclass(RealitioSubgraph, ApiSpecs)


class TestOmenFundsRecovererParams:
    """Test OmenFundsRecovererParams class."""

    def test_inherits_base_params(self) -> None:
        """Test inheritance."""
        assert issubclass(OmenFundsRecovererParams, BaseParams)

    def test_has_multisend_annotations(self) -> None:
        """Test that multisend_address and multisend_batch_size are class annotations."""
        annotations = OmenFundsRecovererParams.__annotations__
        assert "multisend_address" in annotations
        assert annotations["multisend_address"] is str
        assert "multisend_batch_size" in annotations
        assert annotations["multisend_batch_size"] is int

    def test_init_with_all_params(self) -> None:
        """Test OmenFundsRecovererParams initialization with all required parameters."""
        context = MagicMock()
        context.is_abstract_component = True
        kwargs = {
            "skill_context": context,
            "name": "params",
            "liquidity_removal_lead_time": 86400,
            "remove_liquidity_batch_size": 3,
            "redeem_positions_batch_size": 5,
            "claim_bonds_batch_size": 10,
            "min_balance_withdraw_realitio": 10000000000000000000,
            "realitio_start_block": 0,
            "realitio_contract": "0x0000000000000000000000000000000000000000",
            "realitio_oracle_proxy_contract": "0x0000000000000000000000000000000000000000",
            "conditional_tokens_contract": "0x0000000000000000000000000000000000000000",
            "collateral_tokens_contract": "0x0000000000000000000000000000000000000000",
            # BaseParams required fields
            "genesis_config": {
                "genesis_time": "2022-05-20T16:00:21.735122717Z",
                "chain_id": "chain-c4daS1",
                "consensus_params": {
                    "block": {
                        "max_bytes": "22020096",
                        "max_gas": "-1",
                        "time_iota_ms": "1000",
                    },
                    "evidence": {
                        "max_age_duration": "172800000000000",
                        "max_age_num_blocks": "100000",
                        "max_bytes": "1048576",
                    },
                    "validator": {"pub_key_types": ["ed25519"]},
                    "version": {},
                },
                "voting_power": "10",
            },
            "service_id": "omen_funds_recoverer",
            "tendermint_url": "http://localhost:26657",
            "max_healthcheck": 120,
            "round_timeout_seconds": 60.0,
            "sleep_time": 1,
            "retry_timeout": 3,
            "retry_attempts": 400,
            "keeper_timeout": 30.0,
            "reset_pause_duration": 1800,
            "drand_public_key": "868f005eb8e6e4ca0a47c8a77ceaa5309a47978a7c71bc5cce96366b5d7a569937c529eeda66c7293784a9402801af31",
            "tendermint_com_url": "http://localhost:8080",
            "tendermint_max_retries": 5,
            "tendermint_check_sleep_delay": 3,
            "reset_tendermint_after": 1,
            "cleanup_history_depth": 1,
            "cleanup_history_depth_current": None,
            "request_timeout": 10.0,
            "request_retry_delay": 1.0,
            "tx_timeout": 10.0,
            "max_attempts": 10,
            "service_registry_address": None,
            "on_chain_service_id": None,
            "share_tm_config_on_startup": False,
            "tendermint_p2p_url": "localhost:26656",
            "use_termination": False,
            "use_slashing": False,
            "slash_cooldown_hours": 3,
            "slash_threshold_amount": 10000000000000000,
            "light_slash_unit_amount": 5000000000000000,
            "serious_slash_unit_amount": 8000000000000000,
            "setup": {
                "all_participants": ["0x0000000000000000000000000000000000000000"],
                "consensus_threshold": None,
                "safe_contract_address": "0x0000000000000000000000000000000000000000",
            },
            "ipfs_domain_name": None,
            "keeper_allowed_retries": 3,
            "multisend_address": "0x0000000000000000000000000000000000000000",
            "multisend_batch_size": 5,
            "ipfs_address": "https://gateway.autonolas.tech/ipfs/",
            "validate_timeout": 1205,
            "finalize_timeout": 60.0,
            "history_check_timeout": 1205,
        }
        params = OmenFundsRecovererParams(**kwargs)
        assert params.liquidity_removal_lead_time == 86400
        assert params.remove_liquidity_batch_size == 3
        assert params.redeem_positions_batch_size == 5
        assert params.claim_bonds_batch_size == 10
        assert params.min_balance_withdraw_realitio == 10000000000000000000
        assert params.realitio_start_block == 0
        assert params.realitio_contract == "0x0000000000000000000000000000000000000000"
        assert (
            params.realitio_oracle_proxy_contract
            == "0x0000000000000000000000000000000000000000"
        )
        assert (
            params.conditional_tokens_contract
            == "0x0000000000000000000000000000000000000000"
        )
        assert (
            params.collateral_tokens_contract
            == "0x0000000000000000000000000000000000000000"
        )

    def test_missing_required_param_raises(self) -> None:
        """Test that missing a required param raises an error."""
        context = MagicMock()
        context.is_abstract_component = True
        # Missing 'liquidity_removal_lead_time' should cause _ensure to raise
        kwargs = {
            "skill_context": context,
            "name": "params",
            # liquidity_removal_lead_time is missing
            "remove_liquidity_batch_size": 3,
            "redeem_positions_batch_size": 5,
            "claim_bonds_batch_size": 10,
            "min_balance_withdraw_realitio": 10000000000000000000,
            "realitio_start_block": 0,
            "realitio_contract": "0x0000000000000000000000000000000000000000",
            "realitio_oracle_proxy_contract": "0x0000000000000000000000000000000000000000",
            "conditional_tokens_contract": "0x0000000000000000000000000000000000000000",
            "collateral_tokens_contract": "0x0000000000000000000000000000000000000000",
        }
        with pytest.raises(Exception):
            OmenFundsRecovererParams(**kwargs)

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

"""Tests for the market_maker_abci models."""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.market_creation_manager_abci.models import (
    OmenSubgraph as BaseOmenSubgraph,
)
from packages.valory.skills.market_creation_manager_abci.models import (
    RandomnessApi as MarketCreationManagerRandomnessApi,
)
from packages.valory.skills.market_creation_manager_abci.models import (
    SharedState as BaseSharedState,
)
from packages.valory.skills.market_maker_abci.models import (
    BenchmarkTool,
    MARGIN,
    MULTIPLIER,
    OmenSubgraph,
    Params,
    RandomnessApi,
    Requests,
    SharedState,
)
from packages.valory.skills.termination_abci.models import TerminationParams


class TestModelAliases:
    """Test module-level model aliases."""

    def test_requests_alias(self) -> None:
        """Test Requests alias."""
        assert Requests is BaseRequests

    def test_benchmark_tool_alias(self) -> None:
        """Test BenchmarkTool alias."""
        assert BenchmarkTool is BaseBenchmarkTool

    def test_randomness_api_alias(self) -> None:
        """Test RandomnessApi alias."""
        assert RandomnessApi is MarketCreationManagerRandomnessApi

    def test_omen_subgraph_alias(self) -> None:
        """Test OmenSubgraph alias."""
        assert OmenSubgraph is BaseOmenSubgraph


class TestConstants:
    """Test module-level constants."""

    def test_margin(self) -> None:
        """Test MARGIN value."""
        assert MARGIN == 5

    def test_multiplier(self) -> None:
        """Test MULTIPLIER value."""
        assert MULTIPLIER == 2


class TestSharedState:
    """Test SharedState class."""

    def test_inherits_base_shared_state(self) -> None:
        """Test inheritance."""
        assert issubclass(SharedState, BaseSharedState)

    def test_realitio_claim_build_cache_initialized(self) -> None:
        """The withdraw-bonds claim cache must be initialized on the shared state.

        Regression: ``RealitioWithdrawBondsBehaviour._build_claim_txs``
        reads ``self.context.state.realitio_claim_build_cache``. That
        attribute only exists if ``RealitioWithdrawBondsSharedState`` is in
        this composed ``SharedState``'s MRO so its ``__init__`` runs via the
        cooperative ``super()`` chain (same mechanism as
        ``ignored_ct_positions``). When it was absent the round raised
        ``AttributeError`` -> ``stop_and_exit`` -> Propel restart loop.
        """
        from unittest.mock import MagicMock

        from packages.valory.skills.omen_realitio_withdraw_bonds_abci.models import (
            SharedState as RealitioWithdrawBondsSharedState,
        )

        assert RealitioWithdrawBondsSharedState in SharedState.__mro__
        state = SharedState(name="state", skill_context=MagicMock())
        assert state.realitio_claim_build_cache == {}

    def test_abci_app_cls(self) -> None:
        """Test abci_app_cls is set."""
        from packages.valory.skills.market_maker_abci.composition import (
            MarketCreatorAbciApp,
        )

        assert SharedState.abci_app_cls == MarketCreatorAbciApp

    def test_setup_populates_event_to_timeout(self) -> None:
        """Test that setup populates event_to_timeout with the right keys."""
        from packages.valory.skills.funds_forwarder_abci.rounds import (
            Event as FundsForwarderEvent,
        )
        from packages.valory.skills.identify_service_owner_abci.rounds import (
            Event as IdentifyServiceOwnerEvent,
        )
        from packages.valory.skills.market_creation_manager_abci.rounds import (
            Event as MarketCreationManagerEvent,
        )
        from packages.valory.skills.market_maker_abci.composition import (
            MarketCreatorAbciApp,
        )
        from packages.valory.skills.reset_pause_abci.rounds import (
            Event as ResetPauseEvent,
        )
        from packages.valory.skills.transaction_settlement_abci.rounds import (
            Event as TSEvent,
        )

        context = MagicMock()
        context.params.round_timeout_seconds = 30
        context.params.reset_pause_duration = 10
        context.params.validate_timeout = 60
        context.params.finalize_timeout = 90
        context.params.history_check_timeout = 120

        state = SharedState.__new__(SharedState)
        state._context = context  # type: ignore[attr-defined]
        state._skill_context = context  # type: ignore[attr-defined]

        with patch.object(BaseSharedState, "setup"):
            state.setup()

        assert (
            MarketCreatorAbciApp.event_to_timeout[
                MarketCreationManagerEvent.ROUND_TIMEOUT
            ]
            == 30
        )
        assert MarketCreatorAbciApp.event_to_timeout[TSEvent.ROUND_TIMEOUT] == 30
        assert (
            MarketCreatorAbciApp.event_to_timeout[ResetPauseEvent.ROUND_TIMEOUT] == 30
        )
        assert (
            MarketCreatorAbciApp.event_to_timeout[TSEvent.RESET_TIMEOUT]
            == 30 * MULTIPLIER
        )
        assert MarketCreatorAbciApp.event_to_timeout[TSEvent.VALIDATE_TIMEOUT] == 60
        assert MarketCreatorAbciApp.event_to_timeout[TSEvent.FINALIZE_TIMEOUT] == 90
        assert MarketCreatorAbciApp.event_to_timeout[TSEvent.CHECK_TIMEOUT] == 120
        assert (
            MarketCreatorAbciApp.event_to_timeout[
                ResetPauseEvent.RESET_AND_PAUSE_TIMEOUT
            ]
            == 10 + MARGIN
        )
        assert (
            MarketCreatorAbciApp.event_to_timeout[
                IdentifyServiceOwnerEvent.ROUND_TIMEOUT
            ]
            == 30
        )
        assert (
            MarketCreatorAbciApp.event_to_timeout[FundsForwarderEvent.ROUND_TIMEOUT]
            == 30
        )


class TestParams:
    """Test Params class."""

    def test_params_mro(self) -> None:
        """Test Params inherits from all required param classes."""
        from packages.valory.skills.market_creation_manager_abci.models import (
            MarketCreationManagerParams,
        )

        assert issubclass(Params, MarketCreationManagerParams)
        assert issubclass(Params, TerminationParams)


class TestSkillYamlParamsContract:
    """Assert every param declared in skill.yaml is read by some Params class.

    The yaml-to-code contract is only enforced in one direction. ``_ensure``
    raises ``AEAEnforceError`` when a key is missing, so "code needs X, yaml
    lacks it" fails loudly at skill load. The reverse is silent: a key nobody
    reads reaches ``SkillComponent.__init__``, which only logs a warning that
    nothing asserts on. Seven dead params survived roughly two years here
    through exactly that gap.

    Residual kwargs are NOT a usable signal for this: ``_ensure`` pops the key
    but ``kwargs.get`` does not, so every param read the non-popping way stays
    in the dict and would look dead. This scans for the read instead.
    """

    SKILL_YAML = Path(__file__).parent.parent / "skill.yaml"
    SKILLS_DIR = Path(__file__).parent.parent.parent

    # Matches, in order: any _ensure variant taking the key positionally or by
    # keyword; a non-popping or popping kwargs read; and direct subscript access.
    READ_PATTERNS = (
        re.compile(r"_ensure[a-z_]*\(\s*(?:key\s*=\s*)?[\"']([a-z0-9_]+)[\"']"),
        re.compile(r"kwargs\.(?:get|pop)\(\s*[\"']([a-z0-9_]+)[\"']"),
        re.compile(r"kwargs\[\s*[\"']([a-z0-9_]+)[\"']\s*\]"),
    )

    def _consumed_keys(self) -> set:
        """Collect every param key read by any models.py under packages/valory/skills."""
        consumed = set()
        for models_py in self.SKILLS_DIR.glob("*/models.py"):
            source = models_py.read_text(errors="ignore")
            for pattern in self.READ_PATTERNS:
                consumed.update(pattern.findall(source))
        return consumed

    def test_every_declared_param_is_read(self) -> None:
        """No param may be declared in skill.yaml and read by nothing."""
        declared = set(
            yaml.safe_load(self.SKILL_YAML.read_text())["models"]["params"]["args"]
        )
        unread = sorted(declared - self._consumed_keys())
        assert not unread, (
            "skill.yaml declares params that no Params class reads, so they are "
            f"silently dropped at runtime: {unread}"
        )

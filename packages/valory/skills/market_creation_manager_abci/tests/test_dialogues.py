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

"""Tests for the dialogues of the MarketCreationManagerAbciApp."""

import packages.valory.skills.market_creation_manager_abci.dialogues as dialogues_mod  # noqa: F401
from packages.valory.skills.abstract_round_abci.dialogues import (
    AbciDialogue as BaseAbciDialogue,
)
from packages.valory.skills.abstract_round_abci.dialogues import (
    AbciDialogues as BaseAbciDialogues,
)
from packages.valory.skills.abstract_round_abci.dialogues import (
    ContractApiDialogue as BaseContractApiDialogue,
)
from packages.valory.skills.abstract_round_abci.dialogues import (
    ContractApiDialogues as BaseContractApiDialogues,
)
from packages.valory.skills.abstract_round_abci.dialogues import (
    HttpDialogue as BaseHttpDialogue,
)
from packages.valory.skills.abstract_round_abci.dialogues import (
    HttpDialogues as BaseHttpDialogues,
)
from packages.valory.skills.abstract_round_abci.dialogues import (
    IpfsDialogue as BaseIpfsDialogue,
)
from packages.valory.skills.abstract_round_abci.dialogues import (
    IpfsDialogues as BaseIpfsDialogues,
)
from packages.valory.skills.abstract_round_abci.dialogues import (
    LedgerApiDialogue as BaseLedgerApiDialogue,
)
from packages.valory.skills.abstract_round_abci.dialogues import (
    LedgerApiDialogues as BaseLedgerApiDialogues,
)
from packages.valory.skills.abstract_round_abci.dialogues import (
    SigningDialogue as BaseSigningDialogue,
)
from packages.valory.skills.abstract_round_abci.dialogues import (
    SigningDialogues as BaseSigningDialogues,
)
from packages.valory.skills.abstract_round_abci.dialogues import (
    TendermintDialogue as BaseTendermintDialogue,
)
from packages.valory.skills.abstract_round_abci.dialogues import (
    TendermintDialogues as BaseTendermintDialogues,
)
from packages.valory.skills.market_creation_manager_abci.dialogues import (
    AbciDialogue,
    AbciDialogues,
    ContractApiDialogue,
    ContractApiDialogues,
    HttpDialogue,
    HttpDialogues,
    IpfsDialogue,
    IpfsDialogues,
    LedgerApiDialogue,
    LedgerApiDialogues,
    LlmDialogue,
    LlmDialogues,
    SigningDialogue,
    SigningDialogues,
    TendermintDialogue,
    TendermintDialogues,
)


def test_import() -> None:
    """Test that the 'dialogues' Python module can be imported."""
    assert dialogues_mod is not None


def test_dialogue_aliases() -> None:
    """Test that all dialogue aliases point to the correct base classes."""
    assert AbciDialogue is BaseAbciDialogue
    assert AbciDialogues is BaseAbciDialogues
    assert HttpDialogue is BaseHttpDialogue
    assert HttpDialogues is BaseHttpDialogues
    assert SigningDialogue is BaseSigningDialogue
    assert SigningDialogues is BaseSigningDialogues
    assert LedgerApiDialogue is BaseLedgerApiDialogue
    assert LedgerApiDialogues is BaseLedgerApiDialogues
    assert ContractApiDialogue is BaseContractApiDialogue
    assert ContractApiDialogues is BaseContractApiDialogues
    assert TendermintDialogue is BaseTendermintDialogue
    assert TendermintDialogues is BaseTendermintDialogues
    assert IpfsDialogue is BaseIpfsDialogue
    assert IpfsDialogues is BaseIpfsDialogues


def test_llm_dialogue_alias() -> None:
    """Test that LlmDialogue is correctly aliased."""
    from packages.valory.protocols.llm.dialogues import LlmDialogue as BaseLlmDialogue

    assert LlmDialogue is BaseLlmDialogue


def test_llm_dialogues_is_class() -> None:
    """Test that LlmDialogues is a class (not just an alias)."""
    assert isinstance(LlmDialogues, type)


def test_llm_dialogues_initialization() -> None:
    """Test that LlmDialogues can be initialized with proper skill_context."""
    from unittest.mock import MagicMock

    from packages.valory.protocols.llm.dialogues import (
        LlmDialogues as BaseLlmDialoguesProto,
    )

    # Create a mock skill_context
    skill_context = MagicMock()
    skill_context.agent_address = "agent_address"
    skill_context.skill_id = "market_creation_manager_abci/llm_dialogue"

    # Instantiate LlmDialogues - this will cover line 124 (BaseLlmDialogues.__init__)
    dialogues = LlmDialogues(name="llm_dialogues", skill_context=skill_context)

    # Verify it was instantiated successfully
    assert isinstance(dialogues, LlmDialogues)
    assert isinstance(dialogues, BaseLlmDialoguesProto)
    assert dialogues.skill_id == "market_creation_manager_abci/llm_dialogue"

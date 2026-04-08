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

"""Tests for dialogues in the omen_fpmm_liquidity_remove_abci skill."""

import packages.valory.skills.omen_fpmm_liquidity_remove_abci.dialogues as dialogues_module
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


class TestDialogues:
    """Tests that all dialogue aliases are correctly exported."""

    def test_abci_dialogue(self) -> None:
        """Test that AbciDialogue is correctly re-exported."""
        assert dialogues_module.AbciDialogue is BaseAbciDialogue

    def test_abci_dialogues(self) -> None:
        """Test that AbciDialogues is correctly re-exported."""
        assert dialogues_module.AbciDialogues is BaseAbciDialogues

    def test_http_dialogue(self) -> None:
        """Test that HttpDialogue is correctly re-exported."""
        assert dialogues_module.HttpDialogue is BaseHttpDialogue

    def test_http_dialogues(self) -> None:
        """Test that HttpDialogues is correctly re-exported."""
        assert dialogues_module.HttpDialogues is BaseHttpDialogues

    def test_signing_dialogue(self) -> None:
        """Test that SigningDialogue is correctly re-exported."""
        assert dialogues_module.SigningDialogue is BaseSigningDialogue

    def test_signing_dialogues(self) -> None:
        """Test that SigningDialogues is correctly re-exported."""
        assert dialogues_module.SigningDialogues is BaseSigningDialogues

    def test_ledger_api_dialogue(self) -> None:
        """Test that ledgerApiDialogue is correctly re-exported."""
        assert dialogues_module.LedgerApiDialogue is BaseLedgerApiDialogue

    def test_ledger_api_dialogues(self) -> None:
        """Test that ledgerApiDialogues is correctly re-exported."""
        assert dialogues_module.LedgerApiDialogues is BaseLedgerApiDialogues

    def test_contract_api_dialogue(self) -> None:
        """Test that contractApiDialogue is correctly re-exported."""
        assert dialogues_module.ContractApiDialogue is BaseContractApiDialogue

    def test_contract_api_dialogues(self) -> None:
        """Test that contractApiDialogues is correctly re-exported."""
        assert dialogues_module.ContractApiDialogues is BaseContractApiDialogues

    def test_tendermint_dialogue(self) -> None:
        """Test that TendermintDialogue is correctly re-exported."""
        assert dialogues_module.TendermintDialogue is BaseTendermintDialogue

    def test_tendermint_dialogues(self) -> None:
        """Test that TendermintDialogues is correctly re-exported."""
        assert dialogues_module.TendermintDialogues is BaseTendermintDialogues

    def test_ipfs_dialogue(self) -> None:
        """Test that IpfsDialogue is correctly re-exported."""
        assert dialogues_module.IpfsDialogue is BaseIpfsDialogue

    def test_ipfs_dialogues(self) -> None:
        """Test that IpfsDialogues is correctly re-exported."""
        assert dialogues_module.IpfsDialogues is BaseIpfsDialogues

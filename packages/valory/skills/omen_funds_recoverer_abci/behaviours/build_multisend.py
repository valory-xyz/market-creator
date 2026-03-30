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

"""This module contains the BuildMultisendBehaviour of the 'omen_funds_recoverer_abci' skill."""

from typing import Generator, Optional

from packages.valory.skills.omen_funds_recoverer_abci.behaviours.base import (
    OmenFundsRecovererBaseBehaviour,
)
from packages.valory.skills.omen_funds_recoverer_abci.payloads import (
    BuildMultisendPayload,
)
from packages.valory.skills.omen_funds_recoverer_abci.rounds import BuildMultisendRound


class BuildMultisendBehaviour(OmenFundsRecovererBaseBehaviour):
    """BuildMultisendBehaviour

    Reads funds_recovery_txs from SynchronizedData and bundles all accumulated
    raw tx dicts into a single multisend safe transaction.
    """

    matching_round = BuildMultisendRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            tx_hash = yield from self._build_multisend()
            if tx_hash is None:
                tx_submitter = None
            else:
                tx_submitter = self.matching_round.auto_round_id()
            payload = BuildMultisendPayload(
                sender=sender, tx_submitter=tx_submitter, tx_hash=tx_hash
            )
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def _build_multisend(self) -> Generator[None, None, Optional[str]]:
        """Bundle all accumulated funds_recovery_txs into a single multisend.

        :yield: None
        :return: the multisend payload hash, or None if no txs to bundle.
        """
        txs = self.synchronized_data.funds_recovery_txs
        if not txs:
            self.context.logger.info("No recovery transactions to submit.")
            return None
        self.context.logger.info(f"Building multisend with {len(txs)} recovery tx(s).")
        # Convert data fields from hex strings back to bytes if needed
        for tx in txs:
            if isinstance(tx.get("data"), str):
                tx["data"] = bytes.fromhex(tx["data"].replace("0x", ""))
        tx_hash = yield from self._to_multisend(transactions=txs)
        return tx_hash

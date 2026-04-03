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

"""This module contains the ClaimBondsBehaviour of the 'omen_funds_recoverer_abci' skill."""

import json
from string import Template
from typing import Any, Dict, Generator, List, Optional, cast

from packages.valory.contracts.realitio.contract import RealitioContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.omen_funds_recoverer_abci.behaviours.base import (
    ETHER_VALUE,
    OmenFundsRecovererBaseBehaviour,
    SKILL_LOG_PREFIX,
    get_callable_name,
    wei_to_str,
)
from packages.valory.skills.omen_funds_recoverer_abci.payloads import RecoveryTxsPayload
from packages.valory.skills.omen_funds_recoverer_abci.rounds import ClaimBondsRound

# Subgraph max per page.
SUBGRAPH_PAGE_SIZE = 1000

# Zero bytes32 -- indicates an already-claimed question.
ZERO_BYTES32 = b"\x00" * 32

# Realitio subgraph: finalized questions answered by the safe.
CLAIMABLE_RESPONSES_QUERY = Template("""{
    responses(
      where: {user: "$safe", question_: {answerFinalizedTimestamp_lt: "$now", answerFinalizedTimestamp_not: null}}
      first: $page_size
      orderBy: id
      id_gt: "$cursor"
    ) {
      id
      question { id }
      bond
      answer
    }
  }""")


class ClaimBondsBehaviour(OmenFundsRecovererBaseBehaviour):
    """Claim Realitio bonds and optionally withdraw internal balance."""

    matching_round = ClaimBondsRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            new_txs = yield from self._build_claim_bonds_txs()
            existing = self.synchronized_data.funds_recovery_txs
            combined = existing + new_txs
            payload = RecoveryTxsPayload(sender=sender, content=json.dumps(combined))
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def _build_claim_bonds_txs(self) -> Generator[None, None, List[Dict[str, Any]]]:
        """Build claimWinnings txs and an optional withdraw tx."""
        claim_txs = yield from self._build_claim_txs()
        withdraw_tx = yield from self._maybe_build_withdraw_tx()

        txs = claim_txs
        if withdraw_tx is not None:
            txs.append(withdraw_tx)

        self.context.logger.info(f"{SKILL_LOG_PREFIX} ClaimBonds: built {len(txs)} txs")
        return txs

    def _build_claim_txs(self) -> Generator[None, None, List[Dict[str, Any]]]:
        """Query subgraph for finalized responses and build claimWinnings txs."""
        responses = yield from self._get_claimable_responses()
        if not responses:
            return []

        batch_size = self.params.claim_bonds_batch_size
        txs: List[Dict[str, Any]] = []
        unclaimed_count = 0
        for resp in responses:
            if len(txs) >= batch_size:
                break
            claim_tx = yield from self._try_build_single_claim(resp)
            if claim_tx is not None:
                txs.append(claim_tx)
                unclaimed_count += 1

        self.context.logger.info(
            f"{SKILL_LOG_PREFIX} ClaimBonds: found {len(responses)} finalized responses, "
            f"{unclaimed_count} unclaimed"
        )
        return txs

    def _try_build_single_claim(
        self, resp: Dict[str, Any]
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Build a claimWinnings tx for a single response, or None if it should be skipped."""
        raw_question_id = resp["question"]["id"]
        # Realitio subgraph uses composite IDs: "{contract_address}-{question_id}"
        # Extract the actual question_id (after the dash)
        question_id_hex = (
            raw_question_id.split("-")[-1]
            if "-" in raw_question_id
            else raw_question_id
        )
        question_id_bytes = bytes.fromhex(question_id_hex.replace("0x", ""))

        is_unclaimed = yield from self._is_unclaimed(question_id_bytes)
        if not is_unclaimed:
            return None

        claim_params = yield from self._get_claim_params(question_id_bytes)
        if claim_params is None:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} ClaimBonds: RealitioContract.get_claim_params failed "
                f"for {question_id_hex}"
            )
            return None

        simulation_ok = yield from self._simulate_claim(question_id_bytes, claim_params)
        if not simulation_ok:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} ClaimBonds: RealitioContract.simulate_claim_winnings failed "
                f"for {question_id_hex}"
            )
            return None

        claim_tx = yield from self._build_claim_tx(question_id_bytes, claim_params)
        if claim_tx is None:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} ClaimBonds: RealitioContract.build_claim_winnings failed "
                f"for {question_id_hex}"
            )
            return None

        bond = int(resp.get("bond", 0))
        self.context.logger.info(
            f"{SKILL_LOG_PREFIX} ClaimBonds: claiming question {question_id_hex} "
            f"(bond: {wei_to_str(bond)})"
        )
        return claim_tx

    def _get_claimable_responses(
        self,
    ) -> Generator[None, None, List[Dict[str, Any]]]:
        """Query the Realitio subgraph for finalized questions answered by the safe."""
        safe = self.synchronized_data.safe_contract_address.lower()
        now = str(self.last_synced_timestamp)
        all_responses: List[Dict[str, Any]] = []
        cursor = ""

        while True:
            response = yield from self.get_realitio_subgraph_result(
                query=CLAIMABLE_RESPONSES_QUERY.substitute(
                    safe=safe,
                    now=now,
                    page_size=SUBGRAPH_PAGE_SIZE,
                    cursor=cursor,
                )
            )
            if response is None:
                self.context.logger.warning(
                    f"{SKILL_LOG_PREFIX} ClaimBonds: Realitio subgraph query failed"
                )
                break

            responses = response.get("data", {}).get("responses", [])
            if not responses:
                break

            all_responses.extend(responses)
            cursor = responses[-1]["id"]
            if len(responses) < SUBGRAPH_PAGE_SIZE:
                break

        return all_responses

    def _is_unclaimed(self, question_id: bytes) -> Generator[None, None, bool]:
        """Check if a question is unclaimed. A history hash of all zeros means already claimed."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.realitio_contract,
            contract_id=str(RealitioContract.contract_id),
            contract_callable=get_callable_name(RealitioContract.get_history_hash),
            question_id=question_id,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} ClaimBonds: RealitioContract.get_history_hash failed "
                f"for 0x{question_id.hex()}"
            )
            return False

        history_hash = response.state.body["data"]
        if isinstance(history_hash, bytes):
            return history_hash != ZERO_BYTES32
        # If returned as hex string
        if isinstance(history_hash, str):
            return history_hash.replace("0x", "") != "0" * 64
        return False

    def _get_claim_params(
        self, question_id: bytes
    ) -> Generator[None, None, Optional[Any]]:
        """Get claim parameters for a question from on-chain event logs."""
        from_block = self.params.realitio_start_block
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.realitio_contract,
            contract_id=str(RealitioContract.contract_id),
            contract_callable=get_callable_name(RealitioContract.get_claim_params),
            from_block=from_block,
            to_block="latest",
            question_id=question_id,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} ClaimBonds: RealitioContract.get_claim_params failed "
                f"for 0x{question_id.hex()}"
            )
            return None

        body = response.state.body
        if "error" in body:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} ClaimBonds: RealitioContract.get_claim_params failed "
                f"for 0x{question_id.hex()}"
            )
            return None

        answered = body.get("answered")
        if answered is None or len(answered) == 0:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} ClaimBonds: RealitioContract.get_claim_params failed "
                f"for 0x{question_id.hex()}"
            )
            return None

        return answered

    def _simulate_claim(
        self,
        question_id: bytes,
        claim_params: Any,
    ) -> Generator[None, None, bool]:
        """Simulate the claimWinnings call to check it would succeed."""
        safe_address = self.synchronized_data.safe_contract_address
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.realitio_contract,
            contract_id=str(RealitioContract.contract_id),
            contract_callable=get_callable_name(
                RealitioContract.simulate_claim_winnings
            ),
            question_id=question_id,
            claim_params=claim_params,
            sender_address=safe_address,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} ClaimBonds: RealitioContract.simulate_claim_winnings failed "
                f"for 0x{question_id.hex()}"
            )
            return False

        return bool(response.state.body.get("data", False))

    def _build_claim_tx(
        self,
        question_id: bytes,
        claim_params: Any,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Build the encoded Realitio.claimWinnings() call."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.realitio_contract,
            contract_id=str(RealitioContract.contract_id),
            contract_callable=get_callable_name(RealitioContract.build_claim_winnings),
            question_id=question_id,
            claim_params=claim_params,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} ClaimBonds: RealitioContract.build_claim_winnings failed "
                f"for 0x{question_id.hex()}"
            )
            return None

        data = response.state.body["data"]
        data = data.hex() if isinstance(data, bytes) else data
        return {
            "to": self.params.realitio_contract,
            "data": data,
            "value": ETHER_VALUE,
        }

    def _maybe_build_withdraw_tx(
        self,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Build a Realitio withdraw tx if internal balance exceeds threshold."""
        safe_address = self.synchronized_data.safe_contract_address
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.realitio_contract,
            contract_id=str(RealitioContract.contract_id),
            contract_callable="balance_of",
            address=safe_address,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} ClaimBonds: RealitioContract.balance_of failed"
            )
            return None

        balance = cast(int, response.state.body["data"])

        if balance < self.params.min_balance_withdraw_realitio:
            return None

        # Build withdraw tx
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.realitio_contract,
            contract_id=str(RealitioContract.contract_id),
            contract_callable="build_withdraw_tx",
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} ClaimBonds: RealitioContract.build_withdraw_tx failed"
            )
            return None

        data = response.state.body["data"]
        data = data.hex() if isinstance(data, bytes) else data
        self.context.logger.info(
            f"{SKILL_LOG_PREFIX} ClaimBonds: Realitio balance {wei_to_str(balance)}, "
            f"appending withdraw"
        )
        return {
            "to": self.params.realitio_contract,
            "data": data,
            "value": ETHER_VALUE,
        }

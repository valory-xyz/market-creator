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
    get_callable_name,
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
    """ClaimBondsBehaviour

    Claims Realitio bonds via claimWinnings for finalized questions
    answered by the safe, and optionally withdraws the Realitio internal
    balance. Returns raw tx dicts via RecoveryTxsPayload for later bundling.
    """

    matching_round = ClaimBondsRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            new_txs = yield from self._get_recovery_txs()
            existing = self.synchronized_data.funds_recovery_txs
            combined = existing + new_txs
            payload = RecoveryTxsPayload(sender=sender, content=json.dumps(combined))
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def _get_recovery_txs(self) -> Generator[None, None, List[Dict[str, Any]]]:
        """Get recovery transactions for bond claiming and withdrawal.

        1. Query Realitio subgraph for finalized responses by safe
        2. Check getHistoryHash on-chain (skip if 0 = already claimed)
        3. For each unclaimed: get_claim_params, simulate, build claimWinnings tx
        4. Check Realitio.balanceOf(safe) and optionally build withdraw tx

        :yield: None
        :return: list of tx dicts (may be empty).
        """
        # Step 1: Get claimable responses from subgraph
        responses = yield from self._get_claimable_responses()
        if not responses:
            self.context.logger.info("No claimable responses found.")
        else:
            self.context.logger.info(
                f"Found {len(responses)} finalized response(s) from "
                f"Realitio subgraph."
            )

        # Step 2 & 3: Filter unclaimed, build claim txs
        batch_size = self.params.claim_bonds_batch_size
        txs: List[Dict[str, Any]] = []
        for resp in responses:
            if len(txs) >= batch_size:
                break

            question_id_hex = resp["question"]["id"]
            question_id_bytes = bytes.fromhex(question_id_hex[2:])

            # Check if already claimed via getHistoryHash
            is_unclaimed = yield from self._is_unclaimed(question_id_bytes)
            if not is_unclaimed:
                self.context.logger.info(
                    f"Question {question_id_hex} already claimed, skipping."
                )
                continue

            # Get claim params
            claim_params = yield from self._get_claim_params(question_id_bytes)
            if claim_params is None:
                self.context.logger.warning(
                    f"Failed to get claim params for {question_id_hex}, skipping."
                )
                continue

            # Simulate claim
            simulation_ok = yield from self._simulate_claim(
                question_id_bytes, claim_params
            )
            if not simulation_ok:
                self.context.logger.warning(
                    f"Claim simulation failed for {question_id_hex}, skipping."
                )
                continue

            # Build claim tx
            claim_tx = yield from self._build_claim_tx(question_id_bytes, claim_params)
            if claim_tx is None:
                self.context.logger.warning(
                    f"Failed to build claim tx for {question_id_hex}, skipping."
                )
                continue

            self.context.logger.info(
                f"Built claim tx for question {question_id_hex} "
                f"(bond: {resp.get('bond', '?')})"
            )
            txs.append(claim_tx)

        # Step 4: Check Realitio balance and optionally build withdraw tx
        withdraw_tx = yield from self._maybe_build_withdraw_tx()
        if withdraw_tx is not None:
            txs.append(withdraw_tx)

        self.context.logger.info(f"Built {len(txs)} claim-bonds tx(es).")
        return txs

    def _get_claimable_responses(
        self,
    ) -> Generator[None, None, List[Dict[str, Any]]]:
        """Query the Realitio subgraph for finalized questions answered by the safe.

        :yield: None
        :return: list of response dicts.
        """
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
                    "Failed to query Realitio subgraph for claimable responses."
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
        """Check if a question is unclaimed by inspecting getHistoryHash.

        :param question_id: the question ID as bytes.
        :yield: None
        :return: True if unclaimed (non-zero history hash), False otherwise.
        """
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.realitio_contract,
            contract_id=str(RealitioContract.contract_id),
            contract_callable=get_callable_name(RealitioContract.get_history_hash),
            question_id=question_id,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"get_history_hash unsuccessful for " f"{question_id.hex()}: {response}"
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
        """Get claim parameters for a question from on-chain event logs.

        :param question_id: the question ID as bytes.
        :yield: None
        :return: claim params tuple, or None on error.
        """
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
                f"get_claim_params unsuccessful for " f"{question_id.hex()}: {response}"
            )
            return None

        body = response.state.body
        if "error" in body:
            self.context.logger.warning(
                f"get_claim_params error for {question_id.hex()}: {body['error']}"
            )
            return None

        answered = body.get("answered")
        if answered is None or len(answered) == 0:
            self.context.logger.warning(
                f"No answers found for question {question_id.hex()}"
            )
            return None

        return answered

    def _simulate_claim(
        self,
        question_id: bytes,
        claim_params: Any,
    ) -> Generator[None, None, bool]:
        """Simulate the claimWinnings call to check it would succeed.

        :param question_id: the question ID as bytes.
        :param claim_params: the claim parameters.
        :yield: None
        :return: True if simulation succeeded, False otherwise.
        """
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
                f"simulate_claim_winnings unsuccessful for "
                f"{question_id.hex()}: {response}"
            )
            return False

        return bool(response.state.body.get("data", False))

    def _build_claim_tx(
        self,
        question_id: bytes,
        claim_params: Any,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Build a claimWinnings transaction.

        :param question_id: the question ID as bytes.
        :param claim_params: the claim parameters.
        :yield: None
        :return: transaction dict or None on failure.
        """
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
                f"build_claim_winnings unsuccessful for "
                f"{question_id.hex()}: {response}"
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
        """Check Realitio balanceOf and build withdraw tx if above threshold.

        :yield: None
        :return: withdraw tx dict, or None if balance too low or on error.
        """
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
                f"Realitio balance_of unsuccessful!: {response}"
            )
            return None

        balance = cast(int, response.state.body["data"])
        self.context.logger.info(
            f"Realitio internal balance: {balance / 10 ** 18} xDAI"
        )

        if balance < self.params.min_balance_withdraw_realitio:
            self.context.logger.info(
                "Realitio balance below withdrawal threshold, skipping withdraw."
            )
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
                f"Realitio build_withdraw_tx unsuccessful!: {response}"
            )
            return None

        data = response.state.body["data"]
        data = data.hex() if isinstance(data, bytes) else data
        self.context.logger.info("Appending Realitio withdraw tx.")
        return {
            "to": self.params.realitio_contract,
            "data": data,
            "value": ETHER_VALUE,
        }

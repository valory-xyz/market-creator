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
from typing import Any, Dict, Generator, List, Optional, Tuple, cast

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

# Zero bytes32 -- indicates an already-claimed question, and is the
# `last_history_hash` value `claimWinnings` walks back to after the
# very first (oldest) entry in the response history.
ZERO_BYTES32 = b"\x00" * 32

# Type alias for the 4-tuple expected by Realitio.claimWinnings:
#   (history_hashes, addresses, bonds, answers), all in reverse-
#   chronological order (newest first), all the same length.
ClaimParamsType = Tuple[List[Any], List[str], List[int], List[Any]]


def _assemble_claim_params(answered: List[Dict[str, Any]]) -> ClaimParamsType:
    """Convert a chronological event list into the claimWinnings 4-tuple.

    The Realitio v2.1 contract walks the four supplied arrays in
    **reverse-chronological** order (newest entry at index 0, oldest at
    index N-1) and at each step verifies that the running
    ``last_history_hash`` matches ``keccak256(history_hashes[i] || answer
    || bond || addr || is_commitment)``. Critically, ``history_hashes[i]``
    is the hash that existed *before* the i-th entry was posted —
    equivalently, the stored ``history_hash`` of the previous (older)
    chronological entry, or ``0x00…00`` if the i-th entry is the very
    first one.

    Source of the algorithm: ``Realitio.sol::claimWinnings`` +
    ``_verifyHistoryInputOrRevert`` in
    https://github.com/realitio/realitio-contracts.

    :param answered: list of decoded ``LogNewAnswer`` events in
        **chronological** order (oldest first), as returned by
        ``RealitioContract.get_claim_params``.
    :return: tuple ``(history_hashes, addresses, bonds, answers)`` in
        reverse-chronological order, ready to pass to
        ``claimWinnings``.
    """
    history_hashes: List[Any] = []
    addresses: List[str] = []
    bonds: List[int] = []
    answers: List[Any] = []
    for chrono_idx in range(len(answered) - 1, -1, -1):
        args = answered[chrono_idx]["args"]
        if chrono_idx == 0:
            prior_hash: Any = ZERO_BYTES32
        else:
            prior_hash = answered[chrono_idx - 1]["args"]["history_hash"]
        history_hashes.append(prior_hash)
        addresses.append(args["user"])
        bonds.append(int(args["bond"]))
        answers.append(args["answer"])
    return history_hashes, addresses, bonds, answers


# Realitio subgraph: most recent finalized, still-unclaimed responses
# by the safe.
#
# We deliberately do NOT paginate. The query returns at most
# `claim_bonds_batch_size` items ordered by id DESCENDING — i.e. the most
# recently submitted responses first. This bounds per-round work to a
# constant `O(batch_size)` regardless of how many bonds the safe has ever
# posted.
#
# Critically, the `historyHash_not` filter excludes questions whose
# on-chain history hash has already been cleared to zero — i.e. questions
# that have already been successfully claimed. Without this filter, once
# the skill claims a batch of questions the NEXT period's query would
# return the same 10 (now-claimed) questions forever, because the
# id-based ordering doesn't change when the on-chain state changes. That
# would deadlock the backlog drain after exactly one successful batch.
CLAIMABLE_RESPONSES_QUERY = Template("""{
    responses(
      where: {
        user: "$safe",
        question_: {
          answerFinalizedTimestamp_gt: 0,
          historyHash_not: "0x0000000000000000000000000000000000000000000000000000000000000000"
        }
      }
      first: $batch_size
      orderBy: id
      orderDirection: desc
    ) {
      id
      question { id createdBlock }
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
        """Build an optional withdraw tx then claimWinnings txs.

        Withdraw is built FIRST so that even if the claim loop is slow or
        partially fails, the (fast, O(1)) withdraw tx is still queued in
        this round's payload via the funds_recovery_txs accumulator.
        """
        txs: List[Dict[str, Any]] = []
        withdraw_tx = yield from self._maybe_build_withdraw_tx()
        if withdraw_tx is not None:
            txs.append(withdraw_tx)
        claim_txs = yield from self._build_claim_txs()
        txs.extend(claim_txs)
        self.context.logger.info(f"{SKILL_LOG_PREFIX} ClaimBonds: built {len(txs)} txs")
        return txs

    def _build_claim_txs(self) -> Generator[None, None, List[Dict[str, Any]]]:
        """Query subgraph for finalized responses and build claimWinnings txs."""
        responses = yield from self._get_claimable_responses()
        if not responses:
            return []

        # The safe may have posted multiple responses on the same
        # question (e.g. defending its answer through several rounds
        # of bond escalation). Each distinct response is a separate
        # subgraph entry but they all share the same question_id, and
        # a single successful claimWinnings call claims ALL of them at
        # once. Deduplicate by question id so we don't build multiple
        # claim txs for the same question — the second one would
        # revert on-chain because the first one clears the history
        # hash.
        seen_question_ids: set = set()
        unique_responses: List[Dict[str, Any]] = []
        for resp in responses:
            qid = resp.get("question", {}).get("id")
            if qid is None or qid in seen_question_ids:
                continue
            seen_question_ids.add(qid)
            unique_responses.append(resp)

        batch_size = self.params.claim_bonds_batch_size
        txs: List[Dict[str, Any]] = []
        for resp in unique_responses:
            if len(txs) >= batch_size:
                break
            claim_tx = yield from self._try_build_single_claim(resp)
            if claim_tx is not None:
                txs.append(claim_tx)

        self.context.logger.info(
            f"{SKILL_LOG_PREFIX} ClaimBonds: fetched {len(responses)} responses "
            f"({len(unique_responses)} unique questions), built {len(txs)} claim txs"
        )
        return txs

    def _try_build_single_claim(
        self, resp: Dict[str, Any]
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Build a claimWinnings tx for a single response, or None if it should be skipped."""
        # Realitio subgraph always uses composite ids of the form
        # "{contract_address}-{question_id}".
        question_id_hex = resp["question"]["id"].split("-")[-1]
        question_id_bytes = bytes.fromhex(question_id_hex.replace("0x", ""))

        # Per-question lower bound for the eth_getLogs window. Subtract
        # 1 as a defensive margin against subgraph indexing skew.
        # Missing createdBlock means the subgraph row is malformed;
        # skip it rather than fall back to scanning from 0.
        created_block_raw = resp["question"].get("createdBlock")
        if created_block_raw is None:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} ClaimBonds: missing createdBlock for "
                f"question {question_id_hex}, skipping"
            )
            return None
        from_block = max(0, int(created_block_raw) - 1)

        # Linear bail-out chain: each helper logs its own failure, so
        # we just return None on the first step that doesn't produce a
        # value. The subgraph filter already excludes already-claimed
        # questions, so we skip the on-chain getHistoryHash check —
        # any stale-index edge case is caught naturally by simulation.
        claim_params = yield from self._get_claim_params(question_id_bytes, from_block)
        if claim_params is None:
            return None
        simulation_ok = yield from self._simulate_claim(question_id_bytes, claim_params)
        if not simulation_ok:
            return None
        claim_tx = yield from self._build_claim_tx(question_id_bytes, claim_params)
        if claim_tx is None:
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
        """Query the Realitio subgraph for the next batch of finalized responses.

        Returns at most `claim_bonds_batch_size` items, ordered by id desc
        (newest first). No pagination — the per-round work is bounded by
        configuration, not by history size.
        """
        safe = self.synchronized_data.safe_contract_address.lower()
        response = yield from self.get_realitio_subgraph_result(
            query=CLAIMABLE_RESPONSES_QUERY.substitute(
                safe=safe,
                batch_size=self.params.claim_bonds_batch_size,
            )
        )
        if response is None:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} ClaimBonds: Realitio subgraph query failed"
            )
            return []
        return cast(List[Dict[str, Any]], response.get("data", {}).get("responses", []))

    def _get_claim_params(
        self, question_id: bytes, from_block: int
    ) -> Generator[None, None, Optional[Any]]:
        """Get claim parameters for a question from on-chain event logs."""
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

        # The contract wrapper returns the raw chronological list of
        # LogNewAnswer events. claimWinnings expects a 4-tuple of
        # parallel arrays in reverse-chronological order. Without this
        # transform the calldata is malformed and the simulation
        # always reverts.
        return _assemble_claim_params(cast(List[Dict[str, Any]], answered))

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

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

"""RealitioBondWithdrawBehaviour for the omen_realitio_bond_withdraw_abci skill."""

# pylint: disable=too-many-ancestors

from string import Template
from typing import Any, Dict, Generator, List, Optional, cast

from packages.valory.contracts.realitio.contract import RealitioContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.omen_realitio_bond_withdraw_abci.behaviours.base import (
    ETHER_VALUE,
    RealitioBondWithdrawBaseBehaviour,
    SKILL_LOG_PREFIX,
    assemble_claim_params,
    get_callable_name,
    wei_to_str,
)
from packages.valory.skills.omen_realitio_bond_withdraw_abci.payloads import (
    RealitioBondWithdrawPayload,
)
from packages.valory.skills.omen_realitio_bond_withdraw_abci.rounds import (
    RealitioBondWithdrawRound,
)

# tx_submitter tag for the post-settlement router in the parent composition.
TX_SUBMITTER = "omen_realitio_bond_withdraw"


# Realitio subgraph: most recent finalized, still-unclaimed responses
# by the safe.
#
# We deliberately do NOT paginate. The query returns at most
# `realitio_bond_withdraw_batch_size` items ordered by id DESCENDING —
# i.e. the most recently submitted responses first. This bounds per-round
# work to a constant `O(batch_size)` regardless of how many bonds the
# safe has ever posted.
#
# Critically, the `historyHash_not` filter excludes questions whose
# on-chain history hash has already been cleared to zero — i.e. questions
# that have already been successfully claimed. Without this filter, once
# the skill claims a batch of questions the NEXT period's query would
# return the same N (now-claimed) questions forever, because the
# id-based ordering doesn't change when the on-chain state changes.
# That would deadlock the backlog drain after exactly one successful
# batch.
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


class RealitioBondWithdrawBehaviour(RealitioBondWithdrawBaseBehaviour):
    """Single-round behaviour: query, build, wrap, settle-or-skip.

    Builds a multisend that bundles an optional Realitio.withdraw() tx
    (when the safe's internal balance crosses the configured threshold)
    plus up to ``realitio_bond_withdraw_batch_size`` Realitio.claimWinnings
    txs (one per unique unclaimed question, deduplicated). The behaviour
    produces a payload with the safe tx hash, or None when there's
    nothing to do this period.
    """

    matching_round = RealitioBondWithdrawRound

    def async_act(self) -> Generator:
        """Single-round act: query → build → wrap → settle-or-skip."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            tx_hash = yield from self._prepare_multisend()
            tx_submitter: Optional[str] = TX_SUBMITTER if tx_hash is not None else None
            payload = RealitioBondWithdrawPayload(
                sender=self.context.agent_address,
                tx_submitter=tx_submitter,
                tx_hash=tx_hash,
            )
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def _prepare_multisend(self) -> Generator[None, None, Optional[str]]:
        """Build optional withdraw tx + claim txs and wrap in a multisend.

        Withdraw is built FIRST so that even if the claim loop is slow
        or partially fails, the (fast, O(1)) withdraw tx is still queued
        in this period's payload.

        :yield: contract-api / ledger-api requests during the build.
        :return: the multisend tx hash, or ``None`` when neither a
            withdraw nor any claim is producible (the round then routes
            to ``FinishedWithoutRealitioBondWithdrawTxRound`` and skips
            TxSettlement entirely).
        """
        txs: List[Dict[str, Any]] = []

        # Step 1 (Fix A from claim_bonds_fix.md): withdraw FIRST so a
        # broken or slow claim loop can never starve the withdraw step.
        withdraw_tx = yield from self._maybe_build_withdraw_tx()
        if withdraw_tx is not None:
            txs.append(withdraw_tx)

        # Step 2: build per-question claim txs (may produce 0..N items).
        claim_txs = yield from self._build_claim_txs()
        txs.extend(claim_txs)

        if not txs:
            self.context.logger.info(
                f"{SKILL_LOG_PREFIX} nothing to withdraw or claim this period"
            )
            return None

        # Step 3: wrap in a multisend and compute the safe tx hash.
        tx_hash = yield from self._to_multisend(txs)
        if tx_hash is None:
            self.context.logger.warning(f"{SKILL_LOG_PREFIX} multisend build failed")
            return None

        n_claims = len(claim_txs)
        has_withdraw = withdraw_tx is not None
        self.context.logger.info(
            f"{SKILL_LOG_PREFIX} prepared multisend: "
            f"withdraw={has_withdraw}, claims={n_claims}"
        )
        return tx_hash

    def _build_claim_txs(self) -> Generator[None, None, List[Dict[str, Any]]]:
        """Query subgraph for finalized responses and build claimWinnings txs."""
        responses = yield from self._get_claimable_responses()
        if not responses:
            return []

        # Fix F from claim_bonds_fix.md: the safe may have posted
        # multiple responses on the same question (defending its answer
        # through several rounds of bond escalation). Each distinct
        # response is a separate subgraph entry but they all share the
        # same question_id, and a single successful claimWinnings call
        # claims ALL of them at once. Deduplicate by question id so we
        # don't build multiple claim txs for the same question — the
        # second one would revert on-chain because the first one clears
        # the history hash.
        seen_question_ids: set = set()
        unique_responses: List[Dict[str, Any]] = []
        for resp in responses:
            qid = resp.get("question", {}).get("id")
            if qid is None or qid in seen_question_ids:
                continue
            seen_question_ids.add(qid)
            unique_responses.append(resp)

        batch_size = self.params.realitio_bond_withdraw_batch_size
        txs: List[Dict[str, Any]] = []
        for resp in unique_responses:
            if len(txs) >= batch_size:
                break
            claim_tx = yield from self._try_build_single_claim(resp)
            if claim_tx is not None:
                txs.append(claim_tx)

        self.context.logger.info(
            f"{SKILL_LOG_PREFIX} fetched {len(responses)} responses "
            f"({len(unique_responses)} unique questions), built {len(txs)} claim txs"
        )
        return txs

    def _try_build_single_claim(
        self, resp: Dict[str, Any]
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Build a claimWinnings tx for one response, or None if it should be skipped."""
        # Realitio subgraph always uses composite ids of the form
        # "{contract_address}-{question_id}".
        question_id_hex = resp["question"]["id"].split("-")[-1]
        question_id_bytes = bytes.fromhex(question_id_hex.replace("0x", ""))

        # Fix C from claim_bonds_fix.md: per-question lower bound for
        # the eth_getLogs window. Subtract 1 as a defensive margin
        # against subgraph indexing skew. Missing createdBlock means
        # the subgraph row is malformed — skip it rather than fall
        # back to scanning from 0.
        created_block_raw = resp["question"].get("createdBlock")
        if created_block_raw is None:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} missing createdBlock for "
                f"question {question_id_hex}, skipping"
            )
            return None
        from_block = max(0, int(created_block_raw) - 1)

        # Linear bail-out chain: each helper logs its own failure, so
        # we just return None on the first step that doesn't produce a
        # value. The subgraph filter (Fix E) already excludes
        # already-claimed questions, so we skip the on-chain
        # getHistoryHash check — any stale-index edge case is caught
        # naturally by simulation.
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
            f"{SKILL_LOG_PREFIX} claiming question {question_id_hex} "
            f"(bond: {wei_to_str(bond)})"
        )
        return claim_tx

    def _get_claimable_responses(
        self,
    ) -> Generator[None, None, List[Dict[str, Any]]]:
        """Query the Realitio subgraph for the next batch of finalized responses.

        Returns at most ``realitio_bond_withdraw_batch_size`` items,
        ordered by id desc (newest first). No pagination — the per-round
        work is bounded by configuration, not by history size.

        :yield: subgraph HTTP requests during the build.
        :return: list of response dicts (possibly empty).
        """
        safe = self.synchronized_data.safe_contract_address.lower()
        response = yield from self.get_realitio_subgraph_result(
            query=CLAIMABLE_RESPONSES_QUERY.substitute(
                safe=safe,
                batch_size=self.params.realitio_bond_withdraw_batch_size,
            )
        )
        if response is None:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} Realitio subgraph query failed"
            )
            return []
        return cast(List[Dict[str, Any]], response.get("data", {}).get("responses", []))

    def _get_claim_params(
        self, question_id: bytes, from_block: int
    ) -> Generator[None, None, Optional[Any]]:
        """Get claim parameters for a question from on-chain event logs.

        Returns the reverse-chronological 4-tuple expected by
        ``Realitio.claimWinnings``. The contract wrapper returns raw
        chronological events; the reshape into the 4-tuple happens via
        ``assemble_claim_params``.

        :param question_id: the Realitio question id (32-byte).
        :param from_block: lower bound block for the LogNewAnswer scan.
        :yield: contract-api requests during the build.
        :return: the 4-tuple, or ``None`` on any failure.
        """
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
                f"{SKILL_LOG_PREFIX} RealitioContract.get_claim_params failed "
                f"for 0x{question_id.hex()}"
            )
            return None

        body = response.state.body
        if "error" in body:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} RealitioContract.get_claim_params failed "
                f"for 0x{question_id.hex()}"
            )
            return None

        answered = body.get("answered")
        if answered is None or len(answered) == 0:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} RealitioContract.get_claim_params failed "
                f"for 0x{question_id.hex()}"
            )
            return None

        # The contract wrapper returns the raw chronological list of
        # LogNewAnswer events. claimWinnings expects a 4-tuple of
        # parallel arrays in reverse-chronological order. Without this
        # transform the calldata is malformed and the simulation always
        # reverts.
        return assemble_claim_params(cast(List[Dict[str, Any]], answered))

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
                f"{SKILL_LOG_PREFIX} RealitioContract.simulate_claim_winnings failed "
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
                f"{SKILL_LOG_PREFIX} RealitioContract.build_claim_winnings failed "
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
                f"{SKILL_LOG_PREFIX} RealitioContract.balance_of failed"
            )
            return None

        balance = cast(int, response.state.body["data"])

        if balance < self.params.min_balance_withdraw_realitio:
            return None

        # Build withdraw tx.
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.realitio_contract,
            contract_id=str(RealitioContract.contract_id),
            contract_callable="build_withdraw_tx",
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} RealitioContract.build_withdraw_tx failed"
            )
            return None

        data = response.state.body["data"]
        data = data.hex() if isinstance(data, bytes) else data
        self.context.logger.info(
            f"{SKILL_LOG_PREFIX} Realitio balance {wei_to_str(balance)}, "
            f"appending withdraw"
        )
        return {
            "to": self.params.realitio_contract,
            "data": data,
            "value": ETHER_VALUE,
        }

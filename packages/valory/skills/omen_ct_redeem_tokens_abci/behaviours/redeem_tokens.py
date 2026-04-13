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

"""CtRedeemTokensBehaviour for the omen_ct_redeem_tokens_abci skill."""

from string import Template
from typing import Any, Dict, Generator, List, Optional, Set

from packages.valory.contracts.conditional_tokens.contract import (
    ConditionalTokensContract,
)
from packages.valory.contracts.realitio_proxy.contract import RealitioProxyContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.omen_ct_redeem_tokens_abci.behaviours.base import (
    CtRedeemTokensBaseBehaviour,
    ETHER_VALUE,
    SKILL_LOG_PREFIX,
    ZERO_HASH,
    get_callable_name,
)
from packages.valory.skills.omen_ct_redeem_tokens_abci.payloads import (
    CtRedeemTokensPayload,
)
from packages.valory.skills.omen_ct_redeem_tokens_abci.rounds import CtRedeemTokensRound

SUBGRAPH_PAGE_SIZE = 1000
CONDITION_ID_BATCH_SIZE = 100
CT_REDEEM_TX_SUBMITTER = "omen_ct_redeem_tokens"

USER_POSITIONS_QUERY = Template("""{
    user(id: "$safe") {
      userPositions(
        first: $page_size
        where: {
          balance_gt: "0"
          id_gt: "$cursor"
        }
        orderBy: id
      ) {
        id
        balance
        position {
          conditionIds
          indexSets
        }
      }
    }
  }""")

MARKETS_BY_CONDITIONS_QUERY = Template("""{
    fixedProductMarketMakers(
      where: {
        conditions_: {id_in: [$condition_ids]}
        answerFinalizedTimestamp_not: null
        answerFinalizedTimestamp_lt: "$now"
      }
      first: $page_size
      orderBy: id
      orderDirection: asc
    ) {
      id
      payouts
      templateId
      question {
        id
        data
      }
      conditions {
        id
        outcomeSlotCount
      }
    }
  }""")


class CtRedeemTokensBehaviour(CtRedeemTokensBaseBehaviour):
    """Build a multisend that redeems the next batch of winning CT positions."""

    matching_round = CtRedeemTokensRound

    @staticmethod
    def _has_winning_position(payouts: List[str], held_index_sets: Set[int]) -> bool:
        """Check if any held index set corresponds to a winning payout."""
        for idx_set in held_index_sets:
            for i, payout in enumerate(payouts):
                if idx_set == (1 << i) and float(payout) > 0:
                    return True
        return False

    def async_act(self) -> Generator:
        """Single-round act: query → build → wrap → settle-or-skip."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            tx_hash = yield from self._prepare_multisend()
            tx_submitter = CT_REDEEM_TX_SUBMITTER if tx_hash is not None else None
            payload = CtRedeemTokensPayload(
                sender=self.context.agent_address,
                tx_submitter=tx_submitter,
                tx_hash=tx_hash,
            )
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def _prepare_multisend(self) -> Generator[None, None, Optional[str]]:
        """Run the full CT redemption pipeline as a linear recipe."""
        # Step 1: find what the safe holds
        held_positions = yield from self._get_held_positions()
        if not held_positions:
            self.context.logger.info(f"{SKILL_LOG_PREFIX} no CT positions held by safe")
            return None

        # Step 2: find which conditions those positions belong to that have resolved
        redeemable = yield from self._get_redeemable_markets(held_positions)
        if not redeemable:
            self.context.logger.info(
                f"{SKILL_LOG_PREFIX} safe holds {len(held_positions)} positions but "
                f"none have resolved to a winning payout"
            )
            return None

        # Step 3: build the individual per-market txs (with optional resolve prepended)
        txs = yield from self._build_redeem_txs(redeemable)
        if not txs:
            return None

        # Step 4: wrap in a multisend and compute the safe tx hash
        tx_hash = yield from self._to_multisend(txs)
        if tx_hash is None:
            self.context.logger.warning(f"{SKILL_LOG_PREFIX} multisend build failed")
            return None

        self.context.logger.info(
            f"{SKILL_LOG_PREFIX} prepared multisend with {len(txs)} tx(s) "
            f"for {len(redeemable)} market(s)"
        )
        return tx_hash

    def _get_redeemable_markets(
        self, held_positions: Dict[str, Set[int]]
    ) -> Generator[None, None, List[Dict[str, Any]]]:
        """Cross-reference held positions with finalized markets and filter by winning payout."""
        positions_to_redeem = yield from self._get_markets_for_conditions(
            list(held_positions.keys())
        )

        redeemable: List[Dict[str, Any]] = []
        for market in positions_to_redeem:
            condition_id = market.get("condition_id", "").lower()
            held_index_sets = set(held_positions.get(condition_id, []))
            payouts = market.get("payouts", [])
            if payouts and self._has_winning_position(payouts, held_index_sets):
                redeemable.append(market)

        self.context.logger.info(
            f"{SKILL_LOG_PREFIX} found {len(held_positions)} held conditions, "
            f"{len(positions_to_redeem)} finalized, {len(redeemable)} redeemable"
        )
        return redeemable

    def _build_redeem_txs(
        self, redeemable: List[Dict[str, Any]]
    ) -> Generator[None, None, List[Dict[str, Any]]]:
        """Build resolve + redeemPositions txs for the redeemable markets, capped by batch size."""
        batch_size = self.params.ct_redeem_tokens_batch_size
        txs: List[Dict[str, Any]] = []
        for market in redeemable[:batch_size]:
            condition_id = market["condition_id"]

            is_resolved = yield from self._check_resolved(condition_id)
            if not is_resolved:
                resolve_tx = yield from self._get_resolve_tx(market)
                if resolve_tx is not None:
                    self.context.logger.info(
                        f"{SKILL_LOG_PREFIX} resolving condition "
                        f"{condition_id} on market {market['address']}"
                    )
                    txs.append(resolve_tx)
                else:
                    self.context.logger.warning(
                        f"{SKILL_LOG_PREFIX} "
                        f"RealitioProxyContract.build_resolve_tx failed "
                        f"for market {market['address']}"
                    )
                    continue

            self.context.logger.info(
                f"{SKILL_LOG_PREFIX} redeeming condition "
                f"{condition_id} on market {market['address']}"
            )
            index_sets = ConditionalTokensContract.get_partitions(
                market["outcome_slot_count"]
            )
            redeem_tx = yield from self._get_redeem_positions_tx(
                condition_id=condition_id,
                index_sets=index_sets,
            )
            if redeem_tx is not None:
                txs.append(redeem_tx)

        self.context.logger.info(f"{SKILL_LOG_PREFIX} built {len(txs)} txs")
        return txs

    def _get_held_positions(
        self,
    ) -> Generator[None, None, Dict[str, Set[int]]]:
        """Query the ConditionalTokens subgraph for positions the safe holds."""
        safe = self.synchronized_data.safe_contract_address.lower()
        held: Dict[str, Set[int]] = {}
        cursor = ""

        while True:
            response = yield from self.get_conditional_tokens_subgraph_result(
                query=USER_POSITIONS_QUERY.substitute(
                    safe=safe, page_size=SUBGRAPH_PAGE_SIZE, cursor=cursor
                )
            )
            if response is None:
                self.context.logger.warning(
                    f"{SKILL_LOG_PREFIX} ConditionalTokens subgraph query failed"
                )
                break

            positions = (response.get("data", {}).get("user", {}) or {}).get(
                "userPositions", []
            )
            if not positions:
                break

            for pos in positions:
                position = pos.get("position", {})
                condition_ids = position.get("conditionIds", [])
                index_sets = position.get("indexSets", [])
                for cid in condition_ids:
                    cid_lower = cid.lower()
                    if cid_lower not in held:
                        held[cid_lower] = set()
                    for idx_set in index_sets:
                        held[cid_lower].add(int(idx_set))

            cursor = positions[-1]["id"]
            if len(positions) < SUBGRAPH_PAGE_SIZE:
                break

        return held

    def _get_markets_for_conditions(
        self, condition_ids: List[str]
    ) -> Generator[None, None, List[Dict[str, Any]]]:
        """Query the Omen subgraph for finalized markets matching given conditions."""
        now = str(self.last_synced_timestamp)
        all_markets: List[Dict[str, Any]] = []
        seen: set = set()

        for i in range(0, len(condition_ids), CONDITION_ID_BATCH_SIZE):
            batch = condition_ids[i : i + CONDITION_ID_BATCH_SIZE]
            ids_str = ", ".join(f'"{cid}"' for cid in batch)
            response = yield from self.get_omen_subgraph_result(
                query=MARKETS_BY_CONDITIONS_QUERY.substitute(
                    condition_ids=ids_str,
                    now=now,
                    page_size=SUBGRAPH_PAGE_SIZE,
                )
            )
            if response is None:
                continue

            entries = response.get("data", {}).get("fixedProductMarketMakers", [])
            for entry in entries:
                conditions = entry.get("conditions", [])
                if not conditions:
                    continue
                condition = conditions[0]
                if condition.get("outcomeSlotCount") is None:
                    continue
                payouts = entry.get("payouts")
                if not payouts or not any(float(p) > 0 for p in payouts):
                    continue
                address = entry["id"]
                if address not in seen:
                    seen.add(address)
                    question = entry.get("question", {}) or {}
                    all_markets.append(
                        {
                            "address": address,
                            "condition_id": condition["id"],
                            "outcome_slot_count": condition["outcomeSlotCount"],
                            "payouts": payouts,
                            "question_id": question.get("id", ""),
                            "question_data": question.get("data", ""),
                            "template_id": int(entry.get("templateId", 0) or 0),
                        }
                    )

        return all_markets

    def _check_resolved(self, condition_id: str) -> Generator[None, None, bool]:
        """Check if a condition is resolved on ConditionalTokens."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.conditional_tokens_contract,
            contract_id=str(ConditionalTokensContract.contract_id),
            contract_callable=get_callable_name(
                ConditionalTokensContract.check_resolved
            ),
            condition_id=condition_id,
            chain_id=self.params.default_chain_id,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} "
                f"ConditionalTokensContract.check_resolved failed "
                f"for {condition_id}"
            )
            return False
        return bool(response.state.body.get("resolved", False))

    def _get_resolve_tx(
        self, market: Dict[str, Any]
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Build the encoded RealitioProxy.resolve() call."""
        question_id = market.get("question_id", "")
        question_data = market.get("question_data", "")
        template_id = market.get("template_id", 0)
        num_outcomes = market.get("outcome_slot_count", 2)

        if not question_id:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} no question_id for market " f"{market['address']}"
            )
            return None

        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.realitio_oracle_proxy_contract,
            contract_id=str(RealitioProxyContract.contract_id),
            contract_callable=get_callable_name(RealitioProxyContract.build_resolve_tx),
            question_id=bytes.fromhex(question_id[2:]),
            template_id=template_id,
            question=question_data,
            num_outcomes=num_outcomes,
            chain_id=self.params.default_chain_id,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} " f"RealitioProxyContract.build_resolve_tx failed"
            )
            return None

        data = response.state.body["data"]
        data = data.hex() if isinstance(data, bytes) else data
        return {
            "to": self.params.realitio_oracle_proxy_contract,
            "data": data,
            "value": ETHER_VALUE,
        }

    def _get_redeem_positions_tx(
        self,
        condition_id: str,
        index_sets: List[int],
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Build the encoded ConditionalTokens.redeemPositions() call."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.conditional_tokens_contract,
            contract_id=str(ConditionalTokensContract.contract_id),
            contract_callable=get_callable_name(
                ConditionalTokensContract.build_redeem_positions_tx
            ),
            collateral_token=self.params.collateral_tokens_contract,
            parent_collection_id=ZERO_HASH,
            condition_id=condition_id,
            index_sets=index_sets,
            chain_id=self.params.default_chain_id,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{SKILL_LOG_PREFIX} "
                f"ConditionalTokensContract.build_redeem_positions_tx failed"
            )
            return None

        data = response.state.body["data"]
        data = data.hex() if isinstance(data, bytes) else data
        return {
            "to": self.params.conditional_tokens_contract,
            "data": data,
            "value": ETHER_VALUE,
        }

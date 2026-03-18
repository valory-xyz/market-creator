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

"""This module contains the RedeemWinningsBehaviour of the 'market_creation_manager_abci' skill."""

from string import Template
from typing import Any, Dict, Generator, List, Optional, Set

from packages.valory.contracts.conditional_tokens.contract import (
    ConditionalTokensContract,
)
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    ETHER_VALUE,
    MarketCreationManagerBaseBehaviour,
    ZERO_HASH,
    get_callable_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    MultisigTxPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.redeem_winnings import (
    RedeemWinningsRound,
)

# Subgraph max per page.
SUBGRAPH_PAGE_SIZE = 1000

# Max condition IDs per Omen subgraph id_in query to avoid query size limits.
CONDITION_ID_BATCH_SIZE = 100

# ConditionalTokens subgraph: user positions with non-zero balance.
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

# Omen subgraph: finalized markets filtered by specific condition IDs.
# Uses conditions_: {id_in: [...]} to only return markets where the safe
# holds tokens, avoiding pagination through all markets.
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
      conditions {
        id
        outcomeSlotCount
      }
    }
  }""")


class RedeemWinningsBehaviour(MarketCreationManagerBaseBehaviour):
    """RedeemWinningsBehaviour"""

    matching_round = RedeemWinningsRound

    @staticmethod
    def _has_winning_position(payouts: List[str], held_index_sets: Set[int]) -> bool:
        """Check if any held index set corresponds to a winning payout."""
        for idx_set in held_index_sets:
            for i, payout in enumerate(payouts):
                if idx_set == (1 << i) and float(payout) > 0:
                    return True
        return False

    def async_act(self) -> Generator:
        """Implement the act."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            agent = self.context.agent_address
            tx_hash = yield from self.get_payload()
            if tx_hash is None:
                tx_submitter = None
            else:
                tx_submitter = self.matching_round.auto_round_id()
            payload = MultisigTxPayload(
                sender=agent, tx_submitter=tx_submitter, tx_hash=tx_hash
            )
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def get_payload(self) -> Generator[None, None, Optional[str]]:
        """Get the payload."""
        # Step 1: Get positions where the safe holds non-zero balances
        held_positions = yield from self._get_held_positions()
        if not held_positions:
            self.context.logger.info(
                "No non-zero positions found in ConditionalTokens subgraph."
            )
            return None

        self.context.logger.info(
            f"Safe holds non-zero positions for " f"{len(held_positions)} condition(s)."
        )

        # Step 2: Query Omen subgraph for ONLY markets matching held conditions
        markets = yield from self._get_markets_for_conditions(
            list(held_positions.keys())
        )
        if not markets:
            self.context.logger.info("No finalized markets found for held conditions.")
            return None

        # Step 3: Filter for winning positions
        redeemable = [
            m
            for m in markets
            if self._has_winning_position(
                m["payouts"], held_positions[m["condition_id"].lower()]
            )
        ]
        self.context.logger.info(
            f"Cross-reference: {len(redeemable)} redeemable market(s) "
            f"out of {len(markets)} finalized with held positions."
        )

        if not redeemable:
            self.context.logger.info("No redeemable positions found.")
            return None

        # Step 4: Build redeem txs
        batch_size = self.params.redeem_winnings_batch_size
        transactions: List[Dict[str, Any]] = []
        for market in redeemable[:batch_size]:
            self.context.logger.info(
                f"Building redeemPositions tx for market {market['address']} "
                f"with condition {market['condition_id']}"
            )
            index_sets = ConditionalTokensContract.get_partitions(
                market["outcome_slot_count"]
            )
            redeem_tx = yield from self._get_redeem_positions_tx(
                condition_id=market["condition_id"],
                index_sets=index_sets,
            )
            if redeem_tx is not None:
                transactions.append(redeem_tx)

        if len(transactions) == 0:
            self.context.logger.info("Failed to build any redeem transactions.")
            return None

        self.context.logger.info(
            f"Building multisend with {len(transactions)} " f"redeem transaction(s)."
        )
        tx_hash = yield from self._to_multisend(transactions=transactions)
        if tx_hash is None:
            return None
        return tx_hash

    def _get_held_positions(
        self,
    ) -> Generator[None, None, Dict[str, Set[int]]]:
        """Query the ConditionalTokens subgraph for positions the safe holds.

        Paginates through all userPositions with balance > 0 and returns a
        mapping from condition_id to the set of index_sets the safe holds.

        :yield: None
        :return: mapping from condition_id to set of held index_sets.
        """
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
                    "Failed to query ConditionalTokens subgraph."
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
        """Query the Omen subgraph for finalized markets matching given conditions.

        Batches condition IDs into chunks to avoid query size limits.
        Only returns markets with at least one positive payout.

        :param condition_ids: list of condition IDs to query for.
        :yield: None
        :return: list of market dicts with address, condition_id, payouts, etc.
        """
        now = str(self.last_synced_timestamp)
        all_markets: List[Dict[str, Any]] = []
        seen: set = set()

        for i in range(0, len(condition_ids), CONDITION_ID_BATCH_SIZE):
            batch = condition_ids[i : i + CONDITION_ID_BATCH_SIZE]
            ids_str = ", ".join(f'"{cid}"' for cid in batch)
            response = yield from self.get_subgraph_result(
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
                    all_markets.append(
                        {
                            "address": address,
                            "condition_id": condition["id"],
                            "outcome_slot_count": condition["outcomeSlotCount"],
                            "payouts": payouts,
                        }
                    )

        self.context.logger.info(
            f"Queried Omen subgraph for {len(condition_ids)} conditions "
            f"in {(len(condition_ids) - 1) // CONDITION_ID_BATCH_SIZE + 1} "
            f"batch(es): {len(all_markets)} finalized market(s) with payouts."
        )
        return all_markets

    def _get_redeem_positions_tx(
        self,
        condition_id: str,
        index_sets: List[int],
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Build a redeemPositions transaction."""
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
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"ConditionalTokensContract.build_redeem_positions_tx "
                f"unsuccessful! : {response}"
            )
            return None
        return {
            "to": self.params.conditional_tokens_contract,
            "data": response.state.body["data"],
            "value": ETHER_VALUE,
        }

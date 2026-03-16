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
from typing import Any, Dict, Generator, List, Optional, cast

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

# Markets created by the safe.
# Uses fixedProductMarketMakers(creator:) because initial liquidity is added
# by the factory contract, so fpmmLiquidities(funder:) would not match the safe.
LP_MARKETS_QUERY = Template("""{
    fixedProductMarketMakers(
      where: {creator: "$safe", openingTimestamp_lt: "$now"}
      first: $batch_size
      orderBy: creationTimestamp
      orderDirection: asc
    ) {
      id
      conditions {
        id
        outcomeSlotCount
      }
    }
  }""")

# Markets where the safe directly added liquidity (not via factory).
# Covers cases where the safe funds an existing market it did not create.
DIRECT_LP_QUERY = Template("""{
    fpmmLiquidities(
      where: {funder: "$safe", type: Add, fpmm_: {openingTimestamp_lt: "$now"}}
      first: $batch_size
      orderBy: creationTimestamp
      orderDirection: asc
    ) {
      fpmm {
        id
        conditions {
          id
          outcomeSlotCount
        }
      }
    }
  }""")

# Markets where the safe bought outcome tokens as a trader.
# These positions remain redeemable once the market resolves.
TRADE_MARKETS_QUERY = Template("""{
    fpmmTrades(
      where: {creator: "$safe", type: Buy, fpmm_: {openingTimestamp_lt: "$now"}}
      first: $batch_size
      orderBy: creationTimestamp
      orderDirection: asc
    ) {
      fpmm {
        id
        conditions {
          id
          outcomeSlotCount
        }
      }
    }
  }""")


class RedeemWinningsBehaviour(MarketCreationManagerBaseBehaviour):
    """RedeemWinningsBehaviour"""

    matching_round = RedeemWinningsRound

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
        markets = yield from self._get_resolved_markets()
        if markets is None or len(markets) == 0:
            self.context.logger.info("No resolved markets to redeem winnings from.")
            return None

        transactions: List[Dict[str, Any]] = []
        for market in markets:
            redeem_txs = yield from self._build_redeem_txs_for_market(market)
            if redeem_txs is not None:
                transactions.extend(redeem_txs)

        if len(transactions) == 0:
            self.context.logger.info("No redeemable positions found.")
            return None

        self.context.logger.info(
            f"Building multisend with {len(transactions)} redeem transaction(s)."
        )
        tx_hash = yield from self._to_multisend(transactions=transactions)
        if tx_hash is None:
            return None
        return tx_hash

    def _get_resolved_markets(
        self,
    ) -> Generator[None, None, Optional[List[Dict[str, Any]]]]:
        """Query the Omen subgraph for markets where the safe holds redeemable positions.

        Uses three queries to cover all sources of conditional tokens:
        1. Markets created by the safe (factory-funded LP positions)
        2. Markets where the safe directly added liquidity (non-factory LP)
        3. Markets where the safe bought outcome tokens (trader positions)

        Results are deduplicated by market address.
        """
        safe = self.synchronized_data.safe_contract_address.lower()
        now = str(self.last_synced_timestamp)
        batch_size = self.params.redeem_winnings_batch_size

        created_response = yield from self.get_subgraph_result(
            query=LP_MARKETS_QUERY.substitute(safe=safe, now=now, batch_size=batch_size)
        )
        direct_lp_response = yield from self.get_subgraph_result(
            query=DIRECT_LP_QUERY.substitute(safe=safe, now=now, batch_size=batch_size)
        )
        trade_response = yield from self.get_subgraph_result(
            query=TRADE_MARKETS_QUERY.substitute(
                safe=safe, now=now, batch_size=batch_size
            )
        )

        if all(
            r is None for r in (created_response, direct_lp_response, trade_response)
        ):
            self.context.logger.error("Could not retrieve any markets from subgraph.")
            return None

        def _extract_markets(
            response: Optional[Dict], key: str, nested: bool = False
        ) -> List[Dict]:
            if response is None:
                return []
            entries = response.get("data", {}).get(key, [])
            result = []
            for entry in entries:
                fpmm = entry.get("fpmm", {}) if nested else entry
                conditions = fpmm.get("conditions", [])
                if not conditions:
                    continue
                condition = conditions[0]
                if condition.get("outcomeSlotCount") is None:
                    continue
                result.append(
                    {
                        "address": fpmm["id"],
                        "condition_id": condition["id"],
                        "outcome_slot_count": condition["outcomeSlotCount"],
                    }
                )
            return result

        created_markets = _extract_markets(
            created_response, "fixedProductMarketMakers", nested=False
        )
        direct_lp_markets = _extract_markets(
            direct_lp_response, "fpmmLiquidities", nested=True
        )
        trade_markets = _extract_markets(trade_response, "fpmmTrades", nested=True)

        # Deduplicate by market address (safe may appear in multiple queries)
        seen: set = set()
        markets = []
        for m in created_markets + direct_lp_markets + trade_markets:
            if m["address"] not in seen:
                seen.add(m["address"])
                markets.append(m)

        self.context.logger.info(
            f"Found {len(markets)} unique market(s) past opening timestamp "
            f"({len(created_markets)} created, {len(direct_lp_markets)} direct LP, "
            f"{len(trade_markets)} trader)."
        )
        return markets

    def _build_redeem_txs_for_market(
        self, market: Dict[str, Any]
    ) -> Generator[None, None, Optional[List[Dict[str, Any]]]]:
        """Check if a market is resolved and has redeemable positions, then build tx."""
        condition_id = market["condition_id"]
        outcome_slot_count = market["outcome_slot_count"]

        # Check if the condition is resolved
        is_resolved = yield from self._check_resolved(condition_id)
        if is_resolved is None or not is_resolved:
            return None

        # Check if the safe holds any conditional tokens
        has_holdings = yield from self._check_holdings(
            market_address=market["address"],
            condition_id=condition_id,
            outcome_slot_count=outcome_slot_count,
        )
        if not has_holdings:
            return None

        # Build the redeemPositions tx
        self.context.logger.info(
            f"Building redeemPositions tx for market {market['address']} "
            f"with condition {condition_id}"
        )
        index_sets = ConditionalTokensContract.get_partitions(outcome_slot_count)
        redeem_tx = yield from self._get_redeem_positions_tx(
            condition_id=condition_id,
            index_sets=index_sets,
        )
        if redeem_tx is None:
            return None
        return [redeem_tx]

    def _check_resolved(
        self, condition_id: str
    ) -> Generator[None, None, Optional[bool]]:
        """Check whether a condition has been resolved."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.conditional_tokens_contract,
            contract_id=str(ConditionalTokensContract.contract_id),
            contract_callable=get_callable_name(
                ConditionalTokensContract.check_resolved
            ),
            condition_id=condition_id,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"ConditionalTokensContract.check_resolved unsuccessful! : {response}"
            )
            return None
        resolved = cast(bool, response.state.body["resolved"])
        return resolved

    def _check_holdings(
        self,
        market_address: str,
        condition_id: str,
        outcome_slot_count: int,
    ) -> Generator[None, None, bool]:
        """Check if the safe holds any conditional tokens for a market."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.conditional_tokens_contract,
            contract_id=str(ConditionalTokensContract.contract_id),
            contract_callable=get_callable_name(
                ConditionalTokensContract.get_user_holdings
            ),
            outcome_slot_count=outcome_slot_count,
            condition_id=condition_id,
            creator=self.synchronized_data.safe_contract_address,
            collateral_token=self.params.collateral_tokens_contract,
            market=market_address,
            parent_collection_id=ZERO_HASH,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"ConditionalTokensContract.get_user_holdings unsuccessful! : {response}"
            )
            return False

        shares = cast(list, response.state.body["shares"])
        has_shares = any(s > 0 for s in shares)
        if has_shares:
            self.context.logger.info(
                f"Safe holds conditional tokens for market {market_address}: "
                f"shares={shares}"
            )
        return has_shares

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
                f"ConditionalTokensContract.build_redeem_positions_tx unsuccessful! : {response}"
            )
            return None
        return {
            "to": self.params.conditional_tokens_contract,
            "data": response.state.body["data"],
            "value": ETHER_VALUE,
        }

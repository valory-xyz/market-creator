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

# Subgraph max per page.
SUBGRAPH_PAGE_SIZE = 1000

# Markets created by the safe, filtered for finalized answers.
# The answerFinalizedTimestamp filter ensures only resolved markets are returned,
# eliminating the need for on-chain check_resolved calls.
# The payouts field provides payout numerators, eliminating on-chain payout checks.
# id_gt enables cursor-based pagination across cycles.
LP_MARKETS_QUERY = Template("""{
    fixedProductMarketMakers(
      where: {
        creator: "$safe"
        answerFinalizedTimestamp_not: null
        answerFinalizedTimestamp_lt: "$now"
        id_gt: "$cursor"
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

# Markets where the safe directly added liquidity (not via factory).
DIRECT_LP_QUERY = Template("""{
    fpmmLiquidities(
      where: {
        funder: "$safe"
        type: Add
        fpmm_: {
          answerFinalizedTimestamp_not: null
          answerFinalizedTimestamp_lt: "$now"
          id_gt: "$cursor"
        }
      }
      first: $page_size
      orderBy: fpmm__id
      orderDirection: asc
    ) {
      fpmm {
        id
        payouts
        conditions {
          id
          outcomeSlotCount
        }
      }
    }
  }""")

# Markets where the safe bought outcome tokens as a trader.
TRADE_MARKETS_QUERY = Template("""{
    fpmmTrades(
      where: {
        creator: "$safe"
        type: Buy
        fpmm_: {
          answerFinalizedTimestamp_not: null
          answerFinalizedTimestamp_lt: "$now"
          id_gt: "$cursor"
        }
      }
      first: $page_size
      orderBy: fpmm__id
      orderDirection: asc
    ) {
      fpmm {
        id
        payouts
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

    @property
    def _cursor(self) -> str:
        """Get the pagination cursor from shared state."""
        return getattr(self.context.state, "redeem_winnings_cursor", "")

    @_cursor.setter
    def _cursor(self, value: str) -> None:
        """Set the pagination cursor on shared state."""
        self.context.state.redeem_winnings_cursor = value  # type: ignore

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
        markets = yield from self._get_redeemable_candidates()
        if markets is None or len(markets) == 0:
            self.context.logger.info("No resolved markets to redeem winnings from.")
            return None

        batch_size = self.params.redeem_winnings_batch_size
        transactions: List[Dict[str, Any]] = []
        checked = 0
        for market in markets:
            checked += 1
            has_holdings = yield from self._check_holdings(
                market_address=market["address"],
                condition_id=market["condition_id"],
                outcome_slot_count=market["outcome_slot_count"],
                payouts=market["payouts"],
            )
            if not has_holdings:
                continue

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
                if len(transactions) >= batch_size:
                    break

        # Advance cursor to last checked market for next cycle
        if markets:
            last_checked_id = markets[min(checked, len(markets)) - 1]["address"]
            if checked >= len(markets):
                # Reached end of page — if page was full, advance cursor;
                # if page was partial, we've seen all markets, reset cursor.
                if len(markets) < SUBGRAPH_PAGE_SIZE:
                    self._cursor = ""
                else:
                    self._cursor = last_checked_id
            else:
                # Stopped early (found enough txs) — resume from here next cycle
                self._cursor = last_checked_id
            self.context.logger.info(
                f"Pagination cursor advanced to {self._cursor!r} "
                f"(checked {checked}/{len(markets)} markets)."
            )

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

    def _get_redeemable_candidates(
        self,
    ) -> Generator[None, None, Optional[List[Dict[str, Any]]]]:
        """Query the Omen subgraph for finalized markets with winning payouts.

        Uses subgraph filters to only return markets whose answers have been
        finalized (answerFinalizedTimestamp). This eliminates on-chain
        check_resolved calls. The payouts field provides payout numerators,
        eliminating on-chain payout checks.

        Uses id_gt cursor-based pagination to advance through markets across
        cycles, ensuring all markets are eventually checked.
        """
        safe = self.synchronized_data.safe_contract_address.lower()
        now = str(self.last_synced_timestamp)
        cursor = self._cursor
        page_size = SUBGRAPH_PAGE_SIZE

        created_response = yield from self.get_subgraph_result(
            query=LP_MARKETS_QUERY.substitute(
                safe=safe, now=now, cursor=cursor, page_size=page_size
            )
        )
        direct_lp_response = yield from self.get_subgraph_result(
            query=DIRECT_LP_QUERY.substitute(
                safe=safe, now=now, cursor=cursor, page_size=page_size
            )
        )
        trade_response = yield from self.get_subgraph_result(
            query=TRADE_MARKETS_QUERY.substitute(
                safe=safe, now=now, cursor=cursor, page_size=page_size
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
                payouts = fpmm.get("payouts")
                if not payouts or not any(float(p) > 0 for p in payouts):
                    continue
                result.append(
                    {
                        "address": fpmm["id"],
                        "condition_id": condition["id"],
                        "outcome_slot_count": condition["outcomeSlotCount"],
                        "payouts": payouts,
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

        # Deduplicate by market address, sorted by id for deterministic cursor
        seen: set = set()
        markets = []
        for m in created_markets + direct_lp_markets + trade_markets:
            if m["address"] not in seen:
                seen.add(m["address"])
                markets.append(m)
        markets.sort(key=lambda m: m["address"])

        self.context.logger.info(
            f"Found {len(markets)} finalized market(s) with payouts "
            f"(cursor={cursor!r}, {len(created_markets)} created, "
            f"{len(direct_lp_markets)} direct LP, {len(trade_markets)} trader)."
        )
        return markets

    def _check_holdings(
        self,
        market_address: str,
        condition_id: str,
        outcome_slot_count: int,
        payouts: List[str],
    ) -> Generator[None, None, bool]:
        """Check if the safe holds redeemable conditional tokens for a market.

        Uses the payouts from the subgraph to determine which outcomes won.
        Only reports holdings as redeemable if tokens are on a winning side.
        """
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
        has_winnings = any(
            s > 0 and float(payouts[i]) > 0
            for i, s in enumerate(shares)
            if i < len(payouts)
        )
        if has_winnings:
            self.context.logger.info(
                f"Safe holds winning tokens for market {market_address}: "
                f"shares={shares}, payouts={payouts}"
            )
        elif any(s > 0 for s in shares):
            self.context.logger.info(
                f"Safe holds only losing tokens for market {market_address}: "
                f"shares={shares}, payouts={payouts} — skipping"
            )
        return has_winnings

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

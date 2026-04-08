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

"""FpmmRemoveLiquidityBehaviour for the omen_fpmm_remove_liquidity_abci skill."""

from string import Template
from typing import Any, Dict, Generator, List, Optional, Tuple, cast

from packages.valory.contracts.conditional_tokens.contract import (
    ConditionalTokensContract,
)
from packages.valory.contracts.fpmm.contract import FPMMContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.omen_fpmm_remove_liquidity_abci.behaviours.base import (
    ETHER_VALUE,
    FpmmRemoveLiquidityBaseBehaviour,
    LOG_PREFIX,
    ZERO_ADDRESS,
    ZERO_HASH,
    get_callable_name,
)
from packages.valory.skills.omen_fpmm_remove_liquidity_abci.payloads import (
    FpmmRemoveLiquidityPayload,
)
from packages.valory.skills.omen_fpmm_remove_liquidity_abci.rounds import (
    FpmmRemoveLiquidityRound,
)

FPMM_POOL_MEMBERSHIPS_QUERY = Template("""{
    fpmmPoolMemberships(
      where: {funder: "$creator", amount_gt: "0"}
      first: 1000
    ) {
      amount
      id
      pool {
        id
        openingTimestamp
        creator
        conditions {
          id
          question {
            id
          }
          outcomeSlotCount
        }
        liquidityMeasure
        outcomeTokenAmounts
      }
    }
  }""")

_ACTION_SKIP = "skip"
_ACTION_REMOVE_ONLY = "remove_only"
_ACTION_REMOVE_AND_MERGE = "remove_and_merge"

TX_SUBMITTER_NAME = "omen_fpmm_remove_liquidity"


class FpmmRemoveLiquidityBehaviour(FpmmRemoveLiquidityBaseBehaviour):
    """Behaviour that removes LP funds from FPMM markets (and optionally merges positions)."""

    matching_round = FpmmRemoveLiquidityRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            tx_hash = yield from self._prepare_multisend()
            tx_submitter = TX_SUBMITTER_NAME if tx_hash is not None else None
            payload = FpmmRemoveLiquidityPayload(
                sender=sender, tx_submitter=tx_submitter, tx_hash=tx_hash
            )
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def _prepare_multisend(self) -> Generator[None, None, Optional[str]]:
        """Fetch eligible markets, classify each, and build a multisend payload."""
        markets = yield from self._get_markets()
        if not markets:
            return None

        now = self.last_synced_timestamp
        batch_size = self.params.fpmm_remove_liquidity_batch_size
        txs: List[Dict[str, Any]] = []
        markets_processed = 0

        for market in markets:
            if markets_processed >= batch_size:
                break

            action = yield from self._classify_market(market, now)
            if action == _ACTION_SKIP:
                continue

            market_txs = yield from self._build_market_txs(market, action)
            if market_txs:
                txs.extend(market_txs)
                markets_processed += 1

        self.context.logger.info(
            f"{LOG_PREFIX} built {len(txs)} txs from {markets_processed} markets"
        )
        if not txs:
            return None

        return (yield from self._to_multisend(txs))

    def _classify_market(
        self, market: Dict[str, Any], now: int
    ) -> Generator[None, None, str]:
        """Classify a market as skip / remove_only / remove_and_merge.

        :param market: market dict with opening_timestamp and condition_id keys.
        :param now: last synced timestamp (seconds).
        :yield: contract-api requests during the on-chain resolve check.
        :return: one of _ACTION_SKIP, _ACTION_REMOVE_ONLY, _ACTION_REMOVE_AND_MERGE.
        """
        opening_ts = market["opening_timestamp"]
        lead_time = self.params.liquidity_removal_lead_time

        # State 1: market still open — do nothing yet
        if now < opening_ts - lead_time:
            return _ACTION_SKIP

        condition_id = market["condition_id"]
        resolved = yield from self._check_resolved(condition_id)

        if resolved:
            # State 4: closed + CT resolved → remove LP only (merge not possible)
            return _ACTION_REMOVE_ONLY

        # States 2+3: approaching close or closed but CT not yet resolved
        return _ACTION_REMOVE_AND_MERGE

    def _build_market_txs(
        self, market: Dict[str, Any], action: str
    ) -> Generator[None, None, List[Dict[str, Any]]]:
        """Build the transaction list for the given market and action.

        :param market: market dict.
        :param action: _ACTION_REMOVE_ONLY or _ACTION_REMOVE_AND_MERGE.
        :yield: contract-api requests while building the txs.
        :return: list of encoded transaction dicts (possibly empty).
        """
        address = market["address"]
        condition_id = market["condition_id"]
        outcome_slot_count = market["outcome_slot_count"]

        amounts = yield from self._calculate_amounts(
            market=address,
            condition_id=condition_id,
            outcome_slot_count=outcome_slot_count,
        )
        if amounts is None:
            return []

        amount_to_remove, amount_to_merge = amounts
        self.context.logger.info(
            f"{LOG_PREFIX} {action} on {address} "
            f"(shares: {amount_to_remove}, merge: {amount_to_merge})"
        )

        remove_funding_tx = yield from self._get_remove_funding_tx(
            address=address, amount_to_remove=amount_to_remove
        )
        if remove_funding_tx is None:
            return []

        if action == _ACTION_REMOVE_ONLY:
            return [remove_funding_tx]

        merge_positions_tx = yield from self._get_merge_positions_tx(
            collateral_token=self.params.collateral_tokens_contract,
            parent_collection_id=ZERO_HASH,
            condition_id=condition_id,
            outcome_slot_count=outcome_slot_count,
            amount=amount_to_merge,
        )
        if merge_positions_tx is None:
            return [remove_funding_tx]

        return [remove_funding_tx, merge_positions_tx]

    def _get_markets(self) -> Generator[None, None, List[Dict[str, Any]]]:
        """Fetch FPMM LP positions from the Omen subgraph and verify on-chain."""
        creator = self.synchronized_data.safe_contract_address.lower()
        response = yield from self.get_omen_subgraph_result(
            query=FPMM_POOL_MEMBERSHIPS_QUERY.substitute(creator=creator)
        )
        if response is None:
            self.context.logger.warning(
                f"{LOG_PREFIX} Omen subgraph query for LP positions failed"
            )
            return []

        markets: List[Dict[str, Any]] = []
        for entry in response.get("data", {}).get("fpmmPoolMemberships", []):
            liquidity_measure = entry["pool"].get("liquidityMeasure")
            if liquidity_measure is None:
                continue
            if int(liquidity_measure) == 0:
                continue
            if entry["pool"]["openingTimestamp"] is None:
                continue

            condition, *_ = entry["pool"]["conditions"]
            if condition["question"] is None:
                continue

            market: Dict[str, Any] = {
                "address": entry["pool"]["id"],
                "amount": sum(map(int, entry["pool"]["outcomeTokenAmounts"])),
                "opening_timestamp": int(entry["pool"]["openingTimestamp"]),
                "condition_id": condition["id"],
                "outcome_slot_count": condition["outcomeSlotCount"],
                "question_id": condition["question"]["id"],
            }
            markets.append(market)

        if not markets:
            return []

        market_addresses = [m["address"] for m in markets]
        safe_address = self.synchronized_data.safe_contract_address
        markets_with_funds_addresses = yield from self._get_markets_with_funds(
            market_addresses, safe_address
        )
        lower_set = {str(a).lower() for a in markets_with_funds_addresses}
        return [m for m in markets if str(m["address"]).lower() in lower_set]

    def _get_markets_with_funds(
        self,
        market_addresses: List[str],
        safe_address: str,
    ) -> Generator[None, None, List[str]]:
        """Verify which markets have LP funds on-chain."""
        if not market_addresses:
            return []

        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=ZERO_ADDRESS,
            contract_id=str(FPMMContract.contract_id),
            contract_callable=get_callable_name(FPMMContract.get_markets_with_funds),
            markets=market_addresses,
            safe_address=safe_address,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{LOG_PREFIX} FPMMContract.get_markets_with_funds failed"
            )
            return []
        return cast(List[str], response.state.body["data"])

    def _calculate_amounts(
        self,
        market: str,
        condition_id: str,
        outcome_slot_count: int,
    ) -> Generator[None, None, Optional[Tuple[int, int]]]:
        """Calculate LP shares to burn and positions to merge."""
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
            market=market,
            parent_collection_id=ZERO_HASH,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{LOG_PREFIX} ConditionalTokensContract.get_user_holdings failed"
            )
            return None

        shares = cast(List[int], response.state.body["shares"])
        holdings = cast(List[int], response.state.body["holdings"])

        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=market,
            contract_id=str(FPMMContract.contract_id),
            contract_callable=get_callable_name(FPMMContract.get_balance),
            address=self.synchronized_data.safe_contract_address,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(f"{LOG_PREFIX} FPMMContract.get_balance failed")
            return None
        amount_to_remove = cast(int, response.state.body["balance"])

        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=market,
            contract_id=str(FPMMContract.contract_id),
            contract_callable=get_callable_name(FPMMContract.get_total_supply),
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{LOG_PREFIX} FPMMContract.get_total_supply failed"
            )
            return None
        total_pool_shares = cast(int, response.state.body["supply"])

        if total_pool_shares == 0:
            send_amounts = [0] * len(holdings)
        elif amount_to_remove == total_pool_shares:
            send_amounts = [*holdings]
        else:
            send_amounts = [
                int(h * amount_to_remove / total_pool_shares) for h in holdings
            ]

        amount_to_merge = min(
            send_amounts[i] + shares[i] for i in range(len(send_amounts))
        )
        return amount_to_remove, amount_to_merge

    def _get_remove_funding_tx(
        self,
        address: str,
        amount_to_remove: int,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Build the encoded FPMMContract.removeFunds() call."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_id=str(FPMMContract.contract_id),
            contract_callable=get_callable_name(FPMMContract.build_remove_funding_tx),
            contract_address=address,
            amount_to_remove=amount_to_remove,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{LOG_PREFIX} FPMMContract.build_remove_funding_tx failed"
            )
            return None

        data = response.state.body["data"]
        data = data.hex() if isinstance(data, bytes) else data
        return {"to": address, "data": data, "value": ETHER_VALUE}

    def _get_merge_positions_tx(
        self,
        collateral_token: str,
        parent_collection_id: str,
        condition_id: str,
        outcome_slot_count: int,
        amount: int,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Build the encoded ConditionalTokens.mergePositions() call."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.conditional_tokens_contract,
            contract_id=str(ConditionalTokensContract.contract_id),
            contract_callable=get_callable_name(
                ConditionalTokensContract.build_merge_positions_tx
            ),
            collateral_token=collateral_token,
            parent_collection_id=parent_collection_id,
            condition_id=condition_id,
            outcome_slot_count=outcome_slot_count,
            amount=amount,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{LOG_PREFIX} ConditionalTokensContract.build_merge_positions_tx failed"
            )
            return None

        data = response.state.body["data"]
        data = data.hex() if isinstance(data, bytes) else data
        return {
            "to": self.params.conditional_tokens_contract,
            "data": data,
            "value": ETHER_VALUE,
        }

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
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{LOG_PREFIX} ConditionalTokensContract.check_resolved failed "
                f"for {condition_id}"
            )
            return False
        return bool(response.state.body.get("resolved", False))

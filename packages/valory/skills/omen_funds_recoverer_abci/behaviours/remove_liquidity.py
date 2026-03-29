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

"""This module contains the RemoveLiquidityBehaviour of the 'omen_funds_recoverer_abci' skill."""

import json
from datetime import datetime
from string import Template
from typing import Any, Dict, Generator, List, Optional, Tuple, cast

from packages.valory.contracts.conditional_tokens.contract import (
    ConditionalTokensContract,
)
from packages.valory.contracts.fpmm.contract import FPMMContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.omen_funds_recoverer_abci.behaviours.base import (
    ETHER_VALUE,
    OmenFundsRecovererBaseBehaviour,
    ZERO_ADDRESS,
    ZERO_HASH,
    get_callable_name,
)
from packages.valory.skills.omen_funds_recoverer_abci.payloads import (
    RecoveryTxsPayload,
)
from packages.valory.skills.omen_funds_recoverer_abci.rounds import (
    RemoveLiquidityRound,
)

# Subgraph max per page.
SUBGRAPH_PAGE_SIZE = 1000

FPMM_POOL_MEMBERSHIPS_QUERY = Template("""  {
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


class RemoveLiquidityBehaviour(OmenFundsRecovererBaseBehaviour):
    """RemoveLiquidityBehaviour

    Removes liquidity from FPMM markets whose opening time is approaching,
    then merges the resulting conditional token positions back into collateral.
    Returns raw tx dicts via RecoveryTxsPayload for later bundling.
    """

    matching_round = RemoveLiquidityRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            new_txs = yield from self._get_recovery_txs()
            existing = self.synchronized_data.funds_recovery_txs
            combined = existing + new_txs
            payload = RecoveryTxsPayload(
                sender=sender, content=json.dumps(combined)
            )
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def _get_recovery_txs(self) -> Generator[None, None, List[Dict[str, Any]]]:
        """Get recovery transactions for liquidity removal.

        1. Query Omen subgraph for LP positions
        2. Verify on-chain with FPMM.get_markets_with_funds
        3. Filter by opening_timestamp - liquidity_removal_lead_time < now
        4. For each eligible market: build removeFunding + mergePositions tx dicts

        :yield: None
        :return: list of tx dicts (may be empty).
        """
        markets = yield from self._get_markets()
        if not markets:
            self.context.logger.info("No markets with LP positions found.")
            return []

        # Filter eligible markets
        eligible = [
            m for m in markets if m["removal_timestamp"] < self.last_synced_timestamp
        ]
        if not eligible:
            self.context.logger.info("No markets eligible for liquidity removal yet.")
            return []

        batch_size = self.params.remove_liquidity_batch_size
        txs: List[Dict[str, Any]] = []
        for market in eligible[:batch_size]:
            address = market["address"]
            self.context.logger.info(f"Closing market: {address}")

            amounts = yield from self._calculate_amounts(
                market=address,
                condition_id=market["condition_id"],
                outcome_slot_count=market["outcome_slot_count"],
            )
            if amounts is None:
                continue

            amount_to_remove, amount_to_merge = amounts
            self.context.logger.info(f"Amount to remove: {amount_to_remove}")
            self.context.logger.info(f"Amount to merge: {amount_to_merge}")

            remove_funding_tx = yield from self._get_remove_funding_tx(
                address=address, amount_to_remove=amount_to_remove
            )
            if remove_funding_tx is None:
                continue

            merge_positions_tx = yield from self._get_merge_positions_tx(
                collateral_token=self.params.collateral_tokens_contract,
                parent_collection_id=ZERO_HASH,
                condition_id=market["condition_id"],
                outcome_slot_count=market["outcome_slot_count"],
                amount=amount_to_merge,
            )
            if merge_positions_tx is None:
                continue

            txs.append(remove_funding_tx)
            txs.append(merge_positions_tx)

        self.context.logger.info(
            f"Built {len(txs)} remove-liquidity tx(es) "
            f"for {min(len(eligible), batch_size)} market(s)."
        )
        return txs

    def _get_markets(
        self,
    ) -> Generator[None, None, List[Dict[str, Any]]]:
        """Collect FPMM LP positions from the Omen subgraph, verified on-chain.

        :yield: None
        :return: list of market dicts.
        """
        creator = self.synchronized_data.safe_contract_address.lower()
        response = yield from self.get_subgraph_result(
            query=FPMM_POOL_MEMBERSHIPS_QUERY.substitute(creator=creator)
        )
        if response is None:
            self.context.logger.warning(
                "Failed to query Omen subgraph for LP positions."
            )
            return []

        lead_time = self.params.liquidity_removal_lead_time
        markets: List[Dict[str, Any]] = []
        for entry in response.get("data", {}).get("fpmmPoolMemberships", []):
            market: Dict[str, Any] = {}
            liquidity_measure = entry["pool"].get("liquidityMeasure")
            if liquidity_measure is None:
                continue

            liquidity_measure = int(liquidity_measure)
            if liquidity_measure == 0:
                continue

            if entry["pool"]["openingTimestamp"] is None:
                continue

            market["address"] = entry["pool"]["id"]
            market["amount"] = sum(map(int, entry["pool"]["outcomeTokenAmounts"]))
            market["opening_timestamp"] = int(entry["pool"]["openingTimestamp"])
            market["removal_timestamp"] = market["opening_timestamp"] - lead_time

            # The markets created by the agent will only have one condition per market
            condition, *_ = entry["pool"]["conditions"]
            market["condition_id"] = condition["id"]
            market["outcome_slot_count"] = condition["outcomeSlotCount"]
            if condition["question"] is None:
                continue

            market["question_id"] = condition["question"]["id"]
            markets.append(market)

        market_addresses = [m["address"] for m in markets]
        market_addresses_with_funds = yield from self._get_markets_with_funds(
            market_addresses, self.synchronized_data.safe_contract_address
        )
        market_addresses_with_funds_str = [
            str(addr).lower() for addr in market_addresses_with_funds
        ]
        markets_with_funds: List[Dict[str, Any]] = []
        for market in markets:
            if str(market["address"]).lower() not in market_addresses_with_funds_str:
                continue
            markets_with_funds.append(market)
            log_msg = "\n\t".join(
                [
                    "Adding market with",
                    "Address: " + market["address"],
                    "Liquidity: " + str(market["amount"]),
                    "Opening time: "
                    + str(datetime.fromtimestamp(market["opening_timestamp"])),
                    "Liquidity removal time: "
                    + str(datetime.fromtimestamp(market["removal_timestamp"])),
                ]
            )
            self.context.logger.info(log_msg)

        return markets_with_funds

    def _get_markets_with_funds(
        self,
        market_addresses: List[str],
        safe_address: str,
    ) -> Generator[None, None, List[str]]:
        """Verify which markets have LP funds on-chain.

        :param market_addresses: list of market contract addresses.
        :param safe_address: the safe contract address.
        :yield: None
        :return: list of market addresses that have funds.
        """
        if len(market_addresses) == 0:
            return []

        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=ZERO_ADDRESS,  # NOT USED!
            contract_id=str(FPMMContract.contract_id),
            contract_callable=get_callable_name(FPMMContract.get_markets_with_funds),
            markets=market_addresses,
            safe_address=safe_address,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Couldn't get tx data for FPMMContract.get_markets_with_funds. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return []
        return cast(List[str], response.state.body["data"])

    def _calculate_amounts(
        self,
        market: str,
        condition_id: str,
        outcome_slot_count: int,
    ) -> Generator[None, None, Optional[Tuple[int, int]]]:
        """Calculate amount to burn.

        :param market: the market address.
        :param condition_id: the condition ID.
        :param outcome_slot_count: the number of outcome slots.
        :yield: None
        :return: tuple of (amount_to_remove, amount_to_merge), or None on error.
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
            market=market,
            parent_collection_id=ZERO_HASH,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"ConditionalTokensContract.get_user_holdings unsuccessful! : "
                f"{response}"
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
            self.context.logger.warning(
                f"FPMMContract.get_balance unsuccessful! : {response}"
            )
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
                f"FPMMContract.get_total_supply unsuccessful! : {response}"
            )
            return None
        total_pool_shares = cast(int, response.state.body["supply"])
        if amount_to_remove == total_pool_shares:
            send_amounts_after_removing_funding = [
                *holdings,
            ]
        else:
            send_amounts_after_removing_funding = [
                (
                    int(h * amount_to_remove / total_pool_shares)
                    if total_pool_shares > 0
                    else 0
                )
                for h in holdings
            ]
        amount_to_merge = min(
            send_amounts_after_removing_funding[i] + shares[i]
            for i in range(len(send_amounts_after_removing_funding))
        )
        return amount_to_remove, amount_to_merge

    def _get_remove_funding_tx(
        self,
        address: str,
        amount_to_remove: int,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Build the encoded FPMMContract.removeFunds() call.

        :param address: the market address.
        :param amount_to_remove: the LP shares to burn.
        :yield: None
        :return: transaction dict or None on error.
        """
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_id=str(FPMMContract.contract_id),
            contract_callable=get_callable_name(FPMMContract.build_remove_funding_tx),
            contract_address=address,
            amount_to_remove=amount_to_remove,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Couldn't get tx data for FPMMContract.build_remove_funding_tx. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return None

        data = response.state.body["data"]
        data = data.hex() if isinstance(data, bytes) else data
        return {
            "to": address,
            "data": data,
            "value": ETHER_VALUE,
        }

    def _get_merge_positions_tx(
        self,
        collateral_token: str,
        parent_collection_id: str,
        condition_id: str,
        outcome_slot_count: int,
        amount: int,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Build a mergePositions transaction.

        :param collateral_token: the collateral token address.
        :param parent_collection_id: the parent collection ID.
        :param condition_id: the condition ID.
        :param outcome_slot_count: the number of outcome slots.
        :param amount: the amount to merge.
        :yield: None
        :return: transaction dict or None on error.
        """
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
                f"ConditionalTokensContract.build_merge_positions_tx "
                f"unsuccessful! : {response}"
            )
            return None

        data = response.state.body["data"]
        data = data.hex() if isinstance(data, bytes) else data
        return {
            "to": self.params.conditional_tokens_contract,
            "data": data,
            "value": ETHER_VALUE,
        }

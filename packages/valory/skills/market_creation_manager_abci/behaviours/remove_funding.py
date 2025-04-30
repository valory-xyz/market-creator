# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2024 Valory AG
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

"""This module contains the remove funding behaviour."""

import json
from typing import Any, Dict, Generator, List, Optional, Tuple, cast

from packages.valory.contracts.conditional_tokens.contract import ConditionalTokensContract
from packages.valory.contracts.fpmm.contract import FPMMContract
from packages.valory.contracts.wxdai.contract import WxDAIContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.base import MarketCreationManagerBaseBehaviour, ETHER_VALUE, ZERO_HASH, get_callable_name
from packages.valory.skills.market_creation_manager_abci.states.remove_funding_round import RemoveFundingRound
from packages.valory.skills.market_creation_manager_abci.payloads import RemoveFundingPayload


class RemoveFundingBehaviour(MarketCreationManagerBaseBehaviour):
    """Remove funding behaviour."""

    matching_round = RemoveFundingRound

    def _calculate_amounts(
        self,
        market: str,
        condition_id: str,
        outcome_slot_count: int,
    ) -> Generator[None, None, Optional[Tuple[int, int]]]:
        """Calculate amount to burn."""

        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
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
                f"ConditionalTokensContract.get_user_holdings unsuccessful! : {response}"
            )
            return None

        shares = cast(List[int], response.state.body["shares"])
        holdings = cast(List[int], response.state.body["holdings"])

        # Shares to burn
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
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
            performative=ContractApiMessage.Performative.GET_STATE,
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
                int(h * amount_to_remove / total_pool_shares)
                if total_pool_shares > 0
                else 0
                for h in holdings
            ]
        amount_to_merge = min(
            send_amounts_after_removing_funding[i] + shares[i]
            for i in range(len(send_amounts_after_removing_funding))
        )
        return amount_to_remove, amount_to_merge

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            content = yield from self.get_payload()
            payload = RemoveFundingPayload(sender=sender, content=content)
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def get_payload(self) -> Generator[None, None, str]:
        """Get payload."""

        market_to_close = self._get_market_to_close()
        if market_to_close is None:
            self.context.logger.info("No market to close.")
            yield RemoveFundingRound.NO_UPDATE_PAYLOAD
            return

        market = market_to_close["address"]
        self.context.logger.info(f"Closing market: {market}")

        amounts = yield from self._calculate_amounts(
            market=market_to_close["address"],
            condition_id=market_to_close["condition_id"],
            outcome_slot_count=market_to_close["outcome_slot_count"],
        )
        if amounts is None:
            yield RemoveFundingRound.NO_UPDATE_PAYLOAD
            return

        amount_to_remove, amount_to_merge = amounts
        self.context.logger.info(f"Amount to remove: {amount_to_remove}")
        self.context.logger.info(f"Amount to merge: {amount_to_merge}")
        remove_funding_tx = yield from self._get_remove_funding_tx(
            address=market, amount_to_remove=amount_to_remove
        )
        if remove_funding_tx is None:
            yield RemoveFundingRound.ERROR_PAYLOAD
            return

        merge_positions_tx = yield from self._get_merge_positions_tx(
            collateral_token=self.params.collateral_tokens_contract,
            parent_collection_id=ZERO_HASH,
            condition_id=market_to_close["condition_id"],
            outcome_slot_count=market_to_close["outcome_slot_count"],
            amount=amount_to_merge,
        )
        if merge_positions_tx is None:
            yield RemoveFundingRound.ERROR_PAYLOAD
            return

        withdraw_tx = yield from self._get_withdraw_tx(
            amount=amount_to_merge,
        )
        if withdraw_tx is None:
            yield RemoveFundingRound.ERROR_PAYLOAD
            return

        tx_hash = yield from self._to_multisend(
            transactions=[
                remove_funding_tx,
                merge_positions_tx,
                withdraw_tx,
            ]
        )
        if tx_hash is None:
            yield RemoveFundingRound.ERROR_PAYLOAD
            return

        payload_content = {
            "tx": tx_hash,
            "market": market_to_close,
        }
        yield json.dumps(payload_content)

    def _get_market_to_close(self) -> Optional[Dict[str, Any]]:
        """Returns tx data for closing a tx."""
        markets_to_remove_liquidity = self.synchronized_data.markets_to_remove_liquidity
        for market in markets_to_remove_liquidity:
            if market["removal_timestamp"] < self.last_synced_timestamp:
                return market
        return None

    def _get_remove_funding_tx(
        self,
        address: str,
        amount_to_remove: int,
    ) -> Generator[None, None, Optional[Dict]]:
        """This function returns the encoded FPMMContract.removeFunds() function call."""
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

        return {
            "to": address,
            "data": response.state.body["data"],
            "value": ETHER_VALUE,
        }

    def _get_merge_positions_tx(
        self,
        collateral_token: str,
        parent_collection_id: str,
        condition_id: str,
        outcome_slot_count: int,
        amount: int,
    ) -> Generator[None, None, Optional[Dict]]:
        """Prepare a multisend tx for `askQuestionMethod`"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
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
                f"ConditionalTokensContract.build_merge_positions_tx unsuccessful! : {response}"
            )
            return None

        return {
            "to": self.params.conditional_tokens_contract,
            "data": response.state.body["data"],
            "value": ETHER_VALUE,
        }

    def _get_withdraw_tx(self, amount: int) -> Generator[None, None, Optional[Dict]]:
        """Prepare a multisend tx for `askQuestionMethod`"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.conditional_tokens_contract,
            contract_id=str(WxDAIContract.contract_id),
            contract_callable=get_callable_name(WxDAIContract.build_withdraw_tx),
            amount=amount,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"ConditionalTokensContract.build_merge_positions_tx unsuccessful! : {response}"
            )
            return None
        return {
            "to": self.params.collateral_tokens_contract,
            "data": response.state.body["data"],
            "value": ETHER_VALUE,
        }
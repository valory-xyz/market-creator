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

"""This module contains the DepositDaiBehaviour of the 'market_creation_manager_abci' skill."""

from typing import Generator, Optional, cast

from packages.valory.contracts.erc20.contract import ERC20TokenContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.protocols.ledger_api import LedgerApiMessage
from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    MarketCreationManagerBaseBehaviour,
    SAFE_TX_GAS,
    get_callable_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    MultisigTxPayload,
)
from packages.valory.skills.market_creation_manager_abci.rounds import DepositDaiRound
from packages.valory.skills.transaction_settlement_abci.payload_tools import (
    hash_payload_to_hex,
)


class DepositDaiBehaviour(MarketCreationManagerBaseBehaviour):
    """DepositDaiBehaviour"""

    matching_round = DepositDaiRound

    def async_act(self) -> Generator:
        """Implement the act."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            agent = self.context.agent_address
            tx_hash = yield from self.get_tx_hash()
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

    def get_balance(self, address: str) -> Generator[None, None, Optional[int]]:
        """Get the balance of the provided address"""
        ledger_api_response = yield from self.get_ledger_api_response(
            performative=LedgerApiMessage.Performative.GET_STATE,
            ledger_callable="get_balance",
            account=address,
        )
        if ledger_api_response.performative != LedgerApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Couldn't get balance. "
                f"Expected response performative {LedgerApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {ledger_api_response.performative.value}."
            )
            return None
        balance = cast(int, ledger_api_response.state.body.get("get_balance_result"))
        self.context.logger.info(f"balance: {balance / 10 ** 18} xDAI")
        return balance

    def get_tx_hash(self) -> Generator[None, None, Optional[str]]:
        """Get the tx_hash."""
        safe_address = self.synchronized_data.safe_contract_address
        balance = yield from self.get_balance(safe_address)
        if balance is None:
            self.context.logger.error("[DepositDaiBehaviour] Couldn't get balance.")
            return None

        # check if the balance is below the threshold
        if balance <= self.params.xdai_threshold:
            # not enough balance in the safe
            self.context.logger.info("[DepositDaiBehaviour] Balance below threshold.")
            return None

        # leave xdai threshold in the safe for non-market creation purposes of the safe
        balance_to_deposit = balance - self.params.xdai_threshold

        wxdai_address = self.params.collateral_tokens_contract
        tx_data = yield from self._get_deposit_tx(wxdai_address)
        if tx_data is None:
            self.context.logger.error(
                "[DepositDaiBehaviour] _get_deposit_tx() output is None."
            )
            return None

        safe_tx_hash = yield from self._get_safe_tx_hash(
            to_address=wxdai_address, value=balance_to_deposit, data=tx_data
        )
        if safe_tx_hash is None:
            self.context.logger.error(
                "[DepositDaiBehaviour] _get_safe_tx_hash() output is None."
            )
            return None

        tx_payload_data = hash_payload_to_hex(
            safe_tx_hash=safe_tx_hash,
            ether_value=balance_to_deposit,
            safe_tx_gas=SAFE_TX_GAS,
            to_address=wxdai_address,
            data=tx_data,
        )
        return tx_payload_data

    def _get_deposit_tx(
        self,
        wxdai_address: str,
    ) -> Generator[None, None, Optional[bytes]]:
        """This function returns the encoded FPMMContract.removeFunds() function call."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_id=str(ERC20TokenContract.contract_id),
            contract_callable=get_callable_name(ERC20TokenContract.build_deposit_tx),
            contract_address=wxdai_address,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Couldn't get tx data for ERC20.build_deposit_tx. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "
                f"received {response.performative.value}."
            )
            return None

        data = cast(bytes, response.state.body["data"])
        return data

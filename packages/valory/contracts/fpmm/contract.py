# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023 valory
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

"""This module contains the scaffold contract definition."""
import logging
from typing import Any, List

from aea.common import JSONLike
from aea.configurations.base import PublicId
from aea.contracts.base import Contract
from aea.crypto.base import LedgerApi

PUBLIC_ID = PublicId.from_str("valory/fpmm:0.1.0")
_logger = logging.getLogger(
    f"aea.packages.{PUBLIC_ID.author}.contracts.{PUBLIC_ID.name}.contract"
)


class FPMMContract(Contract):
    """The scaffold contract class for a smart contract."""

    contract_id = PublicId.from_str("valory/fpmm:0.1.0")

    @classmethod
    def get_raw_transaction(
        cls, ledger_api: LedgerApi, contract_address: str, **kwargs: Any
    ) -> JSONLike:
        """
        Handler method for the 'GET_RAW_TRANSACTION' requests.

        Implement this method in the sub class if you want
        to handle the contract requests manually.

        :param ledger_api: the ledger apis.
        :param contract_address: the contract address.
        :param kwargs: the keyword arguments.
        :return: the tx  # noqa: DAR202
        """
        raise NotImplementedError

    @classmethod
    def get_raw_message(
        cls, ledger_api: LedgerApi, contract_address: str, **kwargs: Any
    ) -> bytes:
        """
        Handler method for the 'GET_RAW_MESSAGE' requests.

        Implement this method in the sub class if you want
        to handle the contract requests manually.

        :param ledger_api: the ledger apis.
        :param contract_address: the contract address.
        :param kwargs: the keyword arguments.
        :return: the tx  # noqa: DAR202
        """
        raise NotImplementedError

    @classmethod
    def get_state(
        cls, ledger_api: LedgerApi, contract_address: str, **kwargs: Any
    ) -> JSONLike:
        """
        Handler method for the 'GET_STATE' requests.

        Implement this method in the sub class if you want
        to handle the contract requests manually.

        :param ledger_api: the ledger apis.
        :param contract_address: the contract address.
        :param kwargs: the keyword arguments.
        :return: the tx  # noqa: DAR202
        """
        raise NotImplementedError

    @classmethod
    def build_remove_funding_tx(cls, ledger_api: LedgerApi, contract_address: str, **kwargs: Any) -> JSONLike:
        """Build removeFunding tx."""
        instance = cls.get_instance(ledger_api, contract_address)
        # remove everything
        amount = instance.functions.totalSupply().call()
        data = instance.encodeABI(
            fn_name="removeFunding",
            args=[
                amount,
            ],
        )
        return dict(
            data=data,
        )
    @classmethod
    def get_markets_with_funds(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        markets: List[str],
        **kwargs: Any,
    ) -> JSONLike:
        """Get markets with funds."""
        markets_with_liq = []
        # TODO: improve this by introducing multicall2 or constructor trick
        for market_address in markets:
            try:
                instance = cls.get_instance(ledger_api, market_address)
                total_supply = instance.functions.totalSupply().call()
                if total_supply > 0:
                    markets_with_liq.append(market_address)
            except Exception as e:
                _logger.warning(f"Error while getting totalSupply for {market_address}: {e}")

        return dict(data=markets_with_liq)

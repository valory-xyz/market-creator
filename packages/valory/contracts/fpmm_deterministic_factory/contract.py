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

import math
import random
from typing import Any

from aea.common import JSONLike
from aea.configurations.base import PublicId
from aea.contracts.base import Contract
from aea.crypto.base import LedgerApi


DEFAULT_MARKET_FEE = 2.0

CONDIOTIONAL_TOKENS_XDAI = "0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce"
WXDAI_TOKEN = "0xe91d153e0b41518a2ce8dd3d7944fa863463a97d"  # as collateral tokens


class FPMMDeterministicFactory(Contract):
    """The scaffold contract class for a smart contract."""

    contract_id = PublicId.from_str("valory/fpmm_deterministic_factory:0.1.0")

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
    def create_fpmm_tx(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        condition_id: str,
        initial_funds: int,
        market_fee: float = DEFAULT_MARKET_FEE,
    ) -> JSONLike:
        """Create FPMM tx"""
        kwargs = {
            "saltNonce": random.randint(
                0, 1000000
            ),  # https://github.com/protofire/omen-exchange/blob/923756c3a9ac370f8e89af8193393a53531e2c0f/app/src/services/cpk/fns.ts#L942
            "conditionalTokens": CONDIOTIONAL_TOKENS_XDAI,
            "collateralToken": WXDAI_TOKEN,
            "conditionIds": [condition_id],
            "fee": ledger_api.api.to_wei(
                number=market_fee / math.pow(10, 2),
                unit="ether",
            ),
            "initialFunds": initial_funds,
            "distributionHint": [],
        }
        return ledger_api.build_transaction(
            contract_instance=cls.get_instance(
                ledger_api=ledger_api, contract_address=contract_address
            ),
            method_name="create2FixedProductMarketMaker",
            method_args=kwargs,
        )

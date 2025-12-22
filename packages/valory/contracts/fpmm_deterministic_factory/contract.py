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

"""This module contains the class to connect to a Gnosis FPMMDeterministicFactory contract."""
import logging
import math
import random
from typing import Any, List, Optional, Sequence, Union

from aea.common import JSONLike
from aea.configurations.base import PublicId
from aea.contracts.base import Contract
from aea.crypto.base import LedgerApi
from eth_utils import event_abi_to_log_topic
from web3._utils.events import get_event_data
from web3.contract import Contract as W3Contract
from web3.eth import Eth
from web3.types import ABIEvent, BlockIdentifier, FilterParams, LogReceipt, _Hash32


DEFAULT_MARKET_FEE = 2.0

PUBLIC_ID = PublicId.from_str("valory/fpmm_deterministic_factory:0.1.0")

_logger = logging.getLogger(
    f"aea.packages.{PUBLIC_ID.author}.contracts.{PUBLIC_ID.name}.contract"
)


def get_logs(
    eth: Eth,
    contract_instance: W3Contract,
    event_abi: ABIEvent,
    topics: List[Optional[Union[_Hash32, Sequence[_Hash32]]]],
    from_block: BlockIdentifier = "earliest",
    to_block: BlockIdentifier = "latest",
) -> List[LogReceipt]:
    """Helper method to extract the events."""
    event_topic = event_abi_to_log_topic(event_abi)
    topics.insert(0, event_topic)

    filter_params: FilterParams = {
        "fromBlock": from_block,
        "toBlock": to_block,
        "address": contract_instance.address,
        "topics": topics,
    }

    return eth.get_logs(filter_params)


class FPMMDeterministicFactory(Contract):
    """The Gnosis FPMMDeterministicFactory contract."""

    contract_id = PUBLIC_ID

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
    def get_create_fpmm_tx(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        condition_id: str,
        conditional_tokens: str,
        collateral_token: str,
        initial_funds: float,
        market_fee: float = DEFAULT_MARKET_FEE,
    ) -> JSONLike:
        """Create FPMM tx"""
        kwargs = {
            "saltNonce": random.randint(  # nosec
                0, 1000000
            ),  # https://github.com/protofire/omen-exchange/blob/923756c3a9ac370f8e89af8193393a53531e2c0f/app/src/services/cpk/fns.ts#L942
            "conditionalTokens": ledger_api.api.to_checksum_address(conditional_tokens),
            "collateralToken": ledger_api.api.to_checksum_address(collateral_token),
            "conditionIds": [condition_id],
            "fee": ledger_api.api.to_wei(
                number=market_fee / math.pow(10, 2),
                unit="ether",
            ),
            "initialFunds": ledger_api.api.to_wei(
                number=initial_funds / math.pow(10, 2),
                unit="ether",
            ),
            "distributionHint": [],
        }
        return ledger_api.build_transaction(
            contract_instance=cls.get_instance(
                ledger_api=ledger_api, contract_address=contract_address
            ),
            method_name="create2FixedProductMarketMaker",
            method_args=kwargs,
        )

    @classmethod
    def get_create_fpmm_tx_data(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        condition_id: str,
        conditional_tokens: str,
        collateral_token: str,
        initial_funds: float,
        market_fee: float = DEFAULT_MARKET_FEE,
    ) -> JSONLike:
        """Create FPMM tx"""
        initial_funds = ledger_api.api.to_wei(
            number=initial_funds / math.pow(10, 2),
            unit="ether",
        )
        kwargs = {
            "saltNonce": random.randint(  # nosec
                0, 1000000
            ),  # https://github.com/protofire/omen-exchange/blob/923756c3a9ac370f8e89af8193393a53531e2c0f/app/src/services/cpk/fns.ts#L942
            "conditionalTokens": ledger_api.api.to_checksum_address(conditional_tokens),
            "collateralToken": ledger_api.api.to_checksum_address(collateral_token),
            "conditionIds": [condition_id],
            "fee": ledger_api.api.to_wei(
                number=market_fee / math.pow(10, 2),
                unit="ether",
            ),
            "initialFunds": initial_funds,
            "distributionHint": [],
        }
        contract_instance = cls.get_instance(
            ledger_api=ledger_api, contract_address=contract_address
        )
        data = contract_instance.encodeABI(
            fn_name="create2FixedProductMarketMaker", kwargs=kwargs
        )
        return {"data": bytes.fromhex(data[2:]), "value": initial_funds}

    @classmethod
    def get_market_creation_events(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        creator_address: str,
        from_block: BlockIdentifier = "earliest",
        to_block: BlockIdentifier = "latest",
    ) -> JSONLike:
        """Get market creation"""
        eth = ledger_api.api.eth
        contract_instance = cls.get_instance(
            ledger_api=ledger_api, contract_address=contract_address
        )
        event_abi = contract_instance.events.FixedProductMarketMakerCreation().abi
        topics: List[Union[Any, Sequence[Any], None]] = [
            "0x" + creator_address.lower()[2:].rjust(64, "0"),
        ]

        logs = get_logs(eth, contract_instance, event_abi, topics, from_block, to_block)

        entries = [get_event_data(eth.codec, event_abi, log) for log in logs]
        events = [
            {
                "tx_hash": entry["transactionHash"].hex(),
                "block_number": entry["blockNumber"],
                "condition_ids": entry["args"]["conditionIds"],
                "collateral_token": entry["args"]["collateralToken"],
                "conditional_tokens": entry["args"]["conditionalTokens"],
                "fixed_product_market_maker": entry["args"]["fixedProductMarketMaker"],
                "fee": entry["args"]["fee"],
            }
            for entry in entries
        ]

        return {"data": events}

    @classmethod
    def parse_market_creation_event(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        tx_hash: str,
    ) -> JSONLike:
        """Parse market creation"""
        contract = cls.get_instance(
            ledger_api=ledger_api, contract_address=contract_address
        )
        receipt = ledger_api.api.eth.get_transaction_receipt(tx_hash)
        logs = contract.events.FixedProductMarketMakerCreation().process_receipt(
            receipt
        )
        event = logs[0]
        data = dict(
            tx_hash=tx_hash,
            block_number=event.blockNumber,
            condition_ids=event["args"]["conditionIds"],
            collateral_token=event["args"]["collateralToken"],
            conditional_tokens=event["args"]["conditionalTokens"],
            fixed_product_market_maker=event["args"]["fixedProductMarketMaker"],
            fee=event["args"]["fee"],
        )
        return dict(data=data)

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

BATCH_TOTAL_SUPPLY_DATA = {
    "abi": [
        {
            "inputs": [
                {
                    "internalType": "address[]",
                    "name": "_markets",
                    "type": "address[]"
                }
            ],
            "stateMutability": "nonpayable",
            "type": "constructor"
        }
    ],
    "bytecode": "0x608060405234801561001057600080fd5b5060405161069b38038061069b83398181016040528101906100329190610468565b60008151905060008167ffffffffffffffff811115610054576100536102c7565b5b6040519080825280602002602001820160405280156100825781602001602082028036833780820191505090505b5090506000805b838110156101a25760008582815181106100a6576100a56104b1565b5b602002602001015173ffffffffffffffffffffffffffffffffffffffff166318160ddd6040518163ffffffff1660e01b8152600401602060405180830381865afa1580156100f8573d6000803e3d6000fd5b505050506040513d601f19601f8201168201806040525081019061011c9190610516565b111561019757848181518110610135576101346104b1565b5b60200260200101518383815181106101505761014f6104b1565b5b602002602001019073ffffffffffffffffffffffffffffffffffffffff16908173ffffffffffffffffffffffffffffffffffffffff16815250508161019490610572565b91505b806001019050610089565b5060008167ffffffffffffffff8111156101bf576101be6102c7565b5b6040519080825280602002602001820160405280156101ed5781602001602082028036833780820191505090505b50905060005b8281101561026e5783818151811061020e5761020d6104b1565b5b6020026020010151828281518110610229576102286104b1565b5b602002602001019073ffffffffffffffffffffffffffffffffffffffff16908173ffffffffffffffffffffffffffffffffffffffff16815250508060010190506101f3565b506000816040516020016102829190610678565b60405160208183030381529060405290506020810180590381f35b6000604051905090565b600080fd5b600080fd5b600080fd5b6000601f19601f8301169050919050565b7f4e487b7100000000000000000000000000000000000000000000000000000000600052604160045260246000fd5b6102ff826102b6565b810181811067ffffffffffffffff8211171561031e5761031d6102c7565b5b80604052505050565b600061033161029d565b905061033d82826102f6565b919050565b600067ffffffffffffffff82111561035d5761035c6102c7565b5b602082029050602081019050919050565b600080fd5b600073ffffffffffffffffffffffffffffffffffffffff82169050919050565b600061039e82610373565b9050919050565b6103ae81610393565b81146103b957600080fd5b50565b6000815190506103cb816103a5565b92915050565b60006103e46103df84610342565b610327565b905080838252602082019050602084028301858111156104075761040661036e565b5b835b81811015610430578061041c88826103bc565b845260208401935050602081019050610409565b5050509392505050565b600082601f83011261044f5761044e6102b1565b5b815161045f8482602086016103d1565b91505092915050565b60006020828403121561047e5761047d6102a7565b5b600082015167ffffffffffffffff81111561049c5761049b6102ac565b5b6104a88482850161043a565b91505092915050565b7f4e487b7100000000000000000000000000000000000000000000000000000000600052603260045260246000fd5b6000819050919050565b6104f3816104e0565b81146104fe57600080fd5b50565b600081519050610510816104ea565b92915050565b60006020828403121561052c5761052b6102a7565b5b600061053a84828501610501565b91505092915050565b7f4e487b7100000000000000000000000000000000000000000000000000000000600052601160045260246000fd5b600061057d826104e0565b91507fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff82036105af576105ae610543565b5b600182019050919050565b600081519050919050565b600082825260208201905092915050565b6000819050602082019050919050565b6105ef81610393565b82525050565b600061060183836105e6565b60208301905092915050565b6000602082019050919050565b6000610625826105ba565b61062f81856105c5565b935061063a836105d6565b8060005b8381101561066b57815161065288826105f5565b975061065d8361060d565b92505060018101905061063e565b5085935050505092915050565b60006020820190508181036000830152610692818461061a565b90509291505056fe",
}


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
    def get_balance(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        address: str,
        **kwargs: Any,
    ) -> JSONLike:
        """Build remove tx."""
        instance = cls.get_instance(
            ledger_api=ledger_api, contract_address=contract_address
        )
        return dict(
            balance=instance.functions.balanceOf(
                ledger_api.api.to_checksum_address(address)
            ).call()
        )

    @classmethod
    def get_total_supply(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        **kwargs: Any,
    ) -> JSONLike:
        """Build remove tx."""
        instance = cls.get_instance(
            ledger_api=ledger_api, contract_address=contract_address
        )
        return dict(supply=instance.functions.totalSupply().call())

    @classmethod
    def build_remove_funding_tx(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        amount_to_remove: int,
        **kwargs: Any,
    ) -> JSONLike:
        """Build removeFunding tx."""
        instance = cls.get_instance(ledger_api, contract_address)
        # remove everything
        data = instance.encodeABI(
            fn_name="removeFunding",
            args=[
                amount_to_remove,
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
        """Get the markets with funds."""
        # BatchTotalSupply contract is a special contract used specifically for checking getting markets with funds
        # It is not deployed anywhere, nor it needs to be deployed
        batch_workable_contract = ledger_api.api.eth.contract(
            abi=BATCH_TOTAL_SUPPLY_DATA["abi"], bytecode=BATCH_TOTAL_SUPPLY_DATA["bytecode"]
        )

        # Encode the input data (constructor params)
        encoded_input_data = ledger_api.api.codec.encode_abi(
            ["address[]"], [markets]
        )

        # Concatenate the bytecode with the encoded input data to create the contract creation code
        contract_creation_code = batch_workable_contract.bytecode + encoded_input_data

        # Call the function with the contract creation code
        # Note that we are not sending any transaction, we are just calling the function
        # This is a special contract creation code that will return some result
        encoded_markets = ledger_api.api.eth.call({"data": contract_creation_code})

        # Decode the response raw response
        # the decoding returns a Tuple with a single element so we need to access the first element of the tuple,
        # which contains a tuple of markets that have funds
        non_zero_markets = [
            ledger_api.api.toChecksumAddress(market_address)
            for market_address in ledger_api.api.codec.decode_abi(["address[]"], encoded_markets)[0]
        ]
        return dict(data=non_zero_markets)

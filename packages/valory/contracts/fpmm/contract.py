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

"""This module contains the class to connect to an Gnosis FixedProductMarketMaker contract."""
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
                },
                {
                    "internalType": "address",
                    "name": "safeAddress",
                    "type": "address"
                }
            ],
            "stateMutability": "nonpayable",
            "type": "constructor"
        }
    ],
    "bytecode": "0x608060405234801561001057600080fd5b506040516106e33803806106e383398181016040528101906100329190610473565b60008251905060008167ffffffffffffffff811115610054576100536102d2565b5b6040519080825280602002602001820160405280156100825781602001602082028036833780820191505090505b5090506000805b838110156101ad5760008682815181106100a6576100a56104cf565b5b602002602001015173ffffffffffffffffffffffffffffffffffffffff166370a08231876040518263ffffffff1660e01b81526004016100e6919061050d565b602060405180830381865afa158015610103573d6000803e3d6000fd5b505050506040513d601f19601f82011682018060405250810190610127919061055e565b11156101a2578581815181106101405761013f6104cf565b5b602002602001015183838151811061015b5761015a6104cf565b5b602002602001019073ffffffffffffffffffffffffffffffffffffffff16908173ffffffffffffffffffffffffffffffffffffffff16815250508161019f906105ba565b91505b806001019050610089565b5060008167ffffffffffffffff8111156101ca576101c96102d2565b5b6040519080825280602002602001820160405280156101f85781602001602082028036833780820191505090505b50905060005b8281101561027957838181518110610219576102186104cf565b5b6020026020010151828281518110610234576102336104cf565b5b602002602001019073ffffffffffffffffffffffffffffffffffffffff16908173ffffffffffffffffffffffffffffffffffffffff16815250508060010190506101fe565b5060008160405160200161028d91906106c0565b60405160208183030381529060405290506020810180590381f35b6000604051905090565b600080fd5b600080fd5b600080fd5b6000601f19601f8301169050919050565b7f4e487b7100000000000000000000000000000000000000000000000000000000600052604160045260246000fd5b61030a826102c1565b810181811067ffffffffffffffff82111715610329576103286102d2565b5b80604052505050565b600061033c6102a8565b90506103488282610301565b919050565b600067ffffffffffffffff821115610368576103676102d2565b5b602082029050602081019050919050565b600080fd5b600073ffffffffffffffffffffffffffffffffffffffff82169050919050565b60006103a98261037e565b9050919050565b6103b98161039e565b81146103c457600080fd5b50565b6000815190506103d6816103b0565b92915050565b60006103ef6103ea8461034d565b610332565b9050808382526020820190506020840283018581111561041257610411610379565b5b835b8181101561043b578061042788826103c7565b845260208401935050602081019050610414565b5050509392505050565b600082601f83011261045a576104596102bc565b5b815161046a8482602086016103dc565b91505092915050565b6000806040838503121561048a576104896102b2565b5b600083015167ffffffffffffffff8111156104a8576104a76102b7565b5b6104b485828601610445565b92505060206104c5858286016103c7565b9150509250929050565b7f4e487b7100000000000000000000000000000000000000000000000000000000600052603260045260246000fd5b6105078161039e565b82525050565b600060208201905061052260008301846104fe565b92915050565b6000819050919050565b61053b81610528565b811461054657600080fd5b50565b60008151905061055881610532565b92915050565b600060208284031215610574576105736102b2565b5b600061058284828501610549565b91505092915050565b7f4e487b7100000000000000000000000000000000000000000000000000000000600052601160045260246000fd5b60006105c582610528565b91507fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff82036105f7576105f661058b565b5b600182019050919050565b600081519050919050565b600082825260208201905092915050565b6000819050602082019050919050565b6106378161039e565b82525050565b6000610649838361062e565b60208301905092915050565b6000602082019050919050565b600061066d82610602565b610677818561060d565b93506106828361061e565b8060005b838110156106b357815161069a888261063d565b97506106a583610655565b925050600181019050610686565b5085935050505092915050565b600060208201905081810360008301526106da8184610662565b90509291505056fe",
}


class FPMMContract(Contract):
    """The Gnosis FixedProductMarketMaker contract."""

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
        safe_address: str,
        **kwargs: Any,
    ) -> JSONLike:
        try: 
            """Get the markets with funds."""
            # BatchTotalSupply contract is a special contract used specifically for checking getting markets with funds
            # It is not deployed anywhere, nor it needs to be deployed
            batch_workable_contract = ledger_api.api.eth.contract(
                abi=BATCH_TOTAL_SUPPLY_DATA["abi"], bytecode=BATCH_TOTAL_SUPPLY_DATA["bytecode"]
            )

            # Encode the input data (constructor params)
            encoded_input_data = ledger_api.api.codec.encode(
                ["address[]", "address"], [markets, safe_address]
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
                ledger_api.api.to_checksum_address(market_address)
                for market_address in ledger_api.api.codec.decode(["address[]"], encoded_markets)[0]
            ]

            _logger.info(f"Markets with non-zero funds retrieved: {non_zero_markets}")
        except Exception as e:
            _logger.error("An exception occurred in get_markets_with_funds():", str(e))

        return dict(data=non_zero_markets)

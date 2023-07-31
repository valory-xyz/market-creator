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

from typing import Any, List

from aea.common import JSONLike
from aea.configurations.base import PublicId
from aea.contracts.base import Contract
from aea.crypto.base import LedgerApi
from web3.types import BlockIdentifier


DEFAULT_OUTCOME_SLOT = 2


class ConditionalTokensContract(Contract):
    """The scaffold contract class for a smart contract."""

    contract_id = PublicId.from_str("valory/conditional_tokens:0.1.0")

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
    def get_prepare_condition_tx(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        question_id: str,
        oracle_contract: str,
        outcome_slot_count: int = DEFAULT_OUTCOME_SLOT,
    ) -> JSONLike:
        """Tx for preparing condition for marker maker."""
        kwargs = {
            "oracle": ledger_api.api.to_checksum_address(oracle_contract),
            "questionId": question_id,
            "outcomeSlotCount": outcome_slot_count,
        }
        return ledger_api.build_transaction(
            contract_instance=cls.get_instance(
                ledger_api=ledger_api, contract_address=contract_address
            ),
            method_name="prepareCondition",
            method_args=kwargs,
        )

    @classmethod
    def get_prepare_condition_tx_data(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        question_id: str,
        oracle_contract: str,
        outcome_slot_count: int = DEFAULT_OUTCOME_SLOT,
    ) -> JSONLike:
        """Tx for preparing condition for marker maker."""
        kwargs = {
            "oracle": ledger_api.api.to_checksum_address(oracle_contract),
            "questionId": question_id,
            "outcomeSlotCount": outcome_slot_count,
        }
        contract_instance = cls.get_instance(
            ledger_api=ledger_api, contract_address=contract_address
        )
        data = contract_instance.encodeABI(fn_name="prepareCondition", kwargs=kwargs)
        return {"data": bytes.fromhex(data[2:])}

    @classmethod
    def calculate_condition_id(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        oracle_contract: str,
        question_id: str,
        outcome_slot_count: int,
    ) -> str:
        """Calculate condition ID."""
        return {
            "condition_id": ledger_api.api.solidity_keccak(
                ["address", "bytes32", "uint256"],
                [
                    ledger_api.api.to_checksum_address(oracle_contract),
                    bytes.fromhex(question_id[2:]),
                    outcome_slot_count,
                ],
            ).hex()
        }

    @classmethod
    def get_condition_id(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        tx_digest: str,  # retrieved from `prepareCondition` tx
    ) -> JSONLike:
        """Tx for preparing condition for marker maker."""
        contract_instance = cls.get_instance(
            ledger_api=ledger_api, contract_address=contract_address
        )
        tx_receipt = ledger_api.api.eth.getTransactionReceipt(tx_digest)
        (log,) = contract_instance.events.ConditionPreparation().processReceipt(
            tx_receipt
        )
        return "0x" + log["args"]["conditionId"].hex()

    @classmethod
    def get_condition_preparation_events(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        condition_ids: List[bytes],
        from_block: BlockIdentifier = "earliest",
        to_block: BlockIdentifier = "latest",
    ) -> JSONLike:
        """Get condition preparation events."""
        contract_instance = cls.get_instance(
            ledger_api=ledger_api, contract_address=contract_address
        )
        entries = (
            contract_instance.events.ConditionPreparation()
            .createFilter(
                fromBlock=from_block,
                toBlock=to_block,
                argument_filters={
                    "conditionId": condition_ids,
                },
            )
            .get_all_entries()
        )
        events = list(
            dict(
                tx_hash=entry.transactionHash.hex(),
                block_number=entry.blockNumber,
                condition_id=entry["args"]["conditionId"],
                oracle=entry["args"]["oracle"],
                question_id=entry["args"]["questionId"],
                outcome_slot_count=entry["args"]["outcomeSlotCount"],
            )
            for entry in entries
        )
        return dict(data=events)

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
from typing_extensions import TypedDict


MARKET_FEE = 2.0
UNIT_SEPARATOR = "␟"

KLEROS_BRIDGE_XDAI = "0xe40dd83a262da3f56976038f1554fe541fa75ecd"


class QuestionData(TypedDict):
    """Question data."""

    question: str
    answers: List[str]
    topic: str
    language: str


def format_answers(answers: List[str]) -> str:
    """Format answers."""
    return ",".join(map(lambda x: '"' + x + '"', answers))


def build_question(question_data: QuestionData) -> str:
    """Build question."""
    return UNIT_SEPARATOR.join(
        [
            question_data["question"],
            format_answers(question_data["answers"]),
            question_data["topic"],
            question_data["language"],
        ]
    )


class RealtioContract(Contract):
    """The scaffold contract class for a smart contract."""

    contract_id = PublicId.from_str("valory/realtio:0.1.0")

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
    def get_ask_question_tx(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        question_data: QuestionData,
        opening_timestamp: int,
        timeout: int,
        template_id: int = 2,
        question_nonce: int = 0,
    ) -> JSONLike:
        """Get ask question transaction."""
        question = build_question(question_data=question_data)
        kwargs = {
            "template_id": template_id,
            "question": question,
            "arbitrator": ledger_api.api.to_checksum_address(KLEROS_BRIDGE_XDAI),
            "timeout": timeout,
            "opening_ts": opening_timestamp,
            "nonce": question_nonce,
        }
        return ledger_api.build_transaction(
            contract_instance=cls.get_instance(
                ledger_api=ledger_api, contract_address=contract_address
            ),
            method_name="askQuestion",
            method_args=kwargs,
        )

    @classmethod
    def get_ask_question_tx_data(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        question_data: QuestionData,
        opening_timestamp: int,
        timeout: int,
        template_id: int = 2,
        question_nonce: int = 0,
    ) -> JSONLike:
        """Get ask question transaction."""
        question = build_question(question_data=question_data)
        kwargs = {
            "template_id": template_id,
            "question": question,
            "arbitrator": ledger_api.api.to_checksum_address(
                KLEROS_BRIDGE_XDAI
            ),  # TODO: Make configurable
            "timeout": timeout,
            "opening_ts": opening_timestamp,
            "nonce": question_nonce,
        }
        contract_instance = cls.get_instance(
            ledger_api=ledger_api, contract_address=contract_address
        )
        data = contract_instance.encodeABI(fn_name="askQuestion", kwargs=kwargs)
        return {"data": bytes.fromhex(data[2:])}  # type: ignore

    @classmethod
    def calculate_question_id(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        question_data: QuestionData,
        opening_timestamp: int,
        timeout: int,
        sender: str,
        template_id: int = 2,
        question_nonce: int = 0,
    ) -> JSONLike:
        """Get ask question transaction."""
        question = build_question(question_data=question_data)
        content_hash = ledger_api.api.solidity_keccak(
            ["uint256", "uint32", "string"],
            [template_id, opening_timestamp, question],
        )
        question_id = ledger_api.api.solidity_keccak(
            ["bytes32", "address", "uint32", "address", "uint256"],
            [
                content_hash,
                ledger_api.api.to_checksum_address(
                    KLEROS_BRIDGE_XDAI
                ),  # TODO: make configurable
                timeout,
                ledger_api.api.to_checksum_address(sender),
                question_nonce,
            ],
        )
        return {"question_id": question_id.hex()}

# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023 Valory AG
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

"""A script to create a prediction market."""

import json
import math
import random
import time
from datetime import datetime
from pathlib import Path

from aea_ledger_ethereum.ethereum import EthereumApi, EthereumCrypto
from typing_extensions import TypedDict
from typing import List

REALTIO_XDAI = "0x79e32aE03fb27B07C89c0c568F80287C01ca2E57"
KLEROS_BRIDGE_XDAI = "0xe40dd83a262da3f56976038f1554fe541fa75ecd"
CONDIOTIONAL_TOKENS_XDAI = "0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce"
ORACLE_XDAI = "0xab16d643ba051c11962da645f74632d3130c81e2"
FPMM_DETERMINISTIC_FACTORY = "0x9083A2B699c0a4AD06F63580BDE2635d26a3eeF0"
WXDAI_TOKEN = "0xe91d153e0b41518a2ce8dd3d7944fa863463a97d"  # as collateral tokens

UNIT_SEPARATOR = "␟"

MARKET_FEE = 2.0

crypto = EthereumCrypto(  # 0xf33BB476529e93Bb862262f6C6D8Cc324741d7aA
    Path.home() / "gnosis_key"
)
ledger_api = EthereumApi(
    address="https://rpc.gnosischain.com",
    chain_id=100,
    poa_chain=False,
    default_gas_price_strategy="eip1559",
)
realtio_contract = ledger_api.api.eth.contract(
    address=REALTIO_XDAI,
    abi=json.loads(
        Path("temp", "Realtio.json").read_text(),
    )["abi"],
)
conditional_tokens_contract = ledger_api.api.eth.contract(
    address=CONDIOTIONAL_TOKENS_XDAI,
    abi=json.loads(
        Path("temp", "ConditionalTokens.json").read_text(),
    )["abi"],
)
fpmm_deterministic_factory_contract = ledger_api.api.eth.contract(
    address=FPMM_DETERMINISTIC_FACTORY,
    abi=json.loads(
        Path("temp", "FPMMDeterministicFactory.json").read_text(),
    )["abi"],
)


class QuestionData(TypedDict):
    """Question data."""

    question: str
    answers: List[str]
    topic: str
    language: str


def send_tx(tx: dict) -> str:
    """Send tx."""
    gtx = ledger_api.update_with_gas_estimate(transaction=tx)
    stx = crypto.sign_transaction(transaction=gtx)
    return ledger_api.send_signed_transaction(
        tx_signed=stx,
        raise_on_try=True,
    )


def format_answers(answers: List[str]) -> str:
    """Format answers."""
    return ",".join(map(lambda x: f'"{x}"', answers))


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


question_data = QuestionData(
    {
        "question": "Who will win the 5th test in the ongoing ashes series?",
        "answers": ["ENG", "AUD"],
        "topic": "news-politics",
        "language": "en_US",
    }
)
question = build_question(question_data=question_data)
now = datetime.now()
opening_ts = int(
    datetime(
        year=now.year,
        month=now.month,
        day=(now.day + 7),
    ).timestamp()
)
kwargs = {
    "template_id": 2,
    "question": question,
    "arbitrator": ledger_api.api.to_checksum_address(KLEROS_BRIDGE_XDAI),
    "timeout": 86400,  # TODO: make dynamic
    "opening_ts": opening_ts,  # TODO: make dynamic
    "nonce": 0,
}
question_id = "0x" + realtio_contract.functions.askQuestion(**kwargs).call().hex()
tx = ledger_api.build_transaction(
    contract_instance=realtio_contract,
    method_name="askQuestion",
    method_args=kwargs,
    tx_args={
        "sender_address": crypto.address,
    },
)
ask_question_tx_digest = send_tx(tx=tx)
print(f"{ask_question_tx_digest=}")
time.sleep(30)

tx_receipt = ledger_api.api.eth.getTransactionReceipt(ask_question_tx_digest)
(ask_question_log,) = realtio_contract.events.LogNewQuestion().processReceipt(
    tx_receipt
)
question_id = "0x" + ask_question_log["args"]["question_id"].hex()
print(f"Created question with ID {question_id}")

kwargs = {
    "oracle": ledger_api.api.to_checksum_address(ORACLE_XDAI),
    "questionId": question_id,
    "outcomeSlotCount": 2,  # TODO: find out how is this calculated
}
tx = ledger_api.build_transaction(
    contract_instance=conditional_tokens_contract,
    method_name="prepareCondition",
    method_args=kwargs,
    tx_args={
        "sender_address": crypto.address,
    },
)
prepare_condition_tx_digest = send_tx(tx=tx)
print(f"{prepare_condition_tx_digest=}")
time.sleep(15)

tx_receipt = ledger_api.api.eth.getTransactionReceipt(prepare_condition_tx_digest)
(
    condition_preparation_log,
) = conditional_tokens_contract.events.ConditionPreparation().processReceipt(tx_receipt)
condition_id = "0x" + condition_preparation_log["args"]["conditionId"].hex()
fee = ledger_api.api.to_wei(
    number=MARKET_FEE / math.pow(10, 2),
    unit="ether",
)
kwargs = {
    "saltNonce": random.randint(
        0, 1000000
    ),  # https://github.com/protofire/omen-exchange/blob/923756c3a9ac370f8e89af8193393a53531e2c0f/app/src/services/cpk/fns.ts#L942
    "conditionalTokens": CONDIOTIONAL_TOKENS_XDAI,
    "collateralToken": WXDAI_TOKEN,
    "conditionIds": [condition_id],
    "fee": fee,
    "initialFunds": 0,
    "distributionHint": [],
}
tx = ledger_api.build_transaction(
    contract_instance=fpmm_deterministic_factory_contract,
    method_name="create2FixedProductMarketMaker",
    method_args=kwargs,
    tx_args={
        "sender_address": crypto.address,
    },
)
create_market_maker_data = send_tx(tx=tx)
print(f"{create_market_maker_data=}")

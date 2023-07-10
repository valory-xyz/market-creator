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
from pathlib import Path

from aea_ledger_ethereum.ethereum import EthereumApi, EthereumCrypto


REALTIO_XDAI = "0x79e32aE03fb27B07C89c0c568F80287C01ca2E57"
KLEROS_BRIDGE_XDAI = "0xe40dd83a262da3f56976038f1554fe541fa75ecd"
CONDIOTIONAL_TOKENS_XDAI = "0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce"

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

kwargs = {
    "template_id": 2,
    "question": "A test question",
    "arbitrator": ledger_api.api.to_checksum_address(KLEROS_BRIDGE_XDAI),
    "timeout": 86400,  # TODO: make dynamic
    "opening_ts": 1688515200,  # TODO: make dynamic
    "nonce": 0,
}

question_id = realtio_contract.functions.askQuestion(**kwargs).call()
question_id = f"0x{question_id.hex()}"

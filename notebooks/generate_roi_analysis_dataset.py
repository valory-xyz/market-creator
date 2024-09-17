#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2024 Valory AG
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

"""Generates dataset for trader analysis"""

# pylint: disable=wrong-import-position,protected-access
# noqa: E402

import argparse
import bisect
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import requests
from dotenv import dotenv_values
from web3 import Web3


SCRIPT_PATH = Path(__file__).resolve().parent
DOTENV_PATH = Path(SCRIPT_PATH, ".env")

env_file_vars = dotenv_values(DOTENV_PATH)
trader_quickstart_path = env_file_vars.get("TRADER_QUICKSTART_PATH")

sys.path.insert(0, "../scripts")
sys.path.insert(0, os.path.expanduser(trader_quickstart_path))
sys.path.insert(0, os.path.expanduser(f"{trader_quickstart_path}/scripts"))

import trades
from mech_request_utils import get_mech_requests
from trades import INVALID_ANSWER, MarketState, TradeResult


RPC = env_file_vars.get("RPC")
SERVICE_REGISTRY_ADDRESS = "0x9338b5153AE39BB89f50468E608eD9d764B755fD"
DATASET_PREFIX = "roi_analysis_dataset_"


def _get_contract(address: str) -> Any:
    w3 = Web3(Web3.HTTPProvider(RPC))
    abi = _get_abi(address)
    contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)
    return contract


def _get_abi(address: str) -> List:
    contract_abi_url = (
        "https://gnosis.blockscout.com/api/v2/smart-contracts/{contract_address}"
    )
    response = requests.get(contract_abi_url.format(contract_address=address)).json()

    if "result" in response:
        result = response["result"]
        try:
            abi = json.loads(result)
        except json.JSONDecodeError:
            print("Error: Failed to parse 'result' field as JSON")
            sys.exit(1)
    else:
        abi = response.get("abi")

    return abi if abi else []


def _populate_mech_requests(
    fpmm_trades: Dict[str, Any], mech_requests: Dict[str, Any]
) -> List[str]:
    """Populate each trade in trades_json with the corresponding mech_requests"""

    print("Populating mech requests...")

    # Sort mech requests by timestamp
    dumped_mech_requests = list(mech_requests.values())
    sorted_mech_requests = sorted(
        dumped_mech_requests, key=lambda x: int(x["blockTimestamp"])
    )
    timestamps = [int(x["blockTimestamp"]) for x in sorted_mech_requests]

    # TODO shallow copy for efficiency, be careful
    outstanding_mech_requests = mech_requests.copy()

    for trade in fpmm_trades:
        creation_timestamp = int(trade["creationTimestamp"])

        # Find the mech request immediately before 'creationTimestamp'
        idx = bisect.bisect_left(timestamps, creation_timestamp) - 1
        found = False

        if idx < 0:
            print("ERROR: idx < 0")
            continue

        # Almost always, the corresponding mech request should be the mech
        # request immediately before the trade 'creationTimestamp', which is
        # at position 'idx'. Under some exceptional circumstances, it might
        # be a few positions before (e.g., if the trader was crashed and
        # the mech responded 2 requests on the same block). For this reason,
        # this part of the code searches up to N mech requests before the
        # expected one.
        N = 3
        for i in range(idx, max(0, idx - N), -1):
            mech_request = sorted_mech_requests[i]
            mech_request_id = mech_request["id"]

            if trade["title"] in mech_request["ipfsContents"]["prompt"]:
                trade["mechRequestId"] = mech_request_id
                del outstanding_mech_requests[mech_request_id]
                found = True
                if i != idx:
                    print(
                        f"WARNING: {trade['title']} was not found at idx={idx}, used idx={i} instead."
                    )
                break

        if not found:
            print(
                f"ERROR: {trade['title']} is not found in any mech request up to {N} indices before idx={idx}."
            )
            print(f"{trade['id']=}")

    return list(outstanding_mech_requests.keys())


def _populate_market_states(fpmm_trades: Dict[str, Any]) -> None:
    print("Populating market states...")

    for trade in fpmm_trades:
        fpmm = trade["fpmm"]
        state = trades._get_market_state(fpmm)
        fpmm["state"] = state.value

        if state == MarketState.CLOSED:
            outcome_index = int(trade["outcomeIndex"])
            current_answer = int(fpmm["currentAnswer"], 16)
            if current_answer == INVALID_ANSWER:
                trade["result"] = TradeResult.INVALID.value
            elif current_answer == outcome_index:
                trade["result"] = TradeResult.WIN.value
            else:
                trade["result"] = TradeResult.LOSE.value
        else:
            trade["result"] = TradeResult.UNKNOWN.value


def get_service_safe(service_id: int) -> str:
    """Gets the service Safe"""
    service_registry = _get_contract(SERVICE_REGISTRY_ADDRESS)
    service_safe_address = service_registry.functions.getService(service_id).call()[1]
    return service_safe_address


def generate_dataset(service_id: int) -> (Dict[str, Any], Dict[str, Any], List[str]):
    """Generates the dataset"""
    dataset_json = f"{DATASET_PREFIX}{service_id}.json"

    service_safe_address = get_service_safe(service_id)

    print(f"{service_id=}")
    print(f"{service_safe_address=}")
    print(service_safe_address.lower())

    mech_requests = get_mech_requests(service_safe_address, dataset_json)

    fpmm_trades = trades._query_omen_xdai_subgraph(service_safe_address.lower())[
        "data"
    ]["fpmmTrades"]
    outstanding_mech_request_ids = _populate_mech_requests(fpmm_trades, mech_requests)
    _populate_market_states(fpmm_trades)

    try:
        with open(dataset_json, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    data["fpmmTrades"] = fpmm_trades
    data["outstandingMechRequestIds"] = outstanding_mech_request_ids

    with open(dataset_json, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, sort_keys=True)

    print(f"Finished generating datasets for service {service_id}")
    print("")
    print("Finished reading dataset:")
    print(f"  - {len(fpmm_trades)} trades")
    print(f"  - {len(mech_requests)} mech requests")
    print(f"  - {len(outstanding_mech_request_ids)} outstanding mech requests")

    return fpmm_trades, mech_requests, outstanding_mech_request_ids


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate dataset for a specific service."
    )
    parser.add_argument("service_id", type=int, help="Service ID is required.")
    args = parser.parse_args()
    generate_dataset(args.service_id)

# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2024-2026 Valory AG
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

"""Fetch market creator Safe and owner information from Gnosis Chain."""

from dataclasses import dataclass
from typing import Any, Dict, List, Set

from utils import get_asset_balance, wei_to_unit, web3


NATIVE_TOKEN = "0x0000000000000000000000000000000000000000"

GNOSIS_SAFE_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getOwners",
        "outputs": [{"name": "", "type": "address[]"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "getThreshold",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
]


@dataclass
class MarketCreatorInfo:
    """Information about a market creator."""

    label: str
    safe_contract_address: str
    owners: List[str]
    threshold: int
    balances: Dict[str, Dict[str, float]]  # address -> {token_address -> balance}


def _get_balances(address: str, token_addresses: Set[str]) -> Dict[str, float]:
    """Get balances for a set of token addresses.

    Args:
        address: the wallet address to query
        token_addresses: set of token contract addresses (use NATIVE_TOKEN for native)

    Returns:
        mapping of token_address -> balance in token units
    """
    result = {}
    for token in token_addresses:
        if token == NATIVE_TOKEN:
            result[token] = wei_to_unit(get_asset_balance(address))
        else:
            result[token] = wei_to_unit(get_asset_balance(address, token))
    return result


def get_creator_info(config: Dict[str, Any]) -> MarketCreatorInfo:
    """Get Safe owner and balance info for a market creator.

    Args:
        config: dict with "name", "safe_contract_address", and "thresholds" keys

    Returns:
        MarketCreatorInfo with balances for all tokens referenced in thresholds
    """
    label = config["name"]
    safe_contract_address = config["safe_contract_address"]
    thresholds = config.get("thresholds", {})
    checksum = web3.to_checksum_address(safe_contract_address)
    safe_contract = web3.eth.contract(address=checksum, abi=GNOSIS_SAFE_ABI)

    owner_addresses = safe_contract.functions.getOwners().call()
    sig_threshold = safe_contract.functions.getThreshold().call()

    # Collect all token addresses we need to query
    safe_tokens = set(thresholds.get("safe", {}).keys())
    owner_tokens = set(thresholds.get("owner", {}).keys())

    balances = {}
    balances[safe_contract_address.lower()] = _get_balances(safe_contract_address, safe_tokens)
    for owner in owner_addresses:
        balances[owner.lower()] = _get_balances(owner, owner_tokens)

    return MarketCreatorInfo(
        label=label,
        safe_contract_address=safe_contract_address.lower(),
        owners=[o.lower() for o in owner_addresses],
        threshold=sig_threshold,
        balances=balances,
    )


def get_all_creators_info(
    creators: Dict[str, Dict[str, Any]],
) -> List[MarketCreatorInfo]:
    """Get info for multiple market creators.

    Args:
        creators: mapping of label -> config dict

    Returns:
        List of MarketCreatorInfo
    """
    return [get_creator_info(cfg) for cfg in creators.values()]

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
from pathlib import Path
from typing import TypedDict

from dotenv import dotenv_values
from web3 import Web3

# --- Constants & web3 setup (formerly in utils.py) ---

NATIVE_TOKEN = "0x0000000000000000000000000000000000000000"
WXDAI_ADDRESS = "0xe91D153E0b41518A2Ce8Dd3D7944Fa863463a97d"

# Find .env from repo root (works regardless of CWD)
_REPO_ROOT = Path(__file__).resolve().parent.parent
_env_values = dotenv_values(_REPO_ROOT / ".env")

_rpc = _env_values.get("GNOSIS_RPC")
web3 = Web3(Web3.HTTPProvider(_rpc))


# --- Balance utilities (formerly in utils.py) ---

def get_asset_balance(address: str, token_address: str | None = None) -> int:
    """Get the balance of an asset for a given address."""
    if token_address:
        erc20 = web3.eth.contract(
            address=web3.to_checksum_address(token_address),
            abi=ERC20_ABI,
        )
        return erc20.functions.balanceOf(web3.to_checksum_address(address)).call()
    return web3.eth.get_balance(web3.to_checksum_address(address))


def wei_to_unit(wei: int) -> float:
    """Convert WEI to unit token."""
    return wei / 10**18


def wei_to_xdai(wei: int) -> str:
    """Converts and formats wei to xDAI."""
    return "{:.2f} xDAI".format(wei_to_unit(wei))


ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    }
]


# --- Safe / creator info ---

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


class MarketCreatorConfig(TypedDict):
    """Configuration for a single market creator or trusted resolver."""

    name: str
    icon: str
    safe_contract_address: str
    markets_to_approve_per_day: int
    thresholds: dict


@dataclass
class MarketCreatorInfo:
    """Information about a market creator."""

    label: str
    safe_contract_address: str
    owners: list[str]
    threshold: int
    balances: dict  # address -> {token_address -> balance}


def _get_balances(address: str, token_addresses: set) -> dict:
    """Get balances for a set of token addresses.

    :param address: the wallet address to query.
    :param token_addresses: set of token contract addresses (use NATIVE_TOKEN for native).
    :return: mapping of token_address -> balance in token units.
    """
    result = {}
    for token in token_addresses:
        if token == NATIVE_TOKEN:
            result[token] = wei_to_unit(get_asset_balance(address))
        else:
            result[token] = wei_to_unit(get_asset_balance(address, token))
    return result


def get_creator_info(config: MarketCreatorConfig) -> MarketCreatorInfo:
    """Get Safe owner and balance info for a market creator.

    Handles both Gnosis Safe contracts (fetches owners + threshold) and plain
    EOAs (treated as a single-owner "safe" with threshold 1/1).

    :param config: market creator configuration.
    :return: MarketCreatorInfo with balances for all tokens referenced in thresholds.
    """
    label = config["name"]
    safe_contract_address = config["safe_contract_address"]
    thresholds = config.get("thresholds", {})
    checksum = web3.to_checksum_address(safe_contract_address)

    # Detect EOA vs contract by checking deployed code
    code = web3.eth.get_code(checksum)
    if len(code) == 0:
        # EOA — treat as a single-owner "safe" with threshold 1/1
        owner_addresses: list[str] = [safe_contract_address]
        sig_threshold = 1
    else:
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
    creators: dict[str, MarketCreatorConfig],
) -> list[MarketCreatorInfo]:
    """Get info for multiple market creators.

    :param creators: mapping of label -> market creator configuration.
    :return: List of MarketCreatorInfo.
    """
    return [get_creator_info(cfg) for cfg in creators.values()]

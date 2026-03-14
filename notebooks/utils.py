# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2026 Valory AG
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

"""Utility functions for the market creator scripts."""

from pathlib import Path
from typing import Optional

from dotenv import dotenv_values
from web3 import Web3

WXDAI_ADDRESS = "0xe91D153E0b41518A2Ce8Dd3D7944Fa863463a97d"

# Find .env from repo root (works regardless of CWD)
_REPO_ROOT = Path(__file__).resolve().parent.parent
env_values = dotenv_values(_REPO_ROOT / ".env")

rpc = env_values.get("GNOSIS_RPC")
web3 = Web3(Web3.HTTPProvider(rpc))


def get_asset_balance(address: str, token_address: Optional[str] = None) -> int:
    """Get the balance of an asset for a given address."""
    if token_address:
        erc20 = web3.eth.contract(
            address=web3.to_checksum_address(token_address),
            abi=[
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "", "type": "uint256"}],
                    "type": "function",
                }
            ],
        )
        return erc20.functions.balanceOf(web3.to_checksum_address(address)).call()
    return web3.eth.get_balance(web3.to_checksum_address(address))


def wei_to_unit(wei: int) -> float:
    """Convert WEI to unit token."""
    return wei / 10**18


def wei_to_xdai(wei: int) -> str:
    """Converts and formats wei to xDAI."""
    return "{:.2f} xDAI".format(wei_to_unit(wei))

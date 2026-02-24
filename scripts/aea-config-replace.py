#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2025-2026 Valory AG
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


"""Updates fetched agent with correct config"""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv  # type: ignore


AGENT_NAME = "agent"

PATH_TO_VAR = {
    # Ledgers
    "config/ledger_apis/ethereum/address": "ETHEREUM_LEDGER_RPC",
    "config/ledger_apis/ethereum/chain_id": "ETHEREUM_CHAIN_ID",
    "config/ledger_apis/gnosis/address": "GNOSIS_LEDGER_RPC",
    "config/ledger_apis/gnosis/chain_id": "GNOSIS_CHAIN_ID",
    # Agent
    "models/params/args/setup/all_participants": "ALL_PARTICIPANTS",
    "models/params/args/setup/safe_contract_address": "SAFE_CONTRACT_ADDRESS",
    "models/params/args/safe_contract_addresses": "SAFE_CONTRACT_ADDRESSES",
    "models/params/args/store_path": "STORE_PATH",
    "models/benchmark_tool/args/log_dir": "BENCHMARKS_DIR",
    "models/params/args/reset_tendermint_after": "RESET_TENDERMINT_AFTER",
    "models/params/args/reset_pause_duration": "RESET_PAUSE_DURATION",
    # News API
    "models/params/args/newsapi_endpoint": "NEWSAPI_ENDPOINT",
    "models/params/args/newsapi_api_key": "NEWSAPI_API_KEY",
    # OpenAI
    "models/params/args/openai_api_key": "OPENAI_API_KEY",
    "config/openai_api_key": "OPENAI_API_KEY",
    "config/engine": "ENGINE",
    # Market Approval Server
    "models/params/args/market_approval_server_url": "MARKET_APPROVAL_SERVER_URL",
    "models/params/args/market_approval_server_api_key": "MARKET_APPROVAL_SERVER_API_KEY",
    # Market parameters
    "models/params/args/max_proposed_markets": "MAX_PROPOSED_MARKETS",
    "models/params/args/min_market_proposal_interval_seconds": "MIN_MARKET_PROPOSAL_INTERVAL_SECONDS",
    "models/params/args/market_fee": "MARKET_FEE",
    "models/params/args/initial_funds": "INITIAL_FUNDS",
    "models/params/args/market_timeout": "MARKET_TIMEOUT",
    # Subgraph
    "models/omen_subgraph/args/url": "OMEN_SUBGRAPH_URL",
    "models/mechs_subgraph/args/url": "MECHS_SUBGRAPH_URL",
    "models/params/args/subgraph_api_key": "SUBGRAPH_API_KEY",
    # Serper
    "models/params/args/serper_api_key": "SERPER_API_KEY",
}

CONFIG_REGEX = r"\${.*?:(.*)}"


def find_and_replace(config: list, path: list, new_value: Any) -> list[Any]:
    """Find and replace a variable"""

    # Find the correct section where this variable fits
    matching_section_indices = []
    for i, section in enumerate(config):
        value = section
        try:
            for part in path:
                value = value[part]
            matching_section_indices.append(i)
        except KeyError:
            continue

    if not matching_section_indices:
        raise KeyError(f"Path {path} not found in the config.")

    for section_index in matching_section_indices:
        # To persist the changes in the config variable,
        # access iterating the path parts but the last part
        sub_dic = config[section_index]
        for part in path[:-1]:
            sub_dic = sub_dic[part]

        # Now, get the whole string value
        old_str_value = sub_dic[path[-1]]

        # Extract the old variable value
        match = re.match(CONFIG_REGEX, old_str_value)
        old_var_value = match.groups()[0]  # type: ignore

        # Replace the old variable with the secret value in the complete string
        new_str_value = old_str_value.replace(old_var_value, new_value)
        sub_dic[path[-1]] = new_str_value

    return config


def main() -> None:
    """Main"""
    load_dotenv(override=True)

    # Load the aea config
    with open(Path(AGENT_NAME, "aea-config.yaml"), "r", encoding="utf-8") as file:
        config = list(yaml.safe_load_all(file))

    # Search and replace all the secrets
    for path, var in PATH_TO_VAR.items():
        try:
            new_value = os.getenv(var)  # pylint: disable=E1101
            if new_value is None:
                print(f"Environment variable {var} not found. Skipping...")
                continue
            config = find_and_replace(config, path.split("/"), new_value)
        except Exception as e:
            print(f"Exception while replacing {path}:\n{e}")
            raise ValueError from e

    # Dump the updated config
    with open(Path(AGENT_NAME, "aea-config.yaml"), "w", encoding="utf-8") as file:
        yaml.dump_all(config, file, sort_keys=False)


if __name__ == "__main__":
    main()

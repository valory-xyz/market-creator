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

"""Backup market approval server configuration."""

import argparse
import json
import time
from typing import Any, Dict, Optional

import requests


MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 10
ENDPOINTS = [
    "approved_markets",
    "processed_markets",
    "proposed_markets",
    "rejected_markets",
]


def _fetch_data(endpoint_url: str) -> Optional[Dict[str, Any]]:
    for retry_count in range(MAX_RETRIES):
        response = requests.get(endpoint_url)
        if response.status_code == 200:
            return response.json()
        print(
            f"Failed to fetch data from {endpoint_url}. Status code: {response.status_code}"
        )
        if retry_count < MAX_RETRIES - 1:
            print(f"Retrying in {RETRY_DELAY_SECONDS} seconds...")
            time.sleep(RETRY_DELAY_SECONDS)
    return None


def _process_endpoints(url: str) -> Optional[Dict[str, Any]]:
    _backup_data: Dict[str, Any] = {
        "api_keys": {
            "454d31ff03590ff36836e991d3287b23146a7a84c79d082732b56268fe472823": "default_user"
        }
    }

    for endpoint in ENDPOINTS:
        data = _fetch_data(f"{url}/{endpoint}")
        if data is None:
            return None
        _backup_data[endpoint] = data.get(endpoint, {})

    return _backup_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a backup of market approval server configuration."
    )
    parser.add_argument("server_url", help="URL of the server to back up")
    args = parser.parse_args()

    server_url: str = args.server_url
    backup_data: Optional[Dict[str, Any]] = _process_endpoints(server_url)

    if backup_data:
        current_time = time.strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"server_config.backup_{current_time}.json"
        with open(backup_filename, "w", encoding="UTF-8") as backup_file:
            json.dump(backup_data, backup_file, indent=4)
        print(f"Backup created successfully: {backup_filename}")
    else:
        print("Failed to create backup. Please check the server URL and endpoints.")

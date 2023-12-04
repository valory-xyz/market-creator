#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2022-2023 Valory AG
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

"""Script for listing markets."""

import argparse
import csv
from datetime import datetime

import requests


# Function to filter markets based on resolution_time within the specified day
def _filter_markets_by_date(markets, date):
    output = []
    for market_id, market_data in markets.items():
        resolution_time = datetime.utcfromtimestamp(
            market_data.get("resolution_time", 0)
        ).strftime("%Y-%m-%d")
        if resolution_time == date:
            output.append(
                [
                    market_id,
                    market_data["language"],
                    market_data["question"],
                    market_data["resolution_time"],
                    market_data["topic"],
                ]
            )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch and filter market data.")
    parser.add_argument("url", help="Endpoint URL to fetch market data")
    parser.add_argument("date", help="Target date in the format YYYY-MM-DD")
    args = parser.parse_args()

    url = args.url.rstrip("/")
    target_date = args.date

    data = requests.get(url).json()

    url_parts = url.split("/")
    key_from_url = url_parts[-1]
    filtered_markets = _filter_markets_by_date(data[key_from_url], target_date)

    csv_filename = f"output-{key_from_url}-{target_date}.csv"
    with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerows(filtered_markets)

    print(f"CSV file {csv_filename} generated successfully.")

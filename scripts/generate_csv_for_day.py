import argparse
import requests
import json
import csv
from datetime import datetime
from typing import Dict, Optional

def get_markets(url: str, day: Optional[str] = None) -> Dict[str, Dict]:
    # Send a GET request to the specified URL
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()

        # If day is specified, filter markets by resolution_time
        if day:
            timestamp_start = datetime.strptime(day, '%d-%m-%Y').timestamp()
            timestamp_end = timestamp_start + 24 * 60 * 60  # 24 hours
            filtered_markets = {
                key: market for key, market in data["proposed_markets"].items()
                if timestamp_start <= market["resolution_time"] < timestamp_end
            }
        else:
            filtered_markets = data["proposed_markets"]

        return filtered_markets
    else:
        raise Exception(f"Failed to fetch data from {url} (HTTP {response.status_code})")

def export_to_csv(markets: Dict[str, Dict]) -> None:
    # Generate the CSV filename
    current_datetime = datetime.now().strftime('%d-%m-%Y_%H-%M')
    csv_filename = f"output_{current_datetime}.csv"

    with open(csv_filename, mode='w', newline='') as csv_file:
        fieldnames = ["id", "language", "question", "resolution_time", "topic"]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

        for market in markets.values():
            writer.writerow({
                "id": market["id"],
                "language": market["language"],
                "question": market["question"],
                "resolution_time": market["resolution_time"],
                "topic": market["topic"]
            })

    print(f"Data exported to {csv_filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch and process JSON data from a URL.")
    parser.add_argument("url", help="The URL to fetch JSON data from.")
    parser.add_argument("--day", help="Filter markets by UTC timestamp in the format dd-mm-aaaa.")

    args = parser.parse_args()

    markets = get_markets(args.url, args.day)
    export_to_csv(markets)

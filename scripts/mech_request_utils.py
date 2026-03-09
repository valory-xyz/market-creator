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

# pylint: disable=too-many-locals

"""Script for retrieving mech requests and their delivers."""

import base64
import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from typing import Any, Dict

import requests
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport
from tqdm import tqdm


TEXT_ALIGNMENT = 30
MINIMUM_WRITE_FILE_DELAY_SECONDS = 20
DEFAULT_MECH_REQUESTS_JSON_PATH = "mech_requests.json"
IPFS_ADDRESS = "https://gateway.autonolas.tech/ipfs/"
CID_V1_PREFIX = "f01701220"
THREAD_POOL_EXECUTOR_MAX_WORKERS = 10

SUBGRAPH_URL = "https://api.subgraph.autonolas.tech/api/proxy/marketplace-gnosis"

REQUESTS_QUERY = """
query requests_query($sender: String!, $id_gt: ID!) {
  requests(where: {sender: $sender, id_gt: $id_gt}, orderBy: id, first: 1000) {
    blockNumber
    blockTimestamp
    id
    sender {
      id
    }
    transactionHash
    parsedRequest {
      hash
      id
    }
    deliveries {
      blockNumber
      blockTimestamp
      id
      requestId
      sender
      transactionHash
      toolResponse
      mechDelivery {
        ipfsHash
        requestId
      }
      marketplaceDelivery {
        ipfsHashBytes
      }
    }
  }
}
"""


def _populate_requests(
    sender: str, mech_requests: Dict[str, Any]
) -> None:
    """Fetch all requests (with inline deliveries) from the subgraph."""
    print(f"{'Fetching requests...':>{TEXT_ALIGNMENT}}")

    transport = RequestsHTTPTransport(url=SUBGRAPH_URL)
    client = Client(transport=transport, fetch_schema_from_transport=True)

    id_gt = "0x00"
    while True:
        variables = {
            "sender": sender,
            "id_gt": id_gt,
        }
        t0 = time.time()
        response = client.execute(gql(REQUESTS_QUERY), variable_values=variables)
        t1 = time.time()
        items = response.get("requests", [])

        if not items:
            break

        for mech_request in items:
            # Pick the best delivery: closest blockNumber >= request blockNumber
            deliveries = mech_request.pop("deliveries", [])
            req_block = int(mech_request["blockNumber"])
            best_deliver = None
            for d in deliveries:
                if int(d["blockNumber"]) >= req_block:
                    if best_deliver is None or int(d["blockNumber"]) < int(best_deliver["blockNumber"]):
                        best_deliver = d

            if mech_request["id"] not in mech_requests:
                if best_deliver:
                    mech_request["deliver"] = best_deliver
                mech_requests[mech_request["id"]] = mech_request
            elif "deliver" not in mech_requests[mech_request["id"]] and best_deliver:
                mech_requests[mech_request["id"]]["deliver"] = best_deliver

        t2 = time.time()
        print(f"{f'{len(items)} requests fetched':>{TEXT_ALIGNMENT}}. Query time: {t1 - t0:.2f}s. Processing time: {t2 - t1:.2f}s. Total time: {t2 - t0:.2f}s.")
        id_gt = items[-1]["id"]
        _write_mech_events_to_file(mech_requests)

    _write_mech_events_to_file(mech_requests, True)
    print(f"{f'{len(mech_requests)} total requests found':>{TEXT_ALIGNMENT}}")


def get_request_ipfs_url(mech_request: Dict[str, Any]) -> str:
    """Get the IPFS URL for a mech request."""
    ipfs_hash = mech_request["parsedRequest"]["hash"]
    return f"{IPFS_ADDRESS}{ipfs_hash}/metadata.json"


def get_deliver_ipfs_url(deliver: Dict[str, Any]) -> str:
    """Get the IPFS URL for a deliver."""
    if deliver.get("mechDelivery") and deliver["mechDelivery"].get("ipfsHash"):
        ipfs_hash = deliver["mechDelivery"]["ipfsHash"]
        request_id = deliver["mechDelivery"]["requestId"]
        return f"{IPFS_ADDRESS}{ipfs_hash}/{int(request_id, 16)}"
    if deliver.get("marketplaceDelivery") and deliver["marketplaceDelivery"].get("ipfsHashBytes"):
        ipfs_hash = deliver["marketplaceDelivery"]["ipfsHashBytes"]
        request_id = deliver["requestId"]
        return f"{IPFS_ADDRESS}{CID_V1_PREFIX}{ipfs_hash[2:]}/{int(request_id, 16)}"
    return ""


def _populate_event_ipfs_contents(event: Dict[str, Any], url: str) -> None:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    event["ipfsContents"] = response.json()


def _populate_missing_ipfs_contents(mech_requests: Dict[str, Any]) -> int:
    error_count = 0
    pending_events = []

    for _, mech_request in mech_requests.items():
        if "ipfsContents" not in mech_request:
            url = get_request_ipfs_url(mech_request)
            pending_events.append((mech_request, url))

        if "deliver" in mech_request and "ipfsContents" not in mech_request["deliver"]:
            url = get_deliver_ipfs_url(mech_request["deliver"])
            if url:
                pending_events.append((mech_request["deliver"], url))

    with ThreadPoolExecutor(max_workers=THREAD_POOL_EXECUTOR_MAX_WORKERS) as executor:
        futures = [
            executor.submit(_populate_event_ipfs_contents, event, url)
            for event, url in pending_events
        ]

        for future in tqdm(
            as_completed(futures),
            total=len(futures),
            desc=f"{'Fetching IPFS contents':>{TEXT_ALIGNMENT}}",
            miniters=1,
        ):
            try:
                future.result()
                _write_mech_events_to_file(mech_requests)
            except Exception as e:  # pylint: disable=broad-except
                error_count += 1
                print(f"Error occurred: {e}")

    _write_mech_events_to_file(mech_requests, True)
    return error_count


last_write_time = 0.0
mech_events_json_path = DEFAULT_MECH_REQUESTS_JSON_PATH


def _write_mech_events_to_file(
    mech_requests: Dict[str, Any], force_write: bool = False
) -> None:
    global last_write_time  # pylint: disable=global-statement
    now = time.time()

    if force_write or (now - last_write_time) >= MINIMUM_WRITE_FILE_DELAY_SECONDS:
        try:
            with open(mech_events_json_path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}

        data["mechRequests"] = mech_requests

        with open(mech_events_json_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, sort_keys=True)

        last_write_time = now


def get_mech_requests(
    sender: str, json_path: str = DEFAULT_MECH_REQUESTS_JSON_PATH
) -> Dict[str, Any]:
    """Get Mech requests populated with the associated response and IPFS contents."""
    start_time = time.time()

    global mech_events_json_path  # pylint: disable=global-statement
    mech_events_json_path = json_path

    try:
        with open(mech_events_json_path, "r", encoding="UTF-8") as json_file:
            existing_data = json.load(json_file)
            mech_requests = existing_data.get("mechRequests", {})
    except FileNotFoundError:
        print(f"File {mech_events_json_path} not found, setting empty list of requests")
        mech_requests = {}

    try:
        _populate_requests(
            sender=sender.lower(),
            mech_requests=mech_requests,
        )
        error_count = _populate_missing_ipfs_contents(mech_requests)

        if error_count > 0:
            print(f"{error_count} errors populating IPFS contents. Retrying again...")
            _populate_missing_ipfs_contents(mech_requests)
    except Exception as e:  # pylint: disable=broad-except
        print(f"An error occurred while updating mech requests: {e}")
        traceback.print_exc()

    end_time = time.time()
    elapsed_time = end_time - start_time
    elapsed_timedelta = timedelta(seconds=elapsed_time)
    formatted_time = str(elapsed_timedelta)
    print(f"Time of execution: {formatted_time}")

    return mech_requests


if __name__ == "__main__":
    service_safe_address = "0xffc8029154ecd55abed15bd428ba596e7d23f557"
    get_mech_requests(service_safe_address, f"test_{DEFAULT_MECH_REQUESTS_JSON_PATH}")

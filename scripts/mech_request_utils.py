# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2024-2025 Valory AG
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

import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from typing import Any, Dict, List

import requests
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport
from tqdm import tqdm


TEXT_ALIGNMENT = 30
MINIMUM_WRITE_FILE_DELAY_SECONDS = 20
MECH_FROM_BLOCK_RANGE = 50000
DEFAULT_MECH_REQUESTS_JSON_PATH = "mech_requests.json"
IPFS_ADDRESS = "https://gateway.autonolas.tech/ipfs/"
CID_V1_PREFIX = "f01701220"
THREAD_POOL_EXECUTOR_MAX_WORKERS = 10

LEGACY_REQUESTS_QUERY = """
query requests_query($sender: String!, $id_gt: ID!) {
  requests(where: {sender: $sender, id_gt: $id_gt}, orderBy: id, first: 1000) {
    blockNumber
    blockTimestamp
    id
    ipfsHash
    requestId
    sender {
      id
    }
    transactionHash
  }
}
"""

LEGACY_DELIVERS_QUERY = """
query delivers_query($requestId_in: [BigInt!], $id_gt: Bytes!) {
  delivers(where: {requestId_in: $requestId_in, id_gt: $id_gt}, orderBy: blockNumber, first: 1000) {
    blockNumber
    blockTimestamp
    id
    ipfsHash
    requestId
    sender
    transactionHash
  }
}
"""

MM_REQUESTS_QUERY = LEGACY_REQUESTS_QUERY

MM_DELIVERS_QUERY = """
query delivers_query($requestId_in: [Bytes!], $id_gt: ID!) {
  delivers(where: {requestId_in: $requestId_in, id_gt: $id_gt}, orderBy: blockNumber, first: 1000) {
    blockNumber
    blockTimestamp
    id
    ipfsHash
    requestId
    sender
    transactionHash
  }
}
"""

graph_endpoints_data = {
    "legacy": {
        "url": "https://api.subgraph.autonolas.tech/api/proxy/mech",
        "requests_query": LEGACY_REQUESTS_QUERY,
        "delivers_query": LEGACY_DELIVERS_QUERY,
    },
    "marketplace": {
        "url": "https://api.studio.thegraph.com/query/1716136/olas-gnosis-mech-marketplace/version/latest",
        "requests_query": MM_REQUESTS_QUERY,
        "delivers_query": MM_DELIVERS_QUERY,
    },
}


def _populate_missing_requests(
    endpoint_id: str, sender: str, mech_requests: Dict[str, Any]
) -> None:
    print(f"{f'Fetching requests ({endpoint_id})...':>{TEXT_ALIGNMENT}}")

    url = graph_endpoints_data[endpoint_id]["url"]
    requests_query = graph_endpoints_data[endpoint_id]["requests_query"]
    transport = RequestsHTTPTransport(
        url=url,
    )
    client = Client(transport=transport, fetch_schema_from_transport=True)

    id_gt = "0x00"
    while True:
        variables = {
            "sender": sender,
            "id_gt": id_gt,
        }
        response = client.execute(gql(requests_query), variable_values=variables)
        items = response.get("requests", [])

        if not items:
            break

        for mech_request in items:
            if mech_request["id"] not in mech_requests:
                mech_request["endpointId"] = endpoint_id
                mech_requests[mech_request["id"]] = mech_request
            elif "endpointId" not in mech_requests[mech_request["id"]]:
                mech_requests[mech_request["id"]]["endpointId"] = "legacy"

        id_gt = items[-1]["id"]
        _write_mech_events_to_file(mech_requests)

    _write_mech_events_to_file(mech_requests, True)
    print(f"{f'{len(mech_requests)} requests found':>{TEXT_ALIGNMENT}}")


def _populate_missing_delivers(endpoint_id: str, mech_requests: Dict[str, Any]) -> None:
    print(f"{f'Fetching delivers ({endpoint_id})...':>{TEXT_ALIGNMENT}}")

    url = graph_endpoints_data[endpoint_id]["url"]
    delivers_query = graph_endpoints_data[endpoint_id]["delivers_query"]
    transport = RequestsHTTPTransport(url=url)
    client = Client(transport=transport, fetch_schema_from_transport=True)

    NUM_REQUESTS_PER_QUERY = 100
    pending_mech_requests = {
        k: req
        for k, req in mech_requests.items()
        if "deliver" not in req and req["endpointId"] == endpoint_id
    }

    progress_bar = tqdm(
        total=len(pending_mech_requests),
        desc=f"{f'Fetching delivers ({endpoint_id})':>{TEXT_ALIGNMENT}}",
        miniters=1,
    )

    while pending_mech_requests:
        picked_requests = list(pending_mech_requests.values())[:NUM_REQUESTS_PER_QUERY]

        for mech_request in picked_requests:
            del pending_mech_requests[mech_request["id"]]

        requestsId_in = [mech_request["requestId"] for mech_request in picked_requests]

        mech_delivers = []
        id_gt = "0x00"
        while True:
            variables = {
                "requestId_in": requestsId_in,
                "id_gt": id_gt,
            }
            response = client.execute(gql(delivers_query), variable_values=variables)
            items = response.get("delivers")

            if not items:
                break

            mech_delivers.extend(items)
            id_gt = items[-1]["id"]

        # If the user sends requests with the same values (tool, prompt, nonce) it
        # will generate the same requestId. Therefore, multiple items can be retrieved
        # at this point. We assume the most likely deliver to this request is the
        # one with the closest blockNumber among all delivers with the same requestId.
        #
        # In conclusion, for each request in picked_requests, find the deliver with the
        # smallest blockNumber such that >= request's blockNumber
        for mech_request in picked_requests:
            for deliver in mech_delivers:
                if deliver["requestId"] == mech_request["requestId"] and int(
                    deliver["blockNumber"]
                ) >= int(mech_request["blockNumber"]):
                    mech_request["deliver"] = deliver
                    break

        progress_bar.update(len(picked_requests))
        _write_mech_events_to_file(mech_requests)

    _write_mech_events_to_file(mech_requests, True)


def _populate_event_ipfs_contents(event: Dict[str, Any], url: str) -> None:
    response = requests.get(url)
    response.raise_for_status()  # Raise an exception for HTTP error responses
    event["ipfsContents"] = response.json()


def _populate_missing_ipfs_contents(mech_requests: Dict[str, Any]) -> int:
    error_count = 0

    # Collect all pending events
    pending_events = []

    for _, mech_request in mech_requests.items():
        if "ipfsContents" not in mech_request:
            ipfs_hash = mech_request["ipfsHash"]
            if mech_request["endpointId"] == "legacy":
                url = f"{IPFS_ADDRESS}{ipfs_hash}/metadata.json"
            else:  # marketplace
                url = f"{IPFS_ADDRESS}{CID_V1_PREFIX}{ipfs_hash[2:]}/metadata.json"
            pending_events.append((mech_request, url))

        if "deliver" in mech_request:
            deliver = mech_request["deliver"]
            if "ipfsContents" not in deliver:
                ipfs_hash = deliver["ipfsHash"]
                request_id = deliver["requestId"]
                if mech_request["endpointId"] == "legacy":
                    url = f"{IPFS_ADDRESS}{ipfs_hash}/{request_id}"
                else:  # marketplace
                    url = f"{IPFS_ADDRESS}{CID_V1_PREFIX}{ipfs_hash[2:]}/{int(request_id, 16)}"

                pending_events.append((deliver, url))

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


def _find_duplicate_delivers(
    mech_requests: Dict[str, Any]
) -> Dict[str, List[Dict[str, Any]]]:
    requests_with_duplicate_deliver_ids = defaultdict(list)

    for _, r in tqdm(
        mech_requests.items(),
        desc=f"{'Finding duplicate delivers':>{TEXT_ALIGNMENT}}",
        miniters=1,
    ):
        if "deliver" in r:
            requests_with_duplicate_deliver_ids[r["deliver"]["id"]].append(r)

    for k in list(requests_with_duplicate_deliver_ids.keys()):
        if len(requests_with_duplicate_deliver_ids[k]) == 1:
            del requests_with_duplicate_deliver_ids[k]

    print(
        f"Duplicate deliver ids found: {len(requests_with_duplicate_deliver_ids.keys())}"
    )
    return requests_with_duplicate_deliver_ids


def _process_duplicate_delivers(mech_requests: Dict[str, Any]) -> None:
    requests_with_duplicate_deliver_ids = _find_duplicate_delivers(mech_requests)
    for mech_requests_list in tqdm(
        requests_with_duplicate_deliver_ids.values(),
        desc=f"{'Processing duplicate delivers':>{TEXT_ALIGNMENT}}",
        miniters=1,
    ):
        min_difference_request = min(
            mech_requests_list,
            key=lambda x: int(x["deliver"]["blockNumber"]) - int(x["blockNumber"]),
        )
        for mech_request in mech_requests_list:
            if mech_request is not min_difference_request:
                mech_request.pop("deliver", None)

    _write_mech_events_to_file(mech_requests, True)


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
        for endpoint_id in graph_endpoints_data.keys():
            _populate_missing_requests(
                endpoint_id=endpoint_id,
                sender=sender.lower(),
                mech_requests=mech_requests,
            )
            _populate_missing_delivers(
                endpoint_id=endpoint_id, mech_requests=mech_requests
            )

        _process_duplicate_delivers(mech_requests)
        _find_duplicate_delivers(mech_requests)
        error_count = _populate_missing_ipfs_contents(mech_requests)

        if error_count > 0:
            print(f"{error_count} errors populating IPFS contents. Retrying again...")
            _populate_missing_ipfs_contents(mech_requests)
    except Exception as e:  # pylint: disable=broad-except
        print(f"An error occurred while updating mech requests: {e}")

    end_time = time.time()
    elapsed_time = end_time - start_time
    elapsed_timedelta = timedelta(seconds=elapsed_time)
    formatted_time = str(elapsed_timedelta)
    print(f"Time of execution: {formatted_time}")

    return mech_requests


if __name__ == "__main__":
    service_safe_address = "0x89c5cc945dd550BcFfb72Fe42BfF002429F46Fec"
    get_mech_requests(service_safe_address, f"test_{DEFAULT_MECH_REQUESTS_JSON_PATH}")

import json
import time
from collections import defaultdict
from typing import List, Any, Dict
from tqdm import tqdm
import requests
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport


TEXT_ALIGNMENT = 30
MINIMUM_WRITE_FILE_DELAY_SECONDS = 20
MECH_FROM_BLOCK_RANGE = 50000
MECH_REQUESTS_JSON_PATH = "mech_requests.json"
IPFS_ADDRESS = "https://gateway.autonolas.tech/ipfs/"
THEGRAPH_ENDPOINT = "https://api.studio.thegraph.com/query/57238/mech/0.0.2"

REQUESTS_QUERY = """
query requests_query($sender: Bytes, $id_gt: Bytes) {
  requests(where: {sender: $sender, id_gt: $id_gt}, orderBy: id, first: 1000) {
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

DELIVERS_QUERY = """
query delivers_query($requestId: BigInt, $blockNumber_gte: BigInt, $blockNumber_lte: BigInt) {
  delivers(where: {requestId: $requestId, blockNumber_gte: $blockNumber_gte, blockNumber_lte: $blockNumber_lte}, orderBy: blockNumber, first: 1000) {
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


def _populate_missing_requests(sender: str, mech_requests: Dict[str, Any]) -> None:
    print(f"{'Fetching requests...':>{TEXT_ALIGNMENT}}")

    transport = RequestsHTTPTransport(url=THEGRAPH_ENDPOINT)
    client = Client(transport=transport, fetch_schema_from_transport=True)

    id_gt = "0x00"
    while True:
        variables = {
            "sender": sender,
            "id_gt": id_gt,
        }
        response = client.execute(gql(REQUESTS_QUERY), variable_values=variables)
        items = response.get("requests", [])

        if not items:
            break

        for mech_request in items:
            if mech_request["id"] not in mech_requests:
                mech_requests[mech_request["id"]] = mech_request

        id_gt = items[-1]["id"]
        _write_mech_events_to_file(mech_requests)

    _write_mech_events_to_file(mech_requests, True)


def _populate_missing_responses(mech_requests: Dict[str, Any]) -> None:
    transport = RequestsHTTPTransport(url=THEGRAPH_ENDPOINT)
    client = Client(transport=transport, fetch_schema_from_transport=True)

    for _, mech_request in tqdm(mech_requests.items(), desc=f"{'Fetching responses':>{TEXT_ALIGNMENT}}", miniters=1):
        if "deliver" in mech_request:
            continue

        variables = {
            "requestId": mech_request["requestId"],
            "blockNumber_gte": mech_request["blockNumber"],
            "blockNumber_lte": str(int(mech_request["blockNumber"]) + MECH_FROM_BLOCK_RANGE)
        }
        response = client.execute(gql(DELIVERS_QUERY), variable_values=variables)
        items = response.get("delivers")

        # If the user sends requests with the same values (tool, prompt, nonce) it
        # will generate the same requestId. Therefore, multiple items can be retrieved
        # at this point. We assume the most likely deliver to this request is the
        # one with the closest blockNumber among all delivers with the same requestId.
        if items:
            mech_request["deliver"] = items[0]

        _write_mech_events_to_file(mech_requests)

    _write_mech_events_to_file(mech_requests, True)


def _populate_missing_ipfs_contents(mech_requests: Dict[str, Any]) -> None:
    for _, mech_request in tqdm(mech_requests.items(), desc=f"{'Fetching IPFS contents':>{TEXT_ALIGNMENT}}", miniters=1):
        if "ipfsContents" not in mech_request:
            ipfs_hash = mech_request["ipfsHash"]
            url = f"{IPFS_ADDRESS}{ipfs_hash}/metadata.json"
            response = requests.get(url)
            response.raise_for_status()
            mech_request["ipfsContents"] = response.json()

        if "deliver" not in mech_request:
            continue

        deliver = mech_request["deliver"]
        if "ipfsContents" not in deliver:
            ipfs_hash = deliver["ipfsHash"]
            request_id = deliver["requestId"]
            url = f"{IPFS_ADDRESS}{ipfs_hash}/{request_id}"
            response = requests.get(url)
            response.raise_for_status()
            deliver["ipfsContents"] = response.json()

        _write_mech_events_to_file(mech_requests)

    _write_mech_events_to_file(mech_requests, True)


def _find_duplicate_delivers(mech_requests: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    requests_with_duplicate_deliver_ids = defaultdict(list)

    for _, r in tqdm(mech_requests.items(), desc=f"{'Finding duplicate delivers':>{TEXT_ALIGNMENT}}", miniters=1):
        if "deliver" in r:
            requests_with_duplicate_deliver_ids[r["deliver"]["id"]].append(r)

    for k in list(requests_with_duplicate_deliver_ids.keys()):
        if len(requests_with_duplicate_deliver_ids[k]) == 1:
            del requests_with_duplicate_deliver_ids[k]

    print(f"Duplicate deliver ids found: {len(requests_with_duplicate_deliver_ids.keys())}")
    return requests_with_duplicate_deliver_ids


def _process_duplicate_delivers(mech_requests: Dict[str, Any]) -> None:
    requests_with_duplicate_deliver_ids = _find_duplicate_delivers(mech_requests)
    for mech_requests_list in tqdm(requests_with_duplicate_deliver_ids.values(), desc=f"{'Processing duplicate delivers':>{TEXT_ALIGNMENT}}", miniters=1):
        min_difference_request = min(
            mech_requests_list,
            key=lambda x: int(x['deliver']['blockNumber']) - int(x['blockNumber'])
        )
        for mech_request in mech_requests_list:
            if mech_request is not min_difference_request:
                mech_request.pop('deliver', None)

    _write_mech_events_to_file(mech_requests, True)


last_write_time = 0.0


def _write_mech_events_to_file(
    mech_requests: Dict[str, Any], force_write: bool = False
) -> None:
    global last_write_time  # pylint: disable=global-statement
    now = time.time()

    if force_write or (now - last_write_time) >= MINIMUM_WRITE_FILE_DELAY_SECONDS:
        with open(MECH_REQUESTS_JSON_PATH, "w", encoding="utf-8") as file:
            json.dump({"mechRequests": mech_requests}, file, indent=2, sort_keys=True)
        last_write_time = now


def get_mech_requests(sender: str) -> Dict[str, Any]:
    """Get Mech requests populated with the associated response and IPFS contents."""
    mech_requests = {}
    try:
        with open(MECH_REQUESTS_JSON_PATH, "r", encoding="UTF-8") as json_file:
            existing_data = json.load(json_file)
            mech_requests = existing_data.get("mechRequests", {})
    except FileNotFoundError:
        pass  # File doesn't exist yet, so there are no existing requests

    _populate_missing_requests(sender.lower(), mech_requests)
    _populate_missing_responses(mech_requests)
    _process_duplicate_delivers(mech_requests)
    _find_duplicate_delivers(mech_requests)
    _populate_missing_ipfs_contents(mech_requests)
    return mech_requests

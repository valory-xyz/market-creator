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

"""Fetch mech requests and delivers for market creators.

The market creator uses the Realitio question ID as the mech nonce.  When a
mech response is ``not_determinable`` the agent retries with the **same nonce**
but the subgraph assigns a new request ID for each on-chain request, so each
(requestId, delivery) pair is unique — duplicates are tracked via the nonce.

Data is cached to a JSON file per creator so already-delivered requests are not
re-fetched from IPFS on subsequent runs.
"""

import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests as http_requests
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport
from tqdm import tqdm

SUBGRAPH_URL = (
    "https://api.subgraph.autonolas.tech/api/proxy/marketplace-gnosis"
)
IPFS_GATEWAY = "https://gateway.autonolas.tech/ipfs/"
CID_V1_PREFIX = "f01701220"
MAX_WORKERS = 10
WRITE_INTERVAL_SECONDS = 20
DELIVER_TIMEOUT_SECONDS = 24 * 60 * 60  # 1 day

_CACHE_DIR = Path(__file__).resolve().parent.parent / "notebooks" / ".cache"

REQUESTS_QUERY = """
query requests_query(
  $sender: String!,
  $block_timestamp_gte: BigInt!,
  $id_gt: ID!
) {
  requests(
    where: {
      sender: $sender,
      blockTimestamp_gte: $block_timestamp_gte,
      id_gt: $id_gt
    },
    orderBy: id,
    first: 1000
  ) {
    blockNumber
    blockTimestamp
    id
    sender { id }
    transactionHash
    parsedRequest { content hash id }
    deliveries {
      blockNumber
      blockTimestamp
      id
      requestId
      sender
      transactionHash
      toolResponse
      mechDelivery { ipfsHash requestId }
      marketplaceDelivery { ipfsHashBytes }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# IPFS helpers
# ---------------------------------------------------------------------------

def get_request_ipfs_url(mech_request: Dict[str, Any]) -> str:
    """Build the IPFS URL for the request metadata."""
    ipfs_hash = mech_request["parsedRequest"]["hash"]
    return f"{IPFS_GATEWAY}{ipfs_hash}/metadata.json"


def get_deliver_ipfs_url(deliver: Dict[str, Any]) -> str:
    """Build the IPFS URL for a deliver response."""
    if deliver.get("mechDelivery") and deliver["mechDelivery"].get("ipfsHash"):
        h = deliver["mechDelivery"]["ipfsHash"]
        rid = deliver["mechDelivery"]["requestId"]
        return f"{IPFS_GATEWAY}{h}/{int(rid, 16)}"
    if (
        deliver.get("marketplaceDelivery")
        and deliver["marketplaceDelivery"].get("ipfsHashBytes")
    ):
        h = deliver["marketplaceDelivery"]["ipfsHashBytes"]
        rid = deliver["requestId"]
        return f"{IPFS_GATEWAY}{CID_V1_PREFIX}{h[2:]}/{int(rid, 16)}"
    return ""


def _fetch_ipfs_json(event: Dict[str, Any], url: str) -> None:
    """Fetch JSON from IPFS and store it in ``event['ipfsContents']``."""
    resp = http_requests.get(url, timeout=60)
    resp.raise_for_status()
    event["ipfsContents"] = resp.json()


# ---------------------------------------------------------------------------
# Subgraph fetching
# ---------------------------------------------------------------------------

def _pick_best_delivery(
    deliveries: List[Dict[str, Any]], req_block: int
) -> Optional[Dict[str, Any]]:
    """Pick the delivery closest to (and >=) the request block number."""
    best = None
    for d in deliveries:
        if int(d["blockNumber"]) >= req_block:
            if best is None or int(d["blockNumber"]) < int(best["blockNumber"]):
                best = d
    return best


def _fetch_requests_from_subgraph(
    sender: str,
    existing: Dict[str, Any],
    checkpoint_ts: int = 0,
) -> None:
    """Page through requests for *sender* from *checkpoint_ts* and merge into *existing*."""
    transport = RequestsHTTPTransport(url=SUBGRAPH_URL)
    client = Client(transport=transport, fetch_schema_from_transport=True)

    id_gt = "0x00"
    while True:
        response = client.execute(
            gql(REQUESTS_QUERY),
            variable_values={
                "sender": sender,
                "block_timestamp_gte": str(checkpoint_ts),
                "id_gt": id_gt,
            },
        )
        items = response.get("requests", [])
        if not items:
            break

        for req in items:
            deliveries = req.pop("deliveries", [])
            best = _pick_best_delivery(deliveries, int(req["blockNumber"]))
            rid = req["id"]

            if rid not in existing:
                if best:
                    req["deliver"] = best
                existing[rid] = req
            elif "deliver" not in existing[rid] and best:
                existing[rid]["deliver"] = best

        id_gt = items[-1]["id"]


# ---------------------------------------------------------------------------
# IPFS content population
# ---------------------------------------------------------------------------

def _populate_ipfs_contents(
    mech_requests: Dict[str, Any],
    _write_fn: Any,
) -> int:
    """Fetch missing IPFS contents for requests and delivers.

    Returns the number of errors encountered.
    """
    pending = []
    for req in mech_requests.values():
        if "ipfsContents" not in req:
            pending.append((req, get_request_ipfs_url(req)))
        deliver = req.get("deliver")
        if deliver and "ipfsContents" not in deliver:
            url = get_deliver_ipfs_url(deliver)
            if url:
                pending.append((deliver, url))

    if not pending:
        return 0

    errors = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(_fetch_ipfs_json, ev, url) for ev, url in pending]
        for future in tqdm(
            as_completed(futures),
            total=len(futures),
            desc="Fetching IPFS contents",
            miniters=1,
        ):
            try:
                future.result()
                _write_fn(mech_requests)
            except Exception as exc:  # pylint: disable=broad-except
                errors += 1
                print(f"IPFS fetch error: {exc}")

    _write_fn(mech_requests, force=True)
    return errors


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------

def _cache_path(creator_key: str) -> Path:
    """Return the JSON cache path for a creator."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"mech_requests_{creator_key}.json"


def _load_cache(creator_key: str) -> Tuple[Dict[str, Any], int]:
    """Load cached requests and the checkpoint timestamp."""
    path = _cache_path(creator_key)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("mechRequests", {}), data.get("checkpointTimestamp", 0)
    return {}, 0


def _compute_checkpoint(mech_requests: Dict[str, Any]) -> int:
    """Compute the checkpoint timestamp for incremental fetching.

    A request is *settled* if it has a delivery or its blockTimestamp is older
    than ``DELIVER_TIMEOUT_SECONDS``.  The checkpoint is the highest
    blockTimestamp among all settled requests, minus the timeout window.  On the
    next run we query from this timestamp onward, which re-checks any unsettled
    requests and discovers new ones.
    """
    if not mech_requests:
        return 0

    now = time.time()
    cutoff = now - DELIVER_TIMEOUT_SECONDS

    # Find the earliest unsettled request timestamp
    earliest_unsettled = None
    for req in mech_requests.values():
        ts = int(req.get("blockTimestamp", 0))
        if "deliver" not in req and ts >= cutoff:
            if earliest_unsettled is None or ts < earliest_unsettled:
                earliest_unsettled = ts

    if earliest_unsettled is not None:
        return earliest_unsettled

    # All requests are settled — checkpoint at the cutoff
    return int(cutoff)


_last_write: Dict[str, float] = {}


def _make_writer(creator_key: str):
    """Return a write function bound to the creator's cache file."""

    def _write(data: Dict[str, Any], force: bool = False) -> None:
        now = time.time()
        last = _last_write.get(creator_key, 0.0)
        if not force and (now - last) < WRITE_INTERVAL_SECONDS:
            return
        checkpoint_ts = _compute_checkpoint(data)
        path = _cache_path(creator_key)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"mechRequests": data, "checkpointTimestamp": checkpoint_ts},
                f, indent=2, sort_keys=True,
            )
        _last_write[creator_key] = now

    return _write


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_mech_requests(
    creators: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Fetch mech requests + delivers + IPFS contents for each creator.

    Uses a per-creator JSON cache under ``notebooks/.cache/`` so that
    already-delivered requests are not re-fetched from IPFS.

    Args:
        creators: MARKET_CREATORS config dict

    Returns:
        mapping of creator key -> {request_id: request_dict}
    """
    result = {}
    for key, cfg in creators.items():
        sender = cfg["safe_contract_address"].lower()
        print(f"Fetching mech requests for {cfg['name']}...")

        mech_requests, checkpoint_ts = _load_cache(key)
        writer = _make_writer(key)

        if checkpoint_ts > 0:
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(checkpoint_ts, tz=timezone.utc)
            print(f"  Resuming from checkpoint {dt.strftime('%Y-%m-%d %H:%M UTC')}")

        try:
            _fetch_requests_from_subgraph(sender, mech_requests, checkpoint_ts=checkpoint_ts)
            writer(mech_requests, force=True)

            errors = _populate_ipfs_contents(mech_requests, writer)
            if errors > 0:
                print(f"  {errors} IPFS errors, retrying...")
                _populate_ipfs_contents(mech_requests, writer)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"  Error: {exc}")
            traceback.print_exc()

        writer(mech_requests, force=True)
        result[key] = mech_requests
        print(f"  {cfg['name']}: {len(mech_requests)} requests")

    return result

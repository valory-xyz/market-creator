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

"""Server providing endpoints to approve proposed prediction markets through human interaction.

Workflow:
    1- Market creator service proposes markets through the "/propose_market" endpoint.
    2- User reviews proposed markets (e.g., via browser) through the "/proposed_markets" endpoint.
    3- User approves or rejects markets (e.g., using curl) through the "/approve_market" or "/reject_market" endpoints, respectively.
    4- Market creator service reads the approved markets through the "/approved_markets" endpoint.
    5- Market creator service marks the read market as processed through the "/process_market" endpoint.

CLI Usage:

    Usage for server running in http mode (replace by https if applies).

    - Service API:
        curl -X POST -H "Authorization: YOUR_API_KEY" -H "Content-Type: application/json" -d '{"id": "market_id", ...}' -k http://127.0.0.1:5000/propose_market
        curl -X POST -H "Authorization: YOUR_API_KEY" -H "Content-Type: application/json" -d '{"id": "market_id"}' -k http://127.0.0.1:5000/process_market
        curl -X POST -H "Authorization: YOUR_API_KEY" -H "Content-Type: application/json" -k http://127.0.0.1:5000/get_process_random_approved_market
        curl -X PUT -H "Authorization: YOUR_API_KEY" -H "Content-Type: application/json" -d '{"id": "market_id", ...}' -k http://127.0.0.1:5000/update_market
        curl -X PUT -H "Authorization: YOUR_API_KEY" -H "Content-Type: application/json" -d '{"id": "market_id", "new_id": "new_market_id"}' -k http://127.0.0.1:5000/update_market_id

    - User API
        curl -X POST -H "Authorization: YOUR_API_KEY" -H "Content-Type: application/json" -d '{"id": "market_id"}' -k http://127.0.0.1:5000/approve_market
        curl -X POST -H "Authorization: YOUR_API_KEY" -H "Content-Type: application/json" -d '{"id": "market_id"}' -k http://127.0.0.1:5000/reject_market

        curl -X DELETE -H "Authorization: YOUR_API_KEY" -k http://127.0.0.1:5000/clear_proposed_markets
        curl -X DELETE -H "Authorization: YOUR_API_KEY" -k http://127.0.0.1:5000/clear_approved_markets
        curl -X DELETE -H "Authorization: YOUR_API_KEY" -k http://127.0.0.1:5000/clear_rejected_markets
        curl -X DELETE -H "Authorization: YOUR_API_KEY" -k http://127.0.0.1:5000/clear_processed_markets
        curl -X DELETE -H "Authorization: YOUR_API_KEY" -k http://127.0.0.1:5000/clear_all
"""

import contextlib
import hashlib
import logging
import os
import secrets
import shutil
import sys
import threading
import time
import uuid
from datetime import datetime
from enum import Enum
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional, Tuple

from flask import Flask, Response, g, json, jsonify, render_template, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

CONFIG_FILE = os.getenv("MARKET_APPROVAL_SERVER_CONFIG_FILE", "server_config.json")
TMP_CONFIG_FILE = f"{CONFIG_FILE}.tmp"
LOG_FILE = "market_approval_server.log"
CERT_FILE = "server_cert.pem"
KEY_FILE = "server_key.pem"
DEFAULT_API_KEYS = {
    "454d31ff03590ff36836e991d3287b23146a7a84c79d082732b56268fe472823": "default_user"
}


class MarketState(str, Enum):
    """Market state"""

    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PROCESSED = "PROCESSED"


# Global variables to store the markets
proposed_markets: Dict[str, Any] = {}
approved_markets: Dict[str, Any] = {}
rejected_markets: Dict[str, Any] = {}
processed_markets: Dict[str, Any] = {}

# Dictionary to store the SHA-256 hash of valid API keys and user names.
api_keys: Dict[str, str] = {}

# The server is multi-threaded and every request reads or writes the global
# databases above, so requests are processed one at a time.
databases_lock = threading.Lock()


@app.before_request
def acquire_databases_lock() -> None:
    """Acquires the databases lock before processing a request."""
    databases_lock.acquire()
    try:
        g.databases_lock_acquired = True
    except BaseException:
        # An asynchronous exception (e.g. KeyboardInterrupt) raised before the
        # flag is set would otherwise leave the lock held forever.
        databases_lock.release()
        raise


@app.teardown_request
def release_databases_lock(_exc: Optional[BaseException] = None) -> None:
    """Releases the databases lock after processing a request."""
    if g.pop("databases_lock_acquired", False):
        databases_lock.release()


def get_databases() -> Dict[str, Dict[str, Any]]:
    """Returns all databases into a single object."""

    return {
        "proposed_markets": proposed_markets,
        "approved_markets": approved_markets,
        "rejected_markets": rejected_markets,
        "processed_markets": processed_markets,
    }


def load_config() -> None:
    """Loads the configuration from a JSON file."""
    global proposed_markets, approved_markets, rejected_markets, processed_markets, api_keys  # pylint: disable=global-statement
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            logger.info("Using config file: %s", CONFIG_FILE)
            data = json.load(f)
    except FileNotFoundError:
        # If the file is not found, set the dictionaries to empty
        logger.info("FileNotFoundError: %s", CONFIG_FILE)
        sys.exit(1)
    else:
        # If the file is found, set the dictionaries to the loaded data
        proposed_markets = data.get("proposed_markets", {})
        approved_markets = data.get("approved_markets", {})
        rejected_markets = data.get("rejected_markets", {})
        processed_markets = data.get("processed_markets", {})
        api_keys = data.get("api_keys", {})


def save_config() -> None:
    """Saves the configuration to a JSON file.

    The data is written to a temporary file which then replaces the config
    file, so a process killed mid-save leaves the previous config file intact.
    A failed save is logged and re-raised: the databases in memory then hold
    changes which are not on disk.
    """
    data = {
        "proposed_markets": proposed_markets,
        "approved_markets": approved_markets,
        "rejected_markets": rejected_markets,
        "processed_markets": processed_markets,
        "api_keys": api_keys,
    }
    try:
        with open(TMP_CONFIG_FILE, "w", encoding="utf-8", opener=_open_private) as f:
            json.dump(data, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        # The replaced file takes the permissions of the temporary one, so
        # give it those of the config file it replaces.
        with contextlib.suppress(FileNotFoundError):
            shutil.copymode(CONFIG_FILE, TMP_CONFIG_FILE)
        os.replace(TMP_CONFIG_FILE, CONFIG_FILE)
        _fsync_directory(os.path.dirname(CONFIG_FILE) or ".")
    except Exception:
        logger.exception("Failed to save config file: %s", CONFIG_FILE)
        raise


def _open_private(path: str, flags: int) -> int:
    """Opens a file which, when created, is readable by its owner only."""
    return os.open(path, flags, 0o600)


def _fsync_directory(path: str) -> None:
    """Flushes a directory to disk, so that a file rename in it survives a crash."""
    if not hasattr(os, "O_DIRECTORY"):
        # Directories cannot be opened on this platform (e.g. Windows).
        return
    dir_fd = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _is_expired(market_id: str, market: Dict[str, Any], now: int) -> bool:
    """Checks whether the resolution time of a market has passed.

    A market with a missing or malformed resolution time is kept.
    """
    try:
        return int(market["resolution_time"]) < now
    except (KeyError, TypeError, ValueError, OverflowError):
        logger.warning(
            "Proposed market %s has no valid resolution_time, not pruning it",
            market_id,
        )
        return False


def prune_expired_proposed_markets() -> bool:
    """Removes the proposed markets whose resolution time has passed.

    Such markets can no longer be created. The caller must save the config
    when this function returns True.

    :return: True if any market was pruned.
    """
    now = int(time.time())
    expired = [
        market_id
        for market_id, market in proposed_markets.items()
        if _is_expired(market_id, market, now)
    ]
    if not expired:
        return False

    for market_id in expired:
        del proposed_markets[market_id]
    logger.info("Removed %s expired proposed markets", len(expired))
    return True


def hash_api_key(m: str) -> str:
    """Generate the SHA-256 hash of the API key."""
    return hashlib.sha256(m.encode(encoding="utf-8")).hexdigest()


def check_api_key(api_key: Optional[str]) -> bool:
    """Checks the API key."""
    if api_key is None:
        return False
    return hash_api_key(api_key) in api_keys


@app.route("/proposed_markets", methods=["GET"])
@app.route("/approved_markets", methods=["GET"])
@app.route("/rejected_markets", methods=["GET"])
@app.route("/processed_markets", methods=["GET"])
@app.route("/all_markets", methods=["GET"])
def get_markets() -> Tuple[Response, int]:
    """Gets the markets from the corresponding database."""
    try:
        endpoint = request.path.split("/")[1]
        if endpoint == "proposed_markets":
            markets = proposed_markets
        elif endpoint == "approved_markets":
            markets = approved_markets
        elif endpoint == "rejected_markets":
            markets = rejected_markets
        elif endpoint == "processed_markets":
            markets = processed_markets
        elif endpoint == "all_markets":
            all_markets = {}
            all_markets.update(proposed_markets)
            all_markets.update(approved_markets)
            all_markets.update(rejected_markets)
            all_markets.update(processed_markets)
            markets = all_markets
        else:
            return jsonify({"error": "Invalid endpoint."}), 404

        response_json = json.dumps({endpoint: markets}, indent=4)
        return Response(response_json, status=200, content_type="application/json")
    except Exception as e:  # pylint: disable=broad-except
        return jsonify({"error": str(e)}), 500


@app.route("/proposed_market/<market_id>", methods=["GET"])
@app.route("/approved_market/<market_id>", methods=["GET"])
@app.route("/rejected_market/<market_id>", methods=["GET"])
@app.route("/processed_market/<market_id>", methods=["GET"])
def get_market_by_id(market_id: str) -> Tuple[Response, int]:
    """Retrieve a specific market by its ID from the corresponding market database."""
    try:
        endpoint = request.path.split("/")[1]

        if endpoint == "proposed_market":
            markets = proposed_markets
        elif endpoint == "approved_market":
            markets = approved_markets
        elif endpoint == "rejected_market":
            markets = rejected_markets
        elif endpoint == "processed_market":
            markets = processed_markets
        else:
            return jsonify({"error": "Invalid endpoint."}), 404

        if market_id in markets:
            market = markets[market_id]
            return jsonify(market), 200

        return (
            jsonify({"error": f"Market ID {market_id} not found in {endpoint}s."}),
            404,
        )
    except Exception as e:  # pylint: disable=broad-except
        return jsonify({"error": str(e)}), 500


@app.route("/market/<market_id>", methods=["GET"])
def get_market_by_id_all_databases(market_id: str) -> Tuple[Response, int]:
    """Retrieve a market by its ID from any database."""
    try:
        for _, db in get_databases().items():
            if market_id in db:
                return jsonify(db[market_id]), 200

        return (
            jsonify({"error": f"Market ID {market_id!r} not found in any database."}),
            404,
        )

    except Exception as e:  # pylint: disable=broad-except
        return jsonify({"error": str(e)}), 500


@app.route("/clear_proposed_markets", methods=["DELETE"])
@app.route("/clear_approved_markets", methods=["DELETE"])
@app.route("/clear_rejected_markets", methods=["DELETE"])
@app.route("/clear_processed_markets", methods=["DELETE"])
def clear_markets() -> Tuple[Response, int]:
    """Clears the markets from the corresponding database."""
    try:
        api_key = request.headers.get("Authorization")
        if not check_api_key(api_key):
            return jsonify({"error": "Unauthorized access. Invalid API key."}), 401

        endpoint = request.path.split("/")[1]
        market_msg = endpoint[len("clear_") :]
        if endpoint == "clear_proposed_markets":
            markets = proposed_markets
        elif endpoint == "clear_approved_markets":
            markets = approved_markets
        elif endpoint == "clear_rejected_markets":
            markets = rejected_markets
        elif endpoint == "clear_processed_markets":
            markets = processed_markets
        else:
            return jsonify({"error": "Invalid endpoint."}), 404

        markets.clear()
        save_config()
        return (
            jsonify({"info": f"Database {market_msg}_markets cleared successfully."}),
            200,
        )
    except Exception as e:  # pylint: disable=broad-except
        return jsonify({"error": str(e)}), 500


@app.route("/clear_all", methods=["DELETE"])
def clear_all_markets() -> Tuple[Response, int]:
    """Clears all market databases (proposed, approved, rejected, and processed markets)."""
    try:
        api_key = request.headers.get("Authorization")
        if not check_api_key(api_key):
            return jsonify({"error": "Unauthorized access. Invalid API key."}), 401

        proposed_markets.clear()
        approved_markets.clear()
        rejected_markets.clear()
        processed_markets.clear()
        save_config()
        return jsonify({"info": "All databases cleared successfully."}), 200
    except Exception as e:  # pylint: disable=broad-except
        return jsonify({"error": str(e)}), 500


@app.route("/propose_market", methods=["POST"])
def propose_market() -> Tuple[Response, int]:
    """Puts a market in the database of proposed markets"""
    try:
        api_key = request.headers.get("Authorization")
        if not check_api_key(api_key):
            return jsonify({"error": "Unauthorized access. Invalid API key."}), 401

        market = request.get_json()

        if "id" not in market:
            market["id"] = str(uuid.uuid4())

        market_id = str(market["id"])
        market_id = market_id.lower()
        market["id"] = market_id

        # Prune before the duplicate check, so that the id of an expired
        # market can be reused. The save below also stores the pruning.
        prune_expired_proposed_markets()

        if any(
            market_id in db
            for db in [
                proposed_markets,
                approved_markets,
                rejected_markets,
                processed_markets,
            ]
        ):
            return (
                jsonify(
                    {
                        "error": f"Market ID {market_id} already exists in database. Try using a different ID."
                    }
                ),
                400,
            )

        market["state"] = MarketState.PROPOSED
        market["utc_timestamp_proposed"] = int(datetime.utcnow().timestamp())
        proposed_markets[market_id] = market
        save_config()
        return jsonify({"info": f"Market ID {market_id} added successfully."}), 200
    except Exception as e:  # pylint: disable=broad-except
        return jsonify({"error": str(e)}), 500


@app.route("/approve_market", methods=["POST"])
@app.route("/reject_market", methods=["POST"])
@app.route("/process_market", methods=["POST"])
def move_market() -> Tuple[Response, int]:
    """Moves a market from one database to another accordingly."""

    try:
        api_key = request.headers.get("Authorization")
        if not check_api_key(api_key):
            return jsonify({"error": "Unauthorized access. Invalid API key."}), 401

        endpoint = request.path.split("/")[1]
        if endpoint == "approve_market":
            move_from = proposed_markets
            move_to = approved_markets
            new_state = MarketState.APPROVED
            action_msg = "approved"
        elif endpoint == "reject_market":
            move_from = proposed_markets
            move_to = rejected_markets
            new_state = MarketState.REJECTED
            action_msg = "rejected"
        elif endpoint == "process_market":
            move_from = approved_markets
            move_to = processed_markets
            new_state = MarketState.PROCESSED
            action_msg = "processed"
        else:
            return jsonify({"error": "Invalid endpoint."}), 404

        data = request.get_json()

        if "id" not in data:
            return jsonify({"error": "Invalid JSON format. Missing id."}), 400

        market_id = data["id"]
        market_id = market_id.lower()

        if market_id not in move_from:
            return jsonify({"error": f"Market ID {market_id} not found."}), 404

        market = move_from[market_id]
        del move_from[market_id]
        market["state"] = new_state
        market[f"utc_timestamp_{action_msg}"] = int(datetime.utcnow().timestamp())
        move_to[market_id] = market
        save_config()
        return jsonify({"info": f"Market ID {market_id} {action_msg}."}), 200

    except Exception as e:  # pylint: disable=broad-except
        return jsonify({"error": str(e)}), 500


@app.route("/get_process_random_approved_market", methods=["POST"])
def get_random_approved_market() -> Tuple[Response, int]:
    """Gets a random approved market and moves it to the processed markets."""
    try:
        api_key = request.headers.get("Authorization")
        if not check_api_key(api_key):
            return jsonify({"error": "Unauthorized access. Invalid API key."}), 401

        if not approved_markets:
            return (
                jsonify({"info": "No approved markets available."}),
                204,
            )

        market_id = secrets.choice(list(approved_markets.keys()))
        market = approved_markets[market_id]
        del approved_markets[market_id]
        market["state"] = MarketState.PROCESSED
        market["utc_timestamp_processed"] = int(datetime.utcnow().timestamp())
        processed_markets[market_id] = market
        save_config()
        return jsonify(market), 200

    except Exception as e:  # pylint: disable=broad-except
        return jsonify({"error": str(e)}), 500


@app.route("/update_market", methods=["PUT"])
def update_market() -> Tuple[Response, int]:
    """Updates an existing market in the specified database."""
    try:
        api_key = request.headers.get("Authorization")
        if not check_api_key(api_key):
            return jsonify({"error": "Unauthorized access. Invalid API key."}), 401

        market = request.get_json()
        if "id" not in market:
            return jsonify({"error": "Invalid JSON format. Missing id."}), 400

        market_id = market["id"]
        market_id = market_id.lower()

        # Check if the market exists in any of the databases
        databases = [
            proposed_markets,
            approved_markets,
            rejected_markets,
            processed_markets,
        ]
        found = False
        for db in databases:
            if market_id in db:
                found = True
                existing_market = db[market_id]
                existing_market["utc_timestamp_updated"] = int(
                    datetime.utcnow().timestamp()
                )
                for key, value in market.items():
                    existing_market[key] = value

        if found:
            save_config()
            return (
                jsonify({"info": f"Market ID {market_id} updated successfully."}),
                200,
            )

        return (
            jsonify({"error": f"Market ID {market_id} not found in the database."}),
            404,
        )

    except Exception as e:  # pylint: disable=broad-except
        return jsonify({"error": str(e)}), 500


@app.route("/update_market_id", methods=["PUT"])
def update_market_id() -> (
    Tuple[Response, int]
):  # pylint: disable=too-many-return-statements
    """Update the market ID in any of the databases if the market exists."""
    try:
        api_key = request.headers.get("Authorization")
        if not check_api_key(api_key):
            return jsonify({"error": "Unauthorized access. Invalid API key."}), 401

        data = request.get_json()
        current_market_id = data.get("id")
        new_market_id = data.get("new_id")

        if not current_market_id:
            return jsonify({"error": "'id' is required."}), 400
        if not new_market_id:
            return jsonify({"error": "'new_id' is required."}), 400
        if current_market_id == new_market_id:
            return jsonify({"error": "'id' is equal to 'new_id' in the request."}), 409

        # The next line is intentionally commented to allow fixing uppercase market_ids externally.
        # current_market_id = current_market_id.lower()  # noqa
        new_market_id = new_market_id.lower()

        databases = get_databases()

        if any(new_market_id in db for _, db in databases.items()):
            return (
                jsonify(
                    {
                        "error": f"Market ID {new_market_id} already exists in database. Try using a different ID."
                    }
                ),
                409,
            )

        for db_name, db in databases.items():
            if current_market_id in db:
                db[new_market_id] = db.pop(current_market_id)
                db[new_market_id]["id"] = new_market_id
                db[new_market_id]["utc_timestamp_updated"] = int(
                    datetime.utcnow().timestamp()
                )
                save_config()
                return (
                    jsonify(
                        {
                            "message": f"Market ID {current_market_id!r} successfully changed to {new_market_id!r} in {db_name}."
                        }
                    ),
                    200,
                )

        return (
            jsonify(
                {"error": f"Market ID {current_market_id!r} not found in the database."}
            ),
            404,
        )

    except Exception as e:  # pylint: disable=broad-except
        return jsonify({"error": str(e)}), 500


@app.route("/", methods=["GET"])
def main_page() -> Tuple[Response, int]:
    """Render the main page with links to the GET endpoints."""
    server_ip = request.host_url.rstrip("/")
    return render_template("index.html", server_ip=server_ip)


# --------------------------
# Server process starts here
# --------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] - %(message)s",
    handlers=[
        RotatingFileHandler(
            LOG_FILE,
            maxBytes=1024 * 1024,  # 1 MB
            backupCount=10,  # Keep 10 backup files
        ),
        logging.StreamHandler(),  # Log to console as well
    ],
)
logger = logging.getLogger(__name__)

with contextlib.suppress(OSError):
    # Left behind by a process killed mid-save.
    os.remove(TMP_CONFIG_FILE)
load_config()
if prune_expired_proposed_markets():
    try:
        save_config()
    except OSError:
        # Already logged by save_config. Keep serving, e.g. on a read-only volume.
        logger.warning("The pruned config is held in memory only")
if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
    # Run with SSL/TLS (HTTPS)
    logger.info("Running server in HTTPS mode")
    app.run(host="0.0.0.0", debug=False, ssl_context=(CERT_FILE, KEY_FILE))  # nosec
else:
    # Run without SSL/TLS (HTTP)
    logger.info("Running server in HTTP mode")
    app.run(host="0.0.0.0", debug=False)  # nosec

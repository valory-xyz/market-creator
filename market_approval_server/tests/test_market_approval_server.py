# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2026 Valory AG
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

"""Tests for the market approval server."""

import hashlib
import importlib
import json
import os
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, Iterator

import pytest

MODULE_NAME = "market_approval_server.market_approval_server"
API_KEY = "test_api_key"
HEADERS = {"Authorization": API_KEY}
PAST = int(time.time()) - 86400
FUTURE = int(time.time()) + 86400

ServerLoader = Callable[..., ModuleType]


def _market(market_id: str, resolution_time: Any) -> Dict[str, Any]:
    """Build a proposed market."""
    return {"id": market_id, "question": "?", "resolution_time": resolution_time}


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """Path of the server config file."""
    return tmp_path / "server_config.json"


@pytest.fixture
def load_server(
    tmp_path: Path, config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[ServerLoader]:
    """Return a function that imports the server on a given initial state.

    The server loads its config at import time, because production starts it
    with `flask run`. FLASK_RUN_FROM_CLI makes `app.run()` return immediately,
    as it does there.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MARKET_APPROVAL_SERVER_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("FLASK_RUN_FROM_CLI", "true")

    def _load(**databases: Dict[str, Any]) -> ModuleType:
        state = {
            "proposed_markets": {},
            "approved_markets": {},
            "rejected_markets": {},
            "processed_markets": {},
            "api_keys": {hashlib.sha256(API_KEY.encode()).hexdigest(): "tester"},
        }
        state.update(databases)
        config_file.write_text(json.dumps(state), encoding="utf-8")
        sys.modules.pop(MODULE_NAME, None)
        return importlib.import_module(MODULE_NAME)

    yield _load
    sys.modules.pop(MODULE_NAME, None)


def _on_disk(config_file: Path) -> Dict[str, Any]:
    """Read the config file."""
    return json.loads(config_file.read_text(encoding="utf-8"))


def test_startup_prunes_expired_proposed_markets(
    load_server: ServerLoader, config_file: Path
) -> None:
    """Startup removes past proposed markets and keeps future and malformed ones."""
    server = load_server(
        proposed_markets={
            "past": _market("past", PAST),
            "past_str": _market("past_str", str(PAST)),
            "future": _market("future", FUTURE),
            "infinite": _market("infinite", float("inf")),
            "text": _market("text", "tomorrow"),
            "missing": {"id": "missing"},
        },
        processed_markets={"done": _market("done", PAST)},
    )

    kept = {"future", "infinite", "text", "missing"}
    assert set(server.proposed_markets) == kept
    assert set(_on_disk(config_file)["proposed_markets"]) == kept
    assert set(_on_disk(config_file)["processed_markets"]) == {"done"}


def test_startup_removes_leftover_tmp_file(
    load_server: ServerLoader, config_file: Path
) -> None:
    """Startup removes the temporary file left by a process killed mid-save."""
    tmp_file = Path(f"{config_file}.tmp")
    tmp_file.write_text("{", encoding="utf-8")

    load_server()

    assert not tmp_file.exists()


def test_startup_survives_a_failing_save(
    load_server: ServerLoader, config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Startup serves the pruned state from memory when the config cannot be written."""

    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise PermissionError("read-only")

    monkeypatch.setattr(os, "replace", _raise)

    server = load_server(proposed_markets={"past": _market("past", PAST)})

    assert not server.proposed_markets
    assert set(_on_disk(config_file)["proposed_markets"]) == {"past"}


def test_save_config_is_atomic(
    load_server: ServerLoader, config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing save leaves the previous config file intact."""
    server = load_server(proposed_markets={"future": _market("future", FUTURE)})

    server.save_config()
    assert not Path(f"{config_file}.tmp").exists()
    before = config_file.read_text(encoding="utf-8")

    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("killed mid-save")

    monkeypatch.setattr(server.json, "dump", _raise)
    server.proposed_markets["other"] = _market("other", FUTURE)
    with pytest.raises(RuntimeError):
        server.save_config()

    assert config_file.read_text(encoding="utf-8") == before


def test_propose_market_can_reuse_an_expired_id(
    load_server: ServerLoader, config_file: Path
) -> None:
    """Proposing prunes expired markets before the duplicate-id check."""
    server = load_server()
    server.proposed_markets["reused"] = _market("reused", PAST)
    client = server.app.test_client()

    response = client.post(
        "/propose_market", json=_market("reused", FUTURE), headers=HEADERS
    )

    assert response.status_code == 200
    assert _on_disk(config_file)["proposed_markets"]["reused"]["resolution_time"] == (
        FUTURE
    )


def test_propose_market_rejects_a_duplicate_id(load_server: ServerLoader) -> None:
    """Proposing an id which is still in a database fails."""
    server = load_server(proposed_markets={"future": _market("future", FUTURE)})
    client = server.app.test_client()

    response = client.post(
        "/propose_market", json=_market("future", FUTURE), headers=HEADERS
    )

    assert response.status_code == 400


def test_lock_is_released_after_every_request(load_server: ServerLoader) -> None:
    """The databases lock is released after a 404, an error and a success."""
    server = load_server()
    client = server.app.test_client()

    assert client.get("/unknown").status_code == 404
    assert not server.databases_lock.locked()
    # A non-JSON body makes the handler fail.
    assert client.post("/propose_market", data="x", headers=HEADERS).status_code == 500
    assert not server.databases_lock.locked()
    assert client.get("/proposed_markets").status_code == 200
    assert not server.databases_lock.locked()

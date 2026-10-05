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
import threading
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
    """Startup keeps serving the state on disk when the config cannot be written."""

    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise PermissionError("read-only")

    monkeypatch.setattr(os, "replace", _raise)

    server = load_server(proposed_markets={"past": _market("past", PAST)})

    assert set(server.proposed_markets) == {"past"}
    assert set(_on_disk(config_file)["proposed_markets"]) == {"past"}
    assert server.app.test_client().get("/proposed_markets").status_code == 200


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
    assert set(server.proposed_markets) == {"future"}


def test_failed_save_exits_when_the_databases_cannot_be_restored(
    load_server: ServerLoader, config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The process exits when a save fails and the config file cannot be reloaded."""
    server = load_server()
    exit_codes = []

    def _replace(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("disk full")

    def _exit(code: int) -> None:
        exit_codes.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(os, "replace", _replace)
    monkeypatch.setattr(os, "_exit", _exit)
    config_file.write_text("{", encoding="utf-8")
    server.proposed_markets["unsaved"] = _market("unsaved", FUTURE)

    with pytest.raises(SystemExit):
        server.save_config()

    assert exit_codes == [1]


def test_a_request_which_fails_to_save_changes_nothing(
    load_server: ServerLoader, config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A market whose save failed is not kept in memory, so a retry succeeds."""
    server = load_server(approved_markets={"approved": _market("approved", FUTURE)})
    client = server.app.test_client()

    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("disk full")

    with monkeypatch.context() as patched:
        patched.setattr(os, "replace", _raise)
        response = client.post(
            "/propose_market", json=_market("new", FUTURE), headers=HEADERS
        )
        assert response.status_code == 500
        response = client.post("/get_process_random_approved_market", headers=HEADERS)
        assert response.status_code == 500

    assert "new" not in server.proposed_markets
    assert set(server.approved_markets) == {"approved"}
    assert not server.processed_markets
    assert set(_on_disk(config_file)["approved_markets"]) == {"approved"}

    response = client.post(
        "/propose_market", json=_market("new", FUTURE), headers=HEADERS
    )
    assert response.status_code == 200
    response = client.post("/get_process_random_approved_market", headers=HEADERS)
    assert response.status_code == 200
    assert response.get_json()["id"] == "approved"


def test_save_config_survives_a_failing_directory_flush(
    load_server: ServerLoader, config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A save succeeds when only the flush of the directory fails."""
    server = load_server()

    def _raise(_path: str) -> None:
        raise OSError("fsync is not supported on this mount")

    monkeypatch.setattr(server, "_fsync_directory", _raise)
    server.proposed_markets["future"] = _market("future", FUTURE)

    server.save_config()

    assert set(_on_disk(config_file)["proposed_markets"]) == {"future"}


@pytest.mark.skipif(os.name == "nt", reason="POSIX file permissions")
@pytest.mark.parametrize("mode", [0o600, 0o644])
def test_save_config_keeps_the_file_permissions(
    load_server: ServerLoader, config_file: Path, mode: int
) -> None:
    """A save does not change the permissions of the config file."""
    server = load_server()
    config_file.chmod(mode)

    server.save_config()

    assert config_file.stat().st_mode & 0o777 == mode


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


def test_main_page_does_not_wait_for_the_lock(load_server: ServerLoader) -> None:
    """The main page answers while another request holds the databases lock."""
    server = load_server()
    client = server.app.test_client()
    status_codes = []

    def _get_main_page() -> None:
        status_codes.append(client.get("/").status_code)

    with server.databases_lock:
        thread = threading.Thread(target=_get_main_page, daemon=True)
        thread.start()
        thread.join(timeout=10)
        assert not thread.is_alive()

    assert status_codes == [200]

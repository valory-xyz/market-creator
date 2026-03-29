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

"""Tests for the payloads of the OmenFundsRecovererAbciApp."""

import json

import pytest

from packages.valory.skills.omen_funds_recoverer_abci.payloads import (
    BuildMultisendPayload,
    RecoveryTxsPayload,
)

SENDER = "sender_address"


@pytest.mark.parametrize(
    "payload_class, payload_kwargs",
    [
        (
            RecoveryTxsPayload,
            {"content": "[]"},
        ),
        (
            RecoveryTxsPayload,
            {"content": json.dumps([{"to": "0xAddr", "data": "0x1234", "value": 0}])},
        ),
        (
            BuildMultisendPayload,
            {"tx_submitter": "test_submitter", "tx_hash": "0xhash123"},
        ),
    ],
)
def test_payload_construction_and_attributes(
    payload_class: type, payload_kwargs: dict
) -> None:
    """Test payload construction, attributes, and serialization roundtrip."""
    payload = payload_class(sender=SENDER, **payload_kwargs)

    # Verify sender
    assert payload.sender == SENDER

    # Verify all kwargs are accessible as attributes
    for key, value in payload_kwargs.items():
        assert getattr(payload, key) == value

    # Verify data dict matches kwargs
    assert payload.data == payload_kwargs

    # Verify JSON serialization roundtrip
    assert payload_class.from_json(payload.json) == payload  # type: ignore[attr-defined]


def test_recovery_txs_payload_empty_list() -> None:
    """Test RecoveryTxsPayload with empty list content."""
    payload = RecoveryTxsPayload(sender=SENDER, content="[]")
    assert payload.content == "[]"
    assert payload.data == {"content": "[]"}


def test_recovery_txs_payload_with_txs() -> None:
    """Test RecoveryTxsPayload with actual tx dicts."""
    txs = [
        {"to": "0xAddr1", "data": "0xaabb", "value": 0},
        {"to": "0xAddr2", "data": "0xccdd", "value": 0},
    ]
    content = json.dumps(txs)
    payload = RecoveryTxsPayload(sender=SENDER, content=content)
    assert payload.content == content
    assert json.loads(payload.content) == txs


def test_build_multisend_payload_defaults() -> None:
    """Test BuildMultisendPayload with default (None) values."""
    payload = BuildMultisendPayload(sender=SENDER)
    assert payload.tx_submitter is None
    assert payload.tx_hash is None
    assert payload.data == {"tx_submitter": None, "tx_hash": None}


def test_build_multisend_payload_partial() -> None:
    """Test BuildMultisendPayload with only tx_submitter set."""
    payload = BuildMultisendPayload(sender=SENDER, tx_submitter="round_id")
    assert payload.tx_submitter == "round_id"
    assert payload.tx_hash is None


def test_build_multisend_payload_full() -> None:
    """Test BuildMultisendPayload with both fields set."""
    payload = BuildMultisendPayload(
        sender=SENDER, tx_submitter="round_id", tx_hash="0xabc"
    )
    assert payload.tx_submitter == "round_id"
    assert payload.tx_hash == "0xabc"
    assert payload.data == {"tx_submitter": "round_id", "tx_hash": "0xabc"}

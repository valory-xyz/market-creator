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

from packages.valory.skills.omen_funds_recoverer_abci.payloads import (
    BuildMultisendPayload,
    RecoveryTxsPayload,
)

SENDER = "sender_address"


def test_recovery_txs_payload() -> None:
    """Test RecoveryTxsPayload construction."""
    payload = RecoveryTxsPayload(sender=SENDER, content="[]")
    assert payload.sender == SENDER
    assert payload.content == "[]"


def test_recovery_txs_payload_roundtrip() -> None:
    """Test RecoveryTxsPayload JSON roundtrip."""
    payload = RecoveryTxsPayload(sender=SENDER, content='[{"to": "0x1"}]')
    restored = RecoveryTxsPayload.from_json(payload.json)  # type: ignore[attr-defined]
    assert restored == payload


def test_build_multisend_payload_with_tx() -> None:
    """Test BuildMultisendPayload with a valid transaction."""
    payload = BuildMultisendPayload(
        sender=SENDER, tx_submitter="build_multisend_round", tx_hash="0xhash"
    )
    assert payload.tx_submitter == "build_multisend_round"
    assert payload.tx_hash == "0xhash"


def test_build_multisend_payload_defaults() -> None:
    """Test BuildMultisendPayload with default None values."""
    payload = BuildMultisendPayload(sender=SENDER)
    assert payload.tx_submitter is None
    assert payload.tx_hash is None


def test_build_multisend_payload_roundtrip() -> None:
    """Test BuildMultisendPayload JSON roundtrip."""
    payload = BuildMultisendPayload(
        sender=SENDER, tx_submitter="build_multisend_round", tx_hash="0xhash"
    )
    restored = BuildMultisendPayload.from_json(payload.json)  # type: ignore[attr-defined]
    assert restored == payload

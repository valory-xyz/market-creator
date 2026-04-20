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

"""Tests for the payloads of the OmenCtRedeemTokensAbciApp."""

from packages.valory.skills.omen_ct_redeem_tokens_abci.payloads import (
    CtRedeemTokensPayload,
)

SENDER = "sender_address"


def test_ct_redeem_payload_with_tx() -> None:
    """Test CtRedeemTokensPayload with a valid transaction."""
    payload = CtRedeemTokensPayload(
        sender=SENDER, tx_submitter="omen_ct_redeem_tokens", tx_hash="0xhash"
    )
    assert payload.sender == SENDER
    assert payload.tx_submitter == "omen_ct_redeem_tokens"
    assert payload.tx_hash == "0xhash"


def test_ct_redeem_payload_defaults() -> None:
    """Test CtRedeemTokensPayload with default None values."""
    payload = CtRedeemTokensPayload(sender=SENDER)
    assert payload.tx_submitter is None
    assert payload.tx_hash is None


def test_ct_redeem_payload_roundtrip() -> None:
    """Test CtRedeemTokensPayload JSON roundtrip."""
    payload = CtRedeemTokensPayload(
        sender=SENDER, tx_submitter="omen_ct_redeem_tokens", tx_hash="0xhash"
    )
    restored = CtRedeemTokensPayload.from_json(payload.json)  # type: ignore[attr-defined]
    assert restored == payload


def test_ct_redeem_payload_roundtrip_none() -> None:
    """Test CtRedeemTokensPayload JSON roundtrip with default None values."""
    payload = CtRedeemTokensPayload(sender=SENDER)
    restored = CtRedeemTokensPayload.from_json(payload.json)  # type: ignore[attr-defined]
    assert restored == payload

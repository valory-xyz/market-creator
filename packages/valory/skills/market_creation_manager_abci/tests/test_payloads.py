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

"""Tests for the payloads of the MarketCreationManagerAbciApp."""

import pytest

from packages.valory.skills.market_creation_manager_abci.payloads import (
    ApproveMarketsPayload,
    CollectProposedMarketsPayload,
    CollectRandomnessPayload,
    MultisigTxPayload,
    PostTxPayload,
    RetrieveApprovedMarketPayload,
    SelectKeeperPayload,
)

SENDER = "sender_address"


@pytest.mark.parametrize(
    "payload_class, payload_kwargs",
    [
        (
            CollectRandomnessPayload,
            {"round_id": 1, "randomness": "0xabc123"},
        ),
        (
            SelectKeeperPayload,
            {"keeper": "0xkeeper_address"},
        ),
        (
            RetrieveApprovedMarketPayload,
            {"content": '{"market": "test_market"}'},
        ),
        (
            PostTxPayload,
            {"content": "DONE_PAYLOAD"},
        ),
        (
            CollectProposedMarketsPayload,
            {"content": '{"proposed_markets": []}'},
        ),
        (
            ApproveMarketsPayload,
            {
                "content": '{"approved": true}',
                "approved_markets_count": 3,
                "timestamp": 1000000,
            },
        ),
        (
            MultisigTxPayload,
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


def test_multisig_tx_payload_defaults() -> None:
    """Test MultisigTxPayload with default (None) values."""
    payload = MultisigTxPayload(sender=SENDER)
    assert payload.tx_submitter is None
    assert payload.tx_hash is None
    assert payload.data == {"tx_submitter": None, "tx_hash": None}


def test_multisig_tx_payload_partial() -> None:
    """Test MultisigTxPayload with only tx_submitter set."""
    payload = MultisigTxPayload(sender=SENDER, tx_submitter="round_id")
    assert payload.tx_submitter == "round_id"
    assert payload.tx_hash is None

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

"""Tests for payloads in the omen_fpmm_remove_liquidity_abci skill."""

from packages.valory.skills.omen_fpmm_remove_liquidity_abci.payloads import (
    FpmmRemoveLiquidityPayload,
)


class TestFpmmRemoveLiquidityPayload:
    """Tests for FpmmRemoveLiquidityPayload."""

    def test_payload_defaults(self) -> None:
        """Test that payload has None defaults for optional fields."""
        payload = FpmmRemoveLiquidityPayload(sender="0xsender")
        assert payload.tx_submitter is None
        assert payload.tx_hash is None

    def test_payload_with_values(self) -> None:
        """Test that payload stores provided values."""
        payload = FpmmRemoveLiquidityPayload(
            sender="0xsender",
            tx_submitter="omen_fpmm_remove_liquidity",
            tx_hash="0xdeadbeef",
        )
        assert payload.tx_submitter == "omen_fpmm_remove_liquidity"
        assert payload.tx_hash == "0xdeadbeef"

    def test_payload_is_frozen(self) -> None:
        """Test that payload is immutable (frozen dataclass)."""
        from dataclasses import FrozenInstanceError

        payload = FpmmRemoveLiquidityPayload(sender="0xsender", tx_hash="0xhash")
        try:
            payload.tx_hash = "other"  # type: ignore[misc]
            raise AssertionError("Expected FrozenInstanceError")
        except FrozenInstanceError:
            pass

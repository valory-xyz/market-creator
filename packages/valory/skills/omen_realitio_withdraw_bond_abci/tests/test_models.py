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

"""Tests for models."""

from typing import Any
from unittest.mock import patch

from packages.valory.skills.abstract_round_abci.models import BaseParams
from packages.valory.skills.omen_realitio_withdraw_bond_abci.models import (
    RealitioSubgraph,
    RealitioWithdrawBondParams,
    SharedState,
)


def test_import() -> None:
    """Test that the module can be imported and the types are defined."""
    assert RealitioWithdrawBondParams is not None
    assert RealitioSubgraph is not None
    assert SharedState is not None


def test_params_init_carries_required_params() -> None:
    """The params constructor consumes all expected kwargs."""

    def fake_ensure(self: Any, key: str, kwargs: dict, type_: type) -> Any:
        return kwargs.pop(key)

    kwargs: dict = {
        "realitio_withdraw_bond_batch_size": 10,
        "min_realitio_withdraw_balance": 10**19,
        "realitio_contract": "0xRealitio",
    }
    instance = RealitioWithdrawBondParams.__new__(RealitioWithdrawBondParams)
    with (
        patch.object(RealitioWithdrawBondParams, "_ensure", new=fake_ensure),
        patch.object(BaseParams, "__init__", return_value=None),
    ):
        RealitioWithdrawBondParams.__init__(instance, **kwargs)
    assert instance.realitio_withdraw_bond_batch_size == 10
    assert instance.min_realitio_withdraw_balance == 10**19
    assert instance.realitio_contract == "0xRealitio"
    # realitio_start_block was deleted from the design.
    assert not hasattr(instance, "realitio_start_block")


def test_shared_state_abci_app_cls() -> None:
    """SharedState carries the correct abci_app_cls."""
    from packages.valory.skills.omen_realitio_withdraw_bond_abci.rounds import (
        OmenRealitioWithdrawBondAbciApp,
    )

    assert SharedState.abci_app_cls is OmenRealitioWithdrawBondAbciApp

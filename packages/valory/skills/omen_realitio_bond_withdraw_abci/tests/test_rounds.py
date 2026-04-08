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

"""Test the rounds.py module of the skill."""

from unittest.mock import patch

from packages.valory.skills.abstract_round_abci.base import AbciAppDB
from packages.valory.skills.omen_realitio_bond_withdraw_abci.rounds import (
    Event,
    FinishedWithRealitioBondWithdrawTxRound,
    FinishedWithoutRealitioBondWithdrawTxRound,
    OmenRealitioBondWithdrawAbciApp,
    RealitioBondWithdrawRound,
    SynchronizedData,
)


def test_import() -> None:
    """Test that the module can be imported and key symbols are present."""
    assert Event is not None
    assert SynchronizedData is not None
    assert RealitioBondWithdrawRound is not None
    assert FinishedWithRealitioBondWithdrawTxRound is not None
    assert FinishedWithoutRealitioBondWithdrawTxRound is not None
    assert OmenRealitioBondWithdrawAbciApp is not None


def test_abci_app_transition_function_shape() -> None:
    """The FSM has one consensus round with two final states."""
    tf = OmenRealitioBondWithdrawAbciApp.transition_function
    # RealitioBondWithdrawRound has exactly 4 event → state entries.
    assert len(tf[RealitioBondWithdrawRound]) == 4
    # DONE routes to the "with tx" final state.
    assert (
        tf[RealitioBondWithdrawRound][Event.DONE]
        is FinishedWithRealitioBondWithdrawTxRound
    )
    # NONE / NO_MAJORITY / ROUND_TIMEOUT all route to the "without tx" final state.
    for ev in (Event.NONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT):
        assert (
            tf[RealitioBondWithdrawRound][ev]
            is FinishedWithoutRealitioBondWithdrawTxRound
        )
    # Final states have empty transition functions.
    assert tf[FinishedWithRealitioBondWithdrawTxRound] == {}
    assert tf[FinishedWithoutRealitioBondWithdrawTxRound] == {}


def test_abci_app_final_states() -> None:
    """The two final states are both registered."""
    assert OmenRealitioBondWithdrawAbciApp.final_states == {
        FinishedWithRealitioBondWithdrawTxRound,
        FinishedWithoutRealitioBondWithdrawTxRound,
    }


def test_abci_app_initial_state() -> None:
    """The only initial state is RealitioBondWithdrawRound."""
    assert OmenRealitioBondWithdrawAbciApp.initial_states == {RealitioBondWithdrawRound}
    assert (
        OmenRealitioBondWithdrawAbciApp.initial_round_cls is RealitioBondWithdrawRound
    )


def test_abci_app_event_to_timeout() -> None:
    """ROUND_TIMEOUT is set to 120 seconds."""
    assert (
        OmenRealitioBondWithdrawAbciApp.event_to_timeout[Event.ROUND_TIMEOUT] == 120.0
    )


def test_db_post_conditions_require_tx_hash_on_with_tx_final() -> None:
    """The with-tx final state posts the tx_hash to db; the without-tx does not."""
    post = OmenRealitioBondWithdrawAbciApp.db_post_conditions
    assert post[FinishedWithRealitioBondWithdrawTxRound] == {"most_voted_tx_hash"}
    assert post[FinishedWithoutRealitioBondWithdrawTxRound] == set()


def test_synchronized_data_properties() -> None:
    """Test that SynchronizedData exposes the expected typed properties.

    Covers tx_submitter, most_voted_tx_hash, and the
    participant_to_realitio_bond_withdraw_tx mapping.
    """
    initial_data: dict = {
        "tx_submitter": ["omen_realitio_bond_withdraw"],
        "most_voted_tx_hash": ["0xdeadbeef"],
        # The collection field's raw value is read via db.get_strict
        # and then passed to CollectionRound.deserialize_collection.
        # We use a placeholder here and mock the deserializer.
        "participant_to_realitio_bond_withdraw_tx": ["<serialized>"],
    }
    db = AbciAppDB(setup_data=initial_data)
    synced = SynchronizedData(db=db)

    assert synced.tx_submitter == "omen_realitio_bond_withdraw"
    assert synced.most_voted_tx_hash == "0xdeadbeef"

    # Exercise the _get_deserialized method body (lines 62-63) by
    # patching CollectionRound.deserialize_collection so the real
    # method path runs without a real serialized payload.
    sentinel: dict = {"agent_0": "payload"}
    with patch(
        "packages.valory.skills.omen_realitio_bond_withdraw_abci.rounds.CollectionRound.deserialize_collection",
        return_value=sentinel,
    ) as mock_deserialize:
        result = synced.participant_to_realitio_bond_withdraw_tx
    assert result is sentinel
    mock_deserialize.assert_called_once_with("<serialized>")

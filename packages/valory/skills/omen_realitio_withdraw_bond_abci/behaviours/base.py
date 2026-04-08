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

"""Base behaviour and helpers for the omen_realitio_withdraw_bond_abci skill."""

import json
from abc import ABC
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple, cast

from packages.valory.contracts.gnosis_safe.contract import (
    GnosisSafeContract,
    SafeOperation,
)
from packages.valory.contracts.multisend.contract import (
    MultiSendContract,
    MultiSendOperation,
)
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.abstract_round_abci.behaviours import BaseBehaviour
from packages.valory.skills.omen_realitio_withdraw_bond_abci.models import (
    RealitioWithdrawBondParams,
    SharedState,
)
from packages.valory.skills.omen_realitio_withdraw_bond_abci.rounds import (
    SynchronizedData,
)
from packages.valory.skills.transaction_settlement_abci.payload_tools import (
    hash_payload_to_hex,
)

HTTP_OK = 200
SAFE_TX_GAS = 0
ETHER_VALUE = 0

# Zero bytes32 — meaning depends on context. In Realitio it indicates an
# already-claimed question (the on-chain history hash is cleared on
# successful claim) and is the ``last_history_hash`` value
# ``claimWinnings`` walks back to after the very first (oldest) entry in
# the response history.
ZERO_BYTES32 = b"\x00" * 32

SKILL_LOG_PREFIX = "[OmenRealitioWithdrawBond]"


# Type alias for the 4-tuple expected by Realitio.claimWinnings:
#   (history_hashes, addresses, bonds, answers), all in reverse-
#   chronological order (newest first), all the same length.
ClaimParamsType = Tuple[List[Any], List[str], List[int], List[Any]]


def wei_to_str(wei: int, unit: str = "xDAI") -> str:
    """Format a wei amount with a human-readable equivalent."""
    return f"{wei / 10**18:.4f} {unit}"


def to_content(query: str) -> bytes:
    """Convert the given query string to payload content."""
    finalized_query = {"query": query}
    encoded_query = json.dumps(finalized_query, sort_keys=True).encode("utf-8")
    return encoded_query


def get_callable_name(method: Callable) -> str:
    """Return callable name."""
    return getattr(method, "__name__")  # noqa: B009


def assemble_claim_params(answered: List[Dict[str, Any]]) -> ClaimParamsType:
    """Convert a chronological event list into the claimWinnings 4-tuple.

    Realitio v2.1 ``claimWinnings`` walks the four arrays in
    reverse-chronological order (newest first) and verifies that each
    ``history_hashes[i]`` equals the history hash that existed *before*
    the i-th entry was posted — i.e. the stored hash of the older
    chronological entry, or ``ZERO_BYTES32`` for the first entry.

    :param answered: LogNewAnswer events in chronological order (oldest first).
    :return: ``(history_hashes, addresses, bonds, answers)`` reverse-chronological.
    """
    history_hashes: List[Any] = []
    addresses: List[str] = []
    bonds: List[int] = []
    answers: List[Any] = []
    for chrono_idx in range(len(answered) - 1, -1, -1):
        args = answered[chrono_idx]["args"]
        if chrono_idx == 0:
            prior_hash: Any = ZERO_BYTES32
        else:
            prior_hash = answered[chrono_idx - 1]["args"]["history_hash"]
        history_hashes.append(prior_hash)
        addresses.append(args["user"])
        bonds.append(int(args["bond"]))
        answers.append(args["answer"])
    return history_hashes, addresses, bonds, answers


class RealitioWithdrawBondBaseBehaviour(BaseBehaviour, ABC):
    """Base behaviour for the omen_realitio_withdraw_bond_abci skill."""

    @property
    def synchronized_data(self) -> SynchronizedData:
        """Return the synchronized data."""
        return cast(SynchronizedData, super().synchronized_data)

    @property
    def params(self) -> RealitioWithdrawBondParams:
        """Return the params."""
        return cast(RealitioWithdrawBondParams, super().params)

    @property
    def last_synced_timestamp(self) -> int:
        """Get last synced timestamp, guaranteed consistent across 2/3 of agents."""
        state = cast(SharedState, self.context.state)
        last_timestamp = (
            state.round_sequence.last_round_transition_timestamp.timestamp()
        )
        return int(last_timestamp)

    @property
    def shared_state(self) -> SharedState:
        """Get the shared state."""
        return cast(SharedState, self.context.state)

    def _get_safe_tx_hash(
        self,
        to_address: str,
        data: bytes,
        value: int = ETHER_VALUE,
        safe_tx_gas: int = SAFE_TX_GAS,
        operation: int = SafeOperation.CALL.value,
    ) -> Generator[None, None, Optional[str]]:
        """Prepare and return the safe tx hash."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.synchronized_data.safe_contract_address,
            contract_id=str(GnosisSafeContract.contract_id),
            contract_callable="get_raw_safe_transaction_hash",
            to_address=to_address,
            value=value,
            data=data,
            safe_tx_gas=safe_tx_gas,
            operation=operation,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Couldn't get safe hash. "
                f"Expected response performative {ContractApiMessage.Performative.STATE}, "
                f"received {response.performative.value}."
            )
            return None

        tx_hash = cast(str, response.state.body["tx_hash"])[2:]
        return tx_hash

    def _to_multisend(
        self, transactions: List[Dict]
    ) -> Generator[None, None, Optional[str]]:
        """Bundle transactions into a MultiSend and return the safe payload hash."""
        multi_send_txs = []
        for transaction in transactions:
            transaction = {
                "operation": transaction.get("operation", MultiSendOperation.CALL),
                "to": transaction["to"],
                "value": transaction["value"],
                "data": transaction.get("data", b""),
            }
            multi_send_txs.append(transaction)

        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,  # type: ignore
            contract_address=self.params.multisend_address,
            contract_id=str(MultiSendContract.contract_id),
            contract_callable="get_tx_data",
            multi_send_txs=multi_send_txs,
        )
        if response.performative != ContractApiMessage.Performative.RAW_TRANSACTION:
            self.context.logger.error(
                f"Couldn't compile the multisend tx. "
                f"Expected performative {ContractApiMessage.Performative.RAW_TRANSACTION}, "
                f"received {response.performative.value}."
            )
            return None

        multisend_data_str = cast(str, response.raw_transaction.body["data"])[2:]
        tx_data = bytes.fromhex(multisend_data_str)
        tx_hash = yield from self._get_safe_tx_hash(
            self.params.multisend_address,
            tx_data,
            operation=SafeOperation.DELEGATE_CALL.value,
        )
        if tx_hash is None:
            return None

        payload_data = hash_payload_to_hex(
            safe_tx_hash=tx_hash,
            ether_value=ETHER_VALUE,
            safe_tx_gas=SAFE_TX_GAS,
            operation=SafeOperation.DELEGATE_CALL.value,
            to_address=self.params.multisend_address,
            data=tx_data,
        )
        return payload_data

    def get_realitio_subgraph_result(
        self,
        query: str,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Query the Realitio subgraph."""
        response = yield from self.get_http_response(
            content=to_content(query),
            **self.context.realitio_subgraph.get_spec(),
        )

        if response is None:
            self.context.logger.error(
                "Could not retrieve response from Realitio subgraph. "
                "Response was None."
            )
            return None
        if response.status_code != HTTP_OK:
            self.context.logger.error(
                f"Could not retrieve response from Realitio subgraph. "
                f"Received status code {response.status_code}.\n{response}"
            )
            return None

        return json.loads(response.body.decode())

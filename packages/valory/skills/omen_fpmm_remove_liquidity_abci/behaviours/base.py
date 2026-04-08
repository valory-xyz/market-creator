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

"""Base behaviour for the omen_fpmm_remove_liquidity_abci skill."""

# pylint: disable=too-many-ancestors,too-many-arguments,too-many-positional-arguments

import json
from abc import ABC
from typing import Any, Callable, Dict, Generator, List, Optional, cast

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
from packages.valory.skills.omen_fpmm_remove_liquidity_abci.models import (
    FpmmRemoveLiquidityParams,
    SharedState,
)
from packages.valory.skills.omen_fpmm_remove_liquidity_abci.rounds import (
    SynchronizedData,
)
from packages.valory.skills.transaction_settlement_abci.payload_tools import (
    hash_payload_to_hex,
)

HTTP_OK = 200
SAFE_TX_GAS = 0
ETHER_VALUE = 0

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
ZERO_HASH = "0x0000000000000000000000000000000000000000000000000000000000000000"

LOG_PREFIX = "[OmenFpmmRemoveLiquidity]"


def to_content(query: str) -> bytes:
    """Convert the given query string to payload content."""
    finalized_query = {"query": query}
    encoded_query = json.dumps(finalized_query, sort_keys=True).encode("utf-8")
    return encoded_query


def get_callable_name(method: Callable) -> str:
    """Return callable name."""
    return getattr(method, "__name__")  # noqa: B009


class FpmmRemoveLiquidityBaseBehaviour(BaseBehaviour, ABC):
    """Base behaviour for the omen_fpmm_remove_liquidity_abci skill."""

    @property
    def synchronized_data(self) -> SynchronizedData:
        """Return the synchronized data."""
        return cast(SynchronizedData, super().synchronized_data)

    @property
    def params(self) -> FpmmRemoveLiquidityParams:
        """Return the params."""
        return cast(FpmmRemoveLiquidityParams, super().params)

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

    def get_omen_subgraph_result(
        self,
        query: str,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Query the Omen subgraph."""
        response = yield from self.get_http_response(
            content=to_content(query),
            **self.context.omen_subgraph.get_spec(),
        )

        if response is None:
            self.context.logger.error(
                "Could not retrieve response from Omen subgraph. Response was None."
            )
            return None
        if response.status_code != HTTP_OK:
            self.context.logger.error(
                f"Could not retrieve response from Omen subgraph. "
                f"Received status code {response.status_code}.\n{response}"
            )
            return None

        return json.loads(response.body.decode())

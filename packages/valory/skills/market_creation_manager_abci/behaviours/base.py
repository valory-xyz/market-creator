# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2024 Valory AG
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

"""Base behaviour for the Market Creation Manager skill."""

import json
from abc import ABC
from datetime import datetime
from string import Template
from typing import Any, Callable, Generator, Optional, cast

from packages.valory.contracts.gnosis_safe.contract import GnosisSafeContract, SafeOperation
from packages.valory.contracts.conditional_tokens.contract import ConditionalTokensContract
from packages.valory.contracts.multisend.contract import MultiSendContract, MultiSendOperation
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.protocols.llm.message import LlmMessage
from packages.valory.skills.abstract_round_abci.behaviours import BaseBehaviour
from packages.valory.skills.abstract_round_abci.models import Requests
from packages.valory.skills.market_creation_manager_abci.dialogues import LlmDialogue
from packages.valory.skills.market_creation_manager_abci.models import MarketCreationManagerParams, SharedState
from packages.valory.skills.market_creation_manager_abci.rounds import SynchronizedData
from packages.valory.skills.transaction_settlement_abci.payload_tools import hash_payload_to_hex


# Constants
HTTP_OK = 200
HTTP_NO_CONTENT = 204
MAX_RETRIES = 3
SAFE_TX_GAS = 0
ETHER_VALUE = 0
MAX_PREVIOUS = 0
MIN_BALANCE_WITHDRAW_REALITIO = 100000000000000000  # 0.1 DAI

AVAILABLE_FORMATS = (
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d",
)

_ONE_DAY = 86400

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
ZERO_HASH = "0x0000000000000000000000000000000000000000000000000000000000000000"
ANSWER_YES, ANSWER_NO, ANSWER_INVALID = (
    "0x0000000000000000000000000000000000000000000000000000000000000000",
    "0x0000000000000000000000000000000000000000000000000000000000000001",
    "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
)

FPMM_POOL_MEMBERSHIPS_QUERY = Template(
    """  {
    fpmmPoolMemberships(
      where: {funder: "$creator", amount_gt: "0"}
      first: 1000
    ) {
      amount
      id
      pool {
        id
        openingTimestamp
        creator
        conditions {
          id
          question {
            id
          }
          outcomeSlotCount
        }
        liquidityMeasure
        outcomeTokenAmounts
      }
    }
  }"""
)

FPMM_QUERY = Template(
    """{
    fixedProductMarketMakers(
        where: {
            creator: "$creator"
            openingTimestamp_gte:"$openingTimestamp_gte"
            openingTimestamp_lte:"$openingTimestamp_lte"
        }
        first: 1000
        orderBy: creationTimestamp
        orderDirection: desc
    ) {
        currentAnswerTimestamp
        creator
        category
        creationTimestamp
        currentAnswer
        id
        openingTimestamp
        question {
        data
        }
        title
        timeout
    }
    }"""
)

OPEN_FPMM_QUERY = Template(
    """{
    fixedProductMarketMakers(
        where: {
            creator: "$creator"
            openingTimestamp_lt: $current_timestamp
        answerFinalizedTimestamp: null
            currentAnswerBond: null
        }
        first: 1000
        orderBy: openingTimestamp
        orderDirection: asc
    ) {
        currentAnswerTimestamp
        creator
        category
        creationTimestamp
        currentAnswer
        id
        answerFinalizedTimestamp
        openingTimestamp
        question {
            id
          data
          currentAnswerBond
        }
        title
        timeout
    }
    }"""
)

TOP_HEADLINES = "top-headlines"
EVERYTHING = "everything"

ARTICLE_LIMIT = 1_000
ADDITIONAL_INFO_LIMIT = 5_000


# Utility functions
def to_content(query: str) -> bytes:
    """Convert the given query string to payload content, i.e., add it under a `queries` key and convert it to bytes."""
    finalized_query = {"query": query}
    encoded_query = json.dumps(finalized_query, sort_keys=True).encode("utf-8")
    return encoded_query


def parse_date_timestring(string: str) -> Optional[datetime]:
    """Parse and return a datetime string."""
    for format in AVAILABLE_FORMATS:
        try:
            return datetime.strptime(string, format)
        except ValueError:
            continue
    return None


def get_callable_name(method: Callable) -> str:
    """Return callable name, fallback to type name if not present."""
    return getattr(method, "__name__", type(method).__name__)


class MarketCreationManagerBaseBehaviour(BaseBehaviour, ABC):
    """Base behaviour for the market_creation_manager_abci skill."""

    @property
    def synchronized_data(self) -> SynchronizedData:
        """Return the synchronized data."""
        return cast(SynchronizedData, super().synchronized_data)

    @property
    def params(self) -> MarketCreationManagerParams:
        """Return the params."""
        return cast(MarketCreationManagerParams, super().params)

    @property
    def last_synced_timestamp(self) -> int:
        """
        Get last synced timestamp.

        This is the last timestamp guaranteed to be the same by 2/3 of the agents.
        :returns: the last synced timestamp.
        """
        state = cast(SharedState, self.context.state)
        last_timestamp = (
            state.round_sequence.last_round_transition_timestamp.timestamp()
        )
        return int(last_timestamp)

    @property
    def shared_state(self) -> SharedState:
        """Get the shared state."""
        return cast(SharedState, self.context.state)

    def _calculate_condition_id(
        self,
        oracle_contract: str,
        question_id: str,
        outcome_slot_count: int = 2,
    ) -> Generator[None, None, str]:
        """Calculate question ID."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.conditional_tokens_contract,
            contract_id=str(ConditionalTokensContract.contract_id),
            contract_callable="calculate_condition_id",
            oracle_contract=oracle_contract,
            question_id=question_id,
            outcome_slot_count=outcome_slot_count,
        )
        return cast(str, response.state.body["condition_id"])

    def _get_safe_tx_hash(
        self,
        to_address: str,
        data: bytes,
        value: int = ETHER_VALUE,
        safe_tx_gas: int = SAFE_TX_GAS,
        operation: int = SafeOperation.CALL.value,
    ) -> Generator[None, None, Optional[str]]:
        """Prepares and returns the safe tx hash."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.synchronized_data.safe_contract_address,  # the safe contract address
            contract_id=str(GnosisSafeContract.contract_id),
            contract_callable="get_raw_safe_transaction_hash",
            to_address=to_address,  # the contract the safe will invoke
            value=value,
            data=data,
            safe_tx_gas=safe_tx_gas,
            operation=operation,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                "Couldn't get safe hash. Expected response performative %s, received %s.",
                ContractApiMessage.Performative.STATE.value,
                response.performative.value,
            )
            return None

        # strip "0x" from the response hash
        tx_hash = cast(str, response.state.body.get("tx_hash", ""))[2:]
        return tx_hash

    def _to_multisend(
        self, transactions: list[dict]
    ) -> Generator[None, None, Optional[str]]:
        """Transform payload to MultiSend."""
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
                "Couldn't compile the multisend tx. Expected performative %s, received %s.",
                ContractApiMessage.Performative.RAW_TRANSACTION.value,
                response.performative.value,
            )
            return None

        # strip "0x" from the response
        multisend_data_str = cast(str, response.raw_transaction.body.get("data", ""))[2:]
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

    def get_subgraph_result(
        self,
        query: str,
    ) -> Generator[None, None, Optional[dict[str, Any]]]:
        """Get question ids from the Omen subgraph."""
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
                "Could not retrieve response from Omen subgraph. Received status code %s.\n%s",
                response.status_code,
                response,
            )
            return None

        return json.loads(response.body.decode())

    def do_llm_request(
        self,
        llm_message: LlmMessage,
        llm_dialogue: LlmDialogue,
        timeout: Optional[float] = None,
    ) -> Generator[None, None, LlmMessage]:
        """
        Do a request and wait the response, asynchronously.

        :param llm_message: The request message
        :param llm_dialogue: the HTTP dialogue associated to the request
        :param timeout: seconds to wait for the reply.
        :yield: LLMMessage object
        :return: the response message
        """
        self.context.outbox.put_message(message=llm_message)
        request_nonce = self._get_request_nonce_from_dialogue(llm_dialogue)
        cast(Requests, self.context.requests).request_id_to_callback[
            request_nonce
        ] = self.get_callback_request()
        # notify caller by propagating potential timeout exception.
        response = yield from self.wait_for_message(timeout=timeout)
        return response
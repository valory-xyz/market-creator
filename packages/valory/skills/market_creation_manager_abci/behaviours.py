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

"""This package contains round behaviours of MarketCreationManagerAbciApp."""

import json
import random
import time
from abc import ABC
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from string import Template
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    cast,
)

import packages.valory.skills.mech_interact_abci.states.request as MechRequestStates
from packages.valory.contracts.conditional_tokens.contract import (
    ConditionalTokensContract,
)
from packages.valory.contracts.fpmm.contract import FPMMContract
from packages.valory.contracts.fpmm_deterministic_factory.contract import (
    FPMMDeterministicFactory,
)
from packages.valory.contracts.gnosis_safe.contract import (
    GnosisSafeContract,
    SafeOperation,
)
from packages.valory.contracts.multisend.contract import (
    MultiSendContract,
    MultiSendOperation,
)
from packages.valory.contracts.realitio.contract import RealitioContract
from packages.valory.contracts.wxdai.contract import WxDAIContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.protocols.ledger_api import LedgerApiMessage
from packages.valory.protocols.llm.message import LlmMessage
from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)
from packages.valory.skills.abstract_round_abci.common import (
    RandomnessBehaviour,
    SelectKeeperBehaviour,
)
from packages.valory.skills.abstract_round_abci.models import Requests
from packages.valory.skills.market_creation_manager_abci import (
    PUBLIC_ID as MARKET_CREATION_MANAGER_PUBLIC_ID,
)
from packages.valory.skills.market_creation_manager_abci.dialogues import LlmDialogue
from packages.valory.skills.market_creation_manager_abci.models import (
    MarketCreationManagerParams,
    SharedState,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    AnswerQuestionsPayload,
    ApproveMarketsPayload,
    CollectProposedMarketsPayload,
    DepositDaiPayload,
    GetPendingQuestionsPayload,
    PostTxPayload,
    RedeemBondPayload,
    RemoveFundingPayload,
    SyncMarketsPayload,
)
from packages.valory.skills.market_creation_manager_abci.propose_questions import (  # type: ignore
    KeyChain,
)
from packages.valory.skills.market_creation_manager_abci.propose_questions import (
    run as run_propose_questions,  # type: ignore
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    AnswerQuestionsRound,
    ApproveMarketsRound,
    CollectProposedMarketsRound,
    CollectRandomnessPayload,
    CollectRandomnessRound,
    DepositDaiRound,
    GetPendingQuestionsRound,
    MarketCreationManagerAbciApp,
    PostTransactionRound,
    PrepareTransactionPayload,
    PrepareTransactionRound,
    RedeemBondRound,
    RemoveFundingRound,
    RetrieveApprovedMarketPayload,
    RetrieveApprovedMarketRound,
    SelectKeeperPayload,
    SelectKeeperRound,
    SyncMarketsRound,
    SynchronizedData,
)
from packages.valory.skills.mech_interact_abci.states.base import (
    MechInteractionResponse,
    MechMetadata,
)
from packages.valory.skills.transaction_settlement_abci.payload_tools import (
    hash_payload_to_hex,
)


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
    """Return callable name."""
    return getattr(method, "__name__")  # noqa: B009


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
                f"Couldn't get safe hash. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return None

        # strip "0x" from the response hash
        tx_hash = cast(str, response.state.body["tx_hash"])[2:]
        return tx_hash

    def _to_multisend(
        self, transactions: List[Dict]
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
                f"Couldn't compile the multisend tx. "
                f"Expected performative {ContractApiMessage.Performative.RAW_TRANSACTION.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return None

        # strip "0x" from the response
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

    def get_subgraph_result(
        self,
        query: str,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Get question ids."""
        response = yield from self.get_http_response(
            content=to_content(query),
            **self.context.omen_subgraph.get_spec(),
        )

        if response is None or response.status_code != HTTP_OK:
            self.context.logger.error(
                f"Could not retrieve response from Omen subgraph."
                f"Received status code {response.status_code}.\n{response}"
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


class CollectRandomnessBehaviour(RandomnessBehaviour):
    """CollectRandomnessBehaviour"""

    matching_round: Type[AbstractRound] = CollectRandomnessRound
    payload_class = CollectRandomnessPayload


class CollectProposedMarketsBehaviour(MarketCreationManagerBaseBehaviour):
    """CollectProposedMarketsBehaviour"""

    matching_round: Type[AbstractRound] = CollectProposedMarketsRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            current_timestamp = self.last_synced_timestamp
            self.context.logger.info(f"current_timestamp={current_timestamp}")

            openingTimestamp_gte = current_timestamp + _ONE_DAY
            self.context.logger.info(f"openingTimestamp_gte={openingTimestamp_gte}")

            openingTimestamp_lte = current_timestamp + (
                self.params.approve_market_event_days_offset * _ONE_DAY
            )
            self.context.logger.info(f"openingTimestamp_lte={openingTimestamp_lte}")

            # Compute required openingTimestamp (between now and now + approve_market_event_days_offset)
            # openingTimestamp refers to the time the market is closed for trades, and open for answer
            # in Realitio. We require "self.params.markets_to_approve_per_day" markets to close for trades every day.
            required_opening_ts = []
            current_day_start_timestamp = (
                openingTimestamp_gte - (openingTimestamp_gte % _ONE_DAY) + _ONE_DAY
            )
            while current_day_start_timestamp <= openingTimestamp_lte:
                required_opening_ts.append(current_day_start_timestamp)
                current_day_start_timestamp += _ONE_DAY

            self.context.logger.info(f"{required_opening_ts=}")

            # Get existing (open) markets count per openingTimestamp (between now and now + approve_market_event_days_offset)
            latest_open_markets = yield from self._collect_latest_open_markets(
                openingTimestamp_gte, openingTimestamp_lte
            )
            existing_market_count: Dict[int, int] = defaultdict(int)

            for market in latest_open_markets["fixedProductMarketMakers"]:
                ts = int(market.get("openingTimestamp"))
                existing_market_count[ts] += 1

            self.context.logger.info(f"existing_market_count={existing_market_count}")

            # Determine number of markets required to be approved per openingTimestamp (between now and now + approve_market_event_days_offset)
            required_markets_to_approve_per_opening_ts: Dict[int, int] = defaultdict(
                int
            )
            N = self.params.markets_to_approve_per_day

            for ts in required_opening_ts:
                required_markets_to_approve_per_opening_ts[ts] = max(
                    0, N - existing_market_count.get(ts, 0)
                )

            num_markets_to_approve = sum(
                required_markets_to_approve_per_opening_ts.values()
            )

            self.context.logger.info(f"{required_markets_to_approve_per_opening_ts=}")
            self.context.logger.info(f"{num_markets_to_approve=}")

            # Determine largest creation timestamp in markets with openingTimestamp between now and now + approve_market_event_days_offset
            creation_timestamps = [
                int(entry["creationTimestamp"])
                for entry in latest_open_markets.get("fixedProductMarketMakers", {})
            ]
            largest_creation_timestamp = max(creation_timestamps, default=0)
            self.context.logger.info(f"{largest_creation_timestamp=}")

            # Collect misc data related to market approval
            min_approve_markets_epoch_seconds = (
                self.params.min_approve_markets_epoch_seconds
            )
            self.context.logger.info(f"{min_approve_markets_epoch_seconds=}")
            approved_markets_count = self.synchronized_data.approved_markets_count
            self.context.logger.info(f"{approved_markets_count=}")

            latest_approve_market_timestamp = (
                self.synchronized_data.approved_markets_timestamp
            )
            self.context.logger.info(f"{latest_approve_market_timestamp=}")

            # Collect approved markets (not yet processed by the service)
            approved_markets = yield from self._collect_approved_markets()

            # Main logic of the behaviour
            if (
                self.params.max_approved_markets >= 0
                and approved_markets_count >= self.params.max_approved_markets
            ):
                self.context.logger.info("Max markets approved reached.")
                content = (
                    CollectProposedMarketsRound.MAX_APPROVED_MARKETS_REACHED_PAYLOAD
                )
            elif (
                current_timestamp - latest_approve_market_timestamp
                < min_approve_markets_epoch_seconds
            ):
                self.context.logger.info("Timeout to approve markets not reached (1).")
                content = CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD
            elif (
                current_timestamp - largest_creation_timestamp
                < min_approve_markets_epoch_seconds
            ):
                self.context.logger.info("Timeout to approve markets not reached (2).")
                content = CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD
            elif num_markets_to_approve <= 0:
                self.context.logger.info("No market approval required.")
                content = CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD
            elif len(approved_markets["approved_markets"]) > 0:
                self.context.logger.info("There are unprocessed approved markets.")
                content = CollectProposedMarketsRound.SKIP_MARKET_APPROVAL_PAYLOAD
            else:
                self.context.logger.info("Timeout to approve markets reached.")

                content_data = {}
                content_data.update(latest_open_markets)
                content_data.update(approved_markets)
                content_data[
                    "required_markets_to_approve_per_opening_ts"
                ] = required_markets_to_approve_per_opening_ts
                content_data["timestamp"] = current_timestamp
                content = json.dumps(content_data, sort_keys=True)

            payload = CollectProposedMarketsPayload(
                sender=sender,
                content=content,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _collect_approved_markets(self) -> Generator[None, None, Dict[str, Any]]:
        """Auxiliary method to collect approved and unprocessed markets from the endpoint."""
        self.context.logger.info("Collecting approved markets.")

        url = f"{self.params.market_approval_server_url}/approved_markets"
        headers = {
            "Authorization": self.params.market_approval_server_api_key,
            "Content-Type": "application/json",
        }
        http_response = yield from self.get_http_response(
            method="GET",
            url=url,
            headers=headers,
        )
        if http_response.status_code != HTTP_OK:
            self.context.logger.warning(
                f"Failed to retrieve approved markets: {http_response.status_code} {http_response}"
            )
            # TODO return error instead?
            return {"approved_markets": {}}

        body = json.loads(http_response.body.decode())
        self.context.logger.info(
            f"Successfully collected approved markets, received body {body}"
        )
        return body

    def _collect_latest_open_markets(
        self, openingTimestamp_gte: int, openingTimestamp_lte: int
    ) -> Generator[None, None, Dict[str, Any]]:
        """Collect FPMM from subgraph."""
        creator = self.synchronized_data.safe_contract_address.lower()

        self.context.logger.info(f"_collect_latest_open_markets for {creator=}")

        response = yield from self.get_subgraph_result(
            query=FPMM_QUERY.substitute(
                creator=creator,
                openingTimestamp_gte=openingTimestamp_gte,
                openingTimestamp_lte=openingTimestamp_lte,
            )
        )

        # TODO Handle retries
        if response is None:
            return {"fixedProductMarketMakers": []}
        return response.get("data", {})


class ApproveMarketsBehaviour(MarketCreationManagerBaseBehaviour):
    """ApproveMarketsBehaviour"""

    matching_round: Type[AbstractRound] = ApproveMarketsRound

    def _i_am_not_sending(self) -> bool:
        """Indicates if the current agent is the sender or not."""
        return (
            self.context.agent_address
            != self.synchronized_data.most_voted_keeper_address
        )

    def async_act(self) -> Generator[None, None, None]:
        """
        Do the action.

        Steps:
        - If the agent is the keeper, then prepare the transaction and send it.
        - Otherwise, wait until the next round.
        - If a timeout is hit, set exit A event, otherwise set done event.
        """
        if self._i_am_not_sending():
            yield from self._not_sender_act()
        else:
            yield from self._sender_act()

    def _not_sender_act(self) -> Generator:
        """Do the non-sender action."""
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            self.context.logger.info(
                f"Waiting for the keeper to do its keeping: {self.synchronized_data.most_voted_keeper_address}"
            )
            yield from self.wait_until_round_end()
        self.set_done()

    def _sender_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            random.seed(
                "ApproveMarketsBehaviour"
                + self.synchronized_data.most_voted_randomness,
                2,
            )  # nosec

            collected_proposed_markets_json = json.loads(
                self.synchronized_data.collected_proposed_markets_data
            )

            required_markets_to_approve_per_opening_ts = (
                collected_proposed_markets_json[
                    "required_markets_to_approve_per_opening_ts"
                ]
            )

            # Select an openingTimestamp with >0 markets to approve
            opening_ts = next(
                (
                    k
                    for k, v in required_markets_to_approve_per_opening_ts.items()
                    if v > 0
                ),
                None,
            )
            self.context.logger.info(f"{opening_ts=}")
            proposed_markets = {}
            approved_markets_count = 0

            if opening_ts:
                # TODO THIS EMULATES MECH INTERACT SENDING REQUEST TO A TOOL

                # This is very important, the resolution_time (i.e., the event day)
                # is one day less than the openingTimestamp
                resolution_time = int(opening_ts) - _ONE_DAY

                num_questions = min(
                    required_markets_to_approve_per_opening_ts[opening_ts],
                    self.params.max_markets_per_story,
                )

                keys = KeyChain(
                    {
                        "openai": [self.params.openai_api_key],
                        "newsapi": [self.params.newsapi_api_key],
                        "serper": [self.params.serper_api_key],
                        "subgraph": [self.params.subgraph_api_key],
                    }
                )

                tool_kwargs = dict(
                    tool="propose-question",
                    api_keys=keys,
                    news_sources=self.params.news_sources,
                    topics=self.params.topics,
                    num_questions=num_questions,
                    resolution_time=resolution_time,
                )
                proposed_markets = run_propose_questions(**tool_kwargs)[0]
                # END MECH INTERACT EMULATION

                proposed_markets = json.loads(proposed_markets)  # type: ignore

                if "error" in proposed_markets:
                    approved_markets_count = 0
                    self.context.logger.error(
                        f"An error occurred interacting with the Mech tool {proposed_markets=}"
                    )
                else:
                    for market in proposed_markets.values():
                        yield from self._propose_and_approve_market(market)

                    approved_markets_count = len(proposed_markets)

            sender = self.context.agent_address
            payload = ApproveMarketsPayload(
                sender=sender,
                content=json.dumps(proposed_markets, sort_keys=True),
                approved_markets_count=approved_markets_count
                + self.synchronized_data.approved_markets_count,
                timestamp=self.last_synced_timestamp,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _propose_and_approve_market(
        self, market: Dict[str, Any]
    ) -> Generator[None, None, str]:
        """Auxiliary method to approve markets on the endpoint."""

        headers = {
            "Authorization": self.params.market_approval_server_api_key,
            "Content-Type": "application/json",
        }

        market_id = market["id"]

        # Step 1: Propose market
        self.context.logger.info(f"proposing market {market_id=}")
        url = self.params.market_approval_server_url + "/propose_market"
        body = market
        http_response = yield from self.get_http_response(
            method="POST",
            url=url,
            headers=headers,
            content=json.dumps(body).encode("utf-8"),
        )
        if http_response.status_code != HTTP_OK:
            self.context.logger.warning(
                f"Failed to propose market: {http_response.status_code} {http_response}"
            )
            return ApproveMarketsRound.ERROR_PAYLOAD
        body = json.loads(http_response.body.decode())
        self.context.logger.info(f"Successfully proposed market, received body {body}")
        time.sleep(3)

        # Step 2: Approve market
        self.context.logger.info(f"Approving market {market_id=}")
        url = self.params.market_approval_server_url + "/approve_market"
        body = {"id": market_id}
        http_response = yield from self.get_http_response(
            method="POST",
            url=url,
            headers=headers,
            content=json.dumps(body).encode("utf-8"),
        )
        if http_response.status_code != HTTP_OK:
            self.context.logger.warning(
                f"Failed to approve market: {http_response.status_code} {http_response}"
            )
            return ApproveMarketsRound.ERROR_PAYLOAD
        body = json.loads(http_response.body.decode())
        self.context.logger.info(f"Successfully approved market, received body {body}")
        time.sleep(3)

        # Step 3: Update market data
        self.context.logger.info(f"Updating market {market_id=}")
        url = self.params.market_approval_server_url + "/update_market"
        body = {
            "id": market_id,
            "approved_by": f"{MARKET_CREATION_MANAGER_PUBLIC_ID}@{self.context.agent_address}",
        }
        http_response = yield from self.get_http_response(
            method="PUT",
            url=url,
            headers=headers,
            content=json.dumps(body).encode("utf-8"),
        )
        if http_response.status_code != HTTP_OK:
            self.context.logger.warning(
                f"Failed to update market: {http_response.status_code} {http_response}"
            )
            return ApproveMarketsRound.ERROR_PAYLOAD

        body = json.loads(http_response.body.decode())
        self.context.logger.info(f"Successfully updated market, received body {body}")
        time.sleep(3)

        return json.dumps(body, sort_keys=True)


class DepositDaiBehaviour(MarketCreationManagerBaseBehaviour):
    """DepositDaiBehaviour"""

    matching_round = DepositDaiRound

    def async_act(self) -> Generator:
        """Implement the act."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            content = yield from self.get_payload()
            payload = DepositDaiPayload(sender=sender, content=content)
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def get_balance(self, address: str) -> Generator[None, None, Optional[int]]:
        """Get the balance of the provided address"""
        ledger_api_response = yield from self.get_ledger_api_response(
            performative=LedgerApiMessage.Performative.GET_STATE,
            ledger_callable="get_balance",
            account=address,
        )
        if ledger_api_response.performative != LedgerApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Couldn't get balance. "
                f"Expected response performative {LedgerApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {ledger_api_response.performative.value}."
            )
            return None
        balance = cast(int, ledger_api_response.state.body.get("get_balance_result"))
        self.context.logger.info(f"balance: {balance / 10 ** 18} xDAI")
        return balance

    def get_payload(self) -> Generator[None, None, str]:
        """Get the payload."""
        safe_address = self.synchronized_data.safe_contract_address
        balance = yield from self.get_balance(safe_address)
        if balance is None:
            # something went wrong
            return DepositDaiRound.ERROR_PAYLOAD

        # check if the balance is below the threshold
        if balance <= self.params.xdai_threshold:
            # not enough balance in the safe
            return DepositDaiRound.NO_TX_PAYLOAD

        # leave xdai threshold in the safe for non-market creation purposes of the safe
        balance_to_deposit = balance - self.params.xdai_threshold

        # in case there is balance in the safe, fully deposit it to the wxDAI contract
        wxdai_address = self.params.collateral_tokens_contract
        tx_data = yield from self._get_deposit_tx(wxdai_address)
        if tx_data is None:
            # something went wrong
            return DepositDaiRound.ERROR_PAYLOAD

        safe_tx_hash = yield from self._get_safe_tx_hash(
            to_address=wxdai_address, value=balance_to_deposit, data=tx_data
        )
        if safe_tx_hash is None:
            # something went wrong
            return DepositDaiRound.ERROR_PAYLOAD

        tx_payload_data = hash_payload_to_hex(
            safe_tx_hash=safe_tx_hash,
            ether_value=balance_to_deposit,
            safe_tx_gas=SAFE_TX_GAS,
            to_address=wxdai_address,
            data=tx_data,
        )
        return tx_payload_data

    def _get_deposit_tx(
        self,
        wxdai_address: str,
    ) -> Generator[None, None, Optional[bytes]]:
        """This function returns the encoded FPMMContract.removeFunds() function call."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_id=str(WxDAIContract.contract_id),
            contract_callable="build_deposit_tx",
            contract_address=wxdai_address,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Couldn't get tx data for WxDAIContract.build_deposit_tx. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return None

        # strip "0x" from the response data
        data_str = cast(str, response.state.body["data"])[2:]
        data = bytes.fromhex(data_str)
        return data


class RedeemBondBehaviour(MarketCreationManagerBaseBehaviour):
    """RedeemBondBehaviour"""

    matching_round = RedeemBondRound

    def async_act(self) -> Generator:
        """Implement the act."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            content = yield from self.get_payload()
            payload = RedeemBondPayload(sender=sender, content=content)
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def get_balance(self, address: str) -> Generator[None, None, Optional[int]]:
        """Get the balance of the provided address"""
        safe_address = self.synchronized_data.safe_contract_address
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.realitio_contract,
            contract_id=str(RealitioContract.contract_id),
            contract_callable="balance_of",
            address=safe_address,
        )

        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(f"balance_of unsuccessful!: {response}")
            return None

        balance = cast(int, response.state.body["data"])
        self.context.logger.info(f"balance: {balance / 10 ** 18} xDAI")
        return balance

    def get_payload(self) -> Generator[None, None, str]:
        """Get the payload."""
        safe_address = self.synchronized_data.safe_contract_address
        balance = yield from self.get_balance(safe_address)
        if balance is None:
            return RedeemBondRound.ERROR_PAYLOAD

        if balance <= MIN_BALANCE_WITHDRAW_REALITIO:
            return RedeemBondRound.NO_TX_PAYLOAD

        withdraw_tx = yield from self._get_withdraw_tx()
        if withdraw_tx is None:
            return RedeemBondRound.ERROR_PAYLOAD

        tx_hash = yield from self._to_multisend(
            transactions=[
                withdraw_tx,
            ]
        )
        if tx_hash is None:
            return RedeemBondRound.ERROR_PAYLOAD

        return tx_hash

    def _get_withdraw_tx(self) -> Generator[None, None, Optional[Dict]]:
        """Prepare a withdraw tx"""
        self.context.logger.info("Starting RealitioContract.build_withdraw_tx")
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.realitio_contract,
            contract_id=str(RealitioContract.contract_id),
            contract_callable=get_callable_name(RealitioContract.build_withdraw_tx),
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"RealitioContract.build_withdraw_tx unsuccessful! : {response}"
            )
            return None
        return {
            "to": self.params.realitio_contract,
            "data": response.state.body["data"],
            "value": ETHER_VALUE,
        }


class SyncMarketsBehaviour(MarketCreationManagerBaseBehaviour):
    """SyncMarketsBehaviour"""

    matching_round = SyncMarketsRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            payload_content = yield from self.get_payload()
            payload = SyncMarketsPayload(sender=sender, content=payload_content)
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def get_payload(self) -> Generator[None, None, str]:
        """Get the payload."""
        market_removal = yield from self.get_markets()
        if market_removal is None:
            # something went wrong
            return SyncMarketsRound.ERROR_PAYLOAD
        markets, from_block = market_removal
        if len(markets) == 0:
            # no markets to sync
            return SyncMarketsRound.NO_UPDATE_PAYLOAD
        payload = dict(markets=markets, from_block=from_block)
        return json.dumps(payload, sort_keys=True)

    def get_markets(self) -> Generator[None, None, Tuple[List[Dict[str, Any]], int]]:
        """Collect FMPMM from subgraph."""
        creator = self.synchronized_data.safe_contract_address.lower()
        response = yield from self.get_subgraph_result(
            query=FPMM_POOL_MEMBERSHIPS_QUERY.substitute(creator=creator)
        )
        if response is None:
            return [], 0
        markets = []
        for entry in response["data"]["fpmmPoolMemberships"]:
            market = {}
            liquidity_measure = entry["pool"].get("liquidityMeasure")
            if liquidity_measure is None:
                continue

            liquidity_measure = int(liquidity_measure)
            if liquidity_measure == 0:
                continue

            if entry["pool"]["openingTimestamp"] is None:
                continue

            market["address"] = entry["pool"]["id"]
            market["amount"] = sum(map(int, entry["pool"]["outcomeTokenAmounts"]))
            market["opening_timestamp"] = int(entry["pool"]["openingTimestamp"])
            market["removal_timestamp"] = market["opening_timestamp"] - _ONE_DAY

            # The markets created by the agent will only have one condition per market
            condition, *_ = entry["pool"]["conditions"]
            market["condition_id"] = condition["id"]
            market["outcome_slot_count"] = condition["outcomeSlotCount"]
            if condition["question"] is None:
                continue

            market["question_id"] = condition["question"]["id"]
            markets.append(market)

        market_addresses = [market["address"] for market in markets]
        market_addresses_with_funds = yield from self._get_markets_with_funds(
            market_addresses, self.synchronized_data.safe_contract_address
        )
        market_addresses_with_funds_str = [
            str(market).lower() for market in market_addresses_with_funds
        ]
        markets_with_funds = []
        for market in markets:
            if str(market["address"]).lower() not in market_addresses_with_funds_str:
                continue
            markets_with_funds.append(market)
            log_msg = "\n\t".join(
                [
                    "Adding market with",
                    "Address: " + market["address"],
                    "Liquidity: " + str(market["amount"]),
                    "Opening time: "
                    + str(datetime.fromtimestamp(market["opening_timestamp"])),
                    "Liquidity removal time: "
                    + str(datetime.fromtimestamp(market["removal_timestamp"])),
                ]
            )
            self.context.logger.info(log_msg)

        return markets_with_funds, 0

    def _get_markets_with_funds(
        self,
        market_addresses: List[str],
        safe_address: str,
    ) -> Generator[None, None, List[str]]:
        """Get markets with funds."""
        # no need to query the contract if there are no markets
        if len(market_addresses) == 0:
            return []

        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=ZERO_ADDRESS,  # NOT USED!
            contract_id=str(FPMMContract.contract_id),
            contract_callable=get_callable_name(FPMMContract.get_markets_with_funds),
            markets=market_addresses,
            safe_address=safe_address,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Couldn't get tx data for FPMMContract.get_markets_with_funds. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return []
        return cast(List[str], response.state.body["data"])


class RemoveFundingBehaviour(MarketCreationManagerBaseBehaviour):
    """Remove funding behaviour."""

    matching_round = RemoveFundingRound

    def _calculate_amounts(
        self,
        market: str,
        condition_id: str,
        outcome_slot_count: int,
    ) -> Generator[None, None, Optional[Tuple[int, int]]]:
        """Calculate amount to burn."""

        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.conditional_tokens_contract,
            contract_id=str(ConditionalTokensContract.contract_id),
            contract_callable=get_callable_name(
                ConditionalTokensContract.get_user_holdings
            ),
            outcome_slot_count=outcome_slot_count,
            condition_id=condition_id,
            creator=self.synchronized_data.safe_contract_address,
            collateral_token=self.params.collateral_tokens_contract,
            market=market,
            parent_collection_id=ZERO_HASH,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"ConditionalTokensContract.get_user_holdings unsuccessful! : {response}"
            )
            return None

        shares = cast(List[int], response.state.body["shares"])
        holdings = cast(List[int], response.state.body["holdings"])

        # Shares to burn
        # https://github.com/protofire/omen-exchange/blob/88dc0149f61cc4aef7981d3acf187c35e6a24ead/app/src/hooks/market_data/useFundingBalance.tsx#L24
        # https://github.com/protofire/omen-exchange/blob/4313d01c93aa79638d6394521adf3b9aad0e6f56/app/src/components/market/market_pooling/scalar_market_pool_liquidity.tsx#L279
        # https://github.com/protofire/omen-exchange/blob/4313d01c93aa79638d6394521adf3b9aad0e6f56/app/src/pages/market_sections/market_pool_liquidity_container.tsx#L123
        # https://github.com/protofire/omen-exchange/blob/4313d01c93aa79638d6394521adf3b9aad0e6f56/app/src/pages/market_sections/market_pool_liquidity_container.tsx#L357
        # FPMM.balanceOf(ADDRESS) # noqa

        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=market,
            contract_id=str(FPMMContract.contract_id),
            contract_callable=get_callable_name(FPMMContract.get_balance),
            address=self.synchronized_data.safe_contract_address,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"FPMMContract.get_balance unsuccessful! : {response}"
            )
            return None
        amount_to_remove = cast(int, response.state.body["balance"])

        # https://github.com/protofire/omen-exchange/blob/4313d01c93aa79638d6394521adf3b9aad0e6f56/app/src/hooks/market_data/useBlockchainMarketMakerData.tsx#L141-L145
        # FPMM.totalSupply() # noqa
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=market,
            contract_id=str(FPMMContract.contract_id),
            contract_callable=get_callable_name(FPMMContract.get_total_supply),
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"FPMMContract.get_total_supply unsuccessful! : {response}"
            )
            return None
        total_pool_shares = cast(int, response.state.body["supply"])
        if amount_to_remove == total_pool_shares:
            send_amounts_after_removing_funding = [
                *holdings,
            ]
        else:
            send_amounts_after_removing_funding = [
                int(h * amount_to_remove / total_pool_shares)
                if total_pool_shares > 0
                else 0
                for h in holdings
            ]
        amount_to_merge = min(
            send_amounts_after_removing_funding[i] + shares[i]
            for i in range(len(send_amounts_after_removing_funding))
        )
        return amount_to_remove, amount_to_merge

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            content = yield from self.get_payload()
            payload = RemoveFundingPayload(sender=sender, content=content)
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def get_payload(self) -> Generator[None, None, str]:
        """Get payload."""

        market_to_close = self._get_market_to_close()
        if market_to_close is None:
            self.context.logger.info("No market to close.")
            return RemoveFundingRound.NO_UPDATE_PAYLOAD

        market = market_to_close["address"]
        self.context.logger.info(f"Closing market: {market}")

        amounts = yield from self._calculate_amounts(
            market=market_to_close["address"],
            condition_id=market_to_close["condition_id"],
            outcome_slot_count=market_to_close["outcome_slot_count"],
        )
        if amounts is None:
            return RemoveFundingRound.NO_UPDATE_PAYLOAD

        amount_to_remove, amount_to_merge = amounts
        self.context.logger.info(f"Amount to remove: {amount_to_remove}")
        self.context.logger.info(f"Amount to merge: {amount_to_merge}")
        remove_funding_tx = yield from self._get_remove_funding_tx(
            address=market, amount_to_remove=amount_to_remove
        )
        if remove_funding_tx is None:
            return RemoveFundingRound.ERROR_PAYLOAD

        merge_positions_tx = yield from self._get_merge_positions_tx(
            collateral_token=self.params.collateral_tokens_contract,
            parent_collection_id=ZERO_HASH,
            condition_id=market_to_close["condition_id"],
            outcome_slot_count=market_to_close["outcome_slot_count"],
            amount=amount_to_merge,
        )
        if merge_positions_tx is None:
            return RemoveFundingRound.ERROR_PAYLOAD

        withdraw_tx = yield from self._get_withdraw_tx(
            amount=amount_to_merge,
        )
        if withdraw_tx is None:
            return RemoveFundingRound.ERROR_PAYLOAD

        tx_hash = yield from self._to_multisend(
            transactions=[
                remove_funding_tx,
                merge_positions_tx,
                withdraw_tx,
            ]
        )
        if tx_hash is None:
            return RemoveFundingRound.ERROR_PAYLOAD

        payload_content = {
            "tx": tx_hash,
            "market": market_to_close,
        }
        return json.dumps(payload_content)

    def _get_market_to_close(self) -> Optional[Dict[str, Any]]:
        """Returns tx data for closing a tx."""
        markets_to_remove_liquidity = self.synchronized_data.markets_to_remove_liquidity
        for market in markets_to_remove_liquidity:
            if market["removal_timestamp"] < self.last_synced_timestamp:
                return market
        return None

    def _get_remove_funding_tx(
        self,
        address: str,
        amount_to_remove: int,
    ) -> Generator[None, None, Optional[Dict]]:
        """This function returns the encoded FPMMContract.removeFunds() function call."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_id=str(FPMMContract.contract_id),
            contract_callable=get_callable_name(FPMMContract.build_remove_funding_tx),
            contract_address=address,
            amount_to_remove=amount_to_remove,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Couldn't get tx data for FPMMContract.build_remove_funding_tx. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return None

        # strip "0x" from the response data
        return {
            "to": address,
            "data": response.state.body["data"],
            "value": ETHER_VALUE,
        }

    def _get_merge_positions_tx(
        self,
        collateral_token: str,
        parent_collection_id: str,
        condition_id: str,
        outcome_slot_count: int,
        amount: int,
    ) -> Generator[None, None, Optional[Dict]]:
        """Prepare a multisend tx for `askQuestionMethod`"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.conditional_tokens_contract,
            contract_id=str(ConditionalTokensContract.contract_id),
            contract_callable=get_callable_name(
                ConditionalTokensContract.build_merge_positions_tx
            ),
            collateral_token=collateral_token,
            parent_collection_id=parent_collection_id,
            condition_id=condition_id,
            outcome_slot_count=outcome_slot_count,
            amount=amount,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"ConditionalTokensContract.build_merge_positions_tx unsuccessful! : {response}"
            )
            return None

        return {
            "to": self.params.conditional_tokens_contract,
            "data": response.state.body["data"],
            "value": ETHER_VALUE,
        }

    def _get_withdraw_tx(self, amount: int) -> Generator[None, None, Optional[Dict]]:
        """Prepare a multisend tx for `askQuestionMethod`"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.conditional_tokens_contract,
            contract_id=str(WxDAIContract.contract_id),
            contract_callable=get_callable_name(WxDAIContract.build_withdraw_tx),
            amount=amount,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"ConditionalTokensContract.build_merge_positions_tx unsuccessful! : {response}"
            )
            return None
        return {
            "to": self.params.collateral_tokens_contract,
            "data": response.state.body["data"],
            "value": ETHER_VALUE,
        }


class SelectKeeperMarketProposalBehaviour(SelectKeeperBehaviour):
    """Select the keeper agent."""

    matching_round = SelectKeeperRound
    payload_class = SelectKeeperPayload


class RetrieveApprovedMarketBehaviour(MarketCreationManagerBaseBehaviour):
    """RetrieveApprovedMarketBehaviour"""

    matching_round: Type[AbstractRound] = RetrieveApprovedMarketRound

    def _i_am_not_sending(self) -> bool:
        """Indicates if the current agent is the sender or not."""
        return (
            self.context.agent_address
            != self.synchronized_data.most_voted_keeper_address
        )

    def async_act(self) -> Generator[None, None, None]:
        """
        Do the action.

        Steps:
        - If the agent is the keeper, then prepare the transaction and send it.
        - Otherwise, wait until the next round.
        - If a timeout is hit, set exit A event, otherwise set done event.
        """
        if self._i_am_not_sending():
            yield from self._not_sender_act()
        else:
            yield from self._sender_act()

    def _not_sender_act(self) -> Generator:
        """Do the non-sender action."""
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            self.context.logger.info(
                f"Waiting for the keeper to do its keeping: {self.synchronized_data.most_voted_keeper_address}"
            )
            yield from self.wait_until_round_end()
        self.set_done()

    def _sender_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            response = yield from self._get_process_random_approved_market()
            payload = RetrieveApprovedMarketPayload(sender=sender, content=response)
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _get_process_random_approved_market(self) -> Generator[None, None, str]:
        """Auxiliary method to collect data from endpoint."""

        url = (
            self.params.market_approval_server_url
            + "/get_process_random_approved_market"
        )
        headers = {
            "Authorization": self.params.market_approval_server_api_key,
            "Content-Type": "application/json",
        }

        response = yield from self.get_http_response(
            method="POST",
            url=url,
            headers=headers,
        )

        if response.status_code == HTTP_NO_CONTENT:
            return RetrieveApprovedMarketRound.NO_MARKETS_RETRIEVED_PAYLOAD

        if response.status_code != HTTP_OK:
            self.context.logger.error(
                f"Could not retrieve response from {url}."
                f"Received status code {response.status_code}.\n{response}"
            )
            retries = 3  # TODO: Make params
            if retries >= MAX_RETRIES:
                return RetrieveApprovedMarketRound.MAX_RETRIES_PAYLOAD
            return RetrieveApprovedMarketRound.ERROR_PAYLOAD

        response_data = json.loads(response.body.decode())
        self.context.logger.info(f"Response received from {url}:\n {response_data}")

        print(response_data)
        return json.dumps(response_data, sort_keys=True)


class PrepareTransactionBehaviour(MarketCreationManagerBaseBehaviour):
    """PrepareTransactionBehaviour"""

    matching_round: Type[AbstractRound] = PrepareTransactionRound

    def _calculate_time_parameters(
        self,
        resolution_time: float,
        timeout: int,
    ) -> Tuple[int, int]:
        """Calculate time params."""
        days_to_opening = datetime.fromtimestamp(resolution_time + _ONE_DAY)
        opening_time = int(days_to_opening.timestamp())
        return opening_time, timeout * _ONE_DAY

    def _calculate_question_id(
        self,
        question_data: Dict,
        opening_timestamp: int,
        timeout: int,
        template_id: int = 2,
        question_nonce: int = 0,
    ) -> Generator[None, None, str]:
        """Calculate question ID."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.realitio_contract,
            contract_id=str(RealitioContract.contract_id),
            contract_callable="calculate_question_id",
            question_data=question_data,
            opening_timestamp=opening_timestamp,
            timeout=timeout,
            arbitrator_contract=self.params.arbitrator_contract,
            sender=self.synchronized_data.safe_contract_address,
            template_id=template_id,
            question_nonce=question_nonce,
        )
        return cast(str, response.state.body["question_id"])

    def _prepare_ask_question_mstx(
        self,
        question_data: Dict,
        opening_timestamp: int,
        timeout: int,
        template_id: int = 2,
        question_nonce: int = 0,
    ) -> Generator[None, None, Optional[Dict]]:
        """Prepare a multisend tx for `askQuestionMethod`"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.conditional_tokens_contract,
            contract_id=str(RealitioContract.contract_id),
            contract_callable="get_ask_question_tx_data",
            question_data=question_data,
            opening_timestamp=opening_timestamp,
            timeout=timeout,
            arbitrator_contract=self.params.arbitrator_contract,
            template_id=template_id,
            question_nonce=question_nonce,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"get_ask_question_tx_data unsuccessful!: {response}"
            )
            return None
        return {
            "to": self.params.realitio_contract,
            "data": response.state.body["data"],
            "value": self.params.realitio_answer_question_bounty,
        }

    def _prepare_prepare_condition_mstx(
        self,
        question_id: str,
        outcome_slot_count: int = 2,
    ) -> Generator[None, None, Optional[Dict]]:
        """Prepare a multisend tx for `askQuestionMethod`"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.conditional_tokens_contract,
            contract_id=str(ConditionalTokensContract.contract_id),
            contract_callable="get_prepare_condition_tx_data",
            question_id=question_id,
            oracle_contract=self.params.realitio_oracle_proxy_contract,
            outcome_slot_count=outcome_slot_count,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"get_prepare_condition_tx_data unsuccessful!: {response}"
            )
            return None
        return {
            "to": self.params.conditional_tokens_contract,
            "data": response.state.body["data"],
            "value": ETHER_VALUE,
        }

    def _prepare_create_fpmm_mstx(
        self,
        condition_id: str,
        initial_funds: float,
        market_fee: float,
    ) -> Generator[None, None, Optional[Dict]]:
        """Prepare a multisend tx for `askQuestionMethod`"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.fpmm_deterministic_factory_contract,
            contract_id=str(FPMMDeterministicFactory.contract_id),
            contract_callable="get_create_fpmm_tx_data",
            condition_id=condition_id,
            conditional_tokens=self.params.conditional_tokens_contract,
            collateral_token=self.params.collateral_tokens_contract,
            initial_funds=initial_funds,
            market_fee=market_fee,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"get_prepare_condition_tx_data unsuccessful!: {response}"
            )
            return None
        return {
            "to": self.params.fpmm_deterministic_factory_contract,
            "data": response.state.body["data"],
            "value": ETHER_VALUE,
            "approval_amount": response.state.body["value"],
        }

    def _get_approve_tx(self, amount: int) -> Generator[None, None, Optional[Dict]]:
        """Prepare a multisend tx for `askQuestionMethod`"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.collateral_tokens_contract,
            contract_id=str(WxDAIContract.contract_id),
            contract_callable="get_approve_tx_data",
            guy=self.params.fpmm_deterministic_factory_contract,
            amount=amount,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"get_approve_tx_data unsuccessful!: {response}"
            )
            return None
        return {
            "to": self.params.collateral_tokens_contract,
            "data": response.state.body["data"],
            "value": ETHER_VALUE,
        }

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            data = self.synchronized_data.approved_question_data
            question_data = {
                "question": data["question"],
                "answers": data["answers"],
                "topic": data["topic"],
                "language": data["language"],
            }
            self.context.logger.info(f"Preparing txs for {question_data=}")

            opening_timestamp, timeout = self._calculate_time_parameters(
                resolution_time=float(data["resolution_time"]),
                timeout=self.params.market_timeout,
            )
            self.context.logger.info(
                f"Opening time = {datetime.fromtimestamp(opening_timestamp)}"
            )
            self.context.logger.info(
                f"Closing time = {datetime.fromtimestamp(opening_timestamp + timeout)}"
            )

            question_id = yield from self._calculate_question_id(
                question_data=question_data,
                opening_timestamp=opening_timestamp,
                timeout=timeout,
            )
            self.context.logger.info(f"Calculated {question_id=}")

            ask_question_tx = yield from self._prepare_ask_question_mstx(
                question_data=question_data,
                opening_timestamp=opening_timestamp,
                timeout=timeout,
            )
            if ask_question_tx is None:
                return
            prepare_condition_tx = yield from self._prepare_prepare_condition_mstx(
                question_id=question_id,
            )
            if prepare_condition_tx is None:
                return
            condition_id = yield from self._calculate_condition_id(
                oracle_contract=self.params.realitio_oracle_proxy_contract,
                question_id=question_id,
            )
            self.context.logger.info(f"Calculated {condition_id=}")

            create_fpmm_tx = yield from self._prepare_create_fpmm_mstx(
                condition_id=condition_id,
                initial_funds=self.params.initial_funds,
                market_fee=self.params.market_fee,
            )
            if create_fpmm_tx is None:
                return

            amount = cast(int, create_fpmm_tx["approval_amount"])
            wxdai_approval_tx = yield from self._get_approve_tx(amount=amount)
            if wxdai_approval_tx is None:
                return

            self.context.logger.info(f"Added approval for {amount}")
            tx_hash = yield from self._to_multisend(
                transactions=[
                    wxdai_approval_tx,
                    ask_question_tx,
                    prepare_condition_tx,
                    create_fpmm_tx,
                ]
            )
            if tx_hash is None:
                return

            payload = PrepareTransactionPayload(
                sender=self.context.agent_address,
                content=tx_hash,
            )
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()


class PostTransactionBehaviour(MarketCreationManagerBaseBehaviour):
    """A behaviour that is called after a transaction has been settled."""

    matching_round: Type[AbstractRound] = PostTransactionRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            content = yield from self.get_payload()
            payload = PostTxPayload(sender=sender, content=content)
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def get_payload(self) -> Generator[None, None, str]:
        """Get the transaction payload"""
        settled_tx_hash = self.synchronized_data.settled_tx_hash
        if settled_tx_hash is None:
            self.context.logger.info("No settled tx hash.")
            return PostTransactionRound.DONE_PAYLOAD

        if (
            self.synchronized_data.tx_sender
            == MechRequestStates.MechRequestRound.auto_round_id()
        ):
            return PostTransactionRound.MECH_REQUEST_DONE_PAYLOAD

        if self.synchronized_data.tx_sender == RedeemBondRound.auto_round_id():
            return PostTransactionRound.REDEEM_BOND_DONE_PAYLOAD

        if self.synchronized_data.tx_sender == DepositDaiRound.auto_round_id():
            return PostTransactionRound.DEPOSIT_DAI_DONE_PAYLOAD

        if self.synchronized_data.tx_sender == AnswerQuestionsRound.auto_round_id():
            return PostTransactionRound.ANSWER_QUESTION_DONE_PAYLOAD

        if self.synchronized_data.tx_sender == RemoveFundingRound.auto_round_id():
            return PostTransactionRound.REMOVE_FUNDING_DONE_PAYLOAD

        is_approved_question_data_set = (
            self.synchronized_data.is_approved_question_data_set
        )
        if not is_approved_question_data_set:
            self.context.logger.info("No approved question data.")
            return PostTransactionRound.DONE_PAYLOAD

        data = self.synchronized_data.approved_question_data
        market_id = data.get("id", None)
        if market_id is None:
            self.context.logger.info("No market id.")
            return PostTransactionRound.DONE_PAYLOAD

        self.context.logger.info(
            f"Handling settled tx hash {settled_tx_hash}. "
            f"For market with id {market_id}. "
        )

        if self.synchronized_data.tx_sender != PrepareTransactionRound.auto_round_id():
            # we only handle market creation txs atm, any other tx, we don't need to take action
            self.context.logger.info(
                f"No handling required for tx sender with round id {self.synchronized_data.tx_sender}. "
                f"Handling only required for {PrepareTransactionRound.auto_round_id()}."
            )
            return PostTransactionRound.DONE_PAYLOAD

        payload = yield from self._handle_market_creation(market_id, settled_tx_hash)
        return payload

    def _handle_market_creation(
        self, market_id: str, tx_hash: str
    ) -> Generator[None, None, str]:
        """Handle market creation tx settlement."""
        # get fpmm id from the events
        fpmm_id = yield from self._get_fpmm_id(tx_hash)
        if fpmm_id is None:
            # something went wrong
            return PostTransactionRound.ERROR_PAYLOAD

        self.context.logger.info(f"Got fpmm_id {fpmm_id} for market {market_id}")

        # mark as done on the market approval server
        err = yield from self._mark_market_as_done(market_id, fpmm_id)
        if err is not None:
            # something went wrong
            return PostTransactionRound.ERROR_PAYLOAD

        return PostTransactionRound.DONE_PAYLOAD

    def _get_fpmm_id(self, tx_hash: str) -> Generator[None, None, Optional[str]]:
        """Get the fpmm id from the events"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.fpmm_deterministic_factory_contract,
            tx_hash=tx_hash,
            contract_id=str(FPMMDeterministicFactory.contract_id),
            contract_callable=get_callable_name(
                FPMMDeterministicFactory.parse_market_creation_event
            ),
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"{get_callable_name(FPMMDeterministicFactory.parse_market_creation_event)} unsuccessful!: {response}"
            )
            return None

        data = cast(Dict[str, Any], response.state.body["data"])
        fpmm_id = cast(str, data["fixed_product_market_maker"])
        return fpmm_id

    def _mark_market_as_done(
        self, id_: str, fpmm_id: str
    ) -> Generator[None, None, Optional[str]]:
        """Call the market approval server to signal that the provided market is created."""

        headers = {
            "Authorization": self.params.market_approval_server_api_key,
            "Content-Type": "application/json",
        }

        # Update the 'fpmm' field
        url = f"{self.params.market_approval_server_url}/update_market"
        body = {"id": id_, "fpmm_id": fpmm_id}
        http_response = yield from self.get_http_response(
            headers=headers,
            method="PUT",
            url=url,
            content=json.dumps(body).encode("utf-8"),
        )
        if http_response.status_code != HTTP_OK:
            self.context.logger.warning(
                f"Failed to update market: {http_response.status_code} {http_response}"
            )
            return str(http_response.body)

        body = json.loads(http_response.body.decode())
        self.context.logger.info(f"Successfully updated market, received body {body}")

        # Update the market id to match the 'fpmm' id
        url = f"{self.params.market_approval_server_url}/update_market_id"
        body = {"id": id_, "new_id": fpmm_id}
        http_response = yield from self.get_http_response(
            headers=headers,
            method="PUT",
            url=url,
            content=json.dumps(body).encode("utf-8"),
        )
        if http_response.status_code != HTTP_OK:
            self.context.logger.warning(
                f"Failed to update market id: {http_response.status_code} {http_response}"
            )
            return str(http_response.body)

        body = json.loads(http_response.body.decode())
        self.context.logger.info(
            f"Successfully updated market id, received body {body}"
        )

        return None


class GetPendingQuestionsBehaviour(MarketCreationManagerBaseBehaviour):
    """Gets Omen pending questions to close markets"""

    matching_round = GetPendingQuestionsRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            content = yield from self.get_payload()
            payload = GetPendingQuestionsPayload(sender=sender, content=content)
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def _get_unanswered_questions(
        self,
    ) -> Generator[None, None, List[Dict[str, Any]]]:
        """Collect FPMM from subgraph."""
        creator = self.synchronized_data.safe_contract_address.lower()
        response = yield from self.get_subgraph_result(
            query=OPEN_FPMM_QUERY.substitute(
                creator=creator,
                current_timestamp=self.last_synced_timestamp,
            )
        )
        if response is None:
            return []
        questions = response.get("data", {}).get("fixedProductMarketMakers", [])
        self.context.logger.info(f"Collected questions: {questions}")

        if not questions:
            return []

        return questions

    def _get_balance(self, account: str) -> Generator[None, None, Optional[int]]:
        """Get the balance of an account"""
        ledger_api_response = yield from self.get_ledger_api_response(
            performative=LedgerApiMessage.Performative.GET_STATE,
            ledger_callable="get_balance",
            account=account,
        )
        if ledger_api_response.performative != LedgerApiMessage.Performative.STATE:
            # something went wrong
            self.context.logger.error(
                f"Couldn't get balance for account {account}. "
                f"Expected response performative {LedgerApiMessage.Performative.STATE.value}, "  # type: ignore
                f"Received {ledger_api_response.performative.value}."  # type: ignore
            )
            return None
        balance = cast(int, ledger_api_response.state.body.get("get_balance_result"))
        return balance

    def _eligible_questions_to_answer(
        self, unanswered_questions: List[Dict[str, Any]]
    ) -> List[str]:
        """Determine the eligible questions to answer at this time"""
        now = self.last_synced_timestamp
        eligible_questions_id = []
        answer_retry_intervals = self.params.answer_retry_intervals

        self.context.logger.info(f"Answer retry intervals: {answer_retry_intervals}")

        for question in unanswered_questions:
            question_id = question["question"]["id"].lower()

            if question_id in self.shared_state.questions_responded:
                continue

            if question_id not in self.shared_state.questions_requested_mech:
                self.shared_state.questions_requested_mech[question_id] = {
                    "question": question,
                    "retries": [],
                }

            retries = self.shared_state.questions_requested_mech[question_id]["retries"]
            n_retries = len(retries)
            time_since_last_retry = now - retries[-1] if retries else 0
            retry_period = answer_retry_intervals[
                min(n_retries, len(answer_retry_intervals) - 1)
            ]
            if n_retries == 0 or time_since_last_retry > retry_period:
                eligible_questions_id.append(question_id)

        self.context.logger.info(
            f"Determined {len(eligible_questions_id)} eligible questions to answer."
        )

        num_questions = min(
            len(eligible_questions_id), self.params.multisend_batch_size
        )
        random.seed(self.last_synced_timestamp)
        random_questions_id = random.sample(eligible_questions_id, num_questions)

        self.context.logger.info(
            f"Chosen {len(random_questions_id)} eligible questions to answer."
        )
        return random_questions_id

    def get_payload(self) -> Generator[None, None, str]:
        """Get the transaction payload"""
        # get the questions to that need to be answered
        unanswered_questions = yield from self._get_unanswered_questions()

        if unanswered_questions is None:
            self.context.logger.info("Couldn't get the questions")
            return GetPendingQuestionsRound.ERROR_PAYLOAD

        eligible_questions_id = self._eligible_questions_to_answer(unanswered_questions)

        self.context.logger.info(f"{self.shared_state.questions_requested_mech=}")

        if len(eligible_questions_id) == 0:
            self.context.logger.info("No eligible questions to answer")
            return GetPendingQuestionsRound.NO_TX_PAYLOAD

        self.context.logger.info(
            f"Got {len(eligible_questions_id)} questions to close. "
            f"Questions ID: {eligible_questions_id}"
        )

        safe_address = self.synchronized_data.safe_contract_address
        balance = yield from self._get_balance(safe_address)
        if balance is None:
            self.context.logger.info("Couldn't get balance")
            return GetPendingQuestionsRound.NO_TX_PAYLOAD

        self.context.logger.info(f"Address {safe_address!r} has balance {balance}.")
        max_num_questions = min(
            len(eligible_questions_id), self.params.questions_to_close_batch_size
        )
        bond_required = self.params.realitio_answer_question_bond * max_num_questions

        # TODO uncomment
        if balance < bond_required:
            # not enough balance to close the questions
            self.context.logger.info(
                f"Not enough balance to close {max_num_questions} questions. "
                f"Balance {balance}, required {bond_required}"
            )
            return GetPendingQuestionsRound.NO_TX_PAYLOAD

        # Prepare the Mech Requests for these questions
        new_mech_requests = []
        for question_id in eligible_questions_id:
            question = self.shared_state.questions_requested_mech[question_id][
                "question"
            ]
            retries = self.shared_state.questions_requested_mech[question_id]["retries"]
            retries.append(self.last_synced_timestamp)

            self.context.logger.info(
                f"Requesting mech answer for question {question_id} ({question['title']})."
            )
            self.context.logger.info(f"Question {question_id} retries: {retries}.")

            new_mech_requests.append(
                asdict(
                    MechMetadata(
                        nonce=question_id,
                        tool=self.params.mech_tool_resolve_market,
                        prompt=question["title"],
                    )
                )
            )

        self.context.logger.info(f"new_mech_requests: {new_mech_requests}")

        if len(new_mech_requests) == 0:
            self.context.logger.info("No mech requests")
            return GetPendingQuestionsRound.NO_TX_PAYLOAD

        return json.dumps(new_mech_requests, sort_keys=True)


class AnswerQuestionsBehaviour(MarketCreationManagerBaseBehaviour):
    """Answer questions to close markets"""

    matching_round = AnswerQuestionsRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        self.context.logger.info("async_act")
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            content = yield from self._get_payload()
            payload = AnswerQuestionsPayload(sender=sender, content=content)
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def _parse_mech_response(self, response: MechInteractionResponse) -> Optional[str]:
        self.context.logger.info(f"_parse_mech_response: {response}")

        try:
            if response.result is None:
                return None

            data = json.loads(response.result)
            is_valid = data.get("is_valid", True)
            is_determinable = data.get("is_determinable", True)
            has_occurred = data.get("has_occurred", None)

            if not is_valid:
                return ANSWER_INVALID
            if not is_determinable:
                return None
            if has_occurred is False:
                return ANSWER_NO
            if has_occurred is True:
                return ANSWER_YES

            return None
        except json.JSONDecodeError:
            return None

    def _get_payload(self) -> Generator[None, None, str]:
        self.context.logger.info("_get_payload")
        self.context.logger.info(
            f"mech_responses = {self.synchronized_data.mech_responses}"
        )

        question_to_answer = {}
        for response in self.synchronized_data.mech_responses:
            question_id = response.nonce
            self.context.logger.info(
                f"Received mech response: {response.nonce} {response.result}"
            )

            if question_id in self.shared_state.questions_responded:
                continue

            if question_id not in self.shared_state.questions_requested_mech:
                continue

            question = self.shared_state.questions_requested_mech[question_id][
                "question"
            ]
            retries = self.shared_state.questions_requested_mech[question_id]["retries"]
            answer = self._parse_mech_response(response)

            if answer is None and len(retries) >= len(
                self.params.answer_retry_intervals
            ):
                self.context.logger.info(
                    f"Question {question} has been retried at timestamps {retries} without success. Assuming question is invalid."
                )
                answer = ANSWER_INVALID

            self.context.logger.info(f"Got answer {answer} for question {question}")

            if answer is None:
                self.context.logger.warning(
                    f"Couldn't get answer for question {question}"
                )
                continue
            question_to_answer[question_id] = answer

            if len(question_to_answer) == self.params.questions_to_close_batch_size:
                break

        self.context.logger.info(
            f"Got answers for {len(question_to_answer)} questions. "
        )
        if len(question_to_answer) == 0:
            # we couldn't get any answers, no tx to be made
            return AnswerQuestionsRound.NO_TX_PAYLOAD

        # prepare tx for all the answers
        txs = []
        for question_id, answer in question_to_answer.items():
            tx = yield from self._get_answer_tx(question_id, answer)
            if tx is None:
                # something went wrong, skip the current tx
                self.context.logger.warning(
                    f"Couldn't get tx for question {question_id} with answer {answer}"
                )
                continue
            txs.append(tx)
            # mark this question as processed. This is to avoid the situation where we
            # try to answer the same question multiple times due to a out-of-sync issue
            # between the subgraph and the realitio contract.
            self.shared_state.questions_responded.add(question_id)
            del self.shared_state.questions_requested_mech[question_id]

        if len(txs) == 0:
            # something went wrong, respond with ERROR payload for now
            self.context.logger.error(
                "Couldn't get any txs for questions that we have answers for."
            )
            return AnswerQuestionsRound.ERROR_PAYLOAD

        multisend_tx_str = yield from self._to_multisend(txs)
        if multisend_tx_str is None:
            # something went wrong, respond with ERROR payload for now
            return AnswerQuestionsRound.ERROR_PAYLOAD
        return multisend_tx_str

    def _get_answer_tx(
        self, question_id: str, answer: str
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Get an answer a tx."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.realitio_contract,
            contract_id=str(RealitioContract.contract_id),
            contract_callable="get_submit_answer_tx",
            question_id=bytes.fromhex(question_id[2:]),
            answer=bytes.fromhex(answer[2:]),
            max_previous=MAX_PREVIOUS,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Couldn't get submitAnswer transaction. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return None

        data = cast(bytes, response.state.body["data"])
        return {
            "to": self.params.realitio_contract,
            "value": self.params.realitio_answer_question_bond,
            "data": data,
        }


class MarketCreationManagerRoundBehaviour(AbstractRoundBehaviour):
    """MarketCreationManagerRoundBehaviour"""

    initial_behaviour_cls = CollectRandomnessBehaviour
    abci_app_cls = MarketCreationManagerAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = {
        CollectRandomnessBehaviour,
        CollectProposedMarketsBehaviour,
        GetPendingQuestionsBehaviour,
        AnswerQuestionsBehaviour,
        ApproveMarketsBehaviour,
        SelectKeeperMarketProposalBehaviour,
        RetrieveApprovedMarketBehaviour,
        PrepareTransactionBehaviour,
        SyncMarketsBehaviour,
        RemoveFundingBehaviour,
        DepositDaiBehaviour,
        RedeemBondBehaviour,
        PostTransactionBehaviour,
    }

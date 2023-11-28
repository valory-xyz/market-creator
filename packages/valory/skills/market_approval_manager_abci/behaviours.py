# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023 Valory AG
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

"""This package contains round behaviours of MarketApprovalManagerAbciApp."""

import json
import random
from abc import ABC
from datetime import datetime, timedelta, timezone
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

from packages.valory.connections.openai.connection import (
    PUBLIC_ID as LLM_CONNECTION_PUBLIC_ID,
)
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
from packages.valory.skills.market_approval_manager_abci.dialogues import (
    LlmDialogue,
    LlmDialogues,
)
from packages.valory.skills.market_approval_manager_abci.models import (
    MarketApprovalManagerParams,
    SharedState,
)
from packages.valory.skills.market_approval_manager_abci.payloads import (
    CollectRandomnessPayload,
    CollectMarketDataPayload,
    SelectKeeperPayload,
    MarketApprovalPayload,
)
from packages.valory.skills.market_approval_manager_abci.rounds import (
    CollectRandomnessRound,
    CollectMarketDataRound,
    SelectKeeperRound,
    MarketApprovalRound,
)


HTTP_OK = 200
HTTP_NO_CONTENT = 204
MAX_RETRIES = 3
SAFE_TX_GAS = 0
ETHER_VALUE = 0


AVAILABLE_FORMATS = (
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d",
)


_ONE_DAY = 86400

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
ZERO_HASH = "0x0000000000000000000000000000000000000000000000000000000000000000"

FPMM_QUERY = Template(
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


class MarketApprovalManagerBaseBehaviour(BaseBehaviour, ABC):
    """Base behaviour for the market_approval_manager_abci skill."""

    @property
    def synchronized_data(self) -> SynchronizedData:
        """Return the synchronized data."""
        return cast(SynchronizedData, super().synchronized_data)

    @property
    def params(self) -> MarketApprovalManagerParams:
        """Return the params."""
        return cast(MarketApprovalManagerParams, super().params)

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


class CollectRandomnessBehaviour(RandomnessBehaviour):
    """CollectRandomnessBehaviour"""

    matching_round: Type[AbstractRound] = CollectRandomnessRound
    payload_class = CollectRandomnessPayload


class SyncMarketsBehaviour(MarketApprovalManagerBaseBehaviour):
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
        response = yield from self._get_subgraph_result(
            query=FPMM_QUERY.substitute(
                creator=self.synchronized_data.safe_contract_address.lower(),
            )
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

    def _get_subgraph_result(
        self,
        query: str,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Get question ids."""
        response = yield from self.get_http_response(
            content=to_content(query),
            **self.context.omen_subgraph.get_spec(),
        )
        return json.loads(response.body.decode())


class CollectMarketsDataBehaviour(MarketApprovalManagerBaseBehaviour):
    """DataGatheringBehaviour"""

    matching_round: Type[AbstractRound] = DataGatheringRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            current_timestamp = self.last_synced_timestamp
            last_proposed_markets_timestamp = (
                self.synchronized_data.proposed_markets_data["timestamp"]
            )
            proposed_markets_count = self.synchronized_data.proposed_markets_count

            self.context.logger.info(
                f"proposed_markets_count={proposed_markets_count} max_proposed_markets={self.params.max_proposed_markets} proposed_markets_data_timestamp={last_proposed_markets_timestamp} current_timestamp={current_timestamp} min_market_proposal_interval_seconds={self.params.min_market_proposal_interval_seconds}"
            )

            if (
                self.params.max_proposed_markets >= 0
                and proposed_markets_count >= self.params.max_proposed_markets
            ):
                self.context.logger.info("Max markets proposed reached.")
                gathered_data = DataGatheringRound.MAX_PROPOSED_MARKETS_REACHED_PAYLOAD
            elif (
                current_timestamp - last_proposed_markets_timestamp
                < self.params.min_market_proposal_interval_seconds
            ):
                self.context.logger.info("Timeout to propose new markets not reached.")
                gathered_data = DataGatheringRound.SKIP_MARKET_PROPOSAL_PAYLOAD
            else:
                self.context.logger.info("Timeout to propose new markets reached.")
                gathered_data = yield from self._gather_data()

            payload = DataGatheringPayload(
                sender=sender,
                gathered_data=gathered_data,
            )
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _gather_data(self) -> Generator[None, None, str]:
        """Auxiliary method to collect data from endpoint."""
        news_sources = self.params.news_sources
        headers = {"X-Api-Key": self.params.newsapi_api_key}

        random.seed(
            "DataGatheringBehaviour" + self.synchronized_data.most_voted_randomness, 2
        )  # nosec
        k = min(10, len(news_sources))
        sources = random.sample(news_sources, k)

        parameters = {
            "sources": ",".join(sources),
            "pageSize": "100",
        }
        response = yield from self.get_http_response(
            method="GET",
            url=self.params.newsapi_endpoint,
            headers=headers,
            parameters=parameters,
        )
        if response.status_code != HTTP_OK:
            self.context.logger.error(
                f"Could not retrieve response from {self.params.newsapi_endpoint}."
                f"Received status code {response.status_code}.\n{response}"
            )
            retries = 3  # TODO: Make params
            if retries >= MAX_RETRIES:
                return DataGatheringRound.MAX_RETRIES_PAYLOAD
            return DataGatheringRound.ERROR_PAYLOAD

        response_data = json.loads(response.body.decode())
        self.context.logger.info(
            f"Response received from {self.params.newsapi_endpoint}:\n {response_data}"
        )
        return json.dumps(response_data, sort_keys=True)


class SelectKeeperMarketProposalBehaviour(SelectKeeperBehaviour):
    """Select the keeper agent."""

    matching_round = SelectKeeperRound
    payload_class = SelectKeeperPayload


class MarketApprovalBehaviour(MarketApprovalManagerBaseBehaviour):
    """MarketProposalBehaviour"""

    matching_round: Type[AbstractRound] = MarketProposalRound

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
                "MarketProposalBehaviour"
                + self.synchronized_data.most_voted_randomness,
                2,
            )  # nosec

            events_datetime = self._generate_events_datetime(
                self.last_synced_timestamp,
                self.params.event_offset_start_days,
                self.params.event_offset_end_days,
            )

            all_proposed_markets = []
            for dt in events_datetime:
                self.context.logger.info(f"Proposing markets for {dt}")
                data = json.loads(self.synchronized_data.gathered_data)
                k = min(40, len(data["articles"]))
                selected_news_articles = random.sample(data["articles"], k)
                proposed_markets = yield from self._get_llm_response(
                    dt, selected_news_articles
                )

                all_proposed_markets.extend(proposed_markets)

            if self.params.max_proposed_markets == -1:
                n_markets_to_propose = len(all_proposed_markets)
            else:
                remaining_markets = (
                    self.params.max_proposed_markets
                    - self.synchronized_data.proposed_markets_count
                )
                n_markets_to_propose = min(remaining_markets, len(all_proposed_markets))

            for q in all_proposed_markets[:n_markets_to_propose]:
                yield from self._propose_market(q)

            sender = self.context.agent_address
            payload_content = {
                "proposed_markets": all_proposed_markets,
                "timestamp": self.last_synced_timestamp,
            }
            payload = MarketProposalPayload(
                sender=sender,
                content=json.dumps(payload_content, sort_keys=True),
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _generate_events_datetime(
        self,
        reference_day_timestamp: float,
        offset_start_days: int,
        offset_end_days: int,
    ) -> list[datetime]:
        """Generate 02:00 UTC datetimes between date(timestamp) + offset_start_days and date(timestamp) + offset_end_days"""
        datetimes = []
        reference_day = datetime.utcfromtimestamp(reference_day_timestamp).date()
        reference_day_at_midnight = datetime(
            reference_day.year, reference_day.month, reference_day.day
        ).replace(hour=2, minute=0, second=0)
        reference_day_at_midnight.replace(tzinfo=timezone.utc)

        for i in range(offset_start_days, offset_end_days + 1):
            new_day_timestamp = reference_day_at_midnight + timedelta(days=i)
            datetimes.append(new_day_timestamp)

        return datetimes

    def _get_llm_response(
        self, event_day: datetime, news_articles: list[dict[str, Any]]
    ) -> Generator[None, None, list[Any]]:
        """Get the LLM response"""

        input_news = ""
        for article in news_articles:
            title = article["title"]
            content = article["content"]
            date = article["publishedAt"]
            input_news += f"- ({date}) {title}\n  {content}\n\n"

        topics = ", ".join(self.params.topics)
        prompt_template = self.params.market_identification_prompt
        prompt_values = {
            "input_news": input_news,
            "topics": topics,
            "event_day": event_day.strftime("%-d %B %Y"),
        }

        self.context.logger.info(
            f"Sending LLM request...\nprompt_template={prompt_template}\nprompt_values={prompt_values}"
        )

        llm_dialogues = cast(LlmDialogues, self.context.llm_dialogues)

        # llm request message
        request_llm_message, llm_dialogue = llm_dialogues.create(
            counterparty=str(LLM_CONNECTION_PUBLIC_ID),
            performative=LlmMessage.Performative.REQUEST,
            prompt_template=prompt_template,
            prompt_values=prompt_values,
        )
        request_llm_message = cast(LlmMessage, request_llm_message)
        llm_dialogue = cast(LlmDialogue, llm_dialogue)
        llm_response_message = yield from self._do_llm_request(
            request_llm_message, llm_dialogue
        )
        result = llm_response_message.value.replace("OUTPUT:", "").rstrip().lstrip()
        self.context.logger.info(f"Got LLM response: {result}")

        data = json.loads(result)
        valid_responses = []
        for q in data:
            try:
                # Date of the outcome
                resolution_date = parse_date_timestring(q["resolution_date"])
                if resolution_date is None:
                    self.context.logger.error(
                        "Cannot parse datestring " + q["resolution_date"]
                    )
                    continue
                valid_responses.append(
                    {
                        "question": q["question"],
                        "answers": q["answers"],
                        "topic": q["topic"],
                        "language": "en_US",
                        "resolution_time": int(resolution_date.timestamp()),
                    }
                )
            except (ValueError, TypeError, KeyError) as e:
                self.context.logger.error(
                    f"Error converting question object {q} with error {e}"
                )
                continue
        return valid_responses

    def _do_llm_request(
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

    def _propose_market(
        self, proposed_market_data: Dict[str, str]
    ) -> Generator[None, None, str]:
        """Auxiliary method to propose a market to the endpoint."""
        self.context.logger.info(f"Proposing market {proposed_market_data}")

        url = self.params.market_approval_server_url + "/propose_market"
        headers = {
            "Authorization": self.params.market_approval_server_api_key,
            "Content-Type": "application/json",
        }

        response = yield from self.get_http_response(
            method="POST",
            url=url,
            headers=headers,
            content=json.dumps(proposed_market_data).encode("utf-8"),
        )
        if response.status_code != HTTP_OK:
            self.context.logger.error(
                f"Could not retrieve response from {url}."
                f"Received status code {response.status_code}.\n{response}"
            )
            retries = 3  # TODO: Make params
            if retries >= MAX_RETRIES:
                return MarketProposalRound.MAX_RETRIES_PAYLOAD
            return MarketProposalRound.ERROR_PAYLOAD

        response_data = json.loads(response.body.decode())
        self.context.logger.info(f"Response received from {url}:\n {response_data}")
        return json.dumps(response_data, sort_keys=True)



class MarketApprovalManagerRoundBehaviour(AbstractRoundBehaviour):
    """MarketApprovalManagerRoundBehaviour"""

    initial_behaviour_cls = CollectRandomnessBehaviour
    abci_app_cls = MarketApprovalManagerAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = {
        CollectRandomnessBehaviour,
        CollectMarketsDataBehaviour,
        SelectKeeperMarketProposalBehaviour,
        MarketApprovalBehaviour,
    }

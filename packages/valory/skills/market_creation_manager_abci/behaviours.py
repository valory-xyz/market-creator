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

"""This package contains round behaviours of MarketCreationManagerAbciApp."""

import datetime
import json
import random
from abc import ABC
from typing import Any, Dict, Generator, List, Optional, Set, Tuple, Type, cast

from packages.valory.connections.openai.connection import (
    PUBLIC_ID as LLM_CONNECTION_PUBLIC_ID,
)
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
from packages.valory.contracts.realtio.contract import RealtioContract
from packages.valory.contracts.wxdai.contract import WxDAIContract
from packages.valory.protocols.contract_api import ContractApiMessage
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
from packages.valory.skills.market_creation_manager_abci.dialogues import (
    LlmDialogue,
    LlmDialogues,
)
from packages.valory.skills.market_creation_manager_abci.models import (
    MarketCreationManagerParams,
    SharedState,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    SyncMarketsPayload,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    CollectRandomnessPayload,
    CollectRandomnessRound,
    DataGatheringPayload,
    DataGatheringRound,
    MarketCreationManagerAbciApp,
    MarketProposalPayload,
    MarketProposalRound,
    PrepareTransactionPayload,
    PrepareTransactionRound,
    RemoveFundingRound,
    RetrieveApprovedMarketPayload,
    RetrieveApprovedMarketRound,
    SelectKeeperPayload,
    SelectKeeperRound,
    SyncMarketsRound,
    SynchronizedData,
)
from packages.valory.skills.transaction_settlement_abci.payload_tools import (
    hash_payload_to_hex,
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


def parse_date_timestring(string: str) -> Optional[datetime.datetime]:
    """Parse and return a datetime string."""
    for format in AVAILABLE_FORMATS:
        try:
            return datetime.datetime.strptime(string, format)
        except ValueError:
            continue
    return None


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


class CollectRandomnessBehaviour(RandomnessBehaviour):
    """CollectRandomnessBehaviour"""

    matching_round: Type[AbstractRound] = CollectRandomnessRound
    payload_class = CollectRandomnessPayload


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
        # it means we have already synced
        market_removal = yield from self.get_markets_to_removal_ts()
        if market_removal is None:
            # something went wrong
            return SyncMarketsRound.ERROR_PAYLOAD

        market_removal_ts, from_block = market_removal
        if len(market_removal_ts) == 0:
            # no markets to sync
            return SyncMarketsRound.NO_UPDATE_PAYLOAD

        market_removal_ts_str = json.dumps(
            dict(mapping=market_removal_ts, from_block=from_block), sort_keys=True
        )
        return market_removal_ts_str

    def get_markets_to_removal_ts(
        self,
    ) -> Generator[None, None, Optional[Tuple[Dict[str, int], int]]]:
        """
        Sync markets.

        :returns: a tuple of the markets to removal timestamp and the last block to be monitored.
        :yields: None
        """
        # get created markets that still have funds
        market_creator = self.synchronized_data.safe_contract_address
        from_block = self.synchronized_data.market_from_block
        markets = yield from self._get_markets_with_funds(market_creator, from_block)
        if markets is None:
            # something went wrong
            return None

        # if no markets, no need to execute the rest of the code
        if len(markets) == 0:
            return {}, 0

        # get conditions associated with those markets
        condition_id_to_market = {}
        for market in markets:
            for condition_id in market["condition_ids"]:
                condition_id_to_market[condition_id] = market
        condition_ids = list(condition_id_to_market.keys())
        condition_preparations = yield from self._get_condition_preparation_events(
            condition_ids, from_block
        )
        if condition_preparations is None:
            # something went wrong
            return None

        question_to_market = {}
        for condition_preparation in condition_preparations:
            question_id = condition_preparation["question_id"]
            condition_id = condition_preparation["condition_id"]
            if condition_id not in condition_id_to_market:
                # this condition is not associated with a market
                self.context.logger.warning(
                    f"{condition_id} is not associated with a market"
                )
                continue
            market = condition_id_to_market[condition_id]
            question_to_market[question_id] = market

        # get question
        question_ids = [
            preparation["question_id"] for preparation in condition_preparations
        ]
        questions = yield from self._get_questions(question_ids, from_block)
        if questions is None:
            # something went wrong
            return None

        # market_to_removal_ts will act as a mapping between
        # markets and their funds (liquidity) removal timestamp
        market_to_removal_ts = {}
        for question in questions:
            question_id = question["question_id"]
            if question_id not in question_to_market:
                # this question is not associated with a market
                self.context.logger.warning(
                    f"{question_id} is not associated with a market"
                )
                continue
            market = question_to_market[question_id]
            market_address = market["fixed_product_market_maker"]
            # we remove the funds 1 day before the opening ts
            removal_ts = question["opening_ts"] - _ONE_DAY
            market_to_removal_ts[market_address] = removal_ts

        from_block_number = max([market["block_number"] for market in markets])
        return market_to_removal_ts, from_block_number

    def _get_created_markets(
        self, creator_address: str, from_block: int
    ) -> Generator[None, None, Optional[List[Dict[str, Any]]]]:
        """Get created markets."""
        contract_api_response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.fpmm_deterministic_factory_contract,
            contract_id=str(FPMMDeterministicFactory.contract_id),
            contract_callable="get_market_creation_events",
            creator_address=creator_address,
            from_block=from_block,
        )
        if contract_api_response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Failed to get created markets: {contract_api_response}"
            )
            return None

        markets = cast(
            Optional[List[Dict[str, Any]]], contract_api_response.state.body.get("data")
        )
        return markets

    def _get_markets_with_funds(
        self, creator_address: str, from_block: int = 0
    ) -> Generator[None, None, Optional[List[Dict[str, Any]]]]:
        """Get markets with liquidity."""
        markets = yield from self._get_created_markets(creator_address, from_block)
        if markets is None:
            # something went wrong
            return None

        market_addresses = [market["fixed_product_market_maker"] for market in markets]
        contract_api_response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            # the contract address is not used in the contract callable
            # but is required by the contract api
            contract_address=ZERO_ADDRESS,
            contract_id=str(FPMMContract.contract_id),
            contract_callable="get_markets_with_funds",
            markets=market_addresses,
        )
        if contract_api_response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Failed to get markets with funds: {contract_api_response}"
            )
            return None
        market_addresses_with_liq = cast(
            List[str],
            contract_api_response.state.body.get("data", []),
        )
        markets_with_liq = [
            market
            for market in markets
            if market["fixed_product_market_maker"] in market_addresses_with_liq
        ]
        return markets_with_liq

    def _get_condition_preparation_events(
        self,
        condition_ids: List[bytes],
        from_block: int,
    ) -> Generator[None, None, Optional[List[Dict[str, Any]]]]:
        """Get condition preparation events."""
        contract_api_response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.conditional_tokens_contract,
            contract_id=str(ConditionalTokensContract.contract_id),
            contract_callable="get_condition_preparation_events",
            condition_ids=condition_ids,
            from_block=from_block,
        )
        if contract_api_response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Failed to get condition preparation events: {contract_api_response}"
            )
            return None
        condition_preparation_events = cast(
            Optional[List[Dict[str, Any]]],
            contract_api_response.state.body.get("data", []),
        )
        return condition_preparation_events

    def _get_questions(
        self, question_ids: List[str], from_block: int
    ) -> Generator[None, None, Optional[List[Dict[str, Any]]]]:
        """Get question ids."""
        contract_api_response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.realitio_contract,
            contract_id=str(RealtioContract.contract_id),
            contract_callable="get_question_events",
            question_ids=question_ids,
            from_block=from_block,
        )
        if contract_api_response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Failed to get question: {contract_api_response}"
            )
            return None
        questions = cast(
            Optional[List[Dict[str, Any]]],
            contract_api_response.state.body.get("data", []),
        )
        return questions


class RemoveFundingBehaviour(MarketCreationManagerBaseBehaviour):
    """Remove funding behaviour."""

    matching_round = RemoveFundingRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            content = yield from self.get_payload()
            payload = PrepareTransactionPayload(sender=sender, content=content)
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def get_payload(self) -> Generator[None, None, str]:
        """Get payload."""
        market_to_close = self._get_market_to_close()
        if market_to_close is None:
            return RemoveFundingRound.NO_UPDATE_PAYLOAD

        tx_data = yield from self._get_remove_funding_tx(market_to_close)
        if tx_data is None:
            # something went wrong
            return RemoveFundingRound.ERROR_PAYLOAD

        safe_tx_hash = yield from self._get_safe_tx_hash(market_to_close, tx_data)
        if safe_tx_hash is None:
            # something went wrong
            return RemoveFundingRound.ERROR_PAYLOAD

        tx_payload_data = hash_payload_to_hex(
            safe_tx_hash=safe_tx_hash,
            ether_value=ETHER_VALUE,
            safe_tx_gas=SAFE_TX_GAS,
            to_address=market_to_close,
            data=tx_data,
        )

        payload_content = {
            "tx": tx_payload_data,
            "market": market_to_close,
        }
        return json.dumps(payload_content)

    def _get_market_to_close(self) -> Optional[str]:
        """Returns tx data for closing a tx."""
        market_to_remove_funds_deadline = (
            self.synchronized_data.market_to_remove_funds_deadline
        )
        for market, ts in market_to_remove_funds_deadline.items():
            if ts < self.last_synced_timestamp:
                return market
        return None

    def _get_remove_funding_tx(
        self,
        market_address: str,
    ) -> Generator[None, None, Optional[bytes]]:
        """This function returns the encoded FPMMContract.removeFunds() function call."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_id=str(FPMMContract.contract_id),
            contract_callable="build_remove_funding_tx",
            contract_address=market_address,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Couldn't get tx data for ManagedPoolContract.update_weights_gradually. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return None

        # strip "0x" from the response data
        data_str = cast(str, response.state.body["data"])[2:]
        data = bytes.fromhex(data_str)
        return data

    def _get_safe_tx_hash(
        self, market_address: str, data: bytes
    ) -> Generator[None, None, Optional[str]]:
        """Prepares and returns the safe tx hash."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.synchronized_data.safe_contract_address,  # the safe contract address
            contract_id=str(GnosisSafeContract.contract_id),
            contract_callable="get_raw_safe_transaction_hash",
            to_address=market_address,  # the contract the safe will invoke
            value=ETHER_VALUE,
            data=data,
            safe_tx_gas=SAFE_TX_GAS,
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


class DataGatheringBehaviour(MarketCreationManagerBaseBehaviour):
    """DataGatheringBehaviour"""

    matching_round: Type[AbstractRound] = DataGatheringRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            if self.synchronized_data.markets_created < cast(
                int, self.params.num_markets
            ):
                gathered_data = yield from self._gather_data()
            else:
                gathered_data = DataGatheringRound.MAX_MARKETS_REACHED
            payload = DataGatheringPayload(sender=sender, gathered_data=gathered_data)
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _gather_data(self) -> Generator[None, None, str]:
        """Auxiliary method to collect data from endpoint."""
        headers = {"X-Api-Key": self.params.newsapi_api_key}
        today = datetime.date.today()
        from_date = today - datetime.timedelta(days=7)
        to_date = today
        topics_string = " OR ".join(self.params.topics)

        parameters = {
            "q": topics_string,
            "language": "en",
            "sortBy": "popularity",
            "from": from_date.strftime("%y-%m-%d"),
            "to": to_date.strftime("%y-%m-%d"),
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


class MarketProposalBehaviour(MarketCreationManagerBaseBehaviour):
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
            payload_data = yield from self._get_llm_response()
            if payload_data is None:
                return

            yield from self._propose_market(payload_data)

            sender = self.context.agent_address
            payload = MarketProposalPayload(
                sender=sender, content=json.dumps(payload_data, sort_keys=True)
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _get_llm_response(self) -> Generator[None, None, Optional[dict]]:
        """Get the LLM response"""
        data = json.loads(self.synchronized_data.gathered_data)
        articles = data["articles"]
        random.seed(self.synchronized_data.most_voted_randomness, 2)  # nosec
        random.shuffle(articles)

        input_news = ""
        for article in articles[0:5]:
            title = article["title"]
            content = article["content"]
            date = article["publishedAt"]
            input_news += f"- ({date}) {title}\n  {content}\n\n"

        event_day = self._get_event_day()
        topics = ", ".join(self.params.topics)
        prompt_template = self.params.market_identification_prompt
        prompt_values = {
            "input_news": input_news,
            "topics": topics,
            "event_day": event_day,
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
        # Opening date for realitio oracle contract and closing date
        # for answering question on omen market
        minimum_opening_date = datetime.datetime.fromtimestamp(
            self.context.state.round_sequence.last_round_transition_timestamp.timestamp()
            + (_ONE_DAY * self.params.minimum_market_time)
        )
        for q in data:
            try:
                # Date of the outcome
                resolution_date = parse_date_timestring(q["resolution_date"])
                if resolution_date is None:
                    self.context.logger.error(
                        "Cannot parse datestring " + q["resolution_date"]
                    )
                    continue
                if resolution_date < minimum_opening_date:
                    self.context.logger.error(
                        "Invalid resolution date " + q["resolution_date"]
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
        if len(valid_responses) == 0:
            return None
        return valid_responses[0]

    def _get_event_day(self) -> str:
        # Get the current date
        n = self.synchronized_data.markets_created
        today = datetime.datetime.now().date()

        # Set the target year and month
        target_year = 2023
        target_month = 8
        minimum_days_until_event = self.params.minimum_market_time + 1

        # Calculate the start_date in August (at least today + 2 days)
        start_date = max(
            datetime.date(target_year, target_month, 1),
            today + datetime.timedelta(days=minimum_days_until_event),
        )
        end_date = datetime.date(target_year, target_month, 31)
        days_difference = abs((end_date - start_date).days)
        event_day = start_date + datetime.timedelta(n % (days_difference + 1))

        return event_day.strftime("%-d %B %Y")

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
        self, proposed_question_data: Dict[str, str]
    ) -> Generator[None, None, str]:
        """Auxiliary method to propose a market to the endpoint."""

        url = self.params.market_approval_server_url + "/propose_market"
        headers = {
            "Authorization": self.params.market_approval_server_api_key,
            "Content-Type": "application/json",
        }

        response = yield from self.get_http_response(
            method="POST",
            url=url,
            headers=headers,
            content=json.dumps(proposed_question_data).encode("utf-8"),
        )
        if response.status_code != HTTP_OK:
            self.context.logger.error(
                f"Could not retrieve response from {url}."
                f"Received status code {response.status_code}.\n{response}"
            )
            retries = 3  # TODO: Make params
            if retries >= MAX_RETRIES:
                return DataGatheringRound.MAX_RETRIES_PAYLOAD
            return DataGatheringRound.ERROR_PAYLOAD

        response_data = json.loads(response.body.decode())
        self.context.logger.info(f"Response received from {url}:\n {response_data}")
        return json.dumps(response_data, sort_keys=True)


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
        days_to_opening = datetime.datetime.fromtimestamp(resolution_time + _ONE_DAY)
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
            contract_id=str(RealtioContract.contract_id),
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
            contract_id=str(RealtioContract.contract_id),
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
            "value": ETHER_VALUE,
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
                resolution_time=data["resolution_time"],
                timeout=self.params.market_timeout,
            )
            self.context.logger.info(
                f"Opening time = {datetime.datetime.fromtimestamp(opening_timestamp)}"
            )
            self.context.logger.info(
                f"Closing time = {datetime.datetime.fromtimestamp(opening_timestamp + timeout)}"
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
        tx_hash = yield from self._get_safe_tx_hash(tx_data)
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

    def _get_safe_tx_hash(self, data: bytes) -> Generator[None, None, Optional[str]]:
        """
        Prepares and returns the safe tx hash.

        This hash will be signed later by the agents, and submitted to the safe contract.
        Note that this is the transaction that the safe will execute, with the provided data.

        :param data: the safe tx data.
        :yield: None
        :return: the tx hash
        """
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.synchronized_data.safe_contract_address,
            contract_id=str(GnosisSafeContract.contract_id),
            contract_callable="get_raw_safe_transaction_hash",
            to_address=self.params.multisend_address,  # we send the tx to the multisend address
            value=ETHER_VALUE,
            data=data,
            safe_tx_gas=SAFE_TX_GAS,
            operation=SafeOperation.DELEGATE_CALL.value,
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


class MarketCreationManagerRoundBehaviour(AbstractRoundBehaviour):
    """MarketCreationManagerRoundBehaviour"""

    initial_behaviour_cls = CollectRandomnessBehaviour
    abci_app_cls = MarketCreationManagerAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = {
        CollectRandomnessBehaviour,
        DataGatheringBehaviour,
        SelectKeeperMarketProposalBehaviour,
        MarketProposalBehaviour,
        RetrieveApprovedMarketBehaviour,
        PrepareTransactionBehaviour,
    }

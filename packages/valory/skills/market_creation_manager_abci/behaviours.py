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
import math
import random
from abc import ABC
from typing import Dict, Generator, List, Optional, Set, Tuple, Type, cast

from packages.valory.connections.openai.connection import (
    PUBLIC_ID as LLM_CONNECTION_PUBLIC_ID,
)
from packages.valory.contracts.conditional_tokens.contract import (
    ConditionalTokensContract,
)
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
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    CollectRandomnessPayload,
    CollectRandomnessRound,
    DataGatheringPayload,
    DataGatheringRound,
    MarketCreationManagerAbciApp,
    MarketIdentificationPayload,
    MarketIdentificationRound,
    PrepareTransactionPayload,
    PrepareTransactionRound,
    SelectKeeperPayload,
    SelectKeeperRound,
    SynchronizedData,
)
from packages.valory.skills.transaction_settlement_abci.payload_tools import (
    hash_payload_to_hex,
)


HTTP_OK = 200
MAX_RETRIES = 3
SAFE_TX_GAS = 0
ETHER_VALUE = 0
DEFAULT_MARKET_FEE = 2.0

ORACLE_XDAI = "0xab16d643ba051c11962da645f74632d3130c81e2"
REALTIO_XDAI = "0x79e32aE03fb27B07C89c0c568F80287C01ca2E57"
CONDIOTIONAL_TOKENS_XDAI = "0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce"
FPMM_DETERMINISTIC_FACTORY = "0x9083A2B699c0a4AD06F63580BDE2635d26a3eeF0"

MARKET_IDENTIFICATION_PROMPT = """
You are an LLM inside a multi-agent system. Your task is to propose a collection of prediction market questions based
on your input. Your input is under the label "INPUT". You must follow the instructions under "INSTRUCTIONS".
You must provide your response in the format specified under "OUTPUT_FORMAT".

INSTRUCTIONS
* Read the input under the label "INPUT" delimited by three backticks.
* The "INPUT" specifies a list of recent news headlines, their date, and short descriptions.
* Based on the "INPUT" and your training data, you must provide a list of binary questions, valid answers and resolution dates to create prediction markets.
  Each market must satisfy the following conditions:
  - The outcome of the market is unknown at the present date.
  - The outcome of the market must be known by its resolution date.
  - The outcome of the market must be related to a deterministic, measurable or verifiable fact.
  - Questions whose answer is known at the present date are invalid.
  - Questions whose answer is subjective or opinionated are invalid.
  - Questions with relative dates are invalid.
  - Questions about moral values, subjective opinions and not facts are invalid.
  - Questions in which none of the answers are valid will resolve as invalid.
  - Questions with multiple valid answers are invalid.
  - Questions must not incentive to commit an immoral violent action.
  - The dates in the question needs to be in YYYY-MM-DD format.
* The created markets must be different and not overlap semantically.
* You must provide your response in the format specified under "OUTPUT_FORMAT".
* Do not include any other contents in your response.

INPUT:
```
{input_news}
```

OUTPUT_FORMAT:
* Your output response must be only a single JSON array to be parsed by Python's "json.loads()".
* The JSON array must be of length 5.
* All of the date strings should be represented in YYYY-MM-DD format.
* Each entry of the JSON array must be a JSON object containing the fields:
  - question: The binary question to open a prediction market.
  - answers: The possible answers to the question.
  - resolution_date: The resolution date for the outcome of the market to be verified.
  - topic: One word description of topic the news and it should be one of the business, cryptocurrency, politics, science, technology.
* Output only the JSON object. Do not include any other contents in your response.
"""

AVAILABLE_FORMATS = (
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d",
)


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


class CollectRandomnessBehaviour(RandomnessBehaviour):
    """CollectRandomnessBehaviour"""

    matching_round: Type[AbstractRound] = CollectRandomnessRound
    payload_class = CollectRandomnessPayload


class DataGatheringBehaviour(MarketCreationManagerBaseBehaviour):
    """DataGatheringBehaviour"""

    matching_round: Type[AbstractRound] = DataGatheringRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            if self.synchronized_data.markets_created < self.params.num_markets:
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
        parameters = {
            "q": "business OR cryptocurrency OR politics OR science OR technology",
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
            retries = self.synchronized_data.newsapi_endpoint_retries + 1
            if retries >= MAX_RETRIES:
                return DataGatheringRound.MAX_RETRIES_PAYLOAD
            return DataGatheringRound.ERROR_PAYLOAD

        response_data = json.loads(response.body.decode())
        self.context.logger.info(
            f"Response received from {self.params.newsapi_endpoint}:\n {response_data}"
        )
        return json.dumps(response_data, sort_keys=True)


class SelectKeeperMarketIdentificationBehaviour(SelectKeeperBehaviour):
    """Select the keeper agent."""

    matching_round = SelectKeeperRound
    payload_class = SelectKeeperPayload


class MarketIdentificationBehaviour(MarketCreationManagerBaseBehaviour):
    """MarketIdentificationBehaviour"""

    matching_round: Type[AbstractRound] = MarketIdentificationRound

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
            sender = self.context.agent_address
            payload = MarketIdentificationPayload(
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

        prompt_template = MARKET_IDENTIFICATION_PROMPT
        prompt_values = {"input_news": input_news}
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
        llm_response_message = yield from self._do_request(
            request_llm_message, llm_dialogue
        )
        result = llm_response_message.value.replace("OUTPUT:", "").rstrip().lstrip()
        self.context.logger.info(f"Got LLM response: {result}")
        data = json.loads(result)
        valid_responses = []
        minimum_resolution_date = datetime.datetime.fromtimestamp(
            self.context.state.round_sequence.last_round_transition_timestamp.timestamp()
            + (3600 * 24)
        )
        for q in data:
            try:
                resolution_date = parse_date_timestring(q["resolution_date"])
                if resolution_date is None:
                    self.context.logger.error(
                        "Cannot parse datestring " + q["resolution_date"]
                    )
                    continue
                if resolution_date < minimum_resolution_date:
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

    def _do_request(
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


class PrepareTransactionBehaviour(MarketCreationManagerBaseBehaviour):
    """PrepareTransactionBehaviour"""

    matching_round: Type[AbstractRound] = PrepareTransactionRound

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
            contract_address=REALTIO_XDAI,
            contract_id=str(RealtioContract.contract_id),
            contract_callable="calculate_question_id",
            question_data=question_data,
            opening_timestamp=opening_timestamp,
            timeout=timeout,
            template_id=template_id,
            question_nonce=question_nonce,
        )
        return response.state.body["question_id"]

    def _calculate_condition_id(
        self,
        oracle: str,
        question_id: str,
        outcome_slot_count: int = 2,
    ) -> Generator[None, None, str]:
        """Calculate question ID."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=CONDIOTIONAL_TOKENS_XDAI,
            contract_id=str(ConditionalTokensContract.contract_id),
            contract_callable="calculate_condition_id",
            oracle=oracle,
            question_id=question_id,
            outcome_slot_count=outcome_slot_count,
        )
        return response.state.body["condition_id"]

    def _calculate_time_parameters(self, resolution_time: float) -> Tuple[int, int]:
        """Calculate time params."""
        rt = datetime.datetime.fromtimestamp(resolution_time)
        ct = datetime.datetime.fromtimestamp(
            self.context.state.round_sequence.last_round_transition_timestamp.timestamp()
        )
        time_remaining = rt.day - ct.day
        days_to_opening = math.floor(time_remaining / 2)
        opening_time = int(
            datetime.datetime(year=ct.year, month=ct.month, day=ct.day).timestamp()
        ) + (days_to_opening * 24 * 60 * 60)
        timeout = 7 * 24 * 60 * 60
        return opening_time, timeout

    def _prepare_ask_question_mstx(
        self,
        question_data: Dict,
        opening_timestamp: int,
        timeout: int,
        template_id: int = 2,
        question_nonce: int = 0,
    ) -> Generator[None, None, Dict]:
        """Prepare a multisend tx for `askQuestionMethod`"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=CONDIOTIONAL_TOKENS_XDAI,
            contract_id=str(RealtioContract.contract_id),
            contract_callable="get_ask_question_tx_data",
            question_data=question_data,
            opening_timestamp=opening_timestamp,
            timeout=timeout,
            template_id=template_id,
            question_nonce=question_nonce,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"get_ask_question_tx_data unsuccessful!: {response}"
            )
            return None
        return {
            "to": REALTIO_XDAI,
            "value": ETHER_VALUE,
            "data": response.state.body["data"],
        }

    def _prepare_prepare_condition_mstx(
        self,
        question_id: str,
        outcome_slot_count: int = 2,
    ) -> Generator[None, None, Dict]:
        """Prepare a multisend tx for `askQuestionMethod`"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=CONDIOTIONAL_TOKENS_XDAI,
            contract_id=str(ConditionalTokensContract.contract_id),
            contract_callable="get_prepare_condition_tx_data",
            question_id=question_id,
            outcome_slot_count=outcome_slot_count,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"get_prepare_condition_tx_data unsuccessful!: {response}"
            )
            return None
        return {
            "to": CONDIOTIONAL_TOKENS_XDAI,
            "value": ETHER_VALUE,
            "data": response.state.body["data"],
        }

    def _prepare_create_fpmm_mstx(
        self,
        condition_id: str,
        initial_funds: int,
        market_fee: float = DEFAULT_MARKET_FEE,
    ) -> Generator[None, None, Dict]:
        """Prepare a multisend tx for `askQuestionMethod`"""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=FPMM_DETERMINISTIC_FACTORY,
            contract_id=str(FPMMDeterministicFactory.contract_id),
            contract_callable="get_create_fpmm_tx_data",
            condition_id=condition_id,
            initial_funds=initial_funds,
            market_fee=market_fee,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"get_prepare_condition_tx_data unsuccessful!: {response}"
            )
            return None
        return {
            "to": FPMM_DETERMINISTIC_FACTORY,
            "value": ETHER_VALUE,
            "data": response.state.body["data"],
        }

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            data = self.synchronized_data.question_data
            self.context.logger.info(f"Preparing txs for question {data}")
            question_data = {
                "question": data["question"],
                "answers": data["answers"],
                "topic": data["topic"],
                "language": data["language"],
            }
            opening_timestamp, timeout = self._calculate_time_parameters(
                resolution_time=data["resolution_time"]
            )
            question_id = yield from self._calculate_question_id(
                question_data=question_data,
                opening_timestamp=opening_timestamp,
                timeout=timeout,
            )
            ask_question_tx = yield from self._prepare_ask_question_mstx(
                question_data=question_data,
                opening_timestamp=opening_timestamp,
                timeout=timeout,
            )
            prepare_condition_tx = yield from self._prepare_prepare_condition_mstx(
                question_id=question_id,
            )
            condition_id = yield from self._calculate_condition_id(
                oracle=ORACLE_XDAI,
                question_id=question_id,
            )
            create_fpmm_tx = yield from self._prepare_create_fpmm_mstx(
                condition_id=condition_id,
                initial_funds=0,  # TODO: make configurable
            )
            tx_hash = yield from self._to_multisend(
                transactions=[ask_question_tx, prepare_condition_tx, create_fpmm_tx]
            )
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
        SelectKeeperMarketIdentificationBehaviour,
        MarketIdentificationBehaviour,
        PrepareTransactionBehaviour,
    }

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

from abc import ABC
import datetime
import json
import random
from typing import Generator, Set, Type, cast

from packages.valory.protocols.llm.message import LlmMessage
from packages.valory.skills.llm_abci.dialogues import LlmDialogue, LlmDialogues
from packages.valory.skills.abstract_round_abci.models import Requests


from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    SelectKeeperBehaviour,
    BaseBehaviour,
)

from packages.valory.connections.openai.connection import (
    PUBLIC_ID as LLM_CONNECTION_PUBLIC_ID,
)
from packages.valory.skills.market_creation_manager_abci.models import MarketCreationManagerParams
from packages.valory.skills.market_creation_manager_abci.rounds import (
    SynchronizedData,
    MarketCreationManagerAbciApp,
    CollectRandomnessRound,
    DataGatheringRound,
    SelectKeeperRound,
    MarketIdentificationRound,
    PrepareTransactionRound,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    CollectRandomnessPayload,
    DataGatheringPayload,
    SelectKeeperPayload,
    MarketIdentificationPayload,
    PrepareTransactionPayload,
)
from packages.valory.skills.abstract_round_abci.common import (
    RandomnessBehaviour
)

HTTP_OK = 200
MAX_RETRIES = 3

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
* The created markets must be different and not overlap semantically.
* You must provide your response in the format specified under "OUTPUT_FORMAT".
* Do not include any other contents in your response.

INPUT:
```
{input_news}
```

OUTPUT_FORMAT:
* Your output response must be only a single JSON array to be parsed by Python's "json.loads()".
* The JSON array must be of length 10. 
* Each entry of the JSON array must be a JSON object containing the fields:
  - question: The binary question to open a prediction market.
  - answers: The possible answers to the question.
  - resolution_date: The resolution date for the outcome of the market to be verified.
* Output only the JSON object. Do not include any other contents in your response.
"""



class MarketCreationManagerBaseBehaviour(BaseBehaviour, ABC):
    """Base behaviour for the market_creation_manager_abci skill."""

    @property
    def synchronized_data(self) -> SynchronizedData:
        """Return the synchronized data."""
        return cast(SynchronizedData, super().synchronized_data)

    @property
    def params(self) -> Params:
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
            gathered_data = yield from  self._gather_data()
            payload = DataGatheringPayload(sender=sender, gathered_data=gathered_data)

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()


    def _gather_data(self) -> Generator:
        """Auxiliary method to collect data from endpoint."""

        headers = {
            'X-Api-Key': self.params.newsapi_api_key
        }

        today = datetime.date.today()
        from_date = today - datetime.timedelta(days=7)
        to_date = today

        parameters = {
            "q": "arts OR business OR finance OR cryptocurrency OR politics OR science OR technology OR sports OR weather OR entertainment",
            "language": "en",
            "sortBy": "popularity",
            "from": from_date,
            "to": to_date,
        }

        response = yield from self.get_http_response(
            method="GET",
            url=self.params.newsapi_endpoint,
            headers=headers,
            parameters=parameters
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
        
        self.context.logger.info(f"Response received from {self.params.newsapi_endpoint}:\n {response.json()}")
        return json.dumps(response.json(), sorted=True)


class SelectKeeperOracleBehaviour(SelectKeeperBehaviour):
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
            sender = self.context.agent_address
            payload = MarketIdentificationPayload(
                sender=sender, content=json.dumps(payload_data, sort_keys=True)
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _get_llm_response(self) -> Generator[None, None, dict]:
        """Get the LLM response"""

        articles = self.synchronized_data.gathered_data['articles']
        random.seed(self.synchronized_data.most_voted_randomness, 2)  # nosec
        random.shuffle(articles)
        articles = articles[:20]

        input_news = ''
        for article in articles:
            title = article['title']
            content = article['content']
            date = article['publishedAt']
            input_news += f"- ({date}) {title}\n  {content}\n\n"


        prompt_template = MARKET_IDENTIFICATION_PROMPT
        prompt_values = {input_news: input_news}

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
        result = llm_response_message.value

        self.context.logger.info(f"Got LLM response: {result}")

        return {"result": result.strip()}

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

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            payload = PrepareTransactionPayload(sender=sender, content="PrepareTransactionPayloadContent")

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()


class MarketCreationManagerRoundBehaviour(AbstractRoundBehaviour):
    """MarketCreationManagerRoundBehaviour"""

    initial_behaviour_cls = CollectRandomnessBehaviour
    abci_app_cls = MarketCreationManagerAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = [
        CollectRandomnessBehaviour,
        DataGatheringBehaviour,
        MarketIdentificationBehaviour,
        PrepareTransactionBehaviour
    ]

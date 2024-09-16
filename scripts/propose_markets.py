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

"""Script for testing market creator prompts."""

import json
import logging
import os
import random
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv(dotenv_path=".env")

OPENAI_ENGINE = "gpt-4-0125-preview"
OPENAI_MAX_TOKENS = 700
OPENAI_TEMPERATURE = 0.7
OPENAI_REQUEST_TIMEOUT = 600
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEWSAPI_API_KEY = os.getenv("NEWSAPI_API_KEY")

MARKET_APPROVAL_SERVER = os.getenv("MARKET_APPROVAL_SERVER")
MARKET_APPROVAL_SERVER_API_KEY = os.getenv("MARKET_APPROVAL_SERVER_API_KEY")

MAX_RETRIES = 3
HTTP_OK = 200
HTTP_NO_CONTENT = 204
TOP_HEADLINES = "top-headlines"
ENGINES = {
    "chat": ["gpt-3.5-turbo", "gpt-4", "gpt-4-0125-preview"],
}

MARKET_IDENTIFICATION_PROMPT_ORIGINAL = """Based on the
        following news snippets under INPUT, formulate 10 prediction market questions
        with clear, objective\noutcomes that can be verified on a specific date and
        leave no room for interpretation or subjectivity.\nAvoid incorporating questions
        that could potentially encourage unethical behavior or violence.\nEvery question
        must be related to an event happening on or by {event_day}. The answer to
        the question\nmust be unknown until that day, but it must be known after that
        day.\nYour questions should follow a structure similar to this;\n\"Will VERIFIABLE_BINARY_OUTCOME_OR_PREDICTION
        occur on {event_day}\".\nYour output must follow the output format detailed
        under \"OUTPUT FORMAT\".\n\nINPUT\n{input_news}\n\nOUTPUT_FORMAT\n* Your output
        response must be only a single JSON array to be parsed by Python \"json.loads()\".\n*
        All of the date strings should be represented in YYYY-MM-DD format.\n* Each
        entry of the JSON array must be a JSON object containing the fields;\n - question;
        The binary question to open a prediction market.\n - answers; The possible
        answers to the question.\n - resolution_date; The resolution date for the
        outcome of the market to be verified.\n - topic; One word description of the
        topic of the news and it should be one of; {topics}.\n* Output only the JSON
        object. Do not include any other contents in your response.
        """

MARKET_IDENTIFICATION_PROMPT = """Based on the
        following news snippets under NEWS_SNIPPETS, formulate 15 prediction market questions
        with clear, objective outcomes.

        Each question must satisfy all the following criteria:
        - It must be related to an event happening before EVENT_DAY or on EVENT_DAY.
        - It must not encourage unethical behavior or violence.
        - It should follow a structure similar to this: "Will EVENT occur on or before EVENT_DAY?"
        - It must not include unmeasurable statements like "significant increase".
        - It must not reference matches, sport events or any other event that do not occur on EVENT_DAY.
        - Its answer must be 'yes' or 'no.
        - Its answer must be verified using publicly available sources or news media.
        - Its answer must not be an opinion.
        - Its answer must be known after EVENT_DAY.

        OUTPUT_FORMAT
        You must provide a JSON array with entries "question" and "topic". "topic" must be a topic under TOPICS.

        EVENT_DAY
        {event_day}

        INPUT
        {input_news}

        TOPICS
        {topics}
        """


client: Optional[OpenAI] = None


class OpenAIClientManager:
    """Client context manager for OpenAI."""

    def __init__(self, api_key: str):
        """__init__"""
        self.api_key = api_key

    def __enter__(self) -> OpenAI:
        """__enter__"""
        global client  # pylint: disable=global-statement
        if client is None:
            client = OpenAI(api_key=self.api_key)
        return client

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """__exit__"""
        global client  # pylint: disable=global-statement
        if client is not None:
            client.close()
            client = None


class Context:  # pylint: disable=too-few-public-methods
    """Mock class Context"""

    def __init__(self):
        """__init__"""
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(
            logging.DEBUG
        )  # Set the logging level (e.g., DEBUG, INFO, WARNING, ERROR)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)  # Set the level for this handler
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)


class Params:  # pylint: disable=too-few-public-methods
    """Mock class Params"""


class SynchronizedData:  # pylint: disable=too-few-public-methods
    """Mock class SynchronizedData"""


class DataGatheringRound:  # pylint: disable=too-few-public-methods
    """Mock class DataGatheringRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    MAX_RETRIES_PAYLOAD = "MAX_RETRIES_PAYLOAD"
    MAX_PROPOSED_MARKETS_REACHED_PAYLOAD = "MAX_PROPOSED_MARKETS_REACHED_PAYLOAD"
    SKIP_MARKET_PROPOSAL_PAYLOAD = "SKIP_MARKET_PROPOSAL_PAYLOAD"


class MarketProposalBehaviourMock:  # pylint: disable=too-few-public-methods
    """Mock class MarketProposalBehaviourMock"""

    params = Params()
    synchronized_data = SynchronizedData()
    context = Context()

    def __init__(self):
        """__init__"""
        self.synchronized_data.most_voted_randomness = "".join(
            [str(random.randint(0, 9)) for _ in range(74)]  # nosec
        )
        self.params.topics = [
            "business",
            "cryptocurrency",
            "politics",
            "science",
            "technology",
            "trending",
            "fashion",
            "social",
            "health",
            "sustainability",
            "internet",
            "travel",
            "food",
            "pets",
            "animals",
            "curiosities",
            "music",
            "economy",
            "arts",
            "entertainment",
            "weather",
            "sports",
            "finance",
            "international",
        ]
        self.params.market_identification_prompt = MARKET_IDENTIFICATION_PROMPT
        self.params.newsapi_endpoint = "https://newsapi.org/v2"
        self.params.news_sources = [
            "bbc-news",
            "bbc-sport",
            "abc-news",
            "cnn",
            "google-news",
            "reuters",
            "usa-today",
            "breitbart-news",
            "the-verge",
            "techradar",
        ]
        self.params.newsapi_api_key = os.getenv("NEWSAPI_API_KEY")
        self.synchronized_data.gathered_data = None

    def _gather_data(self) -> str:
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
        # only get articles from top headlines
        url = f"{self.params.newsapi_endpoint}/{TOP_HEADLINES}"
        response = requests.get(
            url=url,
            headers=headers,
            params=parameters,
            timeout=60,
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

        response_data = json.loads(response.content.decode("utf-8"))
        self.synchronized_data.gathered_data = response_data["articles"]
        return json.dumps(response_data, sort_keys=True)

    def _get_llm_response(
        self, event_day: str, news_articles: List[Dict[str, Any]]
    ) -> None:
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
            "event_day": event_day,
        }

        print(
            self._get_response(
                prompt_template=prompt_template, prompt_values=prompt_values
            )
        )

    def _get_response(
        self, prompt_template: str, prompt_values: Dict[str, str]
    ):  # pylint: disable=no-self-use
        """Get response from openai."""

        # Format the prompt using input variables and prompt_values
        formatted_prompt = (
            prompt_template.format(**prompt_values)
            if prompt_values
            else prompt_template
        )
        engine = OPENAI_ENGINE

        # Call the OpenAI API
        if engine in ENGINES["chat"]:
            with OpenAIClientManager(OPENAI_API_KEY):
                # Call the OpenAI API
                messages = [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": formatted_prompt},
                ]
                response = client.chat.completions.create(
                    model=engine,
                    messages=messages,
                    temperature=OPENAI_TEMPERATURE,
                    max_tokens=OPENAI_MAX_TOKENS,
                    n=1,
                    timeout=OPENAI_REQUEST_TIMEOUT,
                    stop=None,
                )
                output = response.choices[0].message.content
        else:
            raise AttributeError(f"Unrecognized OpenAI engine: {engine}")

        return output


def main() -> None:
    """Main method"""

    mp_behaviour = MarketProposalBehaviourMock()
    mp_behaviour._gather_data()  # pylint: disable=protected-access
    news_articles = mp_behaviour.synchronized_data.gathered_data
    k = min(40, len(news_articles))
    selected_news_articles = random.sample(news_articles, k)
    mp_behaviour._get_llm_response(  # pylint: disable=protected-access
        "30 July 2024", selected_news_articles
    )


if __name__ == "__main__":
    main()

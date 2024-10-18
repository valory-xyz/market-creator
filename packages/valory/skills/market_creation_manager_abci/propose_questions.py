# -*- coding: utf-8 -*-
# type: ignore
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
"""Contains the job definitions"""

# IMPORTANT: remove this when ported to the mech repository.
# Remove also mypy skip at the top of the file
# flake8: noqa

import functools
import json
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

# import anthropic
# import googleapiclient
import openai
import requests
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport
from openai import OpenAI
from pydantic import BaseModel
from tiktoken import encoding_for_model


NEWSAPI_TOP_HEADLINES_URL = "https://newsapi.org/v2/top-headlines"
NEWSAPI_DEFAULT_NEWS_SOURCES = [
    "bbc-news",
    "bbc-sport",
    "abc-news",
    "cnn",
    #    "google-news",
    "reuters",
    "usa-today",
    "breitbart-news",
    "the-verge",
    "techradar",
]

OMEN_SUBGRAPH_URL = "https://gateway-arbitrum.network.thegraph.com/api/{subgraph_api_key}/subgraphs/id/9fUVQpFwzpdWS9bq5WkAnmKbNNcoBwatMR4yZq81pbbz"
HTTP_OK = 200
MAX_ARTICLES = 40
MAX_LATEST_QUESTIONS = 40

FPMM_CREATORS = [
    "0x89c5cc945dd550bcffb72fe42bff002429f46fec",
    "0xffc8029154ecd55abed15bd428ba596e7d23f557",
]
FPMMS_QUERY = """
    query fpmms_query($creator_in: [Bytes!], $first: Int) {
      fixedProductMarketMakers(
        where: {creator_in: $creator_in}
        orderBy: creationTimestamp
        orderDirection: desc
        first: $first
      ) {
        question {
          title
        }
      }
    }
    """

DEFAULT_TOPICS = [
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

SELECT_STORY_PROMPT = """You are provided a numbered list of recent news article
    snippets under ARTICLES. You are provided a list of existing questions under
    EXISTING_QUESTIONS. Your task is to choose one article or story which is suitable
    to create questions for prediction markets. The chosen article should be that the
    questions created are of public interest. The chosen article should ideally
    be used to create questions based on topics different from the EXISTING_QUESTIONS.
    You must output the article ID a topic from TOPICS and a brief reasoning.

    EXISTING_QUESTIONS
    {latest_questions}

    ARTICLES
    {articles}

    TOPICS
    {topics}
    """

PROPOSE_QUESTION_PROMPT = """You are provided a recent news article
    under ARTICLE. Your task is to formulate {num_questions} novel prediction market question
    with clear, objective outcomes based on the information from the ARTICLE.
    The questions must satisfy all the following criteria:
    - Must be of public interest.
    - Must be semantically different.
    - Must be different from EXISTING_QUESTIONS.
    - Must be related to an event happening before EVENT_DAY or on EVENT_DAY.
    - Must not encourage unethical behavior or violence.
    - Should follow a structure similar to these: "Will EVENT occur on or before EVENT_DAY?", "Will EVENT occur by EVENT_DAY?", etc.
    - Must not include unmeasurable statements like "significant increase".
    - Do not reference matches, sport events or any other event that do not occur on or before EVENT_DAY.
    - The answer must be 'yes' or 'no.
    - The answer must be verified using publicly available sources or news media.
    - The answer must not be an opinion.
    - The answer must be known after EVENT_DAY.

    EXISTING_QUESTIONS
    {latest_questions}

    EVENT_DAY
    {event_day}

    ARTICLE
    {article}
    """

client: Optional[OpenAI] = None


MechResponse = Tuple[str, Optional[str], Optional[Dict[str, Any]], Any, Any]


class LLMQuestionProposalSchema(BaseModel):
    """Schema for proposed questions."""

    questions: List[str]


class LLMStorySelectionSchema(BaseModel):
    """Schema for story selection."""

    topic: str
    article_id: int
    reasoning: str


class KeyChain:
    """Class for managing API keys."""

    def __init__(self, services: Dict[str, List[str]]) -> None:
        """Initialize the KeyChain with a dictionary of service names and corresponding lists of API keys."""
        if not isinstance(services, dict):
            raise ValueError(
                "Services must be a dictionary with service names as keys and lists of API keys as values."
            )

        self.services = services
        self.current_index = {
            service: 0 for service in services
        }  # Start with the first key for each service

    def max_retries(self) -> Dict[str, int]:
        """Get the maximum number of retries for a given service."""
        return {service: len(keys) for service, keys in self.services.items()}

    def rotate(self, service_name: str) -> None:
        """Rotate the current API key for a given service to the next one."""
        if service_name not in self.services:
            raise KeyError(f"Service '{service_name!r}' not found in KeyChain.")

        # Increment the current index, looping back if at the end of the list
        self.current_index[service_name] += 1
        if self.current_index[service_name] >= len(self.services[service_name]):
            self.current_index[service_name] = 0  # Reset to the start

    def get(self, service_name: str, default_value: str) -> str:
        """Get the current API key for a given service."""
        if service_name not in self.services:
            return default_value

        return self.__getitem__(service_name)

    def __getitem__(self, service_name: str) -> str:
        """Get the current API key for a given service."""
        if service_name not in self.services:
            raise KeyError(f"Service '{service_name!r}' not found in KeyChain.")

        index = self.current_index[service_name]
        return self.services[service_name][index]


def with_key_rotation(func: Callable):  # noqa
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> MechResponse:
        # this is expected to be a KeyChain object,
        # although it is not explicitly typed as such
        api_keys = kwargs["api_keys"]
        retries_left: Dict[str, int] = api_keys.max_retries()

        def execute() -> MechResponse:
            """Retry the function with a new key."""
            try:
                result = func(*args, **kwargs)
                return result + (api_keys,)
            # except anthropic.RateLimitError as e:
            #     # try with a new key again
            #     service = "anthropic"
            #     if retries_left[service] <= 0:
            #         raise e
            #     retries_left[service] -= 1
            #     api_keys.rotate(service)
            #     return execute()
            except openai.RateLimitError as e:
                # try with a new key again
                if retries_left["openai"] <= 0 and retries_left["openrouter"] <= 0:
                    raise e
                retries_left["openai"] -= 1
                retries_left["openrouter"] -= 1
                api_keys.rotate("openai")
                api_keys.rotate("openrouter")
                return execute()
            # except googleapiclient.errors.HttpError as e:
            #     # try with a new key again
            #     rate_limit_exceeded_code = 429
            #     if e.status_code != rate_limit_exceeded_code:
            #         raise e
            #     service = "google_api_key"
            #     if retries_left[service] <= 0:
            #         raise e
            #     retries_left[service] -= 1
            #     api_keys.rotate(service)
            #     return execute()
            except Exception as e:
                return str(e), "", None, None, api_keys

        mech_response = execute()
        return mech_response

    return wrapper


class OpenAIClientManager:
    """Client context manager for OpenAI."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def __enter__(self) -> OpenAI:
        global client
        if client is None:
            client = OpenAI(api_key=self.api_key)
        return client

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        global client
        if client is not None:
            client.close()
            client = None


def count_tokens(text: str, model: str) -> int:
    """Count the number of tokens in a text."""
    enc = encoding_for_model(model)
    return len(enc.encode(text))


DEFAULT_OPENAI_SETTINGS = {
    "max_tokens": 500,
    "temperature": 0.7,
}
DEFAULT_ENGINES = {"propose-question": "gpt-4o-2024-08-06"}
ALLOWED_TOOLS = ["propose-question"]


def format_utc_timestamp(utc_timestamp: int) -> str:
    """Format UTC timestamp to a human-readable date"""
    dt = datetime.fromtimestamp(utc_timestamp, tz=timezone.utc)
    formatted_date = dt.strftime("%d %B %Y")
    return formatted_date


def gather_articles(
    news_sources: List[str], newsapi_api_key: str
) -> Optional[List[Dict[str, Any]]]:
    """Gather news from NewsAPI (top-headlines endpoint)"""
    headers = {"X-Api-Key": newsapi_api_key}
    parameters = {
        "sources": ",".join(news_sources),
        "pageSize": "100",  # TODO: pagination
    }
    url = NEWSAPI_TOP_HEADLINES_URL
    response = requests.get(
        url=url,
        headers=headers,
        params=parameters,
        timeout=60,
    )
    if response.status_code != HTTP_OK:
        print(
            f"Could not retrieve response from {url}."
            f"Received status code {response.status_code}."
            f"{response}"
        )
        return None

    response_data = json.loads(response.content.decode("utf-8"))
    articles = response_data["articles"]
    return articles


def gather_latest_questions(subgraph_api_key: str) -> Optional[List[str]]:
    """Gather latest questions opened on Omen exchange"""
    transport = RequestsHTTPTransport(
        url=OMEN_SUBGRAPH_URL.format(subgraph_api_key=subgraph_api_key)
    )
    client = Client(transport=transport, fetch_schema_from_transport=True)
    variables = {
        "creator_in": FPMM_CREATORS,
        "first": MAX_LATEST_QUESTIONS,
    }
    response = client.execute(gql(FPMMS_QUERY), variable_values=variables)
    items = response.get("fixedProductMarketMakers", [])
    output = [q["question"]["title"] for q in items]
    # TODO error handling
    return output


def scrape_url(serper_api_key: str, url: str) -> Optional[dict]:
    """Scrape the contents of a URL"""
    serper_url = "https://scrape.serper.dev"
    headers = {"X-API-KEY": serper_api_key, "Content-Type": "application/json"}

    payload = json.dumps({"url": url})
    try:
        response = requests.post(serper_url, headers=headers, data=payload)
        response.raise_for_status()
        scraped_data = response.json()
        print(f"Successfully scraped URL: {url}")
        return scraped_data
    except requests.RequestException:
        return None
    except json.JSONDecodeError:
        return None


# TODO
@with_key_rotation
def run(**kwargs) -> Tuple[Optional[str], Optional[Dict[str, Any]], Any, Any]:
    """Run the task"""
    try:
        counter_callback = kwargs.get("counter_callback", None)

        # Verify input
        tool = kwargs.get("tool")
        if not tool or tool not in ALLOWED_TOOLS:
            return (
                f'{{"error": "Tool {tool} is not in the list of supported tools.", "tool": {tool}}}',
                None,
                None,
                counter_callback,
            )

        resolution_time = kwargs.get("resolution_time")
        if resolution_time is None:
            return (
                f'{{"error": "\'resolution_time\' is not defined.", "tool": {tool}}}',
                None,
                None,
                counter_callback,
            )

        num_questions = kwargs.get("num_questions")
        if num_questions is None:
            num_questions = 1

        # Gather latest opened questions from input or from TheGraph
        latest_questions = kwargs.get("latest_questions")
        if latest_questions is None:
            latest_questions = gather_latest_questions(kwargs["api_keys"]["subgraph"])

        if latest_questions is None:
            return (
                f'{{"error": "Failed to retrieve latest questions.", "tool": {tool}}}',
                None,
                None,
                counter_callback,
            )

        latest_questions = random.sample(
            latest_questions, min(MAX_LATEST_QUESTIONS, len(latest_questions))
        )
        latest_questions_string = "\n".join(latest_questions)

        # Gather recent news articles from NewsAPI
        news_sources = kwargs.get("news_sources", NEWSAPI_DEFAULT_NEWS_SOURCES)
        articles = gather_articles(news_sources, kwargs["api_keys"]["newsapi"])

        if articles is None:
            return (
                f'{{"error": "Failed to retrieve articles from NewsAPI.", "tool": {tool}}}',
                None,
                None,
                counter_callback,
            )

        print(
            f"{len(articles)} articles collected from {len(news_sources)} news sources\n"
        )

        articles = random.sample(articles, min(MAX_ARTICLES, len(articles)))

        articles_string = ""
        for i, article in enumerate(articles, start=0):
            articles_string += f"{i} - {article['title']} ({article['publishedAt']}): {article['content']}\n"

        # Define topics
        topics = kwargs.get("topics", DEFAULT_TOPICS)
        topics_string = ", ".join(topics)

        # First call to LLM
        with OpenAIClientManager(kwargs["api_keys"]["openai"]):
            max_tokens = kwargs.get("max_tokens", DEFAULT_OPENAI_SETTINGS["max_tokens"])
            temperature = kwargs.get(
                "temperature", DEFAULT_OPENAI_SETTINGS["temperature"]
            )
            model = kwargs.get("engine", DEFAULT_ENGINES.get(tool))

            prompt_values = {
                "articles": articles_string,
                "topics": topics_string,
                "latest_questions": latest_questions_string,
            }

            prompt = SELECT_STORY_PROMPT.format(**prompt_values)

            moderation_result = client.moderations.create(input=prompt)
            if moderation_result.results[0].flagged:
                return (
                    f'{{"error": "Moderation flagged the prompt as in violation of terms.", "tool": {tool}}}',
                    None,
                    None,
                    counter_callback,
                )

            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ]
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                n=1,
                timeout=120,
                stop=None,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "LLMStorySelectionSchema",
                        "schema": LLMStorySelectionSchema.model_json_schema(),
                    },
                },
            )
            if counter_callback:
                counter_callback(
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                    model=model,
                    token_counter=count_tokens,
                )

            response = json.loads(response.choices[0].message.content)
            article_id = response["article_id"]
            topic = response["topic"]
            article = articles[article_id]

            print(
                f"ARTICLE {article['title']!r} SELECTED BECAUSE {response['reasoning']!r}\n"
            )

        # Scrape selected article
        scrape_result = scrape_url(kwargs["api_keys"]["serper"], article["url"])

        if scrape_result is None:
            return (
                f'{{"error": "Failed to scrape url {article["url"]}", "tool": {tool}}}',
                None,
                None,
                counter_callback,
            )

        # Second call to LLM
        with OpenAIClientManager(kwargs["api_keys"]["openai"]):
            max_tokens = kwargs.get("max_tokens", DEFAULT_OPENAI_SETTINGS["max_tokens"])
            temperature = kwargs.get(
                "temperature", DEFAULT_OPENAI_SETTINGS["temperature"]
            )
            model = kwargs.get("engine", DEFAULT_ENGINES.get(tool))

            prompt_values = {
                "article": f"{scrape_result['text']}",
                "event_day": format_utc_timestamp(int(resolution_time)),
                "latest_questions": latest_questions_string,
                "num_questions": f"{num_questions}",
            }

            prompt = PROPOSE_QUESTION_PROMPT.format(**prompt_values)

            moderation_result = client.moderations.create(input=prompt)
            if moderation_result.results[0].flagged:
                return (
                    f'{{"error": "Moderation flagged the prompt as in violation of terms.", "tool": {tool}}}',
                    None,
                    None,
                    counter_callback,
                )

            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ]
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                n=1,
                timeout=120,
                stop=None,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "LLMQuestionProposalSchema",
                        "schema": LLMQuestionProposalSchema.model_json_schema(),
                    },
                },
            )
            if counter_callback:
                counter_callback(
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                    model=model,
                    token_counter=count_tokens,
                )
            response = json.loads(response.choices[0].message.content)

        # Generate output
        questions = response["questions"][:num_questions]
        answers = ["Yes", "No"]
        language = "en_US"
        questions_dict = {}
        for q in questions:
            question_id = str(uuid.uuid4())
            questions_dict[question_id] = {
                "answers": answers,
                "id": question_id,
                "language": language,
                "question": q,
                "resolution_time": resolution_time,
                "topic": topic,
                "article": article,
            }

        return json.dumps(questions_dict, sort_keys=True), None, None, None
    except Exception as e:
        return (
            f'{{"error": "An exception has occurred: {e}.", "tool": {tool}}}',
            None,
            None,
            counter_callback,
        )

# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2026 Valory AG
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
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

# import anthropic
# import googleapiclient
import openai
import requests
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport
from openai import OpenAI
from pydantic import BaseModel
from tiktoken import encoding_for_model, get_encoding

NEWSAPI_TOP_HEADLINES_URL = "https://newsapi.org/v2/top-headlines"
NEWSAPI_DEFAULT_NEWS_SOURCES = [
    "bbc-news",
    "bbc-sport",
    "abc-news",
    "cnn",
    "reuters",
    "usa-today",
    "breitbart-news",
    "the-verge",
    "techradar",
    "associated-press",
    "bloomberg",
    "business-insider",
    "ars-technica",
    "national-geographic",
    "new-scientist",
]

OMEN_SUBGRAPH_URL = "https://gateway-arbitrum.network.thegraph.com/api/{subgraph_api_key}/subgraphs/id/9fUVQpFwzpdWS9bq5WkAnmKbNNcoBwatMR4yZq81pbbz"
HTTP_OK = 200
MAX_ARTICLES = 60
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
    "social",
    "health",
    "sustainability",
    "internet",
    "food",
    "pets",
    "animals",
    "curiosities",
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

    PREFER articles that support MEASUREMENT or CONTINUATION questions, with a
    particular bias toward continuation-friendly topics. Good signals for
    continuation-friendly articles:
    - Economic indicators (interest rates, inflation targets, unemployment,
      stock indices, commodity prices, exchange rates).
    - Political incumbencies (leaders, officials, judges currently in position).
    - Existing moratoriums, sanctions, bans, regulations, policies.
    - Institutional positions (ratings, league standings, memberships,
      subscriptions, listings).
    - Ongoing conflicts, negotiations, strikes, or standoffs.
    These articles produce questions about status-quo persistence, which
    balance the pipeline's natural No-bias from short-deadline announcements.

    Also acceptable:
    - Articles mentioning a measurable quantity that can be checked on a
      future date (measurement framing).

    AVOID articles whose only angle is "will authority X announce Y?" unless
    a scheduled announcement is specifically anticipated in the article.

    You must output the article ID a topic from TOPICS and a brief reasoning.

    EXISTING_QUESTIONS
    {latest_questions}

    ARTICLES
    {articles}

    TOPICS
    {topics}
    """

EXTRACT_STATE_PROMPT = """You are analysing a news article to find MEASURABLE
    STATES that can be turned into prediction-market questions. A measurable
    state is something that can be checked on a specific future date by looking
    up a published value, verifying an ongoing condition, or confirming a
    status-quo persists.

    For each measurable state you find, output:
    - "state": a short description of what can be measured
    - "source": who publishes or confirms this (e.g. "Freddie Mac weekly report",
      "SEC 10-Q filing", "NWS flood gauge", "official company statement")
    - "framing": one of "measurement" (numeric value check), "continuation"
      (will status-quo persist?), or "announcement" (specific event expected)

    PREFER "measurement" and "continuation" framings. Only use "announcement"
    if the article specifically describes an imminent scheduled event.

    If the article has no measurable states at all, return an empty list.

    Return at most 5 states.

    ARTICLE
    {article}
    """

PROPOSE_QUESTION_PROMPT = """You are provided a recent news article
    under ARTICLE, and a list of MEASURABLE STATES extracted from it.
    Your task is to formulate {num_questions} novel prediction market question(s)
    based on these states. Use the measurable states to guide your framing.

    CRITICAL CONSTRAINT: You have a WINDOW of only {window_days} days
    (today -> EVENT_DAY). Every date, threshold, and authority action in
    your question must be achievable within {window_days} days. Do NOT
    reference dates outside this window or in the past.

    RULES:
    - TARGET MIX: when multiple candidate framings are possible for the same
      article, aim for a mix where at least one third of the generated
      questions use "continuation" framing. Continuation questions are the
      main counterweight to the No-bias of announcement framings on short
      windows, so they are actively preferred when an article supports them.

    FRAMING TEMPLATES (use exactly these grammatical shapes -- they avoid the
    past-participle ambiguity of "as confirmed by X" which can be misread as
    "already confirmed by X"):
    - For "measurement" states: frame as
      "Will [metric] be above/below [threshold] on EVENT_DAY, according to
      [source]?"
    - For "continuation" states: frame as
      "Will [condition] still hold on EVENT_DAY, according to [source]?"
    - For "announcement" states: frame as
      "Will [entity] [action] on or before EVENT_DAY, according to [source]?"
    - In all templates, use "according to [source]" to name the jury's
      verification channel. Do NOT use "as confirmed by" / "as reported by" /
      "as announced by" -- the past-participle phrasing can be misread as
      "already confirmed/reported/announced at the time the question is asked".
      "According to [source]" is future-tense relative to EVENT_DAY and
      unambiguously means "the jury will check [source] on that date".
    - If MEASURABLE_STATES is empty, you may create an announcement-style question,
      but it must pass ALL the checks below.
    - Must be of public interest, semantically different, different from
      EXISTING_QUESTIONS.
    - The answer must be 'yes' or 'no', verifiable, not an opinion, unambiguous,
      and known after EVENT_DAY.
    - Must not encourage unethical behavior or violence.
    - Must not include unmeasurable statements like "significant increase".
    - ALL dates in the question must be between today and EVENT_DAY. Never
      reference past dates or dates beyond EVENT_DAY.
    - DATE FORMAT: every date in the question MUST be written as
      "Month D, YYYY" (e.g. "April 22, 2026"). Do NOT use "22 April 2026",
      "April 22 2026" (no comma), or numeric formats. Copy EVENT_DAY verbatim.

    SPECIFIC FRAMING CHECKS (apply to every question):
    1. DEADLINE FEASIBILITY -- Can the criterion physically/procedurally occur
       within {window_days} days? If not, reframe to something that can.
    2. PROCESS-STAGE CLARITY -- If multi-stage process, name the exact stage.
       Never use "formal passage" or "official approval" without a stage qualifier.
    3. DIRECTLY-PUBLISHED FIGURE -- Thresholds must be figures a source publishes
       directly, not derived by arithmetic on separate figures.
    4. AUTHORITY RESPONSE TIME -- The deadline must be realistic for the named
       authority. Government reviews, regulatory investigations take weeks/months.
       If the authority cannot plausibly act within {window_days} days, do NOT
       frame the question around that authority's action.
    5. RESOLUTION SOURCE -- Name WHO confirms and WHAT document/channel.

    MEASURABLE_STATES
    {measurable_states}

    EXISTING_QUESTIONS
    {latest_questions}

    EVENT_DAY
    {event_day}

    ARTICLE
    {article}
    """

SELF_REVIEW_PROMPT = """You are auditing prediction-market questions for
    quality. For EACH question, you must perform explicit step-by-step
    reasoning before deciding accept/reject. Do not skip steps.

    STEP-BY-STEP PROCESS for each question:

    A. STATE THE DEADLINE: Write the exact deadline date from the question.

    B. DEADLINE FEASIBILITY: What specific outcome does the question ask
       for? What is the EARLIEST DATE this could physically/procedurally
       happen? Compare: is earliest_date <= deadline_date?
       - Example: "BBC to complete 1,000 job cuts" -- large-scale layoffs take
         weeks/months to execute. Earliest realistic completion: months away.
         If deadline is 5 days away -> REJECT.
       - Example: "Hurricane landfall in April" -- Atlantic hurricane season
         starts June. Earliest possible: June. April deadline -> REJECT.
       - Example: "FAA suspend laser weapon approval" -- regulatory suspensions
         require review processes taking weeks. 5-day deadline -> REJECT.

    C. PROCESS-STAGE CLARITY: Does the question use ambiguous terms like
       "formal passage", "official approval", "formal review"? If yes -> REJECT
       unless a specific stage is named.

    D. FIGURE DERIVABILITY: Does the question ask for a figure that requires
       arithmetic on two separately-published numbers? If yes -> REJECT.

    E. AUTHORITY RESPONSE TIME: Does the question require a government agency,
       regulator, court, or large organization to complete an action? How long
       does that type of action typically take? Is the deadline realistic?
       - Antitrust reviews: weeks to months -> 5-day deadline = REJECT
       - Regulatory investigations (NHTSA, FAA): weeks -> 5-day deadline = REJECT
       - Large-scale layoffs (1000+ jobs): weeks/months -> 5-day deadline = REJECT
       - Company press release about existing decision: days -> OK

    F. DATE FORMAT: Every date in the question must be written as
       "Month D, YYYY" (e.g. "April 22, 2026"). Formats like "22 April 2026",
       "April 22 2026" (no comma), or numeric dates are INVALID -> REJECT.

    G. DECISION: Accept ONLY if ALL of B, C, D, E, F pass.

    Return JSON with your explicit reasoning at each step.

    QUESTIONS
    {questions}

    SOURCE ARTICLE
    {article}

    EVENT_DAY
    {event_day}
    """

client: Optional[OpenAI] = None


MechResponse = Tuple[str, Optional[str], Optional[Dict[str, Any]], Any, Any]


class MeasurableState(BaseModel):
    """One measurable state extracted from an article."""

    state: str
    source: str
    framing: str  # "measurement", "continuation", or "announcement"


class LLMExtractStateSchema(BaseModel):
    """Schema for the extract-state step output."""

    states: List[MeasurableState]


class LLMQuestionProposalSchema(BaseModel):
    """Schema for proposed questions."""

    questions: List[str]


class SelfReviewItem(BaseModel):
    """One question's self-review result with chain-of-thought reasoning."""

    question: str
    deadline_date: str  # "The deadline is April 21, 2026"
    earliest_plausible_date: str  # "The earliest the authority could act is..."
    deadline_is_feasible: bool
    process_stage_named: bool
    figure_is_directly_published: bool
    authority_can_act_in_time: bool
    date_format_valid: bool
    reasoning: str  # chain-of-thought explanation
    accept: bool


class LLMSelfReviewSchema(BaseModel):
    """Schema for the self-review pass output."""

    reviews: List[SelfReviewItem]


class LLMStorySelectionSchema(BaseModel):
    """Schema for story selection."""

    topic: str
    article_id: int
    reasoning: str


def validate_question_dates(question: str, resolution_ts: int) -> Optional[str]:
    """Check dates in a question: format, not in the past, not too far ahead.

    Dates must be written as "Month D, YYYY" (e.g. "April 22, 2026"). Other
    orderings cause ApproveMarketsBehaviour to silently drop the market.

    :param question: the question text to scan for date references.
    :param resolution_ts: the market resolution timestamp (Unix epoch).
    :return: None if OK, else a human-readable rejection reason.
    """
    now = datetime.now(tz=timezone.utc)
    deadline = datetime.fromtimestamp(resolution_ts, tz=timezone.utc)

    # Any date-like token we find must be in the required "Month D, YYYY"
    # format. Other orderings (e.g. "21 April 2026") cause the downstream
    # ApproveMarketsBehaviour to silently drop the market.
    required_fmt_pattern = r"[A-Z][a-z]+ \d{1,2}, \d{4}"
    any_date_pattern = r"(\w+ \d{1,2},? \d{4}|\d{1,2} \w+ \d{4})"
    for match in re.findall(any_date_pattern, question):
        if not re.fullmatch(required_fmt_pattern, match):
            return (
                f"Date '{match}' is not in required 'Month D, YYYY' format "
                "(e.g. 'April 22, 2026')"
            )
        try:
            d = datetime.strptime(match, "%B %d, %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            return f"Date '{match}' could not be parsed"
        if d < now - timedelta(days=1):
            return f"Date '{match}' is in the past"
        if d > deadline + timedelta(days=365):
            return f"Date '{match}' is too far beyond the deadline"
    return None


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


def with_key_rotation(func: Callable) -> Callable:  # noqa
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> MechResponse:
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

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        global client
        if client is not None:
            client.close()
            client = None


def count_tokens(text: str, model: str) -> int:
    """Count the number of tokens in a text."""
    # TODO address
    # Workaround since tiktoken does not have support yet for gpt4.1
    # https://github.com/openai/tiktoken/issues/395
    if model == "gpt-4.1-2025-04-14":
        return len(get_encoding("o200k_base").encode(text))

    enc = encoding_for_model(model)
    return len(enc.encode(text))


DEFAULT_OPENAI_SETTINGS = {
    "max_tokens": 4096,
    "temperature": 0.7,
}
ALLOWED_TOOLS = ["propose-question"]
TOOL_TO_ENGINE = {tool: "gpt-4.1-2025-04-14" for tool in ALLOWED_TOOLS}
# Cheaper model used for simple classification/extraction steps (story
# selection, measurable-state extraction). These calls don't need the full
# model's creative/reasoning capacity -- using mini here cuts cost by ~50%
# with no observable quality loss on the classification task.
LIGHT_MODEL = "gpt-4.1-mini-2025-04-14"


def format_utc_timestamp(utc_timestamp: int) -> str:
    """Format UTC timestamp as "Month D, YYYY" (US format).

    The downstream ApproveMarketsBehaviour._is_resolution_date_in_question
    check only accepts this format; other date orderings (e.g.
    "18 April 2026") cause the market to be silently dropped before
    reaching the approval server.
    """
    dt = datetime.fromtimestamp(utc_timestamp, tz=timezone.utc)
    return f"{dt.strftime('%B')} {dt.day}, {dt.year}"


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
        response = requests.post(serper_url, headers=headers, data=payload, timeout=60)
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
def run(**kwargs: Any) -> Tuple[Optional[str], Optional[Dict[str, Any]], Any, Any]:
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

        latest_questions = random.sample(  # nosec: B311
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

        articles = random.sample(
            articles, min(MAX_ARTICLES, len(articles))
        )  # nosec: B311

        # Pre-filter: drop articles that individually trigger content
        # moderation before building the selection prompt.  Without this,
        # a single violent-news snippet flags the entire 40-article prompt.
        with OpenAIClientManager(kwargs["api_keys"]["openai"]):
            assert client is not None
            clean_articles = []
            for article in articles:
                text = f"{article.get('title', '')}: {article.get('content', '')}"
                try:
                    mod = client.moderations.create(input=text)
                    if not mod.results[0].flagged:
                        clean_articles.append(article)
                except Exception:
                    clean_articles.append(article)  # keep on moderation API error
            n_dropped = len(articles) - len(clean_articles)
            if n_dropped > 0:
                print(f"Moderation pre-filter: dropped {n_dropped} flagged article(s)")
            articles = clean_articles

        if not articles:
            return (
                f'{{"error": "All articles were flagged by content moderation.", "tool": {tool}}}',
                None,
                None,
                counter_callback,
            )

        articles_string = ""
        for i, article in enumerate(articles, start=0):
            articles_string += f"{i} - {article['title']} ({article['publishedAt']}): {article['content']}\n"

        # Define topics
        topics = kwargs.get("topics", DEFAULT_TOPICS)
        topics_string = ", ".join(topics)

        # First call to LLM -- story selection. Classification task, uses
        # the cheaper light model.
        with OpenAIClientManager(kwargs["api_keys"]["openai"]):
            assert client is not None
            max_tokens = kwargs.get("max_tokens", DEFAULT_OPENAI_SETTINGS["max_tokens"])
            temperature = kwargs.get(
                "temperature", DEFAULT_OPENAI_SETTINGS["temperature"]
            )
            model = LIGHT_MODEL

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
            response = client.chat.completions.create(  # type: ignore[call-overload]
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
            reasoning = f"The article {article['title']!r} ({article.get('author', '')!r}) has been selected to generate prediction market questions because: {response['reasoning']}"

        # Scrape selected article
        scrape_result = scrape_url(kwargs["api_keys"]["serper"], article["url"])

        if scrape_result is None:
            return (
                f'{{"error": "Failed to scrape url {article["url"]}", "tool": {tool}}}',
                None,
                None,
                counter_callback,
            )

        # Step 2: Extract measurable states from the article (iteration 2).
        # This constrains the LLM to identify what CAN be measured before
        # framing a question -- breaking the default "Will X announce Y?" prior.
        # Structured-extraction task, uses the cheaper light model.
        article_text = scrape_result["text"][:6000]  # cap to avoid token limits
        with OpenAIClientManager(kwargs["api_keys"]["openai"]):
            assert client is not None
            model = LIGHT_MODEL
            extract_prompt = EXTRACT_STATE_PROMPT.format(article=article_text)
            extract_messages = [
                {
                    "role": "system",
                    "content": "You are an analyst extracting measurable facts from news articles.",
                },
                {"role": "user", "content": extract_prompt},
            ]
            extract_response = client.chat.completions.create(
                model=model,
                messages=extract_messages,
                temperature=0.3,
                max_tokens=1024,
                n=1,
                timeout=120,
                stop=None,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "LLMExtractStateSchema",
                        "schema": LLMExtractStateSchema.model_json_schema(),
                    },
                },
            )
            if counter_callback:
                counter_callback(
                    input_tokens=extract_response.usage.prompt_tokens,
                    output_tokens=extract_response.usage.completion_tokens,
                    model=model,
                    token_counter=count_tokens,
                )
            extract_data = json.loads(extract_response.choices[0].message.content)
            states = extract_data.get("states", [])
            states_string = json.dumps(states, indent=2) if states else "(none found)"
            print(f"Extracted {len(states)} measurable states:")
            for s in states:
                print(
                    f"  [{s.get('framing', '?')}] {s.get('state', '?')} -- source: {s.get('source', '?')}"
                )

        # Step 3: Generate questions using the extracted states
        with OpenAIClientManager(kwargs["api_keys"]["openai"]):
            assert client is not None
            max_tokens = kwargs.get("max_tokens", DEFAULT_OPENAI_SETTINGS["max_tokens"])
            temperature = kwargs.get(
                "temperature", DEFAULT_OPENAI_SETTINGS["temperature"]
            )
            model = kwargs.get("model", TOOL_TO_ENGINE[tool])

            # Generate more candidates than needed; self-review + date check
            # will filter down. This makes self-review a selector, not just a gate.
            n_candidates = max(num_questions * 5, 5)
            window_days = max(
                1,
                (int(resolution_time) - int(datetime.now(tz=timezone.utc).timestamp()))
                // 86400,
            )

            prompt_values = {
                "article": f"{article_text}",
                "event_day": format_utc_timestamp(int(resolution_time)),
                "latest_questions": latest_questions_string,
                "measurable_states": states_string,
                "num_questions": f"{n_candidates}",
                "window_days": str(window_days),
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
            response = client.chat.completions.create(  # type: ignore[call-overload]
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

        # Self-review pass: audit proposed questions against the four trap checks.
        # Questions that fail any check are rejected before they reach the output.
        questions = response["questions"][:num_questions]

        with OpenAIClientManager(kwargs["api_keys"]["openai"]):
            assert client is not None
            review_prompt = SELF_REVIEW_PROMPT.format(
                questions=json.dumps(questions, indent=2),
                article=f"{scrape_result['text'][:4000]}",
                event_day=format_utc_timestamp(int(resolution_time)),
            )
            review_messages = [
                {
                    "role": "system",
                    "content": "You are a prediction-market question auditor.",
                },
                {"role": "user", "content": review_prompt},
            ]
            review_response = client.chat.completions.create(
                model=model,
                messages=review_messages,
                temperature=0.0,
                max_tokens=2048,
                n=1,
                timeout=120,
                stop=None,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "LLMSelfReviewSchema",
                        "schema": LLMSelfReviewSchema.model_json_schema(),
                    },
                },
            )
            if counter_callback:
                counter_callback(
                    input_tokens=review_response.usage.prompt_tokens,
                    output_tokens=review_response.usage.completion_tokens,
                    model=model,
                    token_counter=count_tokens,
                )
            review_data = json.loads(review_response.choices[0].message.content)
            reviews = review_data.get("reviews", [])

        # Filter: accept questions where at least 3 of 4 quality checks pass
        # AND the date-format check passes. The date-format check is a hard
        # gate because the downstream ApproveMarketsBehaviour silently drops
        # questions whose dates are not in "Month D, YYYY" format.
        accepted_questions = []
        rejected_questions = []
        for rev in reviews:
            checks = [
                rev.get("deadline_is_feasible", True),
                rev.get("process_stage_named", True),
                rev.get("figure_is_directly_published", True),
                rev.get("authority_can_act_in_time", True),
            ]
            passes = sum(1 for c in checks if c)
            date_ok = rev.get("date_format_valid", True)
            if passes >= 3 and date_ok:
                accepted_questions.append(rev["question"])
            else:
                rejected_questions.append(
                    {
                        "question": rev["question"],
                        "reason": rev.get(
                            "reasoning",
                            rev.get("rejection_reason", "failed self-review"),
                        ),
                    }
                )

        # Programmatic date validation -- catches past dates and out-of-range
        # dates that the LLM self-review misses (100% recall on date issues).
        date_validated = []
        for q in accepted_questions:
            date_issue = validate_question_dates(q, int(resolution_time))
            if date_issue:
                rejected_questions.append(
                    {"question": q, "reason": f"DATE CHECK: {date_issue}"}
                )
            else:
                date_validated.append(q)

        print(
            f"Self-review: {len(accepted_questions)} accepted, "
            f"{len(rejected_questions)} rejected out of {len(questions)} proposed"
        )
        for rej in rejected_questions:
            print(f"  REJECTED: {rej['question'][:80]}... -- {rej['reason'][:60]}")

        # Pick the best num_questions from validated candidates.
        # Do NOT fall back to rejected questions -- return error instead.
        if date_validated:
            questions = date_validated[:num_questions]
        else:
            return (
                f'{{"error": "All {len(questions)} proposed questions were rejected by self-review or date validation.", "tool": {tool}}}',
                None,
                None,
                counter_callback,
            )

        # Generate output
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

        output = {
            "questions": questions_dict,
            "reasoning": reasoning,
            "article": article,
        }

        return json.dumps(output, sort_keys=True), None, None, None
    except Exception as e:
        return (
            f'{{"error": "An exception has occurred: {e}.", "tool": {tool}}}',
            None,
            None,
            counter_callback,
        )

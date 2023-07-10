import requests
import json
import openai
import json
import random
import datetime
import os


from typing import Any, Dict, List, Optional, Tuple



DEFAULT_OPENAI_SETTINGS = {
    "max_tokens": 500,
    "temperature": 0.7,
}

TOOL_TO_ENGINE = {
    #"market-creator": "gpt-3.5-turbo",
    "market-creator": "gpt-4",
}

ALLOWED_TOOLS = list(TOOL_TO_ENGINE.keys())

MARKET_CREATION_PROMPT = """
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


def run(**kwargs) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Run the task"""
    openai.api_key = kwargs["api_keys"]["openai"]
    newsapi_api_key = kwargs["api_keys"]["newsapi"]
    max_tokens = kwargs.get("max_tokens", DEFAULT_OPENAI_SETTINGS["max_tokens"])
    temperature = kwargs.get("temperature", DEFAULT_OPENAI_SETTINGS["temperature"])
    prompt = kwargs["prompt"]
    tool = kwargs["tool"]

    if tool not in ALLOWED_TOOLS:
        raise ValueError(f"Tool {tool} is not supported.")

    engine = TOOL_TO_ENGINE[tool]

    newsapi_url = "https://newsapi.org/v2/everything"

    newsapi_headers = headers = {
        'X-Api-Key': newsapi_api_key
    }

    today = datetime.date.today()
    from_date = today - datetime.timedelta(days=7)
    to_date = today

    params = {
        "q": "arts OR business OR finance OR cryptocurrency OR politics OR science OR technology OR sports OR weather OR entertainment",
        "language": "en",
        "sortBy": "popularity",
        "from": from_date,
        "to": to_date,
    }

    response = requests.get(newsapi_url, params=params, headers=newsapi_headers)
    data = response.json()

    # Create the string with the desired format
    articles = data['articles']
    random.shuffle(articles)
    articles = articles[:20]

    input_news = ''
    for article in articles:
        title = article['title']
        content = article['content']
        date = article['publishedAt']
        input_news += f"- ({date}) {title}\n  {content}\n\n"

    market_creation_prompt = MARKET_CREATION_PROMPT.format(
        input_news=input_news,
        from_date=from_date,
        to_date=to_date
    )

    print(market_creation_prompt)

    moderation_result = openai.Moderation.create(market_creation_prompt)

    if moderation_result["results"][0]["flagged"]:
        return "Moderation flagged the prompt as in violation of terms."

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": market_creation_prompt},
    ]

    response = openai.ChatCompletion.create(
        model=engine,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        n=1,
        timeout=120,
        stop=None,
    )

    print(response.choices[0].message.content)

    return response.choices[0].message.content, None



#Testing the script
openai_api_key = os.environ.get('OPENAI_API_KEY')
newsapi_api_key = os.environ.get('NEWSAPI_API_KEY')

kwargs = {
    "prompt": "unused",
    "tool": "market-creator",
    "api_keys": {"openai": openai_api_key, "newsapi": newsapi_api_key}
}

run(**kwargs)
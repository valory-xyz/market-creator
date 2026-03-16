# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2024-2026 Valory AG
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

"""Fetch Realitio question responses from the Reality.eth subgraph.

Queries individual answer submissions (responses) for a set of question IDs.
This gives the full submission history — not just distinct answer values — so
we can accurately determine whether a question was challenged, how many times,
and whether the answer was flipped.
"""

import os
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from dotenv import load_dotenv
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport
from tqdm import tqdm

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

REALITIO_SUBGRAPH_ID = "E7ymrCnNcQdAAgLbdFWzGE5mvr5Mb5T9VfT43FqA7bNh"
_API_KEY = os.getenv("SUBGRAPH_API_KEY", "")
REALITIO_SUBGRAPH_URL = os.getenv(
    "REALITIO_SUBGRAPH_URL",
    f"https://gateway.thegraph.com/api/{_API_KEY}/subgraphs/id/{REALITIO_SUBGRAPH_ID}",
)

RESPONSES_QUERY = """
query responses_query($question_ids: [Bytes!]!) {
  questions(where: {questionId_in: $question_ids}, first: 1000) {
    id
    questionId
    currentAnswer
    currentAnswerBond
    responses(orderBy: timestamp, orderDirection: asc) {
      id
      timestamp
      answer
      bond
      user
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_realitio_responses(
    question_ids: List[str],
) -> Dict[str, Any]:
    """Fetch Realitio responses for a list of question IDs.

    The Omen subgraph stores question IDs as the raw question hash
    (``questionId`` in the Realitio schema), while the Realitio subgraph
    ``id`` is a compound key (``{contract}-{questionId}``).  We query by
    ``questionId_in`` and key the result dict by ``questionId`` so it
    matches the Omen DataFrame's ``question_id`` column.

    :param question_ids: list of Realitio question hashes (from Omen subgraph)
    :return: dict of question_id -> question data with responses
    """
    transport = RequestsHTTPTransport(url=REALITIO_SUBGRAPH_URL)
    client = Client(transport=transport, fetch_schema_from_transport=True)

    result: Dict[str, Any] = {}
    batch_size = 100
    n_total = len(question_ids)
    pbar = tqdm(total=n_total, desc="Fetching Realitio responses")
    for i in range(0, n_total, batch_size):
        batch = question_ids[i : i + batch_size]
        response = client.execute(
            gql(RESPONSES_QUERY),
            variable_values={"question_ids": batch},
        )
        for q in response.get("questions", []):
            result[q["questionId"]] = q
        pbar.update(len(batch))
    pbar.close()

    print(f"  Realitio: {len(result)}/{len(question_ids)} questions fetched")
    return result


def realitio_to_dataframe(questions: Dict[str, Any]) -> pd.DataFrame:
    """Convert Realitio question data to a DataFrame.

    :param questions: dict of question_id -> question data as returned by
        ``fetch_realitio_responses()``
    :return: DataFrame with one row per question and columns for response
        count, challenge status, and flip detection.
    """
    rows = []
    for qid, q in questions.items():
        responses = q.get("responses") or []
        n_responses = len(responses)
        current_answer = q.get("currentAnswer")

        first_response_answer = responses[0]["answer"] if responses else None
        is_challenged = n_responses > 1
        is_flipped = (
            is_challenged
            and current_answer is not None
            and first_response_answer is not None
            and current_answer.lower() != first_response_answer.lower()
        )

        responders = sorted({r["user"].lower() for r in responses if r.get("user")})

        rows.append(
            {
                "question_id": qid,
                "n_responses": n_responses,
                "is_challenged": is_challenged,
                "is_flipped": is_flipped,
                "first_response_answer": first_response_answer,
                "responders": responders,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "question_id",
                "n_responses",
                "is_challenged",
                "is_flipped",
                "first_response_answer",
                "responders",
            ]
        )
    return pd.DataFrame(rows)

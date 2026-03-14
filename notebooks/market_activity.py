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

"""Fetch and aggregate market activity data for the dashboard."""

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import pandas as pd

from omen_subgraph_utils import (
    MarketState,
    get_fpmms,
    get_market_current_answer,
    get_market_state,
)


def fetch_all_markets(
    creators: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch all FPMM markets for each creator.

    Args:
        creators: MARKET_CREATORS config dict (key -> config with "safe_contract_address")

    Returns:
        mapping of creator key -> list of market dicts
    """
    result = {}
    for key, cfg in creators.items():
        safe_contract_address = cfg["safe_contract_address"]
        data = get_fpmms(safe_contract_address)
        markets = list(data.get("fixedProductMarketMakers", {}).values())
        result[key] = markets
    return result


def market_state_summary(
    markets_by_creator: Dict[str, List[Dict[str, Any]]],
    creators: Dict[str, Dict[str, Any]],
) -> pd.DataFrame:
    """Count markets in each state per creator.

    Args:
        markets_by_creator: output of fetch_all_markets
        creators: MARKET_CREATORS config dict

    Returns:
        DataFrame with creator names as rows and states as columns
    """
    rows = []
    for key, markets in markets_by_creator.items():
        name = creators[key]["name"]
        counts = Counter(str(get_market_state(m)) for m in markets)
        counts["Total"] = len(markets)
        counts["_name"] = name
        rows.append(counts)

    df = pd.DataFrame(rows).fillna(0)
    df = df.set_index("_name")
    df.index.name = "Creator"

    # Ensure all states appear as columns in a sensible order
    state_order = [str(s) for s in MarketState] + ["Total"]
    for col in state_order:
        if col not in df.columns:
            df[col] = 0
    df = df[state_order]

    # Convert to int
    return df.astype(int)


def _ts_to_date(ts: Any) -> date:
    """Convert a unix timestamp (str or int) to a UTC date."""
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date()


def daily_activity(
    markets_by_creator: Dict[str, List[Dict[str, Any]]],
    creators: Dict[str, Dict[str, Any]],
    n_days: int = 10,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compute daily opened/closed/resolved counts per creator.

    Definitions:
    - opened: creationTimestamp falls on that day
    - closed (responded): currentAnswerTimestamp falls on that day (first answer submitted)
    - resolved (finalized): answerFinalizedTimestamp falls on that day and is in the past

    Args:
        markets_by_creator: output of fetch_all_markets
        creators: MARKET_CREATORS config dict
        n_days: number of past days to include

    Returns:
        Tuple of (df_opened, df_closed, df_resolved), each with dates as index
        and creator names as columns
    """
    today = datetime.now(timezone.utc).date()
    dates = [today - timedelta(days=i) for i in range(n_days - 1, -1, -1)]
    date_set = set(dates)

    opened: Dict[str, Counter] = {}
    closed: Dict[str, Counter] = {}
    resolved: Dict[str, Counter] = {}

    for key, markets in markets_by_creator.items():
        name = creators[key]["name"]
        opened[name] = Counter()
        closed[name] = Counter()
        resolved[name] = Counter()

        for m in markets:
            # Opened
            creation_ts = m.get("creationTimestamp")
            if creation_ts:
                d = _ts_to_date(creation_ts)
                if d in date_set:
                    opened[name][d] += 1

            # Closed (answered)
            answer_ts = (m.get("question") or {}).get("currentAnswerTimestamp")
            if answer_ts:
                d = _ts_to_date(answer_ts)
                if d in date_set:
                    closed[name][d] += 1

            # Resolved (finalized)
            finalized_ts = m.get("answerFinalizedTimestamp")
            if finalized_ts and int(finalized_ts) > 0:
                finalized_dt = datetime.fromtimestamp(
                    int(finalized_ts), tz=timezone.utc
                )
                if finalized_dt <= datetime.now(timezone.utc):
                    d = finalized_dt.date()
                    if d in date_set:
                        resolved[name][d] += 1

    def _to_df(data: Dict[str, Counter]) -> pd.DataFrame:
        df = pd.DataFrame(
            {name: [counts.get(d, 0) for d in dates] for name, counts in data.items()},
            index=dates,
        )
        df.index.name = "Date"
        return df

    return _to_df(opened), _to_df(closed), _to_df(resolved)


def answer_distribution(
    markets_by_creator: Dict[str, List[Dict[str, Any]]],
    creators: Dict[str, Dict[str, Any]],
    n_days: int = 10,
) -> Dict[str, Counter]:
    """Count answer outcomes for markets closed in the last n_days.

    A market counts as "closed in the period" if its currentAnswerTimestamp
    falls within the date range.

    Args:
        markets_by_creator: output of fetch_all_markets
        creators: MARKET_CREATORS config dict
        n_days: number of past days

    Returns:
        mapping of creator name -> Counter of answer labels (Yes, No, Invalid, N/A)
    """
    today = datetime.now(timezone.utc).date()
    date_set = set(today - timedelta(days=i) for i in range(n_days))

    result = {}
    for key, markets in markets_by_creator.items():
        name = creators[key]["name"]
        counts: Counter = Counter()

        for m in markets:
            answer_ts = (m.get("question") or {}).get("currentAnswerTimestamp")
            if not answer_ts:
                continue
            if _ts_to_date(answer_ts) not in date_set:
                continue
            answer_label = get_market_current_answer(m)
            counts[answer_label] += 1

        result[name] = counts

    return result

"""Standalone benchmark for the propose-question mech tool.

Runs N workers in parallel via ThreadPoolExecutor with a tqdm progress bar.
Results are collected in memory and written to disk at the end.

Usage:
    python benchmark_propose_questions.py --runs 40 --workers 5
    python benchmark_propose_questions.py --runs 40 --workers 5 --output results.jsonl

Requires .env at repo root with at least:
    OPENAI_API_KEY, NEWSAPI_API_KEY, SERPER_API_KEY
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from packages.valory.skills.market_creation_manager_abci.propose_questions import (
    KeyChain,
    gather_latest_questions,
    run,
)

try:
    from tqdm import tqdm
except ImportError:
    # Fallback if tqdm not installed.
    def tqdm(iterable=None, **kwargs):
        return iterable


def _make_keys() -> KeyChain:
    """Build a fresh KeyChain per thread (OpenAI client is not thread-safe)."""
    return KeyChain({
        "openai": [os.environ["OPENAI_API_KEY"]],
        "newsapi": [os.environ["NEWSAPI_API_KEY"]],
        "serper": [os.environ["SERPER_API_KEY"]],
        "subgraph": [os.environ.get("THEGRAPH_API_KEY", "unused")],
    })


def _run_one(
    run_id: int,
    resolution_ts: int,
    num_questions: int,
    latest_questions: list,
) -> dict:
    """Execute a single benchmark run. Thread-safe."""
    keys = _make_keys()
    t0 = time.time()
    try:
        result_tuple = run(
            tool="propose-question",
            api_keys=keys,
            resolution_time=str(resolution_ts),
            num_questions=num_questions,
            latest_questions=list(latest_questions),  # copy to avoid mutation
        )
        elapsed = time.time() - t0
        raw_json = result_tuple[0]
        try:
            parsed = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            parsed = {"raw": raw_json}

        return {
            "run": run_id,
            "elapsed_s": round(elapsed, 1),
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "resolution_time": resolution_ts,
            "result": parsed,
        }
    except Exception as exc:
        elapsed = time.time() - t0
        return {
            "run": run_id,
            "elapsed_s": round(elapsed, 1),
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark propose-question tool")
    parser.add_argument(
        "--runs", type=int, default=10,
        help="Number of independent runs. Default 10.",
    )
    parser.add_argument(
        "--num-questions", type=int, default=1,
        help="Questions per run. Default 1.",
    )
    parser.add_argument(
        "--workers", type=int, default=5,
        help="Parallel workers. Default 5.",
    )
    parser.add_argument(
        "--output", type=str, default="benchmark_results.jsonl",
        help="Output file (JSONL). Default benchmark_results.jsonl.",
    )
    args = parser.parse_args()

    # Resolution time: ~5 days from now.
    resolution_ts = int(
        (datetime.now(tz=timezone.utc) + timedelta(days=5)).timestamp()
    )

    # Seed latest_questions from the subgraph for dedup.
    print("Fetching latest questions from subgraph...")
    try:
        seed_questions = gather_latest_questions(
            os.environ.get("SUBGRAPH_API_KEY")
            or os.environ.get("THEGRAPH_API_KEY", ""),
        ) or []
    except Exception as exc:
        print(f"  Subgraph fetch failed ({exc}), starting with empty list")
        seed_questions = []
    print(f"  Seeded with {len(seed_questions)} existing questions")

    out_path = Path(args.output)
    print(f"\nBenchmark: {args.runs} runs × {args.num_questions} q/run, "
          f"{args.workers} parallel workers")
    print(f"Resolution: {datetime.fromtimestamp(resolution_ts, tz=timezone.utc):%Y-%m-%d}")
    print(f"Output: {out_path}")
    print("=" * 70)

    # Launch parallel runs with tqdm progress bar.
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                _run_one, i, resolution_ts, args.num_questions, seed_questions,
            ): i
            for i in range(1, args.runs + 1)
        }
        pbar = tqdm(total=args.runs, desc="Generating", unit="q")
        for future in as_completed(futures):
            record = future.result()
            results.append(record)

            # Progress line inside tqdm.
            result = record.get("result", {})
            if isinstance(result, dict) and result.get("questions"):
                q = list(result["questions"].values())[0]
                q_text = q["question"] if isinstance(q, dict) else str(q)
                pbar.set_postfix_str(q_text[:60], refresh=True)
            elif "error" in record:
                pbar.set_postfix_str(f"ERR: {record['error'][:40]}", refresh=True)
            elif isinstance(result, dict) and "error" in result:
                pbar.set_postfix_str(f"ERR: {result['error'][:40]}", refresh=True)
            pbar.update(1)
        pbar.close()

    # Sort by run number for deterministic output.
    results.sort(key=lambda r: r.get("run", 0))

    # Write all results.
    with open(out_path, "a") as f:
        for rec in results:
            f.write(json.dumps(rec, default=str) + "\n")

    # Summary.
    all_questions = []
    n_ok = 0
    n_err = 0
    for r in results:
        res = r.get("result", {})
        if isinstance(res, dict) and res.get("questions"):
            n_ok += 1
            for qdata in res["questions"].values():
                q = qdata.get("question", "") if isinstance(qdata, dict) else str(qdata)
                all_questions.append(q)
        else:
            n_err += 1

    print(f"\n{'=' * 70}")
    print(f"DONE: {n_ok} ok, {n_err} errors, {len(all_questions)} questions")
    print(f"Saved to {out_path}")

    if all_questions:
        print(f"\n--- Generated questions ---")
        for i, q in enumerate(all_questions, 1):
            print(f"  {i:>2}. {q}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Daemon: runs the prediction pipeline on a loop.

Usage:
    python -m backend.daemon
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import (
    RUN_INTERVAL_SECONDS,
    MAX_RUNS_PER_INTERVAL,
    TARGET_PREDICTIONS_PER_INTERVAL,
    RUN_ATTEMPT_DELAY_SECONDS,
)
from backend.db import init_db, insert_prediction
from backend.pipeline import run_pipeline


def main():
    print("== howdidtheydo daemon ==")
    print(f"Run interval: {RUN_INTERVAL_SECONDS}s")
    init_db()
    print("Database initialised.")

    while True:
        interval_start = time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n[{interval_start}] Starting pipeline attempts (max {MAX_RUNS_PER_INTERVAL})...")

        total_new = 0
        total_found = 0

        for attempt in range(1, MAX_RUNS_PER_INTERVAL + 1):
            print(f"\n-- Attempt {attempt}/{MAX_RUNS_PER_INTERVAL} --")
            try:
                results, run_log = run_pipeline()
            except Exception as exc:
                import traceback
                print(f"Pipeline error: {exc}")
                traceback.print_exc()
                results, run_log = [], []

            print("-- pipeline log --")
            for line in run_log:
                print(" ", line)
            print("--")

            new_count = 0
            for pred in results:
                total_found += 1
                inserted = insert_prediction(pred)
                if inserted:
                    new_count += 1
                    total_new += 1
                    print(f"  + {pred['title'][:60]}  score={pred.get('score')}")
                else:
                    print(f"  = {pred['title'][:60]}  (duplicate)")

            print(f"Attempt complete: {len(results)} prediction(s) found, {new_count} new.")

            # Stop early if we've achieved the target number of new predictions
            if total_new >= TARGET_PREDICTIONS_PER_INTERVAL:
                print(f"Target reached: {total_new} new predictions — stopping attempts.")
                break

            # If there are more attempts available, wait a short delay before retrying
            if attempt < MAX_RUNS_PER_INTERVAL:
                print(f"Waiting {RUN_ATTEMPT_DELAY_SECONDS}s before next attempt...")
                time.sleep(RUN_ATTEMPT_DELAY_SECONDS)

        print(f"Interval complete: total found={total_found}, total new={total_new}.")
        print(f"Sleeping {RUN_INTERVAL_SECONDS}s …")
        time.sleep(RUN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

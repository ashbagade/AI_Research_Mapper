#!/usr/bin/env python3
"""Run the full ETL pipeline: aggregates first, then bulk download."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
from etl.fetch_aggregates import run as run_aggregates
from etl.fetch_works import run as run_works


def main():
    parser = argparse.ArgumentParser(description="Run OpenAlex ETL pipeline")
    parser.add_argument(
        "--max-works", type=int, default=None,
        help="Limit bulk download to N works (for development)",
    )
    parser.add_argument(
        "--aggregates-only", action="store_true",
        help="Only fetch aggregate counts, skip bulk download",
    )
    args = parser.parse_args()

    run_aggregates()
    print()

    if not args.aggregates_only:
        run_works(max_works=args.max_works)


if __name__ == "__main__":
    main()

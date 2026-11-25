"""Entry point. Examples:

    uv run main.py                       # full daily run (what the cron job executes)
    uv run main.py --hours 72 --dry-run  # wider window, write the email to output/ instead of sending
    uv run main.py --steps scrape content
    uv run main.py --check               # test the database connection
"""

import argparse
import logging
import sys

from app.config import settings


def main() -> int:
    parser = argparse.ArgumentParser(description="AI news aggregator - daily digest pipeline")
    parser.add_argument("--hours", type=int, default=settings.lookback_hours, help="lookback window")
    parser.add_argument("--top", type=int, default=settings.top_n, help="stories in the email")
    parser.add_argument("--dry-run", action="store_true", help="save the email HTML instead of sending")
    parser.add_argument("--steps", nargs="+", choices=["scrape", "content", "digest", "email"])
    parser.add_argument("--check", action="store_true", help="only test the database connection")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if args.check:
        from sqlalchemy import text

        from app.database import describe_database, engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"Connected to {describe_database()}")
        return 0

    from app.pipeline import run_daily_pipeline

    logging.getLogger("httpx").setLevel(logging.WARNING)  # re-apply after the SDK import
    run_daily_pipeline(args.hours, args.top, args.dry_run, args.steps)
    return 0


if __name__ == "__main__":
    sys.exit(main())

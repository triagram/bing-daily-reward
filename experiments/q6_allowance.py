"""
Q6 — measure the daily search allowance.

Runs typed queries from a clean post-reset state, reading the point total after each
one, and stops once three consecutive searches earn nothing. The index where the gain
goes to zero is the allowance.

Kept headful on purpose: the run that established typed queries earn 3 points each was
headful, and switching to headless here would change two things at once. Progress is
appended to logs/q6_run.jsonl as it happens, so an interrupted run keeps its results.

    uv run python experiments/q6_allowance.py
"""

import sys
import asyncio
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright
from rich.console import Console
from rich.logging import RichHandler

from config import USER_DATA_DIR
from utils.task_searches import run_daily_searches

LOG = Path(__file__).resolve().parent.parent / "logs" / "q6_run.jsonl"

console = Console(width=100)
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, show_path=False)],
)


async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            channel="chromium",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()

        result = await run_daily_searches(
            context,
            search_count=24,
            state_page=page,
            per_search_balance=True,
            stop_after_zero=3,
            log_path=LOG,
        )

        console.print("\n" + "=" * 74)
        console.print("  Q6 — daily search allowance")
        console.print("-" * 74)
        cumulative = 0
        for row in result.per_search:
            cumulative += row["gained"] or 0
            mark = "[green]💰[/green]" if row["gained"] else "  "
            console.print(
                f"   #{row['index']:>2}  {mark} {row['gained']:+3}   cumulative {cumulative:>3}"
                f"   {row['term'][:42]}"
            )
        console.print("-" * 74)
        paying = [r for r in result.per_search if r["gained"]]
        console.print(f"  paying searches: {len(paying)}")
        if paying:
            console.print(f"  last paying search: #{paying[-1]['index']}")
            per = {r["gained"] for r in paying}
            console.print(f"  points per paying search: {sorted(per)}")
        console.print(f"  {result.summary()}")
        console.print("=" * 74)

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())

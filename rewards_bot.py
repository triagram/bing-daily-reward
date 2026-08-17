"""
Entry point — runs the day's Rewards tasks and reports what they actually earned.

Each task returns a structured result rather than only logging, and the run ends with
a table of measured point deltas. Nothing here prints a point figure it did not
observe: where a total could not be read it says so.

    uv run python rewards_bot.py            # run today's tasks
    uv run python rewards_bot.py --dry-run  # read state and report, change nothing
"""

import sys
import json
import asyncio
import logging
from datetime import datetime, date
from pathlib import Path

from playwright.async_api import async_playwright
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from config import HEADLESS, REWARDS_URL, USER_DATA_DIR
from utils.claim import claim_pending
from utils.state_reader import fetch_state
from utils.task_daily_set import run_daily_set
from utils.task_explore import run_explore
from utils.task_searches import run_daily_searches

RUN_LOG = Path(__file__).parent / "logs" / "runs.jsonl"

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
)
logger = logging.getLogger("bing_rewards")


def record_run(payload: dict):
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"),
                             **payload}, ensure_ascii=False) + "\n")


async def main():
    dry_run = "--dry-run" in sys.argv

    console.print("\n[bold cyan]Microsoft Rewards[/bold cyan]")
    mode = "dry run — reading state only" if dry_run else "running today's tasks"
    console.print(f"[dim]{mode}[/dim]\n")

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=HEADLESS,
            channel="chromium",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto(REWARDS_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3.0)

        if "login.live.com" in page.url or "signin" in page.url:
            console.print("\n[bold yellow]Sign-in required.[/bold yellow]")
            console.print("Sign in to the Microsoft account in the open browser window,")
            console.print("then press [bold green]ENTER[/bold green] here to continue.\n")
            await asyncio.to_thread(input, "ENTER once signed in > ")

        opening = await fetch_state(page)
        console.print(
            f"  balance [bold]{opening.balance}[/bold]  ·  "
            f"unclaimed [bold]{opening.ready_to_claim}[/bold]  ·  "
            f"total [bold]{opening.total_points}[/bold]"
        )
        outstanding = opening.outstanding(date.today())
        console.print(f"  daily set outstanding today: {len(outstanding)}\n")

        if dry_run:
            for offer in outstanding:
                console.print(f"    would do  {offer.slot}  {offer.points}pts  {offer.title}")
            await context.close()
            return

        results: dict[str, object] = {}

        try:
            results["daily_set"] = await run_daily_set(context, state_page=page)
        except Exception as e:
            logger.error(f"Daily Set failed outright: {e}")

        try:
            results["searches"] = await run_daily_searches(context, state_page=page)
        except Exception as e:
            logger.error(f"Searches failed outright: {e}")

        try:
            results["explore"] = await run_explore(context, state_page=page)
        except Exception as e:
            logger.error(f"Explore failed outright: {e}")

        # Claiming goes last: the pot only stops growing once the tasks are done.
        try:
            results["claim"] = await claim_pending(page)
        except Exception as e:
            logger.error(f"Claim failed outright: {e}")

        closing = await fetch_state(page)

        table = Table(title="Measured this run")
        table.add_column("Task", style="cyan")
        table.add_column("Done", justify="right")
        table.add_column("Points", justify="right")
        table.add_column("Errors", justify="right")
        for name, res in results.items():
            if name == "claim":
                moved = res.claimed
                table.add_row("claim (moved, not earned)",
                              "yes" if res.clicked else "—",
                              f"{moved:+d}" if moved else "0",
                              "1" if res.error else "0")
                continue
            earned = res.points_earned
            done = (f"{res.submitted}/{res.attempted}" if name == "searches"
                    else f"{res.completed}/{res.attempted}")
            table.add_row(name, done,
                          f"{earned:+d}" if earned is not None else "unknown",
                          str(len(res.errors)))
        overall = (closing.total_points - opening.total_points
                   if closing.total_points is not None and opening.total_points is not None
                   else None)
        table.add_row("[bold]overall[/bold]", "",
                      f"[bold]{overall:+d}[/bold]" if overall is not None else "unknown", "")
        console.print()
        console.print(table)

        if closing.ready_to_claim:
            console.print(
                f"\n[yellow]{closing.ready_to_claim} points are still in "
                f"'Ready to claim'.[/yellow] The pot does not drain on its own."
            )

        record_run({
            "date": date.today().isoformat(),
            "opening_total": opening.total_points,
            "closing_total": closing.total_points,
            "overall_delta": overall,
            "claim": (
                {"clicked": results["claim"].clicked,
                 "moved": results["claim"].claimed,
                 "error": results["claim"].error}
                if "claim" in results else None
            ),
            "tasks": {
                name: {
                    "attempted": res.attempted,
                    "done": getattr(res, "completed", getattr(res, "submitted", None)),
                    "points": res.points_earned,
                    "errors": res.errors,
                }
                for name, res in results.items() if name != "claim"
            },
        })
        console.print(f"[dim]Run recorded in {RUN_LOG.relative_to(Path(__file__).parent)}[/dim]\n")

        await context.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(0)

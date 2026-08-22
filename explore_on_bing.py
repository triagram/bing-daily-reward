"""
Run the "Explore on Bing" tiles, separately from the daily run.

    uv run python explore_on_bing.py            # work today's unlocked tiles
    uv run python explore_on_bing.py --dry-run  # read state and report, change nothing

Separate on purpose. The mechanism these tiles credit by is not yet proven — one manual
attempt tested a locked tile and settled nothing — and an unproven task inside
rewards_bot.py would put its verdict into the daily run's Flags column, which is what
the observation window's exit criterion reads. Run this *after* the daily run, so the
day's measurement is already recorded.

It shares every rule the other tasks follow: work is confirmed per tile by re-reading
that tile's own isCompleted, and no point figure is printed that was not observed.
"""

import sys
import asyncio
import logging
from datetime import date

from playwright.async_api import async_playwright
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from config import HEADLESS, REWARDS_URL, USER_DATA_DIR
from utils.state_reader import fetch_state
from utils.task_explore_on_bing import (
    _fetch_earn,
    outstanding_tiles,
    query_for,
    run_explore_on_bing,
    topic_of,
)

console = Console()
logging.basicConfig(
    level=logging.INFO, format="%(message)s", datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
)


async def main():
    dry_run = "--dry-run" in sys.argv

    console.print("\n[bold cyan]Explore on Bing[/bold cyan]")
    mode = "dry run — reading state only" if dry_run else "working today's unlocked tiles"
    console.print(f"[dim]{mode}[/dim]\n")

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR), headless=HEADLESS, channel="chromium",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(REWARDS_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3.0)

        if "login.live.com" in page.url or "signin" in page.url:
            console.print("\n[bold yellow]Sign-in required.[/bold yellow] "
                          "Sign in, then press ENTER here.\n")
            await asyncio.to_thread(input, "ENTER once signed in > ")

        if dry_run:
            earn = await _fetch_earn(page)
            tiles = [o for o in earn.offers if "exploreonbing" in o.offer_id]
            table = Table(title=f"Explore on Bing — {date.today()}")
            table.add_column("Topic", style="cyan")
            table.add_column("State")
            table.add_column("Would search")
            for o in sorted(tiles, key=lambda o: (bool(o.raw.get("isLocked")), o.offer_id)):
                if o.is_completed:
                    state, term = "[green]done[/green]", "—"
                elif o.raw.get("isLocked") or o.raw.get("isDisabled"):
                    state, term = "[dim]locked (tomorrow)[/dim]", "—"
                else:
                    state, term = "[bold]open[/bold]", repr(query_for(o))
                table.add_row(topic_of(o) or "?", state, term)
            console.print(table)
            console.print(f"\n[dim]{len(outstanding_tiles(earn))} would be attempted"
                          "[/dim]")
            await context.close()
            return

        opening = await fetch_state(page)
        result = await run_explore_on_bing(context, state_page=page)
        closing = await fetch_state(page)

        table = Table(title="Measured this run")
        table.add_column("Tiles", justify="right")
        table.add_column("Points", justify="right")
        table.add_column("Errors", justify="right")
        earned = result.points_earned
        table.add_row(f"{result.completed}/{result.attempted}",
                      f"{earned:+d}" if earned is not None else "unknown",
                      str(len(result.errors)))
        console.print()
        console.print(table)

        for err in result.errors:
            console.print(f"  [yellow]{err}[/yellow]")

        if result.attempted and not result.completed:
            console.print(
                "\n[bold red]No tile completed.[/bold red] The mechanism assumed here — "
                "open the tile, then search its topic in what it opens — is unproven. "
                "This is the result that says so; nothing was silently counted."
            )

        overall = (closing.total_points - opening.total_points
                   if None not in (closing.total_points, opening.total_points) else None)
        if overall is not None:
            console.print(f"[dim]account total moved {overall:+d} across the whole run[/dim]")

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())

"""
Take a read-only sample of Rewards account state.

Loads the dashboard, records what it says, and appends one line to
logs/state_samples.jsonl. It never searches, clicks a task, or claims anything —
the only request it makes is the one your browser makes when you open the dashboard.

Each run also archives the raw HTML under captures/samples/. That matters more than
it looks: when the parser turns out to have missed a field, the archive can be
re-parsed with the improved parser instead of going back to the account for another
sample. Collect once, analyse many times.

Run it daily and the questions we currently cannot answer — where the search counter
lives, what resets overnight, whether points credit with a lag — answer themselves
from the diffs.

    uv run python sample_state.py            # take a sample
    uv run python sample_state.py --history  # show what has been collected so far
"""

import sys
import gzip
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, date

from playwright.async_api import async_playwright
from rich.console import Console
from rich.table import Table

from config import USER_DATA_DIR
from utils.dashboard_state import DashboardState, parse_dashboard

BASE = Path(__file__).parent
LOG_PATH = BASE / "logs" / "state_samples.jsonl"
ARCHIVE_DIR = BASE / "captures" / "samples"

console = Console()
logging.basicConfig(level=logging.WARNING)


def to_record(state: DashboardState, note: str = "") -> dict:
    today = date.today()
    return {
        "sampled_at": datetime.now().isoformat(timespec="seconds"),
        "date": today.isoformat(),
        "note": note,
        "balance": state.balance,
        "level": state.level,
        "counters": state.counters,
        "offer_count": len(state.offers),
        "markets": sorted(state.markets),
        "daily_set_today": [
            {
                "slot": o.slot,
                "offer_id": o.offer_id,
                "title": o.title,
                "points": o.points,
                "is_completed": o.is_completed,
            }
            for o in state.daily_set(today)
        ],
        "outstanding_today": len(state.outstanding(today)),
        "daily_set_dates": sorted({str(o.day) for o in state.offers if o.is_daily_set}),
    }


def load_history() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    out = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def show_diff(previous: dict | None, current: dict):
    """Report what moved since the last sample — the reason for sampling at all."""
    if not previous:
        console.print("[dim]No earlier sample to compare against.[/dim]")
        return

    console.print(f"\n[bold]Changes since {previous['sampled_at']}[/bold]")

    before, after = previous.get("balance"), current.get("balance")
    if isinstance(before, int) and isinstance(after, int):
        delta = after - before
        colour = "green" if delta > 0 else "dim"
        console.print(f"  balance  {before} → {after}  [{colour}]{delta:+d}[/{colour}]")

    old_counters = {str(c.get("label")): c for c in previous.get("counters", [])}
    for counter in current.get("counters", []):
        label = str(counter.get("label"))
        old = old_counters.get(label)
        now_text = f"{counter['value']}/{counter['maxValue']}"
        if not old:
            console.print(f"  counter  {label}: (new) → {now_text}")
        elif (old["value"], old["maxValue"]) != (counter["value"], counter["maxValue"]):
            console.print(
                f"  counter  {label}: {old['value']}/{old['maxValue']} → [yellow]{now_text}[/yellow]"
            )

    if previous.get("date") != current.get("date"):
        console.print(
            f"  [cyan]date rolled over: {previous.get('date')} → {current.get('date')}[/cyan]"
        )


def print_history():
    history = load_history()
    if not history:
        console.print("[yellow]No samples collected yet.[/yellow]")
        return

    table = Table(title=f"State samples ({len(history)})")
    table.add_column("Sampled at", style="cyan", no_wrap=True)
    table.add_column("Balance", justify="right")
    table.add_column("Δ", justify="right")
    table.add_column("Counters")
    table.add_column("Today outstanding", justify="right")

    previous_balance = None
    for record in history:
        balance = record.get("balance")
        delta = ""
        if isinstance(balance, int) and isinstance(previous_balance, int):
            delta = f"{balance - previous_balance:+d}"
        previous_balance = balance if isinstance(balance, int) else previous_balance
        counters = " ".join(
            f"{c.get('label')}={c.get('value')}/{c.get('maxValue')}"
            for c in record.get("counters", [])
        )
        table.add_row(
            record.get("sampled_at", "?"),
            str(balance),
            delta,
            counters or "—",
            str(record.get("outstanding_today", "?")),
        )
    console.print(table)


async def take_sample(note: str) -> dict | None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=True,
            channel="chromium",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            from config import REWARDS_URL

            await page.goto(REWARDS_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4.0)

            if "login.live.com" in page.url or "signin" in page.url:
                console.print("[red]Not signed in — sample aborted.[/red]")
                return None

            html = await page.content()
        finally:
            await context.close()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = ARCHIVE_DIR / f"dashboard-{stamp}.html.gz"
    archive.write_bytes(gzip.compress(html.encode("utf-8")))

    state = parse_dashboard(html)
    record = to_record(state, note)
    record["archive"] = str(archive.relative_to(BASE))

    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


async def main():
    if "--history" in sys.argv:
        print_history()
        return

    note = ""
    if "--note" in sys.argv:
        idx = sys.argv.index("--note")
        if idx + 1 < len(sys.argv):
            note = sys.argv[idx + 1]

    console.print("\n[bold cyan]📊 Rewards state sample (read-only)[/bold cyan]")
    console.print("[dim]Loads the dashboard and records it. No searches, no clicks.[/dim]\n")

    previous = load_history()
    previous_record = previous[-1] if previous else None

    record = await take_sample(note)
    if record is None:
        return

    console.print(f"  balance   [bold]{record['balance']}[/bold]  (level {record['level']})")
    console.print(f"  offers    {record['offer_count']}  ·  markets {record['markets']}")
    console.print("  counters:")
    for counter in record["counters"]:
        console.print(f"      {str(counter['label']):14} {counter['value']:>3} / {counter['maxValue']}")
    console.print(f"  today's daily set ({record['outstanding_today']} outstanding):")
    for item in record["daily_set_today"]:
        mark = "✓" if item["is_completed"] else "✗"
        console.print(f"      {item['slot']:8} {mark}  {str(item['points']):>3}pts  {item['title']}")

    show_diff(previous_record, record)

    console.print(f"\n[green]Appended to {LOG_PATH.relative_to(BASE)}[/green]")
    console.print(f"[dim]Raw HTML archived at {record['archive']}[/dim]\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(0)

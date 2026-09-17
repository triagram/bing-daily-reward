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

    uv run python monitor.py            # take a sample
    uv run python monitor.py --history  # show what has been collected so far
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

from config import USER_DATA_DIR, REWARDS_EARN_URL
from utils.dashboard_state import DashboardState, parse_dashboard
from utils import profile_lock

BASE = Path(__file__).parent
LOG_PATH = BASE / "logs" / "state_samples.jsonl"
ARCHIVE_DIR = BASE / "captures" / "samples"

console = Console()
logging.basicConfig(level=logging.WARNING)


def explore_summary(earn: DashboardState | None) -> dict:
    """
    Reduce the /earn page to the few numbers worth a time series.

    Explore offer ids carry no date, so a single capture cannot say whether what is
    outstanding is today's or accumulated (Q7). A series can: ids that persist across
    days are a backlog, ids that vanish have rotated. Storing the ids, not just the
    count, is what makes that diff possible later.
    """
    if earn is None:
        return {"available": False}
    offers = [o for o in earn.offers if not o.is_daily_set and o.points]
    outstanding = [o for o in offers if o.is_completed is False]
    return {
        "available": True,
        "offer_count": len(offers),
        "outstanding": len(outstanding),
        "outstanding_points": sum(o.points for o in outstanding),
        "outstanding_ids": sorted(o.offer_id for o in outstanding),
        "all_ids": sorted(o.offer_id for o in offers),
    }


def to_record(state: DashboardState, note: str = "",
              earn: DashboardState | None = None) -> dict:
    today = date.today()
    return {
        "sampled_at": datetime.now().isoformat(timespec="seconds"),
        "date": today.isoformat(),
        "note": note,
        "balance": state.balance,
        "ready_to_claim": state.ready_to_claim,
        "total_points": state.total_points,
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
        "earn": explore_summary(earn),
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

    for key, label in (("balance", "balance "), ("ready_to_claim", "to claim"),
                       ("total_points", "TOTAL   ")):
        before, after = previous.get(key), current.get(key)
        if isinstance(before, int) and isinstance(after, int) and before != after:
            delta = after - before
            console.print(f"  {label} {before} → {after}  [green]{delta:+d}[/green]")
        elif isinstance(after, int) and before == after:
            console.print(f"  {label} {after}  [dim]+0[/dim]")

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

    pe, ce = previous.get("earn", {}), current.get("earn", {})
    if pe.get("available") and ce.get("available"):
        if pe["outstanding_points"] != ce["outstanding_points"]:
            console.print(
                f"  /earn    {pe['outstanding']} outstanding ({pe['outstanding_points']} pts)"
                f" → [yellow]{ce['outstanding']} ({ce['outstanding_points']} pts)[/yellow]"
            )
        gone = set(pe.get("all_ids", [])) - set(ce.get("all_ids", []))
        new_ids = set(ce.get("all_ids", [])) - set(pe.get("all_ids", []))
        for i in sorted(gone):
            console.print(f"  [dim]  rotated out: {i[:54]}[/dim]")
        for i in sorted(new_ids):
            console.print(f"  [cyan]  appeared:    {i[:54]}[/cyan]")

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


def profile_in_use() -> bool:
    """
    True when something already has the browser profile open.

    Chromium allows only one process per user-data-dir. On a schedule this matters:
    a sample firing while the bot runs, or while the profile is open by hand, would
    fail noisily or disturb the other session. Skipping is the right response — the
    next sample is only hours away.
    """
    return profile_lock.profile_in_use(USER_DATA_DIR)


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

            # The two pages are complementary, not nested: balance and the activity
            # counters exist only on the dashboard, and Explore offers only on /earn.
            # Sampling one and not the other is why Q7 had no series to work from.
            earn_html = None
            try:
                await page.goto(REWARDS_EARN_URL, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(4.0)
                earn_html = await page.content()
            except Exception as e:
                console.print(f"[yellow]Could not sample /earn: {e}[/yellow]")
        finally:
            await context.close()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = ARCHIVE_DIR / f"dashboard-{stamp}.html.gz"
    archive.write_bytes(gzip.compress(html.encode("utf-8")))

    earn_state = None
    earn_archive = None
    if earn_html:
        earn_archive = ARCHIVE_DIR / f"earn-{stamp}.html.gz"
        earn_archive.write_bytes(gzip.compress(earn_html.encode("utf-8")))
        earn_state = parse_dashboard(earn_html)

    state = parse_dashboard(html)
    record = to_record(state, note, earn=earn_state)
    record["archive"] = str(archive.relative_to(BASE))
    if earn_archive:
        record["earn_archive"] = str(earn_archive.relative_to(BASE))

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

    if profile_in_use():
        console.print(
            "[yellow]Browser profile is in use — skipping this sample.[/yellow]\n"
            "[dim]Close the browser or wait for the current run to finish.[/dim]\n"
        )
        return

    previous = load_history()
    previous_record = previous[-1] if previous else None

    record = await take_sample(note)
    if record is None:
        return

    console.print(
        f"  balance   [bold]{record['balance']}[/bold]  (level {record['level']})"
        f"   ready to claim: {record['ready_to_claim']}"
        f"   [dim]total {record['total_points']}[/dim]"
    )
    console.print(f"  offers    {record['offer_count']}  ·  markets {record['markets']}")
    console.print("  counters:")
    for counter in record["counters"]:
        console.print(f"      {str(counter['label']):14} {counter['value']:>3} / {counter['maxValue']}")
    e = record.get("earn", {})
    if e.get("available"):
        console.print(
            f"  /earn      {e['offer_count']} offers  ·  "
            f"[bold]{e['outstanding']}[/bold] outstanding worth "
            f"[bold]{e['outstanding_points']}[/bold] pts"
        )
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

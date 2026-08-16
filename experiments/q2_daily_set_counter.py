"""
Q2 — does the Daily Set counter agree with the Daily Set cards?

The dashboard states today's progress twice and the two have disagreed in both
directions: on 2026-08-11 the ring read 0/3 while a card carried a Completed badge, and
on 08-12 the ring read 1/3 while all three cards reported isCompleted false. Until it is
known which source is authoritative, a rewritten Daily Set task has no trustworthy way
to decide whether a card still needs doing.

This completes **exactly one** card from a clean state and then watches both sources
over an hour. One card, because the question is about how a single completion
propagates; touching more would make the counter ambiguous again.

    Immediately   does either source notice at once?
    +5 minutes    does a lagging source catch up?
    +60 minutes   do they ever agree?

Readings:
    ring moves, card follows later          the ring leads; card state lags
    card moves, ring follows later          the card leads; ring lags
    one moves, the other never              they count different things
    both move together                      the earlier contradictions were transient

This is the first experiment here that is not read-only: it clicks a real task on a real
account. It spends one daily-set card, which is 10 points that would have been earned
anyway by any normal run.

    uv run python experiments/q2_daily_set_counter.py
"""

import sys
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, date
from urllib.parse import parse_qs, quote_plus, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright, Page
from rich.console import Console
from rich.logging import RichHandler

from config import USER_DATA_DIR, REWARDS_URL
from utils.dashboard_state import parse_dashboard
from utils.humanizer import handle_quiz_or_poll_on_page, random_sleep
from utils.state_reader import fetch_state, counter_for

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "q2_run.jsonl"

console = Console(width=100)
logging.basicConfig(level=logging.INFO, format="%(message)s",
                    handlers=[RichHandler(console=console, show_path=False)])
logger = logging.getLogger("bing_rewards")


def write(record: dict):
    """Append immediately — an interrupted run must keep what it observed."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"),
                             **record}, ensure_ascii=False) + "\n")


async def observe(page: Page, label: str) -> dict:
    """Read both sources of truth and record them side by side."""
    state = await fetch_state(page)
    ring = counter_for(state, "Daily Set")
    cards = [
        {"slot": o.slot, "offer_id": o.offer_id, "title": o.title,
         "points": o.points, "is_completed": o.is_completed}
        for o in state.daily_set(date.today())
    ]
    done_by_cards = sum(1 for c in cards if c["is_completed"])
    record = {
        "event": "observation",
        "label": label,
        "ring": f"{ring['value']}/{ring['maxValue']}" if ring else None,
        "ring_value": ring["value"] if ring else None,
        "cards_completed": done_by_cards,
        "cards": cards,
        "total_points": state.total_points,
        "balance": state.balance,
        "ready_to_claim": state.ready_to_claim,
    }
    write(record)

    agree = ring is not None and ring["value"] == done_by_cards
    console.print(
        f"  [{label}] ring [bold]{record['ring']}[/bold]  ·  "
        f"cards say [bold]{done_by_cards}/3[/bold] done  ·  "
        f"total {state.total_points}  ·  "
        + ("[green]agree[/green]" if agree else "[red]DISAGREE[/red]")
    )
    return record


async def complete_one_card(page: Page, context, target) -> dict:
    """
    Complete a single daily-set card.

    Clicking the card is preferred over loading its destination directly. Navigated
    Bing searches are not credited (Q1), and whether the same holds for daily-set
    offers is unknown — clicking is what a person does, so it avoids importing that
    uncertainty into this experiment. The anchor is located by its href, taken from the
    parsed offer, rather than by a CSS class.
    """
    method = None
    before = set(context.pages)

    # The distinctive part of a destination is its query string, not its path: every
    # daily-set card points at bing.com/search, and seven anchors on /earn share that
    # prefix. Match on the q= value, or the form= code if there is no query.
    href_fragment = None
    if target.destination:
        query = parse_qs(urlparse(target.destination.replace("\\u0026", "&")).query)
        for key in ("q", "form", "OCID"):
            values = query.get(key)
            if values and len(values[0]) >= 4:
                href_fragment = quote_plus(values[0]) if key == "q" else values[0]
                break

    if href_fragment:
        anchor = page.locator(f'a[href*="{href_fragment}"]').first
        try:
            if await anchor.is_visible(timeout=4000):
                logger.info(f"Clicking card anchor matched on href fragment {href_fragment!r}")
                await anchor.click()
                method = "anchor-click"
        except Exception as e:
            logger.warning(f"Anchor click did not work: {e}")

    if method is None:
        logger.warning("Falling back to direct navigation — records this as a variable.")
        await page.goto(target.destination, wait_until="domcontentloaded", timeout=30000)
        method = "direct-navigation"

    await asyncio.sleep(2.0)
    opened = [p for p in context.pages if p not in before]
    work_page = opened[0] if opened else page

    try:
        await work_page.wait_for_load_state("domcontentloaded", timeout=15000)
        await work_page.evaluate("window.scrollBy(0, 400)")
        await handle_quiz_or_poll_on_page(work_page)
        await random_sleep(4.0, 6.0)
    except Exception as e:
        logger.warning(f"While working the card: {e}")

    if opened:
        for p in opened:
            try:
                await p.close()
            except Exception:
                pass

    write({"event": "completion_attempt", "offer_id": target.offer_id,
           "title": target.title, "method": method})
    return {"method": method}


async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR), headless=False, channel="chromium",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()

        console.print("\n[bold cyan]Q2 — Daily Set counter vs cards[/bold cyan]")
        console.print("[dim]Completes exactly one card, then watches both sources for an hour.[/dim]\n")

        baseline = await observe(page, "baseline")

        # Match DashboardState.outstanding(): an unknown (None) completion is not the
        # same as a known-incomplete one, and must not satisfy the precondition.
        outstanding = [c for c in baseline["cards"] if c["is_completed"] is False]
        if len(outstanding) != 3:
            console.print(
                f"[yellow]Expected 3 outstanding cards, found {len(outstanding)}. "
                "The day is not clean — aborting rather than measuring something else.[/yellow]"
            )
            await context.close()
            return

        state = parse_dashboard(await page.content())
        target = next(o for o in state.daily_set(date.today()) if o.slot == "Child1")
        console.print(f"\n  target: [bold]{target.slot}[/bold] — {target.title} ({target.points} pts)")
        console.print(f"  offer id: {target.offer_id}\n")

        await complete_one_card(page, context, target)

        await page.goto(REWARDS_URL, wait_until="domcontentloaded")
        await asyncio.sleep(3.0)
        await observe(page, "immediately")

        console.print("\n[dim]waiting 5 minutes ...[/dim]")
        await asyncio.sleep(300)
        await observe(page, "+5min")

        console.print("[dim]waiting 55 more minutes ...[/dim]")
        await asyncio.sleep(3300)
        final = await observe(page, "+60min")

        console.print("\n" + "=" * 72)
        rows = [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]
        obs = [r for r in rows if r.get("event") == "observation"]
        for r in obs:
            flag = "agree" if r["ring_value"] == r["cards_completed"] else "DISAGREE"
            console.print(f"  {r['label']:<12} ring {str(r['ring']):>5}   cards {r['cards_completed']}/3   {flag}")
        console.print("=" * 72 + "\n")

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())

"""
Fetch dashboard state from a live page.

Kept apart from utils/dashboard_state.py on purpose: that module is a pure function
from HTML to structured state, with no browser and no network, so it can be exercised
offline against a capture. This module is the thin layer that supplies it with HTML
from a real session.
"""

import asyncio
import logging
import re

from playwright.async_api import Page

from config import REWARDS_URL, POINTS_PER_SEARCH
from utils.dashboard_state import DashboardState, parse_dashboard

logger = logging.getLogger("bing_rewards")


async def fetch_state(page: Page, settle_seconds: float = 3.5) -> DashboardState:
    """
    Load the Rewards dashboard and parse its embedded state.

    `settle_seconds` gives the client-side app time to finish rendering. The state we
    read comes from the HTML document rather than from the rendered DOM, so this wait
    is a safety margin rather than a hard requirement.
    """
    await page.goto(REWARDS_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(settle_seconds)
    state = parse_dashboard(await page.content())
    if state.balance is None:
        logger.warning("Could not read point balance — the page layout may have changed.")
    return state


def counter_for(state: DashboardState, *labels: str) -> dict | None:
    """Find a progress counter by label, case-insensitively. First match wins."""
    wanted = {label.lower() for label in labels}
    for counter in state.counters:
        label = str(counter.get("label") or "").lower()
        if label in wanted:
            return counter
    return None


async def fetch_search_progress(page: Page) -> tuple[int, int] | None:
    """
    Read today's search points as (earned, cap), e.g. (45, 60).

    The dashboard has no search counter in its embedded state — the `Bing` ring is a
    1/1 gate (Q6) — but the points-breakdown modal renders the real figure. It is
    rendered client-side, so this reads the laid-out text rather than parsing the
    flight stream, which carries only the i18n strings.

    This is the only way to know how much allowance a run actually has left. Without
    it a run assumes a clean day and will happily spend queries that cannot earn,
    which is exactly what happened on 2026-08-17 when manual searches preceded it.

    Note the modal distinguishes "Bing search" (combined) from "Desktop Bing search";
    the combined figure is the one that matches the allowance.
    """
    try:
        await page.goto(f"{REWARDS_URL}?modal=pointbreakdown",
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5.0)
        lines = [l.strip() for l in (await page.inner_text("body")).splitlines()]
    except Exception as e:
        logger.warning(f"Could not open the points breakdown: {e}")
        return None

    for i, line in enumerate(lines):
        if line.lower() == "bing search":
            for follower in lines[i + 1 : i + 4]:
                m = re.fullmatch(r"(\d[\d,]*)\s*/\s*(\d[\d,]*)", follower)
                if m:
                    earned = int(m.group(1).replace(",", ""))
                    cap = int(m.group(2).replace(",", ""))
                    return earned, cap
    logger.warning("Points breakdown did not contain a 'Bing search' progress row.")
    return None


def searches_remaining(progress: tuple[int, int] | None) -> int | None:
    """How many more searches can still earn, or None if it could not be read."""
    if not progress:
        return None
    earned, cap = progress
    return max(0, (cap - earned) // POINTS_PER_SEARCH)

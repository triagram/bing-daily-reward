"""
Fetch dashboard state from a live page.

Kept apart from utils/dashboard_state.py on purpose: that module is a pure function
from HTML to structured state, with no browser and no network, so it can be exercised
offline against a capture. This module is the thin layer that supplies it with HTML
from a real session.
"""

import asyncio
import logging

from playwright.async_api import Page

from config import REWARDS_URL
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

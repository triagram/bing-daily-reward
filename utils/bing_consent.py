"""
Bing's cookie consent banner, which bing.com shows a fresh profile in the UK.

While it is unanswered, typed searches and the Explore tiles earn nothing, though the
Rewards cards are credited as usual (2026-10-27, the Pi's first run). A profile answers
it once and keeps the answer, so it is dealt with in --login, with a person at the
window, rather than clicked away by a run.
"""

import asyncio

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

BING_HOME_URL = "https://www.bing.com/"
CONSENT_BANNER_SELECTOR = "#bnp_container"

PAGE_LOAD_TIMEOUT_MS = 30_000
# The banner is put in after the page has loaded; a look straight after the load
# event can miss it. Measured 0.24-0.46 s after load, 5 of 5 fresh profiles, headless
# on the desktop (2026-11-18).
BANNER_SETTLE_S = 3.0


async def open_bing_home(page) -> None:
    await page.goto(BING_HOME_URL, wait_until="load", timeout=PAGE_LOAD_TIMEOUT_MS)
    await asyncio.sleep(BANNER_SETTLE_S)


async def consent_banner_shown(page) -> bool:
    return await page.locator(CONSENT_BANNER_SELECTOR).first.is_visible()


async def wait_until_answered(page, timeout_s: float) -> bool:
    """Whether the banner left the screen within the timeout, by whatever answer."""
    try:
        await page.locator(CONSENT_BANNER_SELECTOR).first.wait_for(
            state="hidden", timeout=timeout_s * 1000)
    except PlaywrightTimeoutError:
        return False
    return True

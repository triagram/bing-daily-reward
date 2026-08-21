import re
import asyncio
import random
import logging
from datetime import date
from typing import Callable, Awaitable
from playwright.async_api import BrowserContext, Page, Locator

from config import DAILY_SEARCH_MIN, DAILY_SEARCH_MAX

logger = logging.getLogger("bing_rewards")

async def random_sleep(min_seconds: float = 1.5, max_seconds: float = 3.0):
    """Sleep for a random float duration between min_seconds and max_seconds."""
    duration = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(duration)


def daily_search_count(day: date | None = None) -> int:
    """
    How many searches to run today.

    Stops well short of the 20-search allowance, and varies. Finishing exactly on the
    quota is itself a signature — nobody searches until their allowance runs out and
    then stops mid-afternoon — and a fixed count every day is another. Seeded by the
    date, so a given day is reproducible while consecutive days differ.

    This trades points for a lower profile: 8-15 searches earn 24-45 of the 60
    available. Streaks are unaffected, because the daily activity gate is satisfied by
    a single search, so the 100-point search streak and the stamp card do not depend on
    running the full allowance.
    """
    rng = random.Random(f"count-{(day or date.today()).isoformat()}")
    return rng.randint(DAILY_SEARCH_MIN, DAILY_SEARCH_MAX)


def search_gap() -> float:
    """
    Draw a gap between consecutive searches.

    A uniform 6-9s window is not what a person's timing looks like: real gaps are
    heavy-tailed, mostly short with an occasional long pause where attention went
    elsewhere. This draws from a three-part mixture instead, which keeps the mean
    reasonable while producing the long tail.

    Mean is roughly 20s, so a twenty-search run takes about seven minutes.
    """
    roll = random.random()
    if roll < 0.70:
        return random.uniform(7.0, 18.0)     # skimmed the results and moved on
    if roll < 0.95:
        return random.uniform(18.0, 45.0)    # actually read something
    return random.uniform(45.0, 120.0)       # got distracted


async def human_scroll(page: Page):
    """
    Scroll a results page the way someone skimming it would: a few downward steps of
    varying size, sometimes a scroll back up to re-read something, with pauses that
    are not all the same length.
    """
    try:
        for _ in range(random.randint(2, 5)):
            await page.evaluate(f"window.scrollBy(0, {random.randint(180, 620)})")
            await asyncio.sleep(random.uniform(0.5, 2.2))
        if random.random() < 0.35:
            await page.evaluate(f"window.scrollBy(0, -{random.randint(120, 400)})")
            await asyncio.sleep(random.uniform(0.6, 1.8))
    except Exception as e:
        logger.debug(f"scroll note: {e}")

async def human_type(locator: Locator, text: str):
    """Fast typing simulation (15-40ms per key) to speed up search execution."""
    try:
        await locator.click()
        await locator.fill("")
        for char in text:
            await locator.type(char, delay=random.randint(15, 40))
        await asyncio.sleep(0.2)
    except Exception as e:
        logger.debug(f"human_type note: {e}")

async def dismiss_all_modals_and_drawers(page: Page):
    """
    Closes any open slide-out drawer, modal, dialog, or popover overlay
    to ensure background elements are clickable without interception.
    """
    try:
        close_buttons = page.locator("[role='dialog'] button, .slide-out-drawer button, .modal button, [aria-label*='Close' i], .close-button").filter(has_text=re.compile(r"close|×", re.I))
        cnt = await close_buttons.count()
        if cnt > 0:
            for i in range(cnt):
                btn = close_buttons.nth(i)
                if await btn.is_visible():
                    logger.info("🧹 Closing open drawer/modal overlay...")
                    await btn.click(force=True)
                    await random_sleep(1.0, 1.5)
                    break
        await page.keyboard.press("Escape")
    except Exception:
        pass

async def handle_quiz_or_poll_on_page(page: Page):
    """
    Differentiated Quiz vs Poll Handler:
    1. Poll (Daily Poll): Clicks poll option ONCE, waits 2.0s, and exits immediately.
    2. Quiz (Show what you know): Clicks answer options until all questions are completed.
    """
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=5000)

        # 1. Poll Check (#btoption0, .bt_pollOption)
        poll_opt = page.locator("#btoption0, #btoption1, .bt_pollOption, [id*='option0']").first
        try:
            if await poll_opt.is_visible(timeout=2000):
                logger.info("  📊 Found Poll widget. Submitting option ONCE...")
                await poll_opt.click(force=True)
                await random_sleep(2.0, 3.0)
                return  # Poll requires only 1 click! Exit immediately.
        except Exception:
            pass

        # 2. Check for 'Start quiz' button
        start_btn = page.locator("input[value*='Start'], button:has-text('Start quiz'), input[value*='Take']").first
        try:
            if await start_btn.is_visible(timeout=1500):
                logger.info("  🎯 Clicking 'Start Quiz' button...")
                await start_btn.click(force=True)
                await random_sleep(1.5, 2.5)
        except Exception:
            pass

        # 3. Quiz Loop (up to 5 questions)
        for q in range(5):
            quiz_opts = page.locator("#rqAnswerOption0, #rqAnswerOption1, #btoption0, #btoption1, .rqOption, .btOptionCard, .wk_ansCard")
            try:
                qcnt = await quiz_opts.count()
                if qcnt > 0:
                    logger.info(f"  🧠 Found Quiz Question #{q + 1}. Clicking option...")
                    await quiz_opts.first.click(force=True)
                    await random_sleep(2.0, 3.0)
                else:
                    break
            except Exception:
                break
    except Exception as e:
        logger.debug(f"Quiz/Poll solver note: {e}")


async def find_offer_anchor(page: Page, destination: str | None,
                            query: str | None) -> Locator | None:
    """
    Locate a card's own anchor on the page, or return None to let the caller fall back.

    Matches the **whole** destination URL rather than a fragment of it. Both failures
    seen on 2026-08-21 came from matching a fragment:

    - The first word of the query is not unique. "How crystals form" and "How do
      magnets work" were both on the page, both reduced to the needle `How`, and
      `.first` clicked the same card twice — so the second offer reported a successful
      `anchor-click` while never being opened, and never completed.
    - Percent-encoding case varies between cards. One card rendered
      `ru=%2fsearch%3fq%3dweekly+quiz` and another `%2Fsearch%3Fq%3Dtechnology`, on the
      same page. A selector written for `q%3D` misses the lowercase one entirely, which
      is why a perfectly ordinary daily-set card fell through to direct navigation and
      did not register.

    The whole URL fixes both: it is unique per card, and the `i` flag absorbs the
    encoding case. Measured against the 2026-08-21 capture, every daily-set card and
    every outstanding Explore offer matched exactly one anchor this way, including the
    two the needle approach got wrong.

    The needle remains as a fallback for a page whose anchors differ from the payload's
    destination, but only when it identifies **one** anchor — an ambiguous needle is
    the bug above, so clicking its first match is worse than not clicking at all.
    """
    if destination:
        url = destination.replace("\\u0026", "&")
        # URLs do not normally carry either, but a selector broken by one would be
        # indistinguishable from a card that is simply absent.
        escaped = url.replace("\\", "\\\\").replace('"', '\\"')
        anchor = page.locator(f'a[href="{escaped}" i]')
        try:
            if await anchor.count() >= 1:
                return anchor.first
        except Exception as e:
            logger.debug(f"destination match failed for {url[:60]}: {e}")

    if query:
        needle = query.split()[0]
        loose = page.locator(f'a[href*="q={needle}" i], a[href*="q%3D{needle}" i]')
        try:
            n = await loose.count()
            if n == 1:
                return loose.first
            if n > 1:
                logger.debug(f"needle {needle!r} matched {n} anchors; not guessing")
        except Exception as e:
            logger.debug(f"needle match failed for {needle!r}: {e}")

    return None


async def reconcile_late_completions(
    unconfirmed: dict[str, str],
    recheck: Callable[[], Awaitable[set[str]]],
    wait_seconds: float = 25.0,
) -> set[str]:
    """
    Re-check items that looked unfinished, once, after giving credit time to land.

    Crediting lags. On 2026-08-21 an Explore offer was checked about twenty seconds
    after its card was worked, reported as failed, and was marked complete on the next
    read ten minutes later — with the balance up by exactly its five points. The run had
    already recorded an error and a `short` verdict for work that succeeded.

    That matters more than the miscount. `Flags` fires on a recorded error, and the
    observation window's exit criterion reads `Flags`, so a late credit turns a clean
    run dirty. A check that cries wolf is the same failure as one that stays silent,
    pointed the other way.

    One pass, after the loop rather than inside it: a per-item wait would slow every run
    to fix an occasional case, and the items still have the rest of the run to settle in.

    Returns the keys that turned out complete, for the caller to subtract from its own
    errors — leaving the error behind would defeat the point of asking again.
    """
    if not unconfirmed:
        return set()

    logger.info(
        f"   {len(unconfirmed)} not confirmed; waiting {wait_seconds:.0f}s and "
        "re-reading before calling them failed"
    )
    await asyncio.sleep(wait_seconds)
    try:
        completed = await recheck()
    except Exception as e:
        logger.warning(f"   reconciliation read failed: {e}")
        return set()

    late = set(unconfirmed) & completed
    for key in late:
        logger.info(f"     ✓ {key} completed after all — credit was late")
    return late

async def execute_action_and_cleanup_new_tab(
    context: BrowserContext, 
    action_coro: Callable[[], Awaitable[None]], 
    stay_seconds: float = 3.0
):
    """
    Executes an action, captures newly opened tab, interacts with Quiz/Poll widgets,
    scrolls to register view, stays briefly, and closes tab cleanly.
    """
    initial_pages = set(context.pages)
    await action_coro()
    await asyncio.sleep(1.0)
    
    current_pages = context.pages
    new_pages = [p for p in current_pages if p not in initial_pages]
    
    for new_page in new_pages:
        try:
            await new_page.wait_for_load_state("domcontentloaded", timeout=6000)
            await new_page.evaluate("window.scrollBy(0, 400)")
            await handle_quiz_or_poll_on_page(new_page)
        except Exception:
            pass

        await random_sleep(stay_seconds, stay_seconds + 1.0)
        try:
            await new_page.close()
        except Exception:
            pass

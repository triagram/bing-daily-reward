import re
import asyncio
import random
import logging
from typing import Callable, Awaitable
from playwright.async_api import BrowserContext, Page, Locator

logger = logging.getLogger("bing_rewards")

async def random_sleep(min_seconds: float = 1.5, max_seconds: float = 3.0):
    """Sleep for a random float duration between min_seconds and max_seconds."""
    duration = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(duration)


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

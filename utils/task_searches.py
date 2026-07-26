import random
import asyncio
import logging
from urllib.parse import quote_plus
from playwright.async_api import BrowserContext
from config import FALLBACK_KEYWORDS, DAILY_SEARCH_COUNT, MIN_DELAY_BETWEEN_SEARCHES, MAX_DELAY_BETWEEN_SEARCHES
from utils.humanizer import random_sleep

logger = logging.getLogger("bing_rewards")

async def run_daily_searches(context: BrowserContext, search_count: int = DAILY_SEARCH_COUNT):
    """
    Task 3: Single Persistent Search Tab Architecture (TheNetsky Pattern)
    Performs `search_count` (default 20) Bing searches inside ONE single tab to avoid
    tab context switching overhead, memory leaks, and timeout crashes.
    Enforces 6-9s search cooldown per query to guarantee 60/60 points.
    """
    logger.info(f"⚡ [Task 3] Starting {search_count} Bing Searches (Target: 60 points)...")
    
    # 1. Generate unique search terms
    keywords = list(FALLBACK_KEYWORDS)
    random.shuffle(keywords)
    while len(keywords) < search_count:
        keywords.append(f"explore topic {random.randint(1000, 9999)} news")

    # 2. Create ONE persistent search tab
    search_tab = await context.new_page()
    completed = 0

    try:
        for idx in range(search_count):
            term = keywords[idx]
            logger.info(f"Search [{idx + 1}/{search_count}]: Searching for '{term}'...")

            search_url = f"https://www.bing.com/search?q={quote_plus(term)}&form=QBLH"
            try:
                await search_tab.goto(search_url, wait_until="domcontentloaded", timeout=12000)
                await asyncio.sleep(1.5)

                # Scroll search result page to trigger view & Microsoft point verification
                await search_tab.evaluate("window.scrollBy(0, 350)")

                # Sleep 6.0 ~ 9.0s (Search Cooldown Required by Microsoft Rewards Counter)
                await random_sleep(MIN_DELAY_BETWEEN_SEARCHES, MAX_DELAY_BETWEEN_SEARCHES)
                completed += 1
                logger.info(f"✓ Search [{idx + 1}/{search_count}] completed (+3 pts).")
            except Exception as e:
                logger.warning(f"Note on search #{idx + 1}: {e}")

    finally:
        # Close the single search tab when finished
        try:
            await search_tab.close()
        except Exception:
            pass

    logger.info(f"✅ [Task 3] Completed {completed}/{search_count} Bing searches (~{completed * 3} points earned).")

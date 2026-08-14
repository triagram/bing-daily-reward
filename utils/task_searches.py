import random
import asyncio
import logging
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from playwright.async_api import BrowserContext, Page

from config import DAILY_SEARCH_COUNT
from utils import keywords
from utils.humanizer import human_scroll, human_type, search_gap
from utils.state_reader import fetch_state

logger = logging.getLogger("bing_rewards")


@dataclass
class SearchResult:
    """What a search run actually accomplished, as opposed to what it attempted."""

    attempted: int = 0
    submitted: int = 0          # the query reached Bing without raising
    balance_before: int | None = None
    balance_after: int | None = None
    # Search points land in the "Ready to claim" pot rather than the balance, so
    # the balance alone reads zero for a run that did earn. Measured 2026-08-13:
    # one search moved claim 9 -> 12 while the balance did not move at all.
    total_before: int | None = None
    total_after: int | None = None
    errors: list[str] = field(default_factory=list)
    # One entry per search when per_search_balance is on: which term, how it was
    # issued, and what the balance did immediately afterwards. A batch measurement
    # cannot attribute its delta to any single search; this can.
    per_search: list[dict] = field(default_factory=list)

    @property
    def points_earned(self) -> int | None:
        """
        Measured, not assumed: balance plus unclaimed, since earnings can land in
        either. None means the totals could not be read.
        """
        if self.total_before is None or self.total_after is None:
            return None
        return self.total_after - self.total_before

    def summary(self) -> str:
        earned = self.points_earned
        if earned is None:
            return (
                f"{self.submitted}/{self.attempted} searches submitted; "
                "points earned UNKNOWN (balance unreadable)"
            )
        return (
            f"{self.submitted}/{self.attempted} searches submitted; "
            f"{earned:+d} points measured (total {self.total_before} -> {self.total_after}, "
            f"balance {self.balance_before} -> {self.balance_after})"
        )


async def _search_once(page: Page, term: str, use_search_box: bool) -> None:
    """
    Run one query, either by typing into the Bing search box or by navigating.

    Typing is closer to how the query would normally be issued; direct navigation is
    faster and is used for most of the run so the whole thing does not take an hour.
    """
    if use_search_box:
        if "bing.com/search" not in page.url:
            await page.goto("https://www.bing.com", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(random.uniform(0.8, 2.0))
        box = page.locator("#sb_form_q, textarea[name='q'], input[name='q']").first
        await box.wait_for(state="visible", timeout=8000)
        await human_type(box, term)
        await asyncio.sleep(random.uniform(0.3, 1.1))
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("domcontentloaded", timeout=20000)
    else:
        url = f"https://www.bing.com/search?q={quote_plus(term)}"
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)

    await asyncio.sleep(random.uniform(1.0, 2.5))
    await human_scroll(page)


async def run_daily_searches(
    context: BrowserContext,
    search_count: int = DAILY_SEARCH_COUNT,
    state_page: Page | None = None,
    per_search_balance: bool = False,
    force_input_mode: str | None = None,
) -> SearchResult:
    """
    Perform Bing searches and measure what they earned.

    The balance is read before and after from the dashboard's own embedded state, so
    the point total this reports is observed rather than inferred from the number of
    pages that happened to load. When the balance cannot be read the result says so
    instead of quietly claiming success.

    `per_search_balance` reads the balance after every single search instead of only
    at the ends. It roughly doubles the run time, so it is off by default, but it is
    the only way to attribute a gain to a particular search — a before/after pair
    around a batch cannot say which query earned the points, or whether earning
    stopped partway because a quota filled.

    `force_input_mode` pins how queries are issued, "url" or "type", so the two can be
    compared directly instead of mixed at random.
    """
    result = SearchResult(attempted=search_count)
    owns_state_page = state_page is None
    if owns_state_page:
        state_page = await context.new_page()

    logger.info(f"⚡ [Searches] Reading starting balance ...")
    try:
        before = await fetch_state(state_page)
        result.balance_before = before.balance
        result.total_before = before.total_points
        logger.info(
            f"   Before: balance {before.balance}, unclaimed {before.ready_to_claim}, "
            f"total {before.total_points}"
        )
    except Exception as e:
        result.errors.append(f"balance_before: {e}")
        logger.warning(f"   Could not read starting balance: {e}")

    terms = keywords.generate(search_count)
    search_tab = await context.new_page()

    try:
        running_balance = result.total_before

        for idx, term in enumerate(terms, start=1):
            if force_input_mode:
                use_box = force_input_mode == "type"
            else:
                # Type a minority of queries rather than navigating straight to the URL.
                use_box = random.random() < 0.3
            mode = "type" if use_box else "url"
            logger.info(f"   [{idx}/{search_count}] {mode}: {term!r}")
            try:
                await _search_once(search_tab, term, use_box)
                result.submitted += 1
                ok = True
            except Exception as e:
                ok = False
                result.errors.append(f"search {idx} ({term!r}): {e}")
                logger.warning(f"   [{idx}/{search_count}] failed: {e}")

            if per_search_balance:
                await asyncio.sleep(3.0)  # let the credit land before looking
                try:
                    now = (await fetch_state(state_page)).total_points
                except Exception as e:
                    now = None
                    result.errors.append(f"balance after search {idx}: {e}")
                gained = (
                    now - running_balance
                    if isinstance(now, int) and isinstance(running_balance, int)
                    else None
                )
                result.per_search.append(
                    {"index": idx, "term": term, "mode": mode, "ok": ok,
                     "total": now, "gained": gained}
                )
                marker = "💰" if gained else "  "
                logger.info(f"       {marker} total {now} ({gained:+d})" if gained is not None
                            else f"       total {now} (delta unknown)")
                if isinstance(now, int):
                    running_balance = now

            if idx < search_count:
                gap = search_gap()
                logger.info(f"       waiting {gap:.1f}s")
                await asyncio.sleep(gap)
    finally:
        try:
            await search_tab.close()
        except Exception:
            pass

    logger.info("⚡ [Searches] Reading final balance ...")
    try:
        after = await fetch_state(state_page)
        result.balance_after = after.balance
        result.total_after = after.total_points
        logger.info(
            f"   After: balance {after.balance}, unclaimed {after.ready_to_claim}, "
            f"total {after.total_points}"
        )
    except Exception as e:
        result.errors.append(f"balance_after: {e}")
        logger.warning(f"   Could not read final balance: {e}")

    if owns_state_page:
        try:
            await state_page.close()
        except Exception:
            pass

    logger.info(f"✅ [Searches] {result.summary()}")
    return result

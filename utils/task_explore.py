"""
Task 2 — the "Explore on Bing" offers on /earn.

Rewritten around the parsed state, like the Daily Set. The previous version anchored
on an `<h2>Explore on Bing</h2>` heading and a `div[class*='cursor-pointer']` fallback
that matches 147 elements on that page, then reported `(+10 pts)` for every click that
did not raise.

Three things differ from the Daily Set and shape this module:

- **Offer ids carry no date.** Daily-set ids embed one, which is what makes filtering
  by day possible; Explore ids look like `WW_Rewards_locked_level2_Aug26w2_offer1` or
  `ENstar_Rewards_DailyGlobalOffer_Evergreen_Sunday`. So "today's offers" cannot be
  selected — only "outstanding" ones, which rotate rather than accumulate (Q7).
- **Point values vary**: 5, 10 and 15 have all been seen, so what a run is worth is
  not a fixed multiple and has to be measured.
- **The page mixes offers with promotional banners.** Banners have no `points`, and
  clicking them opens app-store pages and referral flows rather than earning
  anything. Only offers with a point value are touched.
"""

import asyncio
import logging
from dataclasses import dataclass, field

from playwright.async_api import BrowserContext, Page

from config import REWARDS_EARN_URL
from utils.dashboard_state import Offer, parse_dashboard
from utils.humanizer import (
    dismiss_all_modals_and_drawers,
    handle_quiz_or_poll_on_page,
    human_scroll,
    random_sleep,
)
from utils.retry import retry_async
from utils.state_reader import fetch_state

logger = logging.getLogger("bing_rewards")


@dataclass
class ExploreResult:
    attempted: int = 0
    completed: int = 0            # confirmed by isCompleted flipping
    total_before: int | None = None
    total_after: int | None = None
    per_offer: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def points_earned(self) -> int | None:
        if self.total_before is None or self.total_after is None:
            return None
        return self.total_after - self.total_before

    def summary(self) -> str:
        earned = self.points_earned
        measured = f"{earned:+d} points measured" if earned is not None else "points UNKNOWN"
        return f"{self.completed}/{self.attempted} offers confirmed complete; {measured}"


async def _fetch_earn(page: Page):
    """Load /earn and parse it. Offers live here; counters and balance do not."""
    await retry_async(
        lambda: page.goto(REWARDS_EARN_URL, wait_until="domcontentloaded", timeout=30000),
        what="/earn load",
    )
    await asyncio.sleep(4.0)
    return parse_dashboard(await page.content())


def outstanding_offers(state) -> list[Offer]:
    """
    Explore offers still to do: point-bearing, not a daily-set card, not complete.

    `points` being set is what separates a real offer from a banner. Banners report
    `None` there and lead to app installs and referral pages.
    """
    return [
        o for o in state.offers
        if not o.is_daily_set and o.points and o.is_completed is False
    ]


async def _open_offer(page: Page, context: BrowserContext, offer: Offer) -> tuple[bool, str]:
    """Click an offer's card and work whatever opens. Same approach as the Daily Set."""
    before = set(context.pages)
    method = "none"

    if offer.query:
        needle = offer.query.split()[0]
        anchor = page.locator(f'a[href*="q={needle}"], a[href*="q%3D{needle}"]').first
        try:
            if await anchor.is_visible(timeout=4000):
                await anchor.click()
                method = "anchor-click"
        except Exception as e:
            logger.debug(f"anchor click failed for {offer.offer_id}: {e}")

    if method == "none" and offer.title:
        # Explore cards are not all searches, so some have no query to match on. The
        # title is the next most specific handle the parsed offer gives us.
        try:
            card = page.locator(f'a:has-text("{offer.title[:40]}")').first
            if await card.is_visible(timeout=3000):
                await card.click()
                method = "title-click"
        except Exception as e:
            logger.debug(f"title click failed for {offer.offer_id}: {e}")

    if method == "none":
        if not offer.destination:
            return False, "no way to open this offer"
        logger.warning(f"   no anchor matched, navigating directly")
        await page.goto(offer.destination.replace("\\u0026", "&"),
                        wait_until="domcontentloaded", timeout=30000)
        method = "direct-navigation"

    await asyncio.sleep(1.5)
    opened = [p for p in context.pages if p not in before]
    work = opened[0] if opened else page

    try:
        await work.wait_for_load_state("domcontentloaded", timeout=15000)
        await human_scroll(work)
        await handle_quiz_or_poll_on_page(work)
        await random_sleep(3.0, 5.0)
    except Exception as e:
        logger.debug(f"while working {offer.offer_id}: {e}")

    for p in opened:
        try:
            await p.close()
        except Exception:
            pass

    return True, method


async def run_explore(
    context: BrowserContext,
    state_page: Page | None = None,
    limit: int | None = None,
) -> ExploreResult:
    """
    Complete the outstanding Explore offers.

    `limit` caps how many to do in one run. Outstanding counts have ranged from one to
    six, and there is no daily boundary to lean on, so a cap keeps a day where several
    have piled up from turning into an unusually long burst of activity.
    """
    result = ExploreResult()
    owns_page = state_page is None
    if owns_page:
        state_page = await context.new_page()

    logger.info("⚡ [Explore] Reading state ...")
    try:
        before = await fetch_state(state_page)
        result.total_before = before.total_points
        earn = await _fetch_earn(state_page)
    except Exception as e:
        result.errors.append(f"state_before: {e}")
        logger.warning(f"   Could not read starting state: {e}")
        if owns_page:
            await state_page.close()
        return result

    todo = outstanding_offers(earn)
    if limit is not None:
        todo = todo[:limit]
    result.attempted = len(todo)

    if not todo:
        logger.info("✅ [Explore] Nothing outstanding.")
        result.total_after = result.total_before
        if owns_page:
            await state_page.close()
        return result

    logger.info(f"   {len(todo)} outstanding, worth {sum(o.points for o in todo)} pts")

    for offer in todo:
        logger.info(f"   → {offer.title!r} ({offer.points} pts)")
        record = {"offer_id": offer.offer_id, "title": offer.title,
                  "points": offer.points, "method": None, "confirmed": False}
        try:
            await _fetch_earn(state_page)
            await dismiss_all_modals_and_drawers(state_page)

            opened, method = await _open_offer(state_page, context, offer)
            record["method"] = method
            if not opened:
                result.errors.append(f"{offer.offer_id}: {method}")
                result.per_offer.append(record)
                continue

            await asyncio.sleep(3.0)
            check = await _fetch_earn(state_page)
            now = next((o for o in check.offers if o.offer_id == offer.offer_id), None)
            record["confirmed"] = bool(now and now.is_completed)
            if record["confirmed"]:
                result.completed += 1
                logger.info("     ✓ confirmed complete")
            else:
                logger.warning(f"     ✗ still incomplete after {method}")
                result.errors.append(f"{offer.offer_id}: not marked complete after {method}")
        except Exception as e:
            result.errors.append(f"{offer.offer_id}: {e}")
            logger.warning(f"     error: {e}")
        finally:
            result.per_offer.append(record)

        await random_sleep(4.0, 10.0)

    try:
        after = await fetch_state(state_page)
        result.total_after = after.total_points
    except Exception as e:
        result.errors.append(f"state_after: {e}")

    if owns_page:
        try:
            await state_page.close()
        except Exception:
            pass

    logger.info(f"✅ [Explore] {result.summary()}")
    return result

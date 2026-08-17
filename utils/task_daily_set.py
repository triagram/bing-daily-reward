"""
Task 1 — the day's Daily Set cards.

Rewritten around the dashboard's own state. The previous version collected card
locators once, reused them across page navigations, and picked the first three matches
from a fallback that could match 112 elements; it also had no notion of *which day* a
card belonged to, on a page that carries three days at once.

Two rules make this tractable, both established by measurement:

- **`isCompleted` on the card is the only source of truth.** The "Daily Set" activity
  ring shows the *previous* day's completions (Q2), so gating on it would skip every
  task on any day following a completed one.
- **Cards are located by the search term in their href.** Every destination points at
  `bing.com/search`, so the path distinguishes nothing; the query does, and it is
  recovered by `Offer.query` including from the `checkuser?ru=` redirect that two of
  the three cards use.

Each card is verified individually: after working it, state is re-read and the card's
own `isCompleted` is checked. A card that does not flip is reported as failed rather
than counted as done.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date

from playwright.async_api import BrowserContext, Page

from config import REWARDS_URL
from utils.dashboard_state import Offer
from utils.humanizer import (
    dismiss_all_modals_and_drawers,
    handle_quiz_or_poll_on_page,
    human_scroll,
    random_sleep,
)
from utils.state_reader import fetch_state

logger = logging.getLogger("bing_rewards")


@dataclass
class DailySetResult:
    """What the run actually accomplished, verified card by card."""

    attempted: int = 0
    completed: int = 0            # confirmed by isCompleted flipping, not by clicking
    total_before: int | None = None
    total_after: int | None = None
    per_card: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def points_earned(self) -> int | None:
        """Balance plus unclaimed, since earnings land in either."""
        if self.total_before is None or self.total_after is None:
            return None
        return self.total_after - self.total_before

    def summary(self) -> str:
        earned = self.points_earned
        measured = f"{earned:+d} points measured" if earned is not None else "points UNKNOWN"
        return f"{self.completed}/{self.attempted} cards confirmed complete; {measured}"


async def _open_card(page: Page, context: BrowserContext, offer: Offer) -> tuple[bool, str]:
    """
    Click a card and work whatever it opens.

    Clicking is preferred to loading the destination directly. Navigated Bing searches
    are not credited at all (Q1); whether the same holds for daily-set offers has not
    been tested, and clicking is what a person does, so it avoids depending on the
    answer. Navigation stays as a fallback and is reported, because a run that fell
    back is measuring something different from one that did not.
    """
    before = set(context.pages)
    method = "none"

    if offer.query:
        # href encoding varies (spaces as + or %20), so match on a stable slice.
        needle = offer.query.split()[0]
        anchor = page.locator(f'a[href*="q={needle}"], a[href*="q%3D{needle}"]').first
        try:
            if await anchor.is_visible(timeout=4000):
                await anchor.click()
                method = "anchor-click"
        except Exception as e:
            logger.debug(f"anchor click failed for {offer.slot}: {e}")

    if method == "none":
        if not offer.destination:
            return False, "no destination"
        logger.warning(f"   {offer.slot}: no anchor matched, navigating directly")
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
        logger.debug(f"while working {offer.slot}: {e}")

    for p in opened:
        try:
            await p.close()
        except Exception:
            pass

    return True, method


async def run_daily_set(
    context: BrowserContext,
    state_page: Page | None = None,
    day: date | None = None,
) -> DailySetResult:
    """
    Complete the outstanding Daily Set cards for `day` (today by default).

    Only cards whose offer id carries that date are touched. The dashboard serves
    yesterday's, today's and tomorrow's at once, so a run without this filter acts on
    the wrong day — which is what the previous version did.
    """
    day = day or date.today()
    result = DailySetResult()
    owns_page = state_page is None
    if owns_page:
        state_page = await context.new_page()

    logger.info("⚡ [Daily Set] Reading state ...")
    try:
        before = await fetch_state(state_page)
        result.total_before = before.total_points
        logger.info(
            f"   Before: balance {before.balance}, unclaimed {before.ready_to_claim}, "
            f"total {before.total_points}"
        )
    except Exception as e:
        result.errors.append(f"state_before: {e}")
        logger.warning(f"   Could not read starting state: {e}")
        if owns_page:
            await state_page.close()
        return result

    todo = before.outstanding(day)
    result.attempted = len(todo)
    if not todo:
        logger.info(f"✅ [Daily Set] Nothing outstanding for {day}.")
        if owns_page:
            await state_page.close()
        result.total_after = result.total_before
        return result

    logger.info(f"   {len(todo)} outstanding for {day}: " +
                ", ".join(f"{o.slot}({o.points}pts)" for o in todo))

    for offer in todo:
        logger.info(f"   → {offer.slot}: {offer.title!r} ({offer.points} pts)")
        record = {"slot": offer.slot, "offer_id": offer.offer_id, "title": offer.title,
                  "points": offer.points, "method": None, "confirmed": False}
        try:
            await state_page.goto(REWARDS_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2.5)
            await dismiss_all_modals_and_drawers(state_page)

            opened, method = await _open_card(state_page, context, offer)
            record["method"] = method
            if not opened:
                result.errors.append(f"{offer.slot}: {method}")
                result.per_card.append(record)
                continue

            # Verify this specific card rather than assuming the click worked.
            await asyncio.sleep(3.0)
            check = await fetch_state(state_page)
            now = next((o for o in check.daily_set(day) if o.offer_id == offer.offer_id), None)
            record["confirmed"] = bool(now and now.is_completed)
            if record["confirmed"]:
                result.completed += 1
                logger.info(f"     ✓ confirmed complete")
            else:
                logger.warning(f"     ✗ still incomplete after {method}")
                result.errors.append(f"{offer.slot}: not marked complete after {method}")
        except Exception as e:
            result.errors.append(f"{offer.slot}: {e}")
            logger.warning(f"     error: {e}")
        finally:
            result.per_card.append(record)

        await random_sleep(3.0, 8.0)

    try:
        after = await fetch_state(state_page)
        result.total_after = after.total_points
        logger.info(
            f"   After: balance {after.balance}, unclaimed {after.ready_to_claim}, "
            f"total {after.total_points}"
        )
    except Exception as e:
        result.errors.append(f"state_after: {e}")

    if owns_page:
        try:
            await state_page.close()
        except Exception:
            pass

    logger.info(f"✅ [Daily Set] {result.summary()}")
    return result

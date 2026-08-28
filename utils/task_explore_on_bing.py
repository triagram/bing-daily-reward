"""
Task 4 — the "Explore on Bing" tiles on /earn.

A different offer family from `task_keep_earning.py`, and the reason that module was
renamed: these render under their own heading and nothing here overlaps with it.

    ENUS_airlinetickets_exploreonbing_activation_Evergreen   "Take off soon"   +10

Four are unlocked on any given day and four sit behind "Unlocks tomorrow"; the
following day yesterday's locked four are the open four. So the section is worth a
steady 40 points a day rather than a backlog to clear, and the locked ones are not
missed work.

Three things about them shape this module:

**They are worked, not clicked.** Every other offer in this project links to
`bing.com/search?q=…` and completes on arrival. These link to the Bing *home page* with
`rwAutoFlyout=exb`, and the account holder — who has done them by hand — reports it
takes opening the tile **and** searching the topic, together. So the tile arms the offer
for the session it opens, and the search has to happen inside that session.

**Which means: do not navigate after opening.** `_search_once` in `task_searches` starts
by loading bing.com when it is not already on a results page, which would throw away the
session the tile just established. Typing here is done in place, on whatever the tile
opened. The typed-only rule from Q1 still holds and is why this types rather than
building a `?q=` URL.

**Availability comes from `isLocked`, never from the page.** A locked tile renders first
in the section, in greyscale, and one browser profile has been seen showing the locked
four as though they were open. An attempt on a locked tile earns nothing however it is
searched — that is what an early manual test proved, having tested nothing else.

Deliberately not wired into `rewards_bot.py`. It runs from `explore_on_bing.py` so that
an unproven task cannot put a `zero` verdict into the daily run's Flags column, which is
what the observation window's exit criterion reads. The result type matches the other
tasks so that merging it later is three lines.
"""

import re
import asyncio
import logging
import random
from dataclasses import dataclass, field

from playwright.async_api import BrowserContext, Page

from config import REWARDS_EARN_URL
from utils.dashboard_state import Offer, parse_dashboard
from utils.humanizer import (
    dismiss_all_modals_and_drawers,
    human_scroll,
    human_type,
    random_sleep,
    reconcile_late_completions,
)
from utils.retry import retry_async
from utils.state_reader import fetch_state

logger = logging.getLogger("bing_rewards")

# Queries that override a tile's own prompt, keyed on the topic in the offer id.
#
# **The default is the tile's own prompt, and it usually works.** 2026-08-25 completed
# 4 of 4 without touching this map at all.
#
# **This is an exception list, learned from failures, not a theory.** Two topics have
# needed help so far, both measured on the same tiles the same day with only the query
# changed:
#
#   flight    "a flight to your perfect vacation"  ✗  ->  "flights from London to Paris"  ✓
#   shopping  "items on your shopping list"        ✗  ->  "buy wireless headphones"       ✓
#
# The tempting generalisation — that Bing verticals need a concrete entity before they
# render anything — does not survive 2026-08-25. `rentalcars`, `concerttickets` and
# `internetproviders` are all verticals, all searched with a placeholder and no entity
# ("book rental cars for your next adventure", "tickets for concerts near you"), and all
# three completed. So flights and shopping are exceptions whose common factor is not yet
# known, and nothing here should pretend otherwise.
#
# Which is why there are no *predicted* entries. An override that has never been measured
# destroys the observation it was guessing at: put "hotels in Edinburgh" here and the
# question of whether `hotel` completes on its own prompt can never be answered. Let the
# default run, and add an entry when a tile actually fails. That costs one tile once.
VERIFIED_QUERIES: dict[str, str] = {
    "flight": "flights from London to Paris",
    "shopping": "buy wireless headphones",
    # 2026-08-28, pending its retry. The prompt reads "open roles at a specific
    # company", and only the placeholder is substituted — the rest is left alone so
    # that the company name is the single thing that changed.
    "jobs": "open roles at Microsoft",
}

TOPIC_QUERIES: dict[str, str] = VERIFIED_QUERIES

# A tile's prompt reads "Search on Bing to find top-rated mattresses at great prices".
# The instruction is not part of the query; what follows it is.
PROMPT_PREFIX = re.compile(r"^\s*search\s+on\s+bing\s+(?:to|for)\s+", re.I)
LEADING_VERB = re.compile(r"^(?:see|find|check|discover|learn\s+about|explore)\s+", re.I)


def topic_of(offer: Offer) -> str | None:
    parts = offer.offer_id.split("_")
    return parts[1] if len(parts) > 1 else None


def query_from_description(description: str | None) -> str | None:
    """Turn a tile's prompt into something a person would plausibly type."""
    if not description:
        return None
    text = PROMPT_PREFIX.sub("", description.strip()).strip()
    text = LEADING_VERB.sub("", text).strip().rstrip(".").strip()
    return text or None


def query_for(offer: Offer) -> str | None:
    """
    What to search for this tile, best source first.

    The first run searched the topic token out of the offer id, because these tiles
    parsed with no title and no description. That produced `timezonedates` and
    `financemarket` — strings nobody would ever type — and completed none of four. The
    text was in the tile the whole time, one level down in its rendered children:
    "Search on Bing to see what time it is in a different time zone."

    So the tile's own prompt is the authority. The curated map overrides it only where a
    better wording has been learned, and the topic token survives as a last resort
    rather than as the first guess.
    """
    topic = topic_of(offer)
    if topic and topic in TOPIC_QUERIES:
        return TOPIC_QUERIES[topic]
    return query_from_description(offer.description) or offer.title or topic


def outstanding_tiles(state) -> list[Offer]:
    """
    Tiles this run may attempt: this family, not complete, and **not locked**.

    Both lock fields are checked. They have only ever been seen agreeing, but a tile
    that is disabled without being locked is one this run should still leave alone.
    """
    return [
        o for o in state.offers
        if "exploreonbing" in o.offer_id
        and o.is_completed is False
        and not o.raw.get("isLocked")
        and not o.raw.get("isDisabled")
    ]


@dataclass
class ExploreOnBingResult:
    attempted: int = 0
    completed: int = 0
    total_before: int | None = None
    total_after: int | None = None
    per_tile: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    expected_points: int = 0

    @property
    def points_earned(self) -> int | None:
        if self.total_before is None or self.total_after is None:
            return None
        return self.total_after - self.total_before

    def summary(self) -> str:
        earned = self.points_earned
        measured = f"{earned:+d} points measured" if earned is not None else "points UNKNOWN"
        return f"{self.completed}/{self.attempted} tiles confirmed complete; {measured}"


async def _fetch_earn(page: Page):
    await retry_async(
        lambda: page.goto(REWARDS_EARN_URL, wait_until="domcontentloaded", timeout=30000),
        what="/earn load",
    )
    await asyncio.sleep(4.0)
    return parse_dashboard(await page.content())


async def _search_in_place(page: Page, term: str) -> bool:
    """
    Type a query into whatever page the tile opened, without navigating first.

    Navigating would discard the session the tile established, which is the one thing
    this offer type appears to need. Returns False when no search box is present, which
    is itself worth knowing: it means the tile opened something other than Bing.
    """
    box = page.locator("#sb_form_q, textarea[name='q'], input[name='q']").first
    try:
        await box.wait_for(state="visible", timeout=8000)
    except Exception as e:
        logger.warning(f"     no search box on {page.url[:60]}: {e}")
        return False

    await human_type(box, term)
    await asyncio.sleep(random.uniform(0.3, 1.1))
    await page.keyboard.press("Enter")
    await page.wait_for_load_state("domcontentloaded", timeout=20000)
    await asyncio.sleep(random.uniform(1.5, 3.0))
    await human_scroll(page)
    return True


async def _find_tile_anchor(page: Page, offer: Offer):
    """
    Locate a tile by its own title, never by its href.

    **Every tile in this section shares one URL.** Measured 2026-08-23: seven tiles,
    one distinct `href`, `…bing.com/?…&rwAutoFlyout=exb` for all of them. So matching
    the whole destination — the strongest signature everywhere else in this project,
    and what `find_offer_anchor` is built on — degenerates here into always clicking
    whichever card the page happens to render first.

    That is the whole of what looked like a mechanism failure. On 08-23 the first tile
    attempted was `couponcodes`, which was also first in the DOM, so it was clicked and
    completed; the three attempted after it re-clicked that same finished card and were
    never activated. A retry that hour, starting with `hotel`, clicked the same card
    again and completed nothing. The queries were never the variable, and the
    activation flow was right all along — `successToast` on the completed tile reads
    "Activated! · Search on Bing to complete this activity".

    The title is unique: measured against the same capture, each of the four open tiles
    matched exactly one anchor by its own text, and the locked three matched none,
    since a locked tile is not a link.

    Exactly one match is required. Two would mean the title is no longer distinguishing,
    and clicking the first of them is how this bug looked from the outside.
    """
    if not offer.title:
        return None
    anchor = page.locator("a", has_text=offer.title)
    try:
        n = await anchor.count()
    except Exception as e:
        logger.debug(f"title lookup failed for {offer.offer_id}: {e}")
        return None
    if n == 1:
        return anchor.first
    logger.warning(f"     title {offer.title!r} matched {n} anchors; not guessing")
    return None


async def _work_tile(page: Page, context: BrowserContext, offer: Offer) -> tuple[bool, str]:
    """Open the tile and search its topic in whatever it opens."""
    term = query_for(offer)
    if not term:
        return False, "no topic in the offer id"

    before = set(context.pages)
    anchor = await _find_tile_anchor(page, offer)
    if anchor is None:
        return False, "tile anchor not found"

    try:
        await anchor.click()
    except Exception as e:
        return False, f"tile click failed: {e}"

    await asyncio.sleep(2.0)
    opened = [p for p in context.pages if p not in before]
    work = opened[0] if opened else page

    try:
        await work.wait_for_load_state("domcontentloaded", timeout=15000)
        searched = await _search_in_place(work, term)
        # Credit has been seen arriving late elsewhere; lingering costs little and the
        # reconciliation pass covers the rest.
        await random_sleep(4.0, 7.0)
    except Exception as e:
        searched = False
        logger.debug(f"while working {offer.offer_id}: {e}")

    for p in opened:
        try:
            await p.close()
        except Exception:
            pass

    return searched, f"tile-click+search:{term!r}" if searched else "opened but could not search"


async def run_explore_on_bing(
    context: BrowserContext,
    state_page: Page | None = None,
) -> ExploreOnBingResult:
    """Work today's unlocked Explore on Bing tiles, confirming each one individually."""
    result = ExploreOnBingResult()
    owns_page = state_page is None
    if owns_page:
        state_page = await context.new_page()

    logger.info("⚡ [Explore on Bing] Reading state ...")
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

    todo = outstanding_tiles(earn)
    result.attempted = len(todo)
    # The payload carries no points for these; the page renders +10 on every one seen.
    result.expected_points = 10 * len(todo)

    locked = [o for o in earn.offers
              if "exploreonbing" in o.offer_id and o.raw.get("isLocked")]
    if locked:
        logger.info(f"   {len(locked)} locked (tomorrow's): "
                    + ", ".join(sorted(filter(None, (topic_of(o) for o in locked)))))

    if not todo:
        logger.info("✅ [Explore on Bing] Nothing unlocked and outstanding.")
        result.total_after = result.total_before
        if owns_page:
            await state_page.close()
        return result

    logger.info(f"   {len(todo)} unlocked and outstanding")

    for offer in todo:
        topic = topic_of(offer)
        logger.info(f"   → {topic} — searching {query_for(offer)!r}")
        record = {"offer_id": offer.offer_id, "topic": topic,
                  "query": query_for(offer), "title": offer.title,
                  "method": None, "confirmed": False}
        try:
            await _fetch_earn(state_page)
            await dismiss_all_modals_and_drawers(state_page)

            worked, method = await _work_tile(state_page, context, offer)
            record["method"] = method
            if not worked:
                result.errors.append(f"{topic}: {method}")
                result.per_tile.append(record)
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
                result.errors.append(f"{topic}: not marked complete after {method}")
        except Exception as e:
            result.errors.append(f"{topic}: {e}")
            logger.warning(f"     error: {e}")
        finally:
            if record not in result.per_tile:
                result.per_tile.append(record)

        await random_sleep(5.0, 12.0)

    pending = {r["topic"]: f"{r['topic']}: not marked complete after {r['method']}"
               for r in result.per_tile if not r["confirmed"] and r["method"]}
    by_topic = {r["topic"]: r["offer_id"] for r in result.per_tile}

    async def _recheck() -> set[str]:
        state = await _fetch_earn(state_page)
        done = {o.offer_id for o in state.offers if o.is_completed}
        return {t for t, oid in by_topic.items() if oid in done}

    late = await reconcile_late_completions(pending, _recheck)
    for topic in late:
        result.completed += 1
        result.errors = [e for e in result.errors if e != pending[topic]]
        for r in result.per_tile:
            if r["topic"] == topic:
                r["confirmed"] = True
                r["late"] = True

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

    logger.info(f"✅ [Explore on Bing] {result.summary()}")
    return result

"""
Tests for the retry-once-then-warn rule of 2026-10-11.

Every item gets one retry; an item that fails again is a warning, reported in the daily
report rather than flagged. The retry only runs against the real page on a bad day, so
these tests stand a scripted server in for the browser: each item completes on a given
attempt, or never, or raises on one. The browser-facing helpers of each task module are
replaced with that script; everything that decides what happens next is the real code.
"""

import asyncio
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pytest

from utils import task_daily_set, task_explore_on_bing, task_keep_earning
from utils.dashboard_state import DashboardState, Offer

DAY = date(2026, 10, 11)
NEVER = None


class ScriptedServer:
    """Which attempt completes which item, and which attempt raises instead."""

    def __init__(self, completes_on: dict[str, int | None],
                 raises_on: dict[str, int] | None = None):
        self.completes_on = completes_on
        self.raises_on = raises_on or {}
        self.attempts = {offer_id: 0 for offer_id in completes_on}

    def attempt(self, offer_id: str) -> None:
        self.attempts[offer_id] += 1
        if self.raises_on.get(offer_id) == self.attempts[offer_id]:
            raise RuntimeError("the page did not load")

    def is_completed(self, offer_id: str) -> bool:
        target = self.completes_on[offer_id]
        return target is not None and self.attempts[offer_id] >= target

    def snapshot(self, offers: list[Offer]) -> list[Offer]:
        return [replace(o, is_completed=self.is_completed(o.offer_id)) for o in offers]


class FakePage:
    async def goto(self, *args, **kwargs):
        return None


async def _instant(*args, **kwargs):
    return None


@pytest.fixture(autouse=True)
def nothing_waits(monkeypatch):
    """The tasks pause for seconds between steps; here nothing does."""
    monkeypatch.setattr(asyncio, "sleep", _instant)
    for module in (task_daily_set, task_explore_on_bing, task_keep_earning):
        monkeypatch.setattr(module, "random_sleep", _instant)
        monkeypatch.setattr(module, "dismiss_all_modals_and_drawers", _instant)


def _totals():
    return DashboardState(balance=1000, ready_to_claim=0)


# --------------------------------------------------------------------------- #
# Keep earning
# --------------------------------------------------------------------------- #

def _keep_earning_offers() -> list[Offer]:
    return [Offer(offer_id=f"WW_Bing_MonthlyFeaturedTopic_20261011_{n}", title=title,
                  points=points, is_completed=False)
            for n, title, points in [(1, "Orangutan intelligence", 10),
                                     (2, "Mars exploration", 10),
                                     (3, "Mid-week puzzle", 5),
                                     (4, "Quote of the day", 5)]]


def _run_keep_earning(monkeypatch, server: ScriptedServer, offers: list[Offer]):
    async def fetch_earn(page):
        return SimpleNamespace(offers=server.snapshot(offers))

    async def open_offer(page, context, offer):
        server.attempt(offer.offer_id)
        return True, "anchor-click"

    async def fetch_state(page):
        return _totals()

    monkeypatch.setattr(task_keep_earning, "_fetch_earn", fetch_earn)
    monkeypatch.setattr(task_keep_earning, "_open_offer", open_offer)
    monkeypatch.setattr(task_keep_earning, "fetch_state", fetch_state)
    return asyncio.run(task_keep_earning.run_keep_earning(None, state_page=FakePage()))


def test_keep_earning_retries_once_and_warns_on_a_second_failure(monkeypatch):
    offers = _keep_earning_offers()
    ids = [o.offer_id for o in offers]
    server = ScriptedServer({ids[0]: 1, ids[1]: 2, ids[2]: NEVER, ids[3]: 2},
                            raises_on={ids[3]: 1})

    result = _run_keep_earning(monkeypatch, server, offers)

    assert server.attempts == {ids[0]: 1, ids[1]: 2, ids[2]: 2, ids[3]: 2}
    assert result.completed == 3
    assert result.errors == [], "a failure that got its retry is never left as an error"
    assert len(result.warnings) == 1
    assert result.warnings[0].startswith(f"{ids[2]}: not marked complete after anchor-click")
    assert "nor after a retry (anchor-click)" in result.warnings[0]
    assert result.warned_points == 5


def test_keep_earning_does_not_retry_what_completed(monkeypatch):
    offers = _keep_earning_offers()
    server = ScriptedServer({o.offer_id: 1 for o in offers})

    result = _run_keep_earning(monkeypatch, server, offers)

    assert set(server.attempts.values()) == {1}
    assert (result.completed, result.warnings, result.errors) == (4, [], [])


# --------------------------------------------------------------------------- #
# Explore on Bing
# --------------------------------------------------------------------------- #

def _tiles() -> list[Offer]:
    return [Offer(offer_id=f"ENUS_{topic}_exploreonbing_activation_Evergreen", title=title,
                  description=f"Search on Bing to find {prompt}", is_completed=False,
                  raw={"isLocked": False})
            for topic, title, prompt in [("jewelry", "Shine bright", "stunning jewelry"),
                                         ("realestate", "Houses near you", "a house"),
                                         ("sports", "Who won?", "your team's score")]]


def _run_explore(monkeypatch, server: ScriptedServer, tiles: list[Offer],
                 search_points: tuple[int, int] | None):
    async def fetch_earn(page):
        return SimpleNamespace(offers=server.snapshot(tiles))

    async def work_tile(page, context, offer):
        server.attempt(offer.offer_id)
        return True, "tile-click+search"

    async def fetch_state(page):
        return _totals()

    async def fetch_search_progress(page):
        return search_points

    monkeypatch.setattr(task_explore_on_bing, "_fetch_earn", fetch_earn)
    monkeypatch.setattr(task_explore_on_bing, "_work_tile", work_tile)
    monkeypatch.setattr(task_explore_on_bing, "fetch_state", fetch_state)
    monkeypatch.setattr(task_explore_on_bing, "fetch_search_progress", fetch_search_progress)
    return asyncio.run(task_explore_on_bing.run_explore_on_bing(None, state_page=FakePage()))


def test_explore_retries_once_and_warns_on_a_second_failure(monkeypatch):
    tiles = _tiles()
    ids = [t.offer_id for t in tiles]
    server = ScriptedServer({ids[0]: 2, ids[1]: NEVER, ids[2]: 1})

    result = _run_explore(monkeypatch, server, tiles, search_points=(36, 60))

    assert server.attempts == {ids[0]: 2, ids[1]: 2, ids[2]: 1}
    assert result.completed == 2
    assert result.errors == []
    assert result.warnings == ["realestate: not marked complete after tile-click+search, "
                               "nor after a retry (tile-click+search)"]
    assert result.warned_points == 10


def test_explore_skips_a_retry_that_would_reach_the_search_quota(monkeypatch):
    tiles = _tiles()
    ids = [t.offer_id for t in tiles]
    server = ScriptedServer({ids[0]: 2, ids[1]: 1, ids[2]: 1})

    # 57 of 60 points: one search left, and a retry would spend it.
    result = _run_explore(monkeypatch, server, tiles, search_points=(57, 60))

    assert server.attempts[ids[0]] == 1, "no retry may land the day on the quota"
    assert result.warnings == ["jewelry: not marked complete after tile-click+search; "
                               "not retried, a retry would reach the daily search quota"]
    assert result.errors == []


def test_explore_does_not_retry_blind_when_the_allowance_cannot_be_read(monkeypatch):
    tiles = _tiles()
    server = ScriptedServer({tiles[0].offer_id: 2, tiles[1].offer_id: 1,
                             tiles[2].offer_id: 1})

    result = _run_explore(monkeypatch, server, tiles, search_points=None)

    assert server.attempts[tiles[0].offer_id] == 1
    assert "not retried, today's search allowance could not be read" in result.warnings[0]


def test_explore_retries_stop_while_the_allowance_still_has_one_left(monkeypatch):
    tiles = _tiles()
    server = ScriptedServer({t.offer_id: NEVER for t in tiles})

    # Two searches left: one retry fits, the next would reach the quota.
    result = _run_explore(monkeypatch, server, tiles, search_points=(54, 60))

    assert sorted(server.attempts.values()) == [1, 1, 2]
    assert len(result.warnings) == 3
    assert sum("not retried" in w for w in result.warnings) == 2


# --------------------------------------------------------------------------- #
# Daily set
# --------------------------------------------------------------------------- #

def _cards() -> list[Offer]:
    return [Offer(offer_id=f"Gamification_DailySet_ENGB_20261011_Child{n}",
                  title=f"Card {n}", points=points, is_completed=False)
            for n, points in [(1, 10), (2, 10), (3, 30), (4, 10), (5, 10)]]


def _run_daily_set(monkeypatch, server: ScriptedServer, cards: list[Offer],
                   late: frozenset[str] = frozenset()):
    """`late` items read complete on any state read after the first, as late credit does."""
    reads = {"count": 0}

    async def fetch_state(page):
        reads["count"] += 1
        offers = server.snapshot(cards)
        if reads["count"] > 1:
            offers = [replace(o, is_completed=True) if o.offer_id in late else o
                      for o in offers]
        return DashboardState(balance=1000, ready_to_claim=0, offers=offers)

    async def open_card(page, context, offer):
        server.attempt(offer.offer_id)
        return True, "anchor-click"

    async def is_complete(page, offer, day):
        return server.is_completed(offer.offer_id)

    monkeypatch.setattr(task_daily_set, "fetch_state", fetch_state)
    monkeypatch.setattr(task_daily_set, "_open_card", open_card)
    monkeypatch.setattr(task_daily_set, "_is_complete", is_complete)
    return asyncio.run(task_daily_set.run_daily_set(None, state_page=FakePage(), day=DAY))


def test_daily_set_retries_every_kind_of_failure_once_and_warns_on_the_second(monkeypatch):
    cards = _cards()[:4]
    ids = [c.offer_id for c in cards]
    server = ScriptedServer({ids[0]: 1, ids[1]: 2, ids[2]: NEVER, ids[3]: 2},
                            raises_on={ids[3]: 1})

    result = _run_daily_set(monkeypatch, server, cards)

    assert server.attempts == {ids[0]: 1, ids[1]: 2, ids[2]: 2, ids[3]: 2}
    assert result.completed == 3
    assert result.errors == []
    assert result.warnings == ["Child3: not marked complete after "
                               "anchor-click+retry:anchor-click"]
    assert result.warned_points == 30
    raised = next(r for r in result.per_card if r["slot"] == "Child4")
    assert raised["method"] == "error: the page did not load+retry:anchor-click"


def test_daily_set_late_credit_clears_the_warning(monkeypatch):
    cards = _cards()
    late_card = cards[4].offer_id
    server = ScriptedServer({c.offer_id: 1 for c in cards[:4]} | {late_card: NEVER})

    result = _run_daily_set(monkeypatch, server, cards, late=frozenset({late_card}))

    assert result.completed == 5
    assert (result.warnings, result.warned_points, result.errors) == ([], 0, [])
    assert next(r for r in result.per_card if r["offer_id"] == late_card)["late"] is True

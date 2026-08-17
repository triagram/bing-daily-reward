"""
Tests for the behavioural choices: search terms, pacing, and how many searches a day.

These are not cosmetic. Query text, timing shape and daily volume are the signals
Microsoft is documented to act on, and each of these functions exists because the
naive version of it was a signature: a fixed keyword list, a flat 6-9s gap, and
finishing exactly on the quota every day.
"""

from datetime import date

import pytest

from config import (
    DAILY_SEARCH_ALLOWANCE,
    DAILY_SEARCH_MAX,
    DAILY_SEARCH_MIN,
    POINTS_PER_SEARCH,
)
from utils import keywords
from utils.humanizer import daily_search_count, search_gap
from utils.state_reader import searches_remaining

DAY = date(2026, 8, 17)


# --------------------------------------------------------------------------- #
# Search terms
# --------------------------------------------------------------------------- #


def test_terms_are_unique_within_a_day():
    terms = keywords.generate(30, DAY)
    assert len(terms) == len(set(terms)) == 30


def test_consecutive_days_barely_overlap():
    """A list reshuffled daily still sends the same strings forever."""
    a = set(keywords.generate(20, date(2026, 9, 1)))
    b = set(keywords.generate(20, date(2026, 9, 2)))
    assert len(a & b) <= 5


def test_a_day_is_reproducible():
    """Seeded by date so a run can be replayed while debugging."""
    assert keywords.generate(12, DAY) == keywords.generate(12, DAY)


def test_refinements_match_their_topic():
    """
    An earlier version drew modifiers from one pool and produced "film noir for small
    spaces" and "sourdough bread for small spaces". Nonsensical queries are exactly
    what a low-quality-traffic check looks for, so a refinement must belong to the
    kind of thing it refines.
    """
    home_only = "for small spaces"
    for seed in range(40):
        for term in keywords.generate(25, date(2026, 1, 1) + __import__("datetime").timedelta(days=seed)):
            if home_only in term:
                subject = term.replace(home_only, "").strip()
                assert subject in keywords.TOPICS["home"], f"{term!r} applies a home modifier to {subject!r}"


def test_every_term_is_plain_text():
    for term in keywords.generate(40, DAY):
        assert term == term.strip() and "  " not in term
        assert not any(c in term for c in "{}[]<>|")


# --------------------------------------------------------------------------- #
# Pacing
# --------------------------------------------------------------------------- #


def test_gaps_are_heavy_tailed_not_uniform():
    """
    The point of the mixture is the long tail: a flat window never produces the
    occasional two-minute pause that a distracted person does.
    """
    gaps = [search_gap() for _ in range(4000)]
    assert min(gaps) >= 7.0
    assert max(gaps) <= 120.0
    long_ones = [g for g in gaps if g > 45]
    assert 0.01 < len(long_ones) / len(gaps) < 0.12, "the long tail vanished"
    median = sorted(gaps)[len(gaps) // 2]
    assert 9 < median < 25, "typical gap drifted away from a plausible skim"


# --------------------------------------------------------------------------- #
# Daily volume
# --------------------------------------------------------------------------- #


def test_count_stays_inside_its_range():
    counts = [daily_search_count(date(2026, 1, 1) + __import__("datetime").timedelta(days=i))
              for i in range(400)]
    assert min(counts) >= DAILY_SEARCH_MIN
    assert max(counts) <= DAILY_SEARCH_MAX


def test_count_never_reaches_the_allowance():
    """
    Landing exactly on the quota is a signature in itself — nobody searches until
    their allowance runs out and then stops.
    """
    counts = [daily_search_count(date(2026, 1, 1) + __import__("datetime").timedelta(days=i))
              for i in range(400)]
    assert max(counts) < DAILY_SEARCH_ALLOWANCE


def test_count_varies_between_days():
    counts = {daily_search_count(date(2026, 3, 1) + __import__("datetime").timedelta(days=i))
              for i in range(30)}
    assert len(counts) > 1, "a fixed count every day is the thing this avoids"


def test_a_day_count_is_reproducible():
    assert daily_search_count(DAY) == daily_search_count(DAY)


# --------------------------------------------------------------------------- #
# Remaining allowance
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "progress, expected",
    [((0, 60), 60 // POINTS_PER_SEARCH),
     ((45, 60), 5),
     ((60, 60), 0),
     ((58, 60), 0),      # 2 points left is not a whole search
     (None, None)],      # unreadable must not be mistaken for "none left"
)
def test_searches_remaining(progress, expected):
    assert searches_remaining(progress) == expected


# --------------------------------------------------------------------------- #
# Retry
# --------------------------------------------------------------------------- #


def test_retry_succeeds_after_transient_failures():
    import asyncio
    from utils.retry import retry_async

    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("still hydrating")
        return "ok"

    assert asyncio.run(retry_async(flaky, attempts=3, base_delay=0, what="flaky")) == "ok"
    assert calls["n"] == 3


def test_retry_raises_once_attempts_are_exhausted():
    import asyncio
    from utils.retry import retry_async

    async def always_fails():
        raise TimeoutError("gone")

    with pytest.raises(TimeoutError):
        asyncio.run(retry_async(always_fails, attempts=2, base_delay=0, what="doomed"))


def test_retry_or_none_swallows_the_failure():
    import asyncio
    from utils.retry import retry_or_none

    async def always_fails():
        raise RuntimeError("nope")

    assert asyncio.run(retry_or_none(always_fails, attempts=2, base_delay=0)) is None


def test_retry_does_not_repeat_a_success():
    """An operation that works first time must be called exactly once."""
    import asyncio
    from utils.retry import retry_async

    calls = {"n": 0}

    async def fine():
        calls["n"] += 1
        return 42

    assert asyncio.run(retry_async(fine, attempts=3, base_delay=0)) == 42
    assert calls["n"] == 1

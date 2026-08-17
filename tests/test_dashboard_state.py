"""
Tests for the dashboard parser.

The parser is the one piece everything else stands on, and the failure it is exposed
to is silent: Microsoft redeploys the dashboard, parsing yields nothing, and the bot
reports "nothing outstanding" every day until somebody notices the points stopped.
These tests turn that into a red test run instead.

Two layers:

- Against `fixtures/dashboard_min.html`, which is synthetic. It carries the shapes
  learned from real captures — a direct `?q=` destination, a `checkuser?ru=` redirect,
  a completed card, a card from the previous day, an Explore offer with no date in its
  id, a banner with no points, progress rings, and a Ready-to-claim pair — with no
  account data in it, so it can be committed and run anywhere, CI included.
- Against whatever real captures happen to be on disk, skipped when there are none.
  Synthetic fixtures verify the parser does what it was written to do; real pages are
  what catch it drifting from what Microsoft actually serves.
"""

import glob
import gzip
from datetime import date
from pathlib import Path

import pytest

from utils.dashboard_state import (
    Offer,
    extract_flight_stream,
    iter_objects_containing,
    parse_dashboard,
)

FIXTURE = Path(__file__).parent / "fixtures" / "dashboard_min.html"
TODAY = date(2026, 8, 17)
YESTERDAY = date(2026, 8, 16)


@pytest.fixture(scope="module")
def state():
    return parse_dashboard(FIXTURE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Flight stream
# --------------------------------------------------------------------------- #


def test_flight_stream_is_reassembled():
    stream = extract_flight_stream(FIXTURE.read_text(encoding="utf-8"))
    assert stream, "no flight stream recovered — __next_f extraction is broken"
    assert '"offerId"' in stream


def test_flight_stream_empty_for_a_page_without_one():
    assert extract_flight_stream("<html><body>nothing here</body></html>") == ""


def test_iter_objects_returns_the_innermost_match():
    """
    The scanner must claim each key by the tightest object enclosing it. A regex
    window straddles neighbours instead, which is how an early version paired titles
    with the wrong offer ids.
    """
    text = '{"outer":1,"wrap":{"offerId":"A","title":"a"},"other":{"offerId":"B","title":"b"}}'
    found = list(iter_objects_containing(text, "offerId"))
    assert [o["offerId"] for o in found] == ["A", "B"]
    assert all(set(o) == {"offerId", "title"} for o in found), "returned an outer wrapper"


# --------------------------------------------------------------------------- #
# Offers
# --------------------------------------------------------------------------- #


def test_offers_are_found_with_their_fields(state):
    card = next(o for o in state.offers if o.slot == "Child1" and o.day == TODAY)
    assert card.points == 10
    assert card.is_completed is False
    assert card.title == "Direct query card"


def test_offer_id_decomposes(state):
    card = next(o for o in state.offers if o.title == "Nested ru card")
    assert (card.market, card.slot, card.day) == ("ENGB", "Child2", TODAY)
    assert card.is_daily_set


def test_explore_offer_has_no_date_and_is_not_a_daily_set(state):
    offer = next(o for o in state.offers if o.title == "Explore offer")
    assert offer.is_daily_set is False
    assert offer.day is None, "Explore ids carry no date; treating one as dated would misfilter"


def test_banner_has_no_points(state):
    """Banners lead to app installs and referral flows; point value is what separates them."""
    banner = next(o for o in state.offers if o.title == "A banner")
    assert banner.points is None


@pytest.mark.parametrize(
    "title, expected",
    [("Direct query card", "Sport events near me"),   # ?q= directly
     ("Nested ru card", "Nelson mandela")],           # hidden inside ru=
)
def test_query_is_recovered_from_both_destination_shapes(state, title, expected):
    """Two of each day's three cards hide the query behind a checkuser redirect."""
    assert next(o for o in state.offers if o.title == title).query == expected


def test_query_is_none_when_there_is_no_destination():
    assert Offer(offer_id="X", destination=None).query is None


# --------------------------------------------------------------------------- #
# Day filtering
# --------------------------------------------------------------------------- #


def test_daily_set_selects_one_day_only(state):
    """The page carries several days at once; acting on the wrong one was a real bug."""
    assert {o.slot for o in state.daily_set(TODAY)} == {"Child1", "Child2", "Child3"}
    assert [o.title for o in state.daily_set(YESTERDAY)] == ["Yesterday card"]


def test_daily_set_is_ordered_by_slot(state):
    assert [o.slot for o in state.daily_set(TODAY)] == ["Child1", "Child2", "Child3"]


def test_outstanding_excludes_completed(state):
    assert {o.slot for o in state.outstanding(TODAY)} == {"Child1", "Child2"}


def test_outstanding_ignores_unknown_completion():
    """`None` means "not known", which must not be treated as "still to do"."""
    unknown = Offer(offer_id="Gamification_DailySet_ENGB_20260817_Child9", is_completed=None)
    state = parse_dashboard("")
    state.offers.append(unknown)
    assert unknown not in state.outstanding(TODAY)


# --------------------------------------------------------------------------- #
# Totals and counters
# --------------------------------------------------------------------------- #


def test_balance_and_level(state):
    assert state.balance == 12345
    assert state.level == 3


def test_ready_to_claim_is_read_from_the_rendered_tree(state):
    """It has no field of its own — only a label node followed by a heading."""
    assert state.ready_to_claim == 77


def test_total_points_sums_both_pots(state):
    assert state.total_points == 12345 + 77


def test_total_points_is_none_without_a_balance():
    assert parse_dashboard("").total_points is None


def test_counters(state):
    labels = {c["label"]: (c["value"], c["maxValue"]) for c in state.counters}
    assert labels["Bing"] == (1, 1)
    assert labels["Daily Set"] == (2, 3)


def test_markets(state):
    assert state.markets == {"ENGB"}


def test_empty_input_is_survivable():
    """A page that fails to load must not raise; it must report nothing found."""
    state = parse_dashboard("")
    assert state.offers == [] and state.balance is None


# --------------------------------------------------------------------------- #
# Real captures, when present
# --------------------------------------------------------------------------- #

REAL = sorted(glob.glob(str(Path(__file__).parent.parent / "captures" / "samples" / "dashboard-*.html.gz")))


@pytest.mark.skipif(not REAL, reason="no local captures; synthetic coverage still applies")
def test_latest_real_capture_still_parses():
    """
    Guards against drift: the synthetic fixture cannot notice Microsoft changing the
    page, because it is frozen. This runs the same parser over the newest real sample.
    """
    state = parse_dashboard(gzip.decompress(Path(REAL[-1]).read_bytes()).decode("utf-8"))
    assert state.balance is not None, "no balance in a real capture — the page shape moved"
    assert state.offers, "no offers in a real capture"
    assert state.counters, "no activity counters in a real capture"
    assert any(o.is_daily_set for o in state.offers)

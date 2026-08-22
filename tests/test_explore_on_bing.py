"""
Selecting Explore on Bing tiles.

The one manual attempt at this offer type, on 2026-08-20, was spent on a tile the
server had locked — it renders first in the section, so it looked available. Nothing
was learned and no points were earned. Everything here is about not repeating that.
"""

from utils.dashboard_state import Offer
from utils.task_explore_on_bing import (
    ExploreOnBingResult,
    outstanding_tiles,
    query_for,
    topic_of,
)


class FakeState:
    def __init__(self, offers):
        self.offers = offers


def tile(topic, *, completed=False, locked=False, disabled=None):
    """One tile in the shape captures show: no points and no title in the payload."""
    return Offer(
        offer_id=f"ENUS_{topic}_exploreonbing_activation_Evergreen",
        is_completed=completed,
        destination="https://www.bing.com/?form=ML2PCR&rwAutoFlyout=exb",
        raw={"isLocked": locked,
             "isDisabled": locked if disabled is None else disabled,
             "isCompleted": completed},
    )


# The 2026-08-20 capture: four open, four behind "Unlocks tomorrow".
OPEN = ["airlinetickets", "airportparking", "flowerdelivery", "streamingservices"]
LOCKED = ["creditreport", "health", "recipe", "videogames"]


def a_day():
    return FakeState([tile(t) for t in OPEN] + [tile(t, locked=True) for t in LOCKED])


def test_locked_tiles_are_never_attempted():
    """`creditreport` was locked and was the one tried by hand; it earned nothing."""
    picked = {topic_of(o) for o in outstanding_tiles(a_day())}
    assert picked == set(OPEN)


def test_a_disabled_tile_is_left_alone_even_if_it_is_not_locked():
    """The two fields have only been seen agreeing; disagreement is not an invitation."""
    state = FakeState([tile("airlinetickets", locked=False, disabled=True)])
    assert outstanding_tiles(state) == []


def test_completed_tiles_are_not_redone():
    state = FakeState([tile("airlinetickets", completed=True), tile("airportparking")])
    assert [topic_of(o) for o in outstanding_tiles(state)] == ["airportparking"]


def test_other_offer_families_are_not_picked_up():
    """This task must not touch what task_keep_earning does, or they will fight."""
    state = FakeState([
        tile("airlinetickets"),
        Offer(offer_id="WW_Bing_MonthlyFeaturedTopic_20260821_30",
              points=10, is_completed=False, raw={}),
        Offer(offer_id="Gamification_DailySet_ENGB_20260821_Child1",
              points=10, is_completed=False, raw={}),
    ])
    assert [topic_of(o) for o in outstanding_tiles(state)] == ["airlinetickets"]


def test_a_known_topic_becomes_a_phrase_a_person_would_type():
    assert query_for(tile("airlinetickets")) == "cheap flights"
    assert query_for(tile("flowerdelivery")) == "flower delivery"


def test_an_unknown_topic_falls_back_to_the_topic_itself():
    """
    The pool rotates, so a topic nobody has mapped yet is expected. Searching the raw
    token is a worse query than a phrase but is still on the subject, which beats
    skipping a tile that is worth ten points.
    """
    assert query_for(tile("astronomygear")) == "astronomygear"


def test_an_id_with_no_topic_yields_no_query():
    assert query_for(Offer(offer_id="nounderscores", raw={})) is None


def test_points_are_unknown_until_both_totals_are_read():
    """Same rule as every other task: never report a figure that was not observed."""
    assert ExploreOnBingResult(total_before=100).points_earned is None
    assert ExploreOnBingResult(total_before=100, total_after=140).points_earned == 40

"""
Selecting Explore on Bing tiles.

The one manual attempt at this offer type, on 2026-08-20, was spent on a tile the
server had locked — it renders first in the section, so it looked available. Nothing
was learned and no points were earned. Everything here is about not repeating that.
"""

import contextlib

from utils.dashboard_state import Offer
from utils.task_explore_on_bing import (
    ExploreOnBingResult,
    SHELVED_TOPICS,
    TOPIC_QUERIES,
    outstanding_tiles,
    query_for,
    query_from_description,
    shelved_tiles,
    topic_of,
)


class FakeState:
    def __init__(self, offers):
        self.offers = offers


def tile(topic, *, completed=False, locked=False, disabled=None,
         title=None, description=None):
    """One tile in the shape captures show: no points of its own in the payload."""
    return Offer(
        offer_id=f"ENUS_{topic}_exploreonbing_activation_Evergreen",
        is_completed=completed,
        title=title,
        description=description,
        destination="https://www.bing.com/?form=ML2PCR&rwAutoFlyout=exb",
        raw={"isLocked": locked,
             "isDisabled": locked if disabled is None else disabled,
             "isCompleted": completed},
    )


@contextlib.contextmanager
def no_override_for(topic):
    """
    The fallback tests name real topics from real captures, and the override map grows
    every time a tile fails — `dictionary` and `timezonedates` both acquired an entry on
    2026-09-05. What those tests check is the *order* query_for resolves in, so a topic
    joining the map must not turn them red.
    """
    learned = TOPIC_QUERIES.pop(topic, None)
    try:
        yield
    finally:
        if learned is not None:
            TOPIC_QUERIES[topic] = learned


@contextlib.contextmanager
def shelved(topic):
    """Same reasoning as `no_override_for`, for the other map."""
    SHELVED_TOPICS[topic] = "test"
    try:
        yield
    finally:
        SHELVED_TOPICS.pop(topic, None)


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


def test_a_shelved_topic_is_reported_but_never_attempted():
    # lyrics, 2026-09-16: four failures, then shelved. Once this task joins the daily
    # run, an unattempted tile must not read as a failed one.
    state = FakeState([tile("airlinetickets"), tile("videogames")])
    with shelved("videogames"):
        assert [topic_of(o) for o in outstanding_tiles(state)] == ["airlinetickets"]
        assert [topic_of(o) for o in shelved_tiles(state)] == ["videogames"]


def test_a_shelved_topic_that_is_locked_or_done_is_not_listed_as_shelved():
    state = FakeState([tile("videogames", locked=True), tile("recipe", completed=True)])
    with shelved("videogames"), shelved("recipe"):
        assert shelved_tiles(state) == []
        assert outstanding_tiles(state) == []


def test_every_shelved_entry_carries_a_dated_reason():
    for topic, reason in SHELVED_TOPICS.items():
        assert reason[:4].isdigit() and reason[4] == "-", (topic, reason)


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


# The prompts below are verbatim from captures/20260822-183438.


def test_the_query_comes_from_the_tiles_own_prompt():
    """
    The first run guessed from the offer id and searched `timezonedates`, which is not
    a thing anyone types. The tile said what to search all along.
    """
    t = tile("timezonedates", title="What time is it?",
             description="Search on Bing to see what time it is in a different time zone.")
    with no_override_for("timezonedates"):
        assert query_for(t) == "what time it is in a different time zone"


def test_the_instruction_is_stripped_but_the_subject_is_not():
    assert (query_from_description("Search on Bing for the latest price of a specific stock.")
            == "the latest price of a specific stock")
    assert (query_from_description("Search on Bing to find top-rated mattresses at great prices")
            == "top-rated mattresses at great prices")


def test_the_title_carries_a_tile_whose_prompt_did_not_parse():
    """`dictionary` rendered a title and no description on 2026-08-22."""
    with no_override_for("dictionary"):
        assert query_for(tile("dictionary", title="Expand your vocabulary")) == "Expand your vocabulary"


def test_a_learned_phrasing_overrides_the_prompt():
    """The map exists for wordings found to work; nothing is in it on evidence yet."""
    TOPIC_QUERIES["mattress"] = "best mattress 2026"
    try:
        t = tile("mattress", description="Search on Bing to find top-rated mattresses")
        assert query_for(t) == "best mattress 2026"
    finally:
        TOPIC_QUERIES.pop("mattress")


def test_the_topic_token_is_the_last_resort_not_the_first_guess():
    assert query_for(tile("astronomygear")) == "astronomygear"


def test_an_id_with_no_topic_and_no_text_yields_no_query():
    assert query_for(Offer(offer_id="nounderscores", raw={})) is None


def test_points_are_unknown_until_both_totals_are_read():
    """Same rule as every other task: never report a figure that was not observed."""
    assert ExploreOnBingResult(total_before=100).points_earned is None
    assert ExploreOnBingResult(total_before=100, total_after=140).points_earned == 40

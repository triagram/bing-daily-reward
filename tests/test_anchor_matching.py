"""
Anchor location, against the two shapes that broke a run on 2026-08-21.

These need a browser because the defects were in DOM matching, not in string building:
a selector that looks correct fails on real markup. Nothing here goes near the network
or the account — the page is set from a literal string — but chromium has to exist, so
the module skips rather than fails where it does not (CI installs the library, not the
browser).

Both fragments are the real thing, lifted from captures/20260821-113129.
"""

import asyncio

import pytest

from utils.humanizer import find_offer_anchor

playwright_api = pytest.importorskip("playwright.async_api")


@pytest.fixture(scope="module")
def browser():
    async def launch():
        p = await playwright_api.async_playwright().start()
        try:
            b = await p.chromium.launch(channel="chromium", args=["--no-sandbox"])
        except Exception as e:
            await p.stop()
            pytest.skip(f"no chromium available: {e}")
        return p, b

    loop = asyncio.new_event_loop()
    p, b = loop.run_until_complete(launch())
    yield loop, b
    loop.run_until_complete(b.close())
    loop.run_until_complete(p.stop())


def _match(browser, html: str, destination: str | None, query: str | None) -> str | None:
    """Return the href find_offer_anchor picks, or None."""
    loop, b = browser

    async def run():
        page = await b.new_page()
        try:
            await page.set_content(html)
            anchor = await find_offer_anchor(page, destination, query)
            return None if anchor is None else await anchor.get_attribute("href")
        finally:
            await page.close()

    return loop.run_until_complete(run())


# The daily set rendered these two side by side, with the percent-encoding in
# different cases. A selector written for q%3D silently misses the lowercase one.
MIXED_CASE = (
    '<a href="https://www.bing.com/rewards/checkuser?rabruid=0'
    '&ru=%2fsearch%3fq%3dweekly+quiz%26rnoreward%3d1">Test your smarts</a>'
    '<a href="https://www.bing.com/rewards/checkuser?rabruid=0'
    '&ru=%2Fsearch%3Fq%3Dtechnology+trends%26rnoreward%3D1">Daily poll</a>'
)

LOWER = ("https://www.bing.com/rewards/checkuser?rabruid=0"
         "&ru=%2fsearch%3fq%3dweekly+quiz%26rnoreward%3d1")


def test_lowercase_percent_encoding_still_matches(browser):
    """`Test your smarts` fell through to direct navigation and did not register."""
    assert _match(browser, MIXED_CASE, LOWER, "weekly quiz") == LOWER


def test_the_destination_wins_over_the_encoding_case(browser):
    """The payload may spell the same URL in the other case; it is still that card."""
    assert _match(browser, MIXED_CASE, LOWER.replace("%2f", "%2F").replace("%3f", "%3F")
                  .replace("%3d", "%3D"), "weekly quiz") is not None


# Two Explore offers whose queries share a first word. Reduced to the needle `How`,
# both resolved to the first card: the second reported a successful anchor-click and
# was never opened.
COLLIDING = (
    '<a href="https://www.bing.com/search?q=How+crystals+form">Crystals creation</a>'
    '<a href="https://www.bing.com/search?q=How+do+magnets+work">Magnet science</a>'
)
MAGNETS = "https://www.bing.com/search?q=How+do+magnets+work"


def test_a_shared_first_word_does_not_pick_the_wrong_card(browser):
    assert _match(browser, COLLIDING, MAGNETS, "How do magnets work") == MAGNETS


def test_an_ambiguous_needle_is_refused_rather_than_guessed(browser):
    """
    With no destination the needle is all there is, and `How` names two cards. Clicking
    either is a coin flip that reports success, which is worse than declining: the
    caller still has direct navigation, and that at least cannot open the wrong card.
    """
    assert _match(browser, COLLIDING, None, "How do magnets work") is None


def test_an_unambiguous_needle_is_still_usable(browser):
    """The fallback has to keep working for a page whose hrefs differ from the payload."""
    assert _match(browser, COLLIDING, None, "crystals form") is None, "not a q= prefix"
    single = '<a href="https://www.bing.com/search?q=Quote+of+the+day">Quote</a>'
    assert _match(browser, single, None, "Quote of the day") is not None


def test_no_destination_and_no_query_yields_nothing(browser):
    assert _match(browser, COLLIDING, None, None) is None


# --------------------------------------------------------------------------- #
# Explore on Bing tiles, which all share one URL
# --------------------------------------------------------------------------- #
#
# Measured 2026-08-23 against a live capture: seven tiles, one distinct href between
# them. Matching the destination — the right answer for every other card on the site —
# picks the same card every time, which is what made three tiles look like a broken
# mechanism when they had simply never been clicked.

from utils.dashboard_state import Offer  # noqa: E402
from utils.task_explore_on_bing import _find_tile_anchor  # noqa: E402

SHARED = "https://www.bing.com/?form=ML2PCR&rwAutoFlyout=exb"
TILES = (
    f'<a href="{SHARED}"><img alt="Save more today">'
    '<p>Save more today</p><p>Search on Bing for the latest coupon codes</p></a>'
    f'<a href="{SHARED}"><img alt="Find places to stay">'
    '<p>Find places to stay</p><p>Search on Bing for hotels</p></a>'
    f'<a href="{SHARED}"><img alt="Houses near you">'
    '<p>Houses near you</p><p>Search on Bing for real-estate</p></a>'
)


def _tile_anchor(browser, html: str, title: str | None) -> str | None:
    """Return the text of the anchor _find_tile_anchor picks, or None."""
    loop, b = browser

    async def run():
        page = await b.new_page()
        try:
            await page.set_content(html)
            offer = Offer(offer_id="ENUS_x_exploreonbing_activation_Evergreen",
                          title=title, destination=SHARED, raw={})
            anchor = await _find_tile_anchor(page, offer)
            return None if anchor is None else (await anchor.inner_text())
        finally:
            await page.close()

    return loop.run_until_complete(run())


def test_each_tile_is_found_by_its_own_title(browser):
    assert "Find places to stay" in _tile_anchor(browser, TILES, "Find places to stay")
    assert "Houses near you" in _tile_anchor(browser, TILES, "Houses near you")


def test_the_shared_href_never_decides_which_tile_is_clicked(browser):
    """
    The bug, stated as a test: with one href across every tile, a destination match
    resolves to the first card no matter which tile was asked for.
    """
    picked = _tile_anchor(browser, TILES, "Houses near you")
    assert "Save more today" not in picked, "clicked the first card instead of the asked-for one"


def test_a_tile_with_no_title_is_not_guessed_at(browser):
    assert _tile_anchor(browser, TILES, None) is None


def test_an_ambiguous_title_is_refused(browser):
    """Two cards carrying the same text is how this defect looked from outside."""
    dup = TILES + f'<a href="{SHARED}"><p>Houses near you</p></a>'
    assert _tile_anchor(browser, dup, "Houses near you") is None

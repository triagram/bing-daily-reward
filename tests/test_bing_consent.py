"""
Bing's cookie banner, as utils/bing_consent.py sees it.

The pages are literal strings shaped like the real banner (an `#bnp_container` holding
Accept, Reject and More options links, read from a fresh profile on 2026-11-18).
Nothing goes near the network or the account, but chromium has to exist, so the module
skips rather than fails where it does not.
"""

import asyncio

import pytest

from utils.bing_consent import consent_banner_shown, wait_until_answered

playwright_api = pytest.importorskip("playwright.async_api")

BANNER = ('<div id="bnp_container"><span>We use cookies</span>'
          '<a href="#">Accept</a><a href="#">Reject</a>'
          '<a id="bnp_btn_preference" href="#">More options</a></div>')
HIDDEN_BANNER = BANNER.replace('id="bnp_container"', 'id="bnp_container" style="display:none"')
NO_BANNER = "<div id='sb_form'>search</div>"
# What a person's answer does: the banner leaves the page shortly after.
BANNER_ANSWERED_SOON = BANNER + (
    "<script>setTimeout(() => document.getElementById('bnp_container').remove(), 200)"
    "</script>")
SHORT_WAIT_S = 1.0


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


def _on_page(browser, html: str, check):
    loop, b = browser

    async def run():
        page = await b.new_page()
        try:
            await page.set_content(html)
            return await check(page)
        finally:
            await page.close()

    return loop.run_until_complete(run())


def test_a_visible_banner_is_shown(browser):
    assert _on_page(browser, BANNER, consent_banner_shown) is True


def test_a_hidden_or_absent_banner_is_not_shown(browser):
    assert _on_page(browser, HIDDEN_BANNER, consent_banner_shown) is False
    assert _on_page(browser, NO_BANNER, consent_banner_shown) is False


def test_an_answer_that_removes_the_banner_counts(browser):
    answered = _on_page(browser, BANNER_ANSWERED_SOON,
                        lambda page: wait_until_answered(page, SHORT_WAIT_S))
    assert answered is True


def test_a_banner_left_alone_times_out(browser):
    answered = _on_page(browser, BANNER, lambda page: wait_until_answered(page, SHORT_WAIT_S))
    assert answered is False

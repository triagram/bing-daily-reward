"""
Tests for the daily report — the one message that carries point figures to a phone.

The constraint that matters is width: a Telegram monospace block on a phone wraps at
about thirty characters, and a wrapped aligned line is worse than no alignment. So the
table rows are held to TABLE_WIDTH here, and anything that may run long (error text,
offer ids) is checked to sit below the table on lines of its own.
"""

import copy

from utils.run_report import TABLE_WIDTH, render_report

CLEAN_RUN = {
    "at": "2026-10-05T10:02:47",
    "started_at": "2026-10-05T09:49:30",
    "date": "2026-10-05",
    "opening": {"balance": 119560, "unclaimed": 602, "total": 120162},
    "closing": {"balance": 120361, "unclaimed": 0, "total": 120361},
    "opening_total": 120162,
    "closing_total": 120361,
    "overall_delta": 199,
    "claim": {"clicked": True, "moved": 3, "error": None},
    "tasks": {
        "daily_set": {"attempted": 3, "done": 3, "points": 50, "expected": 50,
                      "verdict": "ok", "errors": [], "cards": []},
        "searches": {"attempted": 12, "done": 12, "points": 36, "expected": 36,
                     "verdict": "ok", "errors": []},
        "keep_earning": {"attempted": 5, "done": 5, "points": 61, "expected": 55,
                         "verdict": "ok", "errors": [], "offers": []},
        "explore_on_bing": {"attempted": 4, "done": 4, "points": 52, "expected": 40,
                            "verdict": "ok", "errors": [], "tiles": [], "shelved": []},
    },
}

FLAGGED_RUN = copy.deepcopy(CLEAN_RUN)
FLAGGED_RUN.update({
    "at": "2026-10-04T11:17:46", "started_at": "2026-10-04T11:06:24",
    "date": "2026-10-04", "opening_total": 120040, "closing_total": 120157,
    "overall_delta": 117,
})
FLAGGED_RUN["tasks"]["keep_earning"] = {
    "attempted": 2, "done": 1, "points": 11, "expected": 10, "verdict": "ok",
    "errors": ["ENstar_Rewards_DailyGlobalOffer_Evergreen_Sunday: "
               "not marked complete after anchor-click"],
    "offers": [
        {"offer_id": "ENstar_Rewards_DailyGlobalOffer_Evergreen_Sunday",
         "title": "Do you know the answer?", "points": 5,
         "method": "anchor-click", "confirmed": False},
        {"offer_id": "EN_Bing_moreactivities_flight_202606",
         "title": "Book Flights with Bing", "points": 5,
         "method": "anchor-click", "confirmed": True},
    ],
}


def _table_rows(text: str) -> list[str]:
    """The aligned block: from the 'Task' header to the next blank line."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Task "))
    rows = []
    for line in lines[start:]:
        if not line:
            break
        rows.append(line)
    return rows


def test_clean_day_reads_as_clean_with_times_and_duration():
    text = render_report(CLEAN_RUN)
    assert text.splitlines()[0] == "Rewards 2026-10-05 Mon"
    assert "09:49–10:02 · 13 min" in text
    assert "✓ clean" in text
    assert "⚠" not in text


def test_every_task_and_the_totals_are_in_the_table():
    rows = _table_rows(render_report(CLEAN_RUN))
    joined = "\n".join(rows)
    for label, done, points in [("Daily set", "3/3", "+50"), ("Searches", "12/12", "+36"),
                                ("Keep earning", "5/5", "+61"), ("Explore", "4/4", "+52"),
                                ("Claim (moved)", "yes", "+3")]:
        row = next(r for r in rows if r.startswith(label))
        assert row.split()[-2:] == [done, points], row
    assert "Earned" in joined and "+199" in joined
    assert "Total  120,162 → 120,361" in joined


def test_table_rows_fit_a_phone():
    for record in (CLEAN_RUN, FLAGGED_RUN):
        for row in _table_rows(render_report(record)):
            assert len(row) <= TABLE_WIDTH, row


def test_columns_line_up():
    rows = _table_rows(render_report(CLEAN_RUN))
    # Right-aligned columns: every row ends at the same width, so the last
    # characters of Done and Points sit under the header's.
    header = rows[0]
    assert all(len(r) == len(header) for r in rows if not r.startswith("Total"))


def test_flagged_day_names_the_task_the_offer_and_the_problem():
    text = render_report(FLAGGED_RUN)
    assert "⚠ keep_earning:1err" in text
    assert "⚠ Keep earning — 1 error" in text
    assert "• Do you know the answer?: not marked complete after anchor-click" in text
    assert "  (ENstar_Rewards_DailyGlobalOffer_Evergreen_Sunday)" in text


def test_long_detail_sits_below_the_table_not_in_it():
    text = render_report(FLAGGED_RUN)
    rows = _table_rows(text)
    assert not any("ENstar" in r for r in rows)
    assert text.index("ENstar_Rewards") > text.index("Total  ")


def test_an_error_without_a_known_title_is_printed_raw():
    record = copy.deepcopy(FLAGGED_RUN)
    record["tasks"]["keep_earning"]["offers"] = []
    text = render_report(record)
    assert ("• ENstar_Rewards_DailyGlobalOffer_Evergreen_Sunday: "
            "not marked complete after anchor-click") in text


def test_a_record_from_before_the_report_still_renders():
    old = copy.deepcopy(FLAGGED_RUN)
    for key in ("started_at", "opening", "closing"):
        old.pop(key)
    old["tasks"]["keep_earning"].pop("offers")
    text = render_report(old)
    assert "finished 11:17" in text
    assert "min" not in text.splitlines()[1]
    assert "⚠ keep_earning:1err" in text


def test_a_short_verdict_is_explained_and_shelved_topics_are_listed():
    record = copy.deepcopy(CLEAN_RUN)
    record["tasks"]["searches"].update({"points": 3, "verdict": "short"})
    record["tasks"]["explore_on_bing"]["shelved"] = ["lyrics"]
    text = render_report(record)
    assert "⚠ searches:short" in text
    assert "⚠ Searches — short:" in text
    assert "Shelved, not attempted: lyrics" in text


def test_idle_task_and_unreadable_total_are_shown_not_invented():
    record = copy.deepcopy(CLEAN_RUN)
    record["tasks"]["keep_earning"].update({"attempted": 0, "done": 0, "points": 0,
                                            "expected": 0, "verdict": "idle"})
    record["tasks"]["searches"]["points"] = None
    record["tasks"]["searches"]["verdict"] = "unknown"
    record["closing_total"] = None
    record["overall_delta"] = None
    text = render_report(record)
    rows = _table_rows(text)
    assert next(r for r in rows if r.startswith("Keep earning")).split()[-2:] == ["—", "0"]
    assert next(r for r in rows if r.startswith("Searches")).split()[-1] == "?"
    assert "Total unknown" in text
    assert "⚠ Searches — unknown:" in text

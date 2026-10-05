"""
The day's report, rendered from a run record for a phone screen.

`rewards_bot.py --report` prints this for a recorded day and `rewards-alert.sh report`
sends it, after every run, through the phone channels in alert.env. It is the one
message this project sends that carries point figures — by the account holder's
decision on 2026-10-05, which supersedes the earlier rule that no push does. The
failure alert still carries none.

Why the shape is what it is: Telegram shows a monospace block on a phone at roughly
thirty characters before it wraps, and it wraps rather than scrolls, so an aligned
line wider than that is torn in two. Every aligned line here stays within
`TABLE_WIDTH`, which a test holds it to. Lines that may be long — error messages,
offer ids — come after the table, one per line, where wrapping harms nothing.

ntfy renders the same text in a proportional font, so its columns come out ragged.
Known cost; the content is identical.
"""

from datetime import datetime

from utils.shortfall import assess, flags_for

# Thirty is what a phone shows of a monospace block before wrapping; this keeps a
# margin under it.
TABLE_WIDTH = 27
_LABEL_WIDTH = 13
_DONE_WIDTH = 5
_POINTS_WIDTH = 7

_TASK_LABELS = {
    "daily_set": "Daily set",
    "searches": "Searches",
    "keep_earning": "Keep earning",
    "explore_on_bing": "Explore",
}


def _label(task_name: str) -> str:
    return _TASK_LABELS.get(task_name, task_name)[:_LABEL_WIDTH]


def _points(value) -> str:
    if value is None:
        return "?"
    return f"{value:+d}" if value else "0"


def _row(label: str, done: str, points: str) -> str:
    return f"{label:<{_LABEL_WIDTH}} {done:>{_DONE_WIDTH}} {points:>{_POINTS_WIDTH}}"


def _hhmm(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M")
    except ValueError:
        return None


def _time_line(record: dict) -> str:
    started, finished = record.get("started_at"), record.get("at")
    start_hm, end_hm = _hhmm(started), _hhmm(finished)
    if start_hm and end_hm:
        minutes = round((datetime.fromisoformat(finished)
                         - datetime.fromisoformat(started)).total_seconds() / 60)
        return f"{start_hm}–{end_hm} · {minutes} min"
    if end_hm:
        return f"finished {end_hm}"
    return "time unknown"


def _title_line(record: dict) -> str:
    day = record.get("date") or "unknown date"
    try:
        weekday = datetime.fromisoformat(day).strftime("%a")
        return f"Rewards {day} {weekday}"
    except ValueError:
        return f"Rewards {day}"


def _total_line(record: dict) -> str:
    opening, closing = record.get("opening_total"), record.get("closing_total")
    if opening is None or closing is None:
        return "Total unknown"
    return f"Total  {opening:,} → {closing:,}"


def _titles_by_id(entry: dict) -> dict[str, str]:
    """Offer ids to human titles, from whatever per-item detail the task recorded."""
    out = {}
    for key in ("offers", "cards", "tiles"):
        for item in entry.get(key) or []:
            offer_id = item.get("offer_id")
            title = item.get("title") or item.get("topic")
            if offer_id and title:
                out[offer_id] = title
    return out


def _error_lines(task_name: str, entry: dict) -> list[str]:
    errors = entry.get("errors") or []
    if not errors:
        return []
    titles = _titles_by_id(entry)
    noun = "error" if len(errors) == 1 else "errors"
    lines = [f"⚠ {_TASK_LABELS.get(task_name, task_name)} — {len(errors)} {noun}"]
    for raw in errors:
        offer_id, sep, message = raw.partition(": ")
        if sep and offer_id in titles:
            lines.append(f"• {titles[offer_id]}: {message}")
            lines.append(f"  ({offer_id})")
        else:
            lines.append(f"• {raw}")
    return lines


def _verdict_lines(task_name: str, entry: dict) -> list[str]:
    if entry.get("verdict") not in ("zero", "short", "unknown"):
        return []
    shortfall = assess(entry.get("expected") or 0, entry.get("points"),
                       entry.get("attempted") or 0)
    return [f"⚠ {_TASK_LABELS.get(task_name, task_name)} — {shortfall.verdict.value}: "
            f"{shortfall.message}"]


def render_report(record: dict) -> str:
    """Plain text; the sender decides how to wrap it for each channel."""
    tasks = record.get("tasks") or {}
    flags = flags_for(tasks)

    lines = [_title_line(record), _time_line(record)]
    lines.append("✓ clean" if not flags else f"⚠ {' '.join(flags)}")
    lines.append("")

    lines.append(_row("Task", "Done", "Points"))
    for name, entry in tasks.items():
        attempted = entry.get("attempted") or 0
        done = f"{entry.get('done')}/{attempted}" if attempted else "—"
        lines.append(_row(_label(name), done, _points(entry.get("points"))))
    claim = record.get("claim")
    if claim:
        lines.append(_row("Claim (moved)", "yes" if claim.get("clicked") else "—",
                          _points(claim.get("moved"))))
    lines.append(_row("Earned", "", _points(record.get("overall_delta"))))
    lines.append(_total_line(record))

    detail = []
    for name, entry in tasks.items():
        detail += _verdict_lines(name, entry)
        detail += _error_lines(name, entry)
        shelved = entry.get("shelved") or []
        if shelved:
            detail.append(f"Shelved, not attempted: {', '.join(shelved)}")
    if claim and claim.get("error"):
        detail.append(f"⚠ Claim — {claim['error']}")
    if detail:
        lines.append("")
        lines += detail

    return "\n".join(lines)

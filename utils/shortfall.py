"""
Judge whether a run fell short, and say so loudly.

A broken run is silent by default: it completes, prints `0/3 confirmed, +0 points`,
and exits zero. Nothing distinguishes that from a day with nothing to do. The two
causes that matter — a selector breaking after a Microsoft redesign, and the account
being restricted — produce exactly that output, and both are worth knowing about the
same day rather than a week later.

The comparison is against what the run *could* have earned: the point values the page
itself advertised for the work it set out to do. That number is available for free,
since every task already reads the offers before touching them.
"""

from dataclasses import dataclass
from enum import Enum


class Verdict(str, Enum):
    OK = "ok"                  # earned what the work was worth
    NOTHING_TO_DO = "idle"     # nothing was outstanding; not a failure
    SHORT = "short"            # earned something, but well under
    ZERO = "zero"              # attempted real work and earned nothing
    UNKNOWN = "unknown"        # totals unreadable; cannot judge either way


@dataclass
class Shortfall:
    verdict: Verdict
    expected: int
    measured: int | None
    message: str

    @property
    def is_problem(self) -> bool:
        return self.verdict in (Verdict.ZERO, Verdict.SHORT, Verdict.UNKNOWN)


def assess(expected: int, measured: int | None, attempted: int,
           tolerance: float = 0.6) -> Shortfall:
    """
    Compare what a run earned against what it set out to earn.

    `tolerance` is the fraction of the advertised value below which a run counts as
    short. It is loose on purpose: measured totals do not always match the advertised
    ones — an Explore run on 2026-08-17 measured 50 against 40 advertised — so a tight
    threshold would cry wolf. What this is for is catching the difference between
    "roughly worked" and "earned nothing", not auditing individual point values.

    `measured is None` is reported as UNKNOWN rather than treated as zero. Being
    unable to read the total is its own failure, and a different one.
    """
    if attempted == 0:
        return Shortfall(Verdict.NOTHING_TO_DO, expected, measured,
                         "nothing was outstanding")

    if measured is None:
        return Shortfall(
            Verdict.UNKNOWN, expected, None,
            f"attempted {attempted} item(s) worth {expected} pts, but the point total "
            "could not be read — the run cannot say whether it worked",
        )

    if measured <= 0:
        return Shortfall(
            Verdict.ZERO, expected, measured,
            f"attempted {attempted} item(s) worth {expected} pts and earned nothing. "
            "That is what both a broken selector and a restricted account look like",
        )

    if expected and measured < expected * tolerance:
        return Shortfall(
            Verdict.SHORT, expected, measured,
            f"earned {measured} pts against {expected} advertised across "
            f"{attempted} item(s)",
        )

    return Shortfall(Verdict.OK, expected, measured,
                     f"earned {measured} pts against {expected} advertised")


def flags_for(tasks: dict) -> list[str]:
    """
    Why a recorded run is not clean — one entry per task, empty when it is.

    This is the observation window's exit criterion, and the one judgement the
    project makes about a day: a task is clean when its verdict is not zero / short /
    unknown, it recorded no errors, and it did everything it attempted. Errors flag on
    their own, not only through the verdict: the 2026-08-19 run failed a card outright
    and still assessed `ok`, because 20 of an advertised 30 clears the tolerance. The
    tolerance is right — advertised values are a guide — but a run carrying an error is
    never clean, whatever it earned.

    `--history` prints these; a scheduled run turns a non-empty list into its exit
    code. Both read this function so the two can never drift apart.
    """
    flags = []
    for name, task in tasks.items():
        verdict = task.get("verdict")
        if verdict in ("zero", "short", "unknown"):
            flags.append(f"{name}:{verdict}")
        elif task.get("errors"):
            flags.append(f"{name}:{len(task['errors'])}err")
        elif task.get("done") is not None and task.get("done") != task.get("attempted"):
            flags.append(f"{name}:{task['done']}/{task['attempted']}")
    return flags

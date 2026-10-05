# Design

Why the project is built the way it is. Stable: this changes when a design decision
changes, not when the code does. Where a number came from is in
[DEVELOP.md](DEVELOP.md), the lab notebook; the routine is in the
[README](../README.md).

## Goal

Do the daily Microsoft Rewards tasks the way a person would, every day, and know —
not assume — whether they were done. The second half is the whole project: a bot that
cannot tell success from silent failure is worse than none, because it removes the
person who would have noticed.

## Shape

`rewards_bot.py` only orchestrates: launch the persistent browser, check the session,
run four tasks in sequence — each in its own `try`/`except`, so one failure does not
abort the rest — then collect the "Ready to claim" pot, print the measured table, and
record the run.

Each `utils/task_*.py` owns exactly one Rewards activity and knows nothing about the
others. `utils/humanizer.py` is the shared toolbox. A task returns a structured result
(attempted, completed, measured points, errors); nothing is inferred from a log line.

| Task | What it does |
|---|---|
| Daily set | Today's three cards, each opened, worked, and confirmed by its own completion flag |
| Searches | A number of queries typed into the search box, paced, measured against the balance |
| Keep earning | The point-bearing offers still outstanding, each confirmed individually |
| Explore on Bing | The unlocked tiles: click to *activate*, then search the topic inside what opens |

## Principles

**Measure; never assert.** State is read before and after; every item is confirmed by
re-reading its own `isCompleted`, so what does not flip is reported failed rather than
counted done. No point figure is printed that was not observed — where a total cannot
be read the run says "unknown", which is its own failure. The number compared is
**balance plus unclaimed**, because earnings land in the "Ready to claim" pot as often
as in the balance, and a balance-only comparison reads zero for a run that did earn.

**Read the page's own state, not the DOM.** The dashboard ships its data inside the
HTML as a React flight stream. `utils/dashboard_state.py` parses it into offers and
counters as a pure function — no browser, no network — so it is developed and tested
against archived pages; `utils/state_reader.py` feeds it from a live page. Selectors
anchor on URL signatures, which survive redesigns, and fall back to CSS classes only
when nothing else matches.

**Persistent profile, not stored credentials.** The browser owns the cookie lifecycle
in `browser_session/`; there is deliberately no credential-handling code. Signing in is
a person's job (`--login`); a scheduled run that meets the sign-in page exits with a
code that says so instead of waiting on a prompt.

**Queries are typed.** Loading a search URL directly is not credited at all; typing
into the search box is. Every search in this project is typed, and the fallback that
navigated to an offer's destination has never completed anything — the credit comes
from the click on the Rewards card, not from visiting where it points.

**Fewer than the allowance, and not the same number twice.** The day's search count is
drawn from a range short of the measured allowance and trimmed by what the day has
already used, so the run never lands exactly on the quota — a signature in itself, as is
a fixed count. Streaks do not depend on volume: one search satisfies the daily gate.
Gaps between searches come from a heavy-tailed mixture, not a flat window; pacing is
also functional, since queries that arrive too fast are not counted.

**New tabs are captured by set difference.** Activities open new tabs.
`execute_action_and_cleanup_new_tab()` snapshots the context's pages before an action
and diffs after, bundling open → interact → linger → close into one call.

**One judgement about a day.** `flags_for()` decides whether a recorded run is clean —
no bad verdict, no recorded error, everything attempted done — and both `--history`
and the scheduled run's exit code read it, so the two cannot drift apart.

## Unattended operation

- A user timer fires at a fixed morning hour plus a random delay of up to three hours,
  and is persistent, so a day the machine was off is caught up at boot.
- The bot opens a real window, which needs the desktop session; the user manager
  lingers for the monitor's sake, so the service runs through a wrapper that waits for
  the session's display (re-read each minute — a fresh login re-imports it) and gives up
  with its own exit code after the window.
- The bot and the read-only monitor share one browser profile. The monitor skips a
  sample while the bot holds it; the bot waits for the monitor, which holds it for
  seconds.
- Exit codes carry the outcome: 0 clean, 1 crashed, 2 ran with flags, 3 sign-in
  required, 4 profile busy, 5 no desktop session. `OnFailure=` hands the code to one
  alert script, which words it and sends it — a desktop notification always, a phone
  push when configured, never a point figure. An evening timer covers the case no
  failure can report: a run that never started.
- The day's report is the one message that does carry figures, by the account
  holder's decision on 2026-10-05. `ExecStopPost=` sends it through the same script
  after every run, to the phone channels only, rendered from the run just recorded:
  times, per-task done and points, the totals, and every error in full with the task
  and the offer it belongs to. It is shaped for a phone — aligned lines under thirty
  characters, long detail below them — and on a flagged day it replaces the phone
  copy of the failure sentence, so a day is one push either way.
- Nothing runs twice on purpose. A second run on a clean day would add a second burst
  of searches and leave the day four short of the quota, so the routine is one run,
  and the retry tools are for a failed day.

## Ruled out

- **Multi-account and VPN/proxy.** The most frequently cited causes of suspension in
  the community's own reports, ahead of search rate; every signal anyone names is
  behavioural. These are the two behaviours this project can simply not have, so
  nothing here makes either easy.
- **Headless mode.** Launches, undetectability unproven, and unnecessary: the scheduled
  run has a desktop session.
- **Stealth patches.** No source claims the dashboard fingerprints the browser, and a
  new variable on a baseline that has proved boring is a cost with no measured need.

## Deferred

A wider inter-search gap, an occasional click on a result, and the unexplored `Edge`
counter — one at a time, after a clean week under the timer. See
[notes/roadmap.md](../notes/roadmap.md).

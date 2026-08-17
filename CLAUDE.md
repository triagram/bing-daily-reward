# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                              # create .venv and install deps
uv run playwright install chromium   # download the browser — separate step, easy to miss

uv run python monitor.py             # read-only state sample, appends to logs/state_samples.jsonl
uv run python monitor.py --history   # what has been collected so far
uv run python recon.py               # read-only deep capture: screenshots, DOM, network log
```

> `rewards_bot.py` is **not** the way to run anything right now. It is untouched since
> the initial commit and still calls the original Daily Set and Explore code, which
> guesses at selectors, has no date filter, and swallows its errors. It also discards
> the `SearchResult` it gets back, so nothing records what a run earned. Drive `run_daily_searches()` directly until the
> orchestration layer is rewritten.

Diagnostics from the original version, kept for selector archaeology:

```bash
uv run python scientific_diagnostics.py   # dump points/task states/claim buttons → diagnostics_report.json
uv run python step_by_step_debugger.py    # interactive walkthrough, pauses and highlights at each step
uv run python debug_task1.py              # screenshot dashboard, list every Daily set card found
```

There are no tests, no linter and no CI. "Verifying a change" here means either running a
diagnostic script, or a real run against a live Microsoft account — see below.

Long experiments must run in the background: a foreground command is capped at ten
minutes, and a run that exceeds it is killed. That is how the first attempt at
measuring the search allowance was lost.

## Committing and pushing

Commit freely as work is verified; **push only at milestones**. The user asked for this
explicitly, so that commits stay rewritable — squashable, re-wordable — until a piece of
work is actually finished.

Commit when a change is self-contained, **verified**, and describable in one sentence
without "and". Verification is the real gate: `recon.py` sat uncommitted for two days
until the parser proved it earned its place. Findings count as changes worth committing —
an experiment result that is not written down is lost.

A milestone is an open question resolved, a task module rewritten and verified, or a
release tagged. Also push before the user steps away, so nothing of theirs exists only on
this disk. If they say "push", push.

Messages: Conventional Commits prefix, imperative summary, then a body explaining *why*
and what evidence supports it — not a restatement of the diff.

## Running the bot is not a free action

`rewards_bot.py` drives a real browser against the user's real Microsoft Rewards account,
which holds a real point balance and is subject to Microsoft's anti-automation enforcement.
Do not launch it casually to "check something" — reach for `scientific_diagnostics.py`
first, and ask before doing a full run.

`HEADLESS = False` in `config.py` is the working default. Headless mode launches but has
never been validated against Microsoft's detection.

## Architecture

`rewards_bot.py` only orchestrates: launch persistent browser → check login → run three
tasks in sequence, each in its own `try`/`except` so one failure does not abort the rest.
Each `utils/task_*.py` owns exactly one Rewards activity and knows nothing about the
others, so a fourth task is additive. `utils/humanizer.py` is the shared toolbox all tasks
draw on.

Three design decisions worth knowing before editing:

**Persistent profile, not stored credentials.** `launch_persistent_context()` points at
`browser_session/`; Chromium owns the cookie lifecycle. There is deliberately no
credential-handling code in this project. First run blocks on `input()` waiting for a
manual sign-in, which is why unattended scheduling is not yet possible.

**Selectors anchor on URL signatures, not CSS classes.** The Rewards dashboard uses
utility-first CSS (`bg-bgCardOnPrimaryDefaultRest`), which churns. `locate_daily_set_individual_cards()`
in `utils/task_daily_set.py` matches `BTDSUOID`, `filters=BTEPOKey`, `REWARDSQUIZ` instead,
falling back to class matching only when that finds nothing. Preserve this ordering when
fixing broken selectors.

**New tabs are captured by set difference.** Rewards activities open new tabs.
`execute_action_and_cleanup_new_tab()` snapshots `context.pages` before an action and
diffs after, rather than awaiting a `page` event. It bundles open → interact → linger →
close into one call; use it rather than hand-rolling tab handling.

## Measure; never assert

Searches are closed-loop: `run_daily_searches()` reads the point total before and after
and returns a `SearchResult` carrying the observed delta. **The two remaining tasks are
not.** `task_explore.py` still logs `(+10 pts)` whenever a click did not raise, and
`task_daily_set.py` is the same shape — neither has been touched since the initial commit,
and between them they hold about a dozen `except Exception: pass` blocks that make a
broken selector indistinguishable from a completed task.

Treat any point figure from those two as fiction. Do not cite them as evidence a change
worked, and do not add more of them.

Measure **balance + unclaimed**, never the balance alone: earnings land in the "Ready to
claim" pot as often as in the balance, so a balance-only comparison reads zero for a run
that did earn. `DashboardState.total_points` is the number to compare.

What made this tractable was reading the dashboard's own state rather than inferring it.
`utils/dashboard_state.py` parses the React flight stream embedded in the page HTML into
offers (id, points, `isCompleted`, date) and counters. It is a pure function — no browser,
no network — so it can be developed against archived pages; `utils/state_reader.py` is the
thin layer that feeds it from a live page. Prefer it over any DOM scraping.

Known related bug: `run_daily_set_streak()` collects card locators once and reuses them
across page navigations, so cards #2 and #3 can resolve to the wrong element after the DOM
updates. Re-query inside the loop; identify cards by offer id, not index — and note the
page carries several days of offers at once, so filter by date.

**The "Daily Set" activity ring shows *yesterday's* completions, not today's** (Q2,
resolved 2026-08-17). Gate work on `isCompleted` on the cards and nothing else — reading
the ring as today's progress skips every task on any day following a completed one.

## Constraints that look like waste but are not

- **Queries must be typed into the search box.** Loading `bing.com/search?q=…` is not
  credited at all — measured 2026-08-14, six navigated queries earned nothing and did not
  move the daily search gate, while three typed ones earned 3 points each within seconds.
  `_search_once()` always types; do not "optimise" it back to navigation.
- **The allowance is 20 searches at 3 points** on this UK account (measured 2026-08-16;
  21-23 earned nothing), but the bot runs **8-15**, drawn per day by
  `daily_search_count()`. Landing exactly on the quota daily is a signature, and so is a
  fixed count. Do not "fix" this back to the maximum — the shortfall is deliberate, and
  streaks do not depend on it since one search satisfies the daily gate.
- **Inter-search gaps come from a heavy-tailed mixture** in `search_gap()` (median ~15 s,
  mean ~21 s), not the flat 6–9 s window `config.py` still describes. Real gaps are not
  uniform, and pacing is also a functional requirement: queries arriving too fast are not
  counted.
- **`playwright` is pinned to `==1.61.0`.** Each release expects a matching Chromium
  build; bumping it without re-running `playwright install chromium` breaks every run with
  a "just installed or updated" message. Do not upgrade it as a drive-by.
- **`handle_quiz_or_poll_on_page()` clicks the first option, not the correct one.** It is
  a known stub, not a bug to be surprised by. Polls need exactly one click and return
  early; quizzes loop.

## Never commit `browser_session/`

It is a live Chromium profile holding Microsoft session cookies (`_U`, `WLSSC`,
`MSPAuth`). On Linux these are encrypted with a hardcoded key, so anyone with the
directory can read them. It was committed once and had to be stripped from history; it is
now in `.gitignore` alongside `diagnostics_report.json` (which leaks the point balance),
`debug_*.png` and `logs/`. Keep it that way, and never `git add -f` it.

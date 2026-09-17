# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Where to pick up

**The observation window closed on 2026-09-16 at 14 of 14, and the routine has not
changed.** All four tasks are rewritten, verified against a live account and covered by
tests; the daily run has been proved boring. Two commands are still run by hand each day
— `rewards_bot.py`, then `explore_on_bing.py` — for a further period of clean runs by
decision, and nothing else should start without being asked. Folding the second into the
first (half of v1.0.0) waits for that period. The `lyrics` tile is shelved, not open.

Read in this order: **`docs/OBSERVATION.md` first** — it carries the window's status, its
freeze list and every loose end still open — then this file for the rules that must not
be broken, `docs/DEVELOP.md` for what the dashboard actually returns and which questions
are settled, `README.md` for how to run it. Between them they carry everything; do not
re-derive findings by experimenting on the account.

Deferred by decision, not oversight: the Edge counter (Q8) and packaging. Unattended
scheduling is **built and switched off** — `contrib/systemd/` carries the units, and
nothing is installed or enabled until 2026-09-23 (see `docs/OBSERVATION.md`, *After the
window*). CI is written but manual-only until the suite has been stable a while.

**Never, by decision on 2026-09-16: multi-account, and running through a VPN or proxy.**
Not deferred — ruled out. A survey of suspension reports (script maintainers' own issue
trackers and Microsoft Q&A, 2023-2026) names those two as the most frequently cited
causes, ahead of search rate; every ban signal anyone names is behavioural, and these
are the two behaviours this project can simply not have. Do not add a `profiles/`
directory, a proxy setting, or anything that makes either easy.

The window carries a freeze list of its own, time-boxed and distinct from the permanent
deferrals above. Probing Q8 is on it: it is the obvious next thing to reach for, and
doing it mid-window contaminates the baseline being established.

## Commands

```bash
uv sync                              # create .venv and install deps
uv run playwright install chromium   # download the browser — separate step, easy to miss

uv run python rewards_bot.py             # run today's tasks
uv run python rewards_bot.py --dry-run   # read state and report, change nothing
uv run python rewards_bot.py --history   # what past runs earned, per task
uv run python rewards_bot.py --login     # sign in by hand; confirms the session works

uv run python explore_on_bing.py             # the Explore on Bing tiles, until the switch is on
uv run python explore_on_bing.py --dry-run   # which tiles are open today, and what it would search

uv run python monitor.py             # read-only state sample, appends to logs/state_samples.jsonl
uv run python monitor.py --history   # what has been collected so far
uv run python recon.py               # read-only deep capture: screenshots, DOM, network log

uv run pytest -q                     # the offline suite; no browser, no account
```

> `rewards_bot.py` is the entry point again (repaired in 4f24d89). It reads dashboard
> state up front and runs only what is outstanding, each task returning a structured
> result; the run ends with a table of measured deltas, a warning for any task that
> earned less than the work was worth, and a line appended to `logs/runs.jsonl`.
> `--dry-run` reads state and reports without touching anything — reach for it rather
> than driving the task functions by hand.

Pre-rewrite DOM-scraping diagnostics now live in `legacy/`, kept for selector
archaeology after a redesign. They must be run as modules from the repository root —
they `from config import …`, and a file-path invocation puts `legacy/` on `sys.path`
instead of the root, so the import fails. See `legacy/README.md`.

```bash
uv run python -m legacy.scientific_diagnostics   # points/task states/claim buttons → diagnostics_report.json
uv run python -m legacy.step_by_step_debugger    # interactive walkthrough, pauses at each step
uv run python -m legacy.debug_task1              # screenshot dashboard, list every Daily set card found
```

`uv run pytest -q` runs the suite (87 tests, ~1 s). It parses a synthetic fixture and
never opens a browser or touches the account, so it is free to run — and proves nothing
about a live run. There is no linter. CI (`.github/workflows/tests.yml`) runs the same
suite on a clean machine, but is `workflow_dispatch` only on purpose; enable its `push:`
trigger once the suite has been stable a while.

So "verifying a change" splits in two: anything in `dashboard_state.py` and the
behavioural helpers is verifiable offline by test, while anything that touches the live
dashboard still needs a diagnostic script or a real run — see below.

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
Do not launch it casually to "check something" — `uv run python rewards_bot.py --dry-run`
reads the state and changes nothing, and is the cheap first reach. Ask before doing a
full run.

`HEADLESS = False` in `config.py` is the working default. Headless mode launches but has
never been validated against Microsoft's detection.

## Architecture

`rewards_bot.py` only orchestrates: launch persistent browser → check login → run three
tasks in sequence, each in its own `try`/`except` so one failure does not abort the rest.

`utils/task_explore_on_bing.py` is a fourth task, in that sequence **only when
`RUN_EXPLORE_ON_BING` in `config.py` is on** — after keep-earning, before the claim, with
its four typed searches reserved out of the search allowance. It is off until the
post-window test period ends (2026-09-23); until then run it after the daily run, from
`explore_on_bing.py`, which stays as the retry and dry-run tool afterwards.

Its mechanism is settled — click the tile to *activate* it, then search its topic inside
what it opens, typed and without navigating away. What is not settled is the query for
every topic: the tile's own prompt usually works, a few topics need an entity Bing cannot
supply for itself, and an unlearned one fails once before it can be added. That failure
must not land in the Flags column the observation window reads, which is the whole reason
this task sits outside the daily run. Merging it back is three lines and is half of what
v1.0.0 means — see `docs/OBSERVATION.md`.

Task 2 is `utils/task_keep_earning.py`, renamed from `task_explore.py` on 2026-08-22.
The page has a section headed **"Explore on Bing"** that this task does not do and cannot
complete as written; the old name made `docs/DEVELOP.md` claim it was covered for two
days, and made a clean run read as a failure. Do not reintroduce "explore" as a name for
this task. `runs.jsonl` records written before the rename use the old key and are
remapped on read.
Each `utils/task_*.py` owns exactly one Rewards activity and knows nothing about the
others, so a fourth task is additive. `utils/humanizer.py` is the shared toolbox all tasks
draw on.

Three design decisions worth knowing before editing:

**Persistent profile, not stored credentials.** `launch_persistent_context()` points at
`browser_session/`; Chromium owns the cookie lifecycle. There is deliberately no
credential-handling code in this project. Signing in is done by a person, through
`--login`; a run that meets the sign-in page with no terminal attached exits with code 3
and records nothing, so a scheduled run can never wait on an `input()` nobody will answer.

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

All three tasks are closed-loop, and each confirms items **individually**: after working
a card or offer, state is re-read and that item's own `isCompleted` is checked, so
anything that does not flip is reported failed rather than counted as done. Preserve that
rule in anything new — it has caught real failures twice, including a claim
implementation that clicked the right tile and moved nothing.

Do not reintroduce a point figure that was not observed.

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
  21-23 earned nothing), but the bot runs **8-12**, drawn per day by
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

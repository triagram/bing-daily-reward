# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                              # create .venv and install deps
uv run playwright install chromium   # download the browser — separate step, easy to miss
uv run python rewards_bot.py         # full run: Daily set → Explore → 20 searches (~4-6 min)
```

Diagnostics (development tools, not part of the daily flow):

```bash
uv run python scientific_diagnostics.py   # dump points/task states/claim buttons → diagnostics_report.json
uv run python step_by_step_debugger.py    # interactive walkthrough, pauses and highlights at each step
uv run python debug_task1.py              # screenshot dashboard, list every Daily set card found
```

There are no tests, no linter and no CI. "Verifying a change" here means either running a
diagnostic script, or a real run against a live Microsoft account — see below.

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

## The central defect: success is asserted, not measured

**The point totals in the logs are fabricated.** `task_searches.py` increments a counter
and logs `✓ Search [n/20] completed (+3 pts)` whenever `page.goto()` merely failed to
throw; `task_explore.py` logs `(+10 pts)` the same way. Neither ever reads the account's
balance. A run blocked by a captcha, a spent quota, or bot detection still prints
`✅ Completed 20/20 (~60 points earned)`.

Compounding it, roughly a dozen `except Exception: pass` / `logger.debug(...)` blocks
across `utils/` swallow failures, so a broken selector is indistinguishable from a
completed task.

Treat any log line claiming points as unverified. Do not cite them as evidence a change
worked, and do not add more of them. The agreed next engineering step is closing this
loop: promote `extract_points()` out of `scientific_diagnostics.py` into `utils/`, capture
the balance before and after each task, and have tasks return structured results
(attempted / succeeded / point delta / errors) instead of only logging. Everything else on
the README roadmap is unverifiable until that lands.

Known related bug: `run_daily_set_streak()` collects card locators once and reuses them
across page navigations, so cards #2 and #3 can resolve to the wrong element after the DOM
updates. Re-query inside the loop; identify cards by URL or text, not index.

## Constraints that look like waste but are not

- **The 6–9 s gap between searches** (`MIN/MAX_DELAY_BETWEEN_SEARCHES`) is a functional
  requirement — Microsoft's counter ignores searches that arrive faster. Shortening it
  costs points. It is not padding to be optimised away.
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

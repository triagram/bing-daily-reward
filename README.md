# Bing Daily Reward Automation

> An automated agent for Microsoft Bing Rewards daily tasks, built with Python, Playwright and uv.

> [!NOTE]
> **All three tasks are measured.** Verified on 2026-08-17: 3/3 daily-set cards
> (+50), 15/15 searches (+45), 4/4 Explore offers (+50), and 121 points collected
> from the "Ready to claim" pot. Every task confirms each item individually by
> re-reading its `isCompleted` rather than trusting the click, and every figure
> reported is observed — where a total cannot be read it says so.
>
> Working notes, the reverse-engineered data contract, and the list of unsettled
> questions live in [docs/DEVELOP.md](docs/DEVELOP.md).

---

## Table of Contents

- [Overview](#overview)
- [Directory Structure](#directory-structure)
- [Architecture & Design](#architecture--design)
- [Tasks & Features](#tasks--features)
- [Environment & Installation](#environment--installation)
- [Usage & Execution](#usage--execution)
- [Logging & Diagnostics](#logging--diagnostics)
- [Current Limitations](#current-limitations)
- [Roadmap](#roadmap)
- [Disclaimer](#disclaimer)
- [License](#license)

---

## Overview

Microsoft Rewards grants points for a handful of repetitive daily actions:
completing the three "Daily set" cards, working through the "Explore on Bing"
activities, and running a number of Bing searches. Done by hand this is a few
minutes of clicking every day, which is exactly the shape of task worth handing
to a script.

This project drives a real Chromium browser through those tasks with
[Playwright](https://playwright.dev/python/), reusing a persistent browser
profile so you only sign in to your Microsoft account once.

**Project status: early skeleton (v0.1.0).** The three task flows are
implemented and the bot completes a full run without crashing. What it does
*not* have yet is any way to confirm the run worked — see
[Current Limitations](#current-limitations). Treat this version as a foundation
to build on rather than something to leave unattended.

---

## Directory Structure

```
bing-daily-reward/
├── rewards_bot.py              # Entry point — launches the browser, runs the three tasks in order
├── config.py                   # All tunable constants: URLs, delays, search count, headless flag
├── utils/
│   ├── humanizer.py            # Shared browser primitives: random delays, typing, modal dismissal,
│   │                           #   new-tab capture/cleanup, quiz & poll interaction
│   ├── task_daily_set.py       # Task 1 — the three "Daily set" cards, plus point claiming
│   ├── task_explore.py         # Task 2 — the "Explore on Bing" activity cards
│   ├── task_searches.py        # Task 3 — N Bing searches, closed-loop measured
│   ├── dashboard_state.py      # Pure parser: dashboard HTML → structured offers & counters
│   ├── state_reader.py         # Thin layer that feeds the parser from a live page
│   └── keywords.py             # Date-seeded search-term generation
│
├── monitor.py                  # Read-only daily sampler — records state, diffs against last run
├── recon.py                    # Read-only deep capture — screenshots, DOM, network log
│
├── docs/DEVELOP.md             # Data contract, open questions, tooling notes
├── scientific_diagnostics.py   # Diagnostic — dumps points, task states and claim buttons to JSON
├── step_by_step_debugger.py    # Diagnostic — interactive walkthrough, pauses at each step
├── debug_task1.py              # Diagnostic — screenshots the dashboard and scans for Daily set cards
│
├── browser_session/            # Persistent Chromium profile (git-ignored — see the note below)
├── pyproject.toml              # Dependencies
├── uv.lock                     # Exact resolved versions, committed for reproducible installs
└── LICENSE                     # MIT
```

> [!CAUTION]
> **`browser_session/` must never be committed.** It is a live Chromium profile
> containing your Microsoft account session cookies, which on Linux are stored
> with a hardcoded encryption key and are therefore trivially readable by anyone
> who obtains the directory. It is listed in `.gitignore`; keep it that way.

---

## Architecture & Design

**One task per module, one shared toolbox.** `rewards_bot.py` only orchestrates:
it launches the browser, checks the login state, then calls each task in turn
inside its own `try`/`except` so that one failing task does not abort the rest.
Each `utils/task_*.py` module owns one Rewards activity and knows nothing about
the others, so a fourth task can be added without touching existing code.

**Persistent profile instead of stored cookies.** The bot uses Playwright's
`launch_persistent_context()` pointed at `browser_session/`. Chromium manages
its own cookie lifecycle there, so a single interactive sign-in keeps working
across runs and there is no credential handling code in this project at all.

**Selectors anchored on URL signatures, not CSS classes.** The Rewards dashboard
is built with utility-first CSS, so class names like
`bg-bgCardOnPrimaryDefaultRest` change without warning. Where possible the bot
locates cards by stable URL parameters instead — `BTDSUOID`, `filters=BTEPOKey`,
`REWARDSQUIZ` — and falls back to class-based matching only when that finds
nothing. See `locate_daily_set_individual_cards()` in `utils/task_daily_set.py`.

**New tabs are captured by set difference.** Rewards activities open in new
tabs. `execute_action_and_cleanup_new_tab()` in `utils/humanizer.py` snapshots
`context.pages` before an action and diffs afterwards, which is more reliable
than waiting on a `page` event. It bundles the whole
open → interact → linger → close cycle into one reusable call.

**State is read, not inferred.** The dashboard is a Next.js app that makes no
data request of its own: its state ships inside the HTML as a React flight
stream. `utils/dashboard_state.py` parses that stream, so the task list, each
task's point value and its completion flag are read from the same data the page
draws from, rather than guessed at from CSS classes. It is a pure function of the
HTML, which lets it be tested offline against an archived page.

**Searches are measured, not assumed.** `run_daily_searches()` reads the point
total before and after and reports the observed difference. The total is balance
*plus* unclaimed points, because earnings can land in either — a run measured on
the balance alone can read zero for a run that did earn. If the totals cannot be
read it says the result is unknown instead of claiming success.

**Queries are typed, never navigated.** Issuing a search by loading
`bing.com/search?q=…` is not credited by Rewards at all: measured on 2026-08-14,
six navigated queries earned nothing and did not move the account's daily search
gate, while three typed into the search box earned 3 points each within seconds.
Anything that navigates directly is doing unpaid work.

**Pacing is drawn from a heavy-tailed distribution.** Gaps between searches come
from a three-part mixture (median ~15 s, mean ~21 s, 5% over 45 s) rather than a
flat window, and search terms are generated from topic/modifier combinations
seeded by the date, so consecutive days do not repeat the same strings.

---

## Tasks & Features

| # | Task | Module | Nominal reward |
|---|---|---|---|
| 1 | **Daily set** — today's cards only, each verified individually | `task_daily_set.py` | 10–30 pts each (measured) |
| 2 | **Explore on Bing** — outstanding offers, each verified | `task_explore.py` | 5/10/15 pts each (measured) |
| 3 | **Daily searches** — 8-15 typed searches, variably spaced | `task_searches.py` | 3 pts each; 20 available, fewer taken |

> [!NOTE]
> Measured on this UK account, 2026-08-16: **20 searches pay 3 points each, then
> payment stops** — searches 21, 22 and 23 all earned nothing.
>
> The bot deliberately runs **8-12**, drawn per day, rather than the full 20.
> Finishing exactly on the quota every day is a signature in itself, and so is a
> fixed count. This forgoes 15-36 points a day; streaks are unaffected, since the
> daily activity gate is satisfied by a single search. Point values differ by market.

Supporting behaviour:

- **Point claiming** — `utils/claim.py` collects the "Ready to claim" pot, which
  does not drain on its own. It takes two clicks: the tile opens a panel, the panel
  carries the control that actually claims. Success is judged by the pot shrinking.
- **Quiz & poll handling** — `handle_quiz_or_poll_on_page()` distinguishes a
  one-click poll from a multi-question quiz. Note that it selects the *first*
  option rather than the correct one; see
  [Current Limitations](#current-limitations).
- **Skip-if-complete** — each task inspects card text and markup for a completed
  state and skips those cards, so a partial re-run does not redo finished work.
- **Modal dismissal** — `dismiss_all_modals_and_drawers()` clears the slide-out
  drawers that otherwise intercept clicks on the dashboard.

---

## Environment & Installation

**Requirements:** Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:triagram/bing-daily-reward.git
cd bing-daily-reward

# 1. Create the virtual environment and install dependencies
uv sync

# 2. Download the Chromium build Playwright drives
uv run playwright install chromium
```

> [!IMPORTANT]
> Step 2 is easy to miss and does not fail loudly. `uv sync` installs the
> Playwright *library*; it does not download the *browser*. Skipping it produces
> an "Executable doesn't exist" error at launch that does not obviously point at
> the missing install step.

Dependencies are just two:

| Package | Version | Purpose |
|---|---|---|
| `playwright` | 1.61.0 (pinned) | Browser automation |
| `rich` | >= 15.0.0 | Coloured console output and log formatting |

`playwright` is pinned to an exact version deliberately. Each release expects a
matching Chromium build, so upgrading it without also re-running
`playwright install chromium` produces the "just installed or updated" error
above. Exact versions for the whole tree are recorded in `uv.lock`.

---

## Usage & Execution

### First run — sign in once

```bash
uv run python rewards_bot.py
```

A Chromium window opens on the Rewards dashboard. If you are not signed in, the
bot detects the redirect to `login.live.com`, prints a prompt, and **waits for
you to press ENTER in the terminal**. Sign in inside the browser window, then
press ENTER to continue.

Your session is written to `browser_session/` and reused from then on, so this
is a one-time step.

### Subsequent runs

```bash
uv run python rewards_bot.py            # run today's tasks
uv run python rewards_bot.py --dry-run  # report what it would do, change nothing
uv run python rewards_bot.py --history  # what past runs earned, per task
```

Tasks 1 → 2 → 3 run in sequence. A full run takes roughly 4–6 minutes, most of
it the deliberate search cooldown.

### Configuration

Everything tunable lives in `config.py`:

| Constant | Default | Meaning |
|---|---|---|
| `DAILY_SEARCH_MIN` / `MAX` | `8` / `12` | Range the daily search count is drawn from |
| `DAILY_SEARCH_ALLOWANCE` | `20` | The measured ceiling. Recorded, deliberately not used |
| `EXPLORE_MAX_PER_RUN` | `6` | Most Explore offers per run. Covers the observed range |
| `MIN_DELAY_BETWEEN_SEARCHES` | `6.0` | Lower bound of the inter-search wait, seconds |
| `MAX_DELAY_BETWEEN_SEARCHES` | `9.0` | Upper bound |
| `HEADLESS` | `False` | Run without a visible window. **See limitations.** |
| `FALLBACK_KEYWORDS` | 20 topics | Search terms, shuffled each run |

---

## Logging & Diagnostics

Normal runs log to the console through `rich`, with per-task progress and a
summary line. **Nothing is written to disk yet** — when the terminal closes, the
run history is gone.

Three standalone diagnostic scripts are included. They are development tools
rather than part of the daily flow, but they are the practical way to work out
why a task stopped finding its cards after a Microsoft redesign:

```bash
# Dump current points, task states and claim buttons to diagnostics_report.json
uv run python scientific_diagnostics.py

# Walk the whole flow with a pause and a highlighted element at each step
uv run python step_by_step_debugger.py

# Screenshot the dashboard and list every Daily set card it can find
uv run python debug_task1.py
```

`scientific_diagnostics.py` is the most useful of the three: its
`extract_points()` function scrapes the account's available and ready-to-claim
point totals, and promoting it into the main run loop is the next planned
change (see [Roadmap](#roadmap)).

---

## Current Limitations

Known and honest, as of v0.1.0:

- **Point totals in the logs are fabricated.** Lines like
  `✓ Search [3/20] completed (+3 pts)` are printed whenever a page navigation
  did not raise an exception. The bot never reads your point balance, so a run
  blocked by a captcha, a spent daily quota, or bot detection still reports
  `✅ Completed 20/20 (~60 points earned)`. **This is the most important thing
  to fix, and the reason for everything else on the roadmap.**
- **Errors are swallowed.** Most failure paths are `except Exception: pass` or
  log at debug level, so a broken selector looks identical to a completed task.
- **Headless mode is untested.** `HEADLESS = True` will launch, but the anti-bot
  posture is a single Chromium flag and Microsoft's detection of headless
  sessions has not been checked. The default is `False` for a reason.
- **The first run cannot be automated.** Login waits on a blocking `input()`
  call, so an unattended scheduled run is not possible until that is reworked.
- **Quizzes are answered at random.** `handle_quiz_or_poll_on_page()` clicks the
  first available option. Quizzes award points for wrong answers too, but fewer.
- **Selectors will break.** The Rewards dashboard is redesigned periodically. The
  URL-signature strategy is more durable than class matching, but not immune.
- **Cross-navigation locators are unstable.** Task 1 collects card locators once
  and reuses them across page navigations, so the second and third cards can
  resolve to the wrong element after the DOM updates.
- **Single account only.** `USER_DATA_DIR` is one fixed path in `config.py`.
- **No tests, no CI.**

---

## Roadmap

Ordered by what unblocks the most. The first item comes before everything else,
because until the bot can measure its own effect, none of the rest can be
verified.

- [ ] **Closed-loop point verification** — move `extract_points()` into `utils/`,
      capture the balance before and after each task, and report the real delta
      instead of an assumed one.
- [ ] **Structured task results** — have each task return attempted / succeeded /
      point delta / errors rather than only logging, and render a summary table
      at the end of a run. This also delivers the self-updating logbook below.
- [ ] **Fix cross-navigation locators** — re-query cards inside each loop
      iteration; identify them by URL or text rather than by index.
- [ ] **Idempotent re-runs** — read the day's completion state up front and only
      run what is outstanding, so a failed run can simply be repeated.
- [ ] **Retries with backoff** — wrap navigation and key clicks.
- [ ] **Persistent logs** — one JSON-lines file per day under `logs/`.
- [ ] **Unattended operation** — replace the blocking login prompt with an
      explicit `--login` mode, make `HEADLESS` configurable by environment
      variable, and schedule daily runs with a systemd timer.
- [ ] **Failure notifications** — alert only when a run does not earn what it
      should.
- [ ] **Multi-account support** — `profiles/<account>/`, driven by config.
- [ ] **Real quiz answering** — extract the correct option instead of guessing.

---

## Disclaimer

Automating Microsoft Rewards very likely violates the
[Microsoft Rewards Terms of Service](https://www.microsoft.com/rewards/terms).
Accounts found to be using automation can have their points revoked or be
suspended entirely.

This project was written as a personal exercise in browser automation. Use it on
your own account, at your own risk, and be aware that the risk includes losing
whatever balance that account has accumulated.

---

## License

[MIT](LICENSE) © 2026 Triagram

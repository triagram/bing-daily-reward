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

**Project status: four task flows, all rewritten and closed-loop.** Each one
reads the dashboard's own state, confirms every item individually, and reports the
point delta it actually measured — or says "unknown" rather than inventing a number.
All three have been verified against a live account, and the parser and the
behavioural choices are covered by an offline test suite.

It is still run by hand, on purpose. Unattended scheduling and headless mode are
deliberately deferred until the daily run has been stable for a stretch; multi-account
use and VPNs are ruled out, not deferred — see [Current Limitations](#current-limitations).

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
│   ├── task_keep_earning.py    # Task 2 — the point-bearing offers under "Keep earning"
│   ├── task_searches.py        # Task 3 — N Bing searches, closed-loop measured
│   ├── task_explore_on_bing.py # Task 4 — the "Explore on Bing" tiles (behind a switch)
│   ├── claim.py                # Moves the "Ready to claim" pot into the balance
│   ├── dashboard_state.py      # Pure parser: dashboard HTML → structured offers & counters
│   ├── state_reader.py         # Thin layer that feeds the parser from a live page
│   ├── retry.py                # Backoff for transient navigation and click failures
│   ├── shortfall.py            # Judges a run: did it earn what the work was worth?
│   └── keywords.py             # Date-seeded search-term generation
│
├── explore_on_bing.py          # Task 4 on its own: the retry and dry-run tool
├── monitor.py                  # Read-only daily sampler — records state, diffs against last run
├── recon.py                    # Read-only deep capture — screenshots, DOM, network log
│
├── tests/                      # Offline suite — no browser, no network, no account
├── .github/workflows/tests.yml # Runs that suite on a clean machine (manual trigger for now)
├── experiments/                # One-off measurements that settled an open question
├── contrib/systemd/            # Timer units for the read-only monitor (not for the bot)
├── logs/                       # Run records and state samples (git-ignored)
├── captures/                   # Archived pages the parser is developed against
│
├── docs/DEVELOP.md             # Data contract, open questions, tooling notes
├── docs/OBSERVATION.md         # The stability window: daily routine, exit criterion, freeze list
├── legacy/                     # Pre-rewrite DOM-scraping diagnostics, kept for selector archaeology
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
| 2 | **Keep earning** — outstanding point-bearing offers, each verified | `task_keep_earning.py` | 5/10/15 pts each (measured) |
| 3 | **Daily searches** — 8-12 typed searches, variably spaced | `task_searches.py` | 3 pts each; 20 available, fewer taken |
| 4 | **Explore on Bing** — the unlocked tiles, activated then searched | `task_explore_on_bing.py` | 10 pts each; 4 unlock daily |

> [!NOTE]
> Measured on this UK account, 2026-08-16: **20 searches pay 3 points each, then
> payment stops** — searches 21, 22 and 23 all earned nothing.
>
> The bot deliberately runs **8-12**, drawn per day, rather than the full 20.
> Finishing exactly on the quota every day is a signature in itself, and so is a
> fixed count. This forgoes 15-36 points a day; streaks are unaffected, since the
> daily activity gate is satisfied by a single search. Point values differ by market.

> [!NOTE]
> Tasks 2 and 4 are different sections of the same page and are easy to confuse. Task 2 was
> called `explore` until 2026-08-22, and that collision misled both the notes and the
> account holder, so it is now named for the heading its offers appear under.
>
> **Task 4 sits behind `RUN_EXPLORE_ON_BING` in `config.py`, off until 2026-09-23.** Its
> tiles credit in two steps — clicking one *activates* it, and a search inside what it
> opens *completes* it — and a topic the query map has not learned yet fails once before
> it can be added. While the switch is off, run it from `explore_on_bing.py` after the
> daily run, so that such a failure cannot dirty a day that was otherwise clean. With the
> switch on, the daily run works the tiles itself (after keep-earning, before the claim,
> with their four searches held back from the search allowance) and records them with
> the others; `explore_on_bing.py` stays as the retry and dry-run tool. A topic that has
> been given up on goes on `SHELVED_TOPICS` and is reported, never attempted.

Supporting behaviour:

- **Point claiming** — `utils/claim.py` collects the "Ready to claim" pot, which
  does not drain on its own. It takes two clicks: the tile opens a panel, the panel
  carries the control that actually claims. Success is judged by the pot shrinking.
- **Quiz & poll handling** — `handle_quiz_or_poll_on_page()` distinguishes a
  one-click poll from a multi-question quiz. Note that it selects the *first*
  option rather than the correct one; see
  [Current Limitations](#current-limitations).
- **Skip-if-complete** — each task reads the day's outstanding work from the parsed
  state before starting, so a partial re-run picks up where the last one stopped
  instead of redoing finished work.
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

Dependencies are two, plus `pytest` for development:

| Package | Version | Purpose |
|---|---|---|
| `playwright` | 1.61.0 (pinned) | Browser automation |
| `rich` | >= 15.0.0 | Coloured console output and log formatting |
| `pytest` | >= 8.0 (dev) | The offline test suite |

`playwright` is pinned to an exact version deliberately. Each release expects a
matching Chromium build, so upgrading it without also re-running
`playwright install chromium` produces the "just installed or updated" error
above. Exact versions for the whole tree are recorded in `uv.lock`.

```bash
uv run pytest -q     # the suite; parses a fixture, never opens a browser
```

Worth running before any change to `utils/dashboard_state.py` — but it proves
nothing about a live run, which only a real run can.

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
uv run python rewards_bot.py --login    # sign in by hand; confirms the session works

uv run python explore_on_bing.py            # the Explore on Bing tiles, after the daily run
uv run python explore_on_bing.py --dry-run  # which are open today, and what it would search
```

Tasks 1 → 2 → 3 run in sequence. A full run takes roughly 4–6 minutes, most of
it the deliberate search cooldown.

### Configuration

Everything tunable lives in `config.py`:

| Constant | Default | Meaning |
|---|---|---|
| `DAILY_SEARCH_MIN` / `MAX` | `8` / `12` | Range the daily search count is drawn from |
| `DAILY_SEARCH_ALLOWANCE` | `20` | The measured ceiling. Recorded, deliberately not used |
| `KEEP_EARNING_MAX_PER_RUN` | `6` | Most Keep-earning offers per run. Covers the observed range |
| `MIN_DELAY_BETWEEN_SEARCHES` | `6.0` | Lower bound of the inter-search wait, seconds |
| `MAX_DELAY_BETWEEN_SEARCHES` | `9.0` | Upper bound |
| `HEADLESS` | `False` | Run without a visible window. **See limitations.** |
| `FALLBACK_KEYWORDS` | 20 topics | Search terms, shuffled each run |

---

## Logging & Diagnostics

Normal runs log to the console through `rich`, and end with a table of measured
point deltas per task. Each run also appends one JSON line to `logs/runs.jsonl`, so
a bad day stays visible after the terminal has closed:

```bash
uv run python rewards_bot.py --history   # every recorded run, per task, with flags
```

The `Flags` column is the one to read. `zero`, `short` and `unknown` come from
`utils/shortfall.py`, which compares what a task earned against what the work it did
was worth — the distinction a bot cannot otherwise make between a quiet day and a
broken one.

`monitor.py` writes separately to `logs/state_samples.jsonl`. It is read-only, so it
is the safe instrument to leave running. `logs/` is git-ignored.

Three standalone diagnostic scripts are kept in `legacy/`. They are not part of the
daily flow, but they are the practical way to work out why a task stopped finding its
cards after a Microsoft redesign. They must be run as modules from the repository
root, because they import `config` (see `legacy/README.md`):

```bash
# Dump current points, task states and claim buttons to diagnostics_report.json
uv run python -m legacy.scientific_diagnostics

# Walk the whole flow with a pause and a highlighted element at each step
uv run python -m legacy.step_by_step_debugger

# Screenshot the dashboard and list every Daily set card it can find
uv run python -m legacy.debug_task1
```

These predate `utils/dashboard_state.py` and scrape the DOM, which the rest of the
project no longer does — prefer `--dry-run`, or `recon.py` when a capture is needed
for comparison. They are kept because after a Microsoft redesign, the DOM is what you
have to go back to.

> [!NOTE]
> `legacy/scientific_diagnostics.py` writes `diagnostics_report.json`, which contains
> your point balance. It is git-ignored, but it does land on disk.

---

## Current Limitations

Honest as of the closed-loop rewrite. The measurement problems that dominated this
list are fixed; what is left is either a deliberate deferral or a genuine unknown.

- **Headless mode is untested.** `HEADLESS = True` will launch, but the anti-bot
  posture is a single Chromium flag and Microsoft's detection of headless sessions
  has not been checked. The default is `False` for a reason.
- **Signing in is by hand.** `rewards_bot.py --login` opens the browser, waits for
  you, and confirms the balance is readable before it says the session works. A run
  that finds the sign-in page with no terminal to wait in — a scheduled one — stops
  with exit code 3 and records nothing, rather than crashing on `input()`.
- **Quizzes are answered at random.** `handle_quiz_or_poll_on_page()` clicks the
  first available option. Quizzes award points for wrong answers too, but fewer.
- **Selectors will break.** The Rewards dashboard is redesigned periodically.
  Reading the page's own state is far more durable than class matching, but the
  shape of that state is not a published contract either.
- **Single account only, and that is permanent.** `USER_DATA_DIR` is one fixed path
  in `config.py`. Multi-account use and VPN/proxy routing are the two most-cited
  causes of suspension in the community's own reports (decision 2026-09-16), so
  neither will be made easy here.
- **The run history is thin.** `logs/runs.jsonl` holds only a handful of records,
  so `--history` cannot yet tell an unusual day from a normal one. This resolves
  itself with use.
- **Two questions are still open.** The `Edge` 0/30 counter has never been
  investigated, and how fast Explore offers replenish is unknown — so the bot
  cannot predict what a day *should* be worth, only measure what it was. See
  [Open questions](docs/DEVELOP.md#open-questions).
- **CI is manual-only.** The workflow exists but runs on `workflow_dispatch`, not
  on push. Deliberate, until the suite has proved stable.

---

## Roadmap

**Done.** Listed because the shape of the solution differs from what was planned:

- [x] **Closed-loop point verification** — the plan was to promote
      `extract_points()` out of the diagnostics. The route taken instead was
      `utils/dashboard_state.py`, which parses the state the page itself renders
      from, making the whole thing a pure function that can be tested offline.
      Totals are compared as balance **+** unclaimed, because earnings land in
      either.
- [x] **Structured task results** — each task returns attempted / completed /
      point delta / errors, rendered as a table at the end of a run.
- [x] **Verdicts on a run** — `utils/shortfall.py` compares what a task earned
      against what its work was worth, so a broken run is distinguishable from an
      idle one instead of both printing zeros and exiting successfully.
- [x] **Fix cross-navigation locators** — cards are re-queried inside the loop and
      identified by offer id, and the day's offers are filtered by date.
- [x] **Idempotent re-runs** — state is read up front and only outstanding work is
      done, so a failed run can simply be repeated.
- [x] **Retries with backoff** — `utils/retry.py`, including a re-attempt of a card
      whose completion flag did not flip.
- [x] **Claim the pending pot** — points sitting in "Ready to claim" do not move on
      their own.
- [x] **Tests** — an offline suite over the parser and the behavioural choices.

**Next**, roughly in order:

- [ ] **Accumulate run history** — the immediate task is simply to run daily and
      let `logs/runs.jsonl` fill, so "stable" becomes something the Flags column
      can answer rather than an impression.
- [ ] **Enable CI on push** — a one-line uncomment, once the suite has held.
- [ ] **Answer Q8 — the `Edge` 0/30 counter** — the largest unexplored surface on
      the account.
- [ ] **Unattended operation** — replace the blocking login prompt with an explicit
      `--login` mode, make `HEADLESS` configurable by environment variable, and
      only then consider a systemd timer. `contrib/systemd/` already carries units
      for the read-only monitor.
- [ ] **Out-of-band failure alerts** — a shortfall currently only prints to a
      console nobody is watching. This one is worth having *before* scheduling,
      not after.
- [ ] **Real quiz answering** — extract the correct option instead of guessing.

**Not planned:** multi-account support. Ruled out 2026-09-16 as the most-cited cause
of suspension; see Current Limitations.

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

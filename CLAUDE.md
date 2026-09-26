# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Where to pick up

**v1.0.0 is tagged (2026-09-26) and the daily run is scheduled.** All four tasks run
from `rewards_bot.py` under `rewards-bot.timer`, 07:30 plus up to three hours, waiting
for the desktop session. The observation window closed 14 of 14 on 09-16; a seven-day
test period closed clean on 09-23. **Nothing is run by hand any more, and a second run
on a clean day is harmful** — the search task fills the allowance to the quota.
`--dry-run` and `--history` are the ways to look. The `lyrics` tile is shelved;
`recipe` is learned.

Read in this order: this file for the rules; `docs/DESIGN.md` for why it is built this
way; `docs/DEVELOP.md` for what the dashboard actually returns, which questions are
settled and every finding with its evidence; `docs/OBSERVATION.md` for the record of
the window; `notes/roadmap.md` for what is next, deferred, or never; `README.md` for
how it is used. Between them they carry everything — do not re-derive findings by
experimenting on the account.

**Never, by decision on 2026-09-16: multi-account, and running through a VPN or proxy.**
Not deferred — ruled out. A survey of suspension reports (script maintainers' own issue
trackers and Microsoft Q&A, 2023-2026) names those two as the most frequently cited
causes, ahead of search rate; every ban signal anyone names is behavioural. Do not add a
`profiles/` directory, a proxy setting, or anything that makes either easy.

Deferred, one at a time after a clean week under the timer: a wider inter-search gap,
an occasional result click, then Q8 (the `Edge` 0/30 counter — the obvious next thing,
and a new activity type, which is why it waits for the baseline). The Telegram push is
pending on the user's account being allowed to create a bot; ntfy is in use.

## Commands

```bash
uv sync                              # create .venv and install deps
uv run playwright install chromium   # download the browser — separate step, easy to miss

uv run python rewards_bot.py --dry-run   # read state and report, change nothing
uv run python rewards_bot.py --history   # what past runs earned, per task, with flags
uv run python rewards_bot.py --login     # sign in by hand; confirms the session works
uv run python rewards_bot.py             # a full run — not on a day that already ran clean

uv run python explore_on_bing.py --dry-run   # which tiles are open today, and what it would search
uv run python explore_on_bing.py             # the tiles alone — a retry tool after a failed day

uv run python monitor.py             # read-only state sample, appends to logs/state_samples.jsonl
uv run python monitor.py --history   # what has been collected so far
uv run python recon.py               # read-only deep capture: screenshots, DOM, network log

uv run pytest -q                     # the offline suite; no browser, no account
```

`uv run pytest -q` runs the suite (111 tests, ~1 s). It parses a synthetic fixture and
never opens a browser or touches the account, so it is free to run — and proves nothing
about a live run. There is no linter. CI runs the same suite on a clean machine on every
push to main.

So "verifying a change" splits in two: anything in `dashboard_state.py` and the
behavioural helpers is verifiable offline by test, while anything that touches the live
dashboard still needs a diagnostic script or a real run. After a change to `config.py`
or an import, also `uv run python -c "import rewards_bot, explore_on_bing, monitor,
recon"` — pytest never imports the entry points.

Long experiments must run in the background: a foreground command is capped at ten
minutes, and a run that exceeds it is killed. Under memory pressure this harness also
kills background tasks that hold a browser; launch the bot with
`systemd-run --user --unit=rewards-bot-manual --collect -p WorkingDirectory=/projects/bing-daily-reward /home/mengyuan/.local/bin/uv run python rewards_bot.py`
and poll `systemctl --user is-active` in a foreground loop. A killed run leaves a stale
`browser_session/SingletonLock`; check its pid is dead before removing it.

## Committing and pushing

Commit freely as work is verified; **push only at milestones**. The user asked for this
explicitly, so that commits stay rewritable until a piece of work is actually finished.

Commit when a change is self-contained, **verified**, and describable in one sentence
without "and". Findings count as changes worth committing — an experiment result that
is not written down is lost.

A milestone is an open question resolved, a task module rewritten and verified, or a
release tagged. Also push before the user steps away, so nothing of theirs exists only on
this disk. If they say "push", push.

Messages: Conventional Commits prefix, imperative summary, then a body explaining *why*
and what evidence supports it — not a restatement of the diff.

## Running the bot is not a free action

`rewards_bot.py` drives a real browser against the user's real Microsoft Rewards account,
which holds a real point balance and is subject to Microsoft's anti-automation
enforcement. Do not launch it to "check something" — `--dry-run` reads the state and
changes nothing. Ask before any full run, and never run one on a day that already ran
clean. `HEADLESS = False` is the working default; headless has never been validated.

## Rules that must not be broken

The design is in `docs/DESIGN.md`. These are the parts of it that a plausible-looking
change would break:

- **Measure; never assert.** Every task confirms items **individually** by re-reading
  that item's own `isCompleted`; anything that does not flip is reported failed. Do not
  reintroduce a point figure that was not observed. Compare **balance + unclaimed**
  (`DashboardState.total_points`), never the balance alone.
- **Read state through `utils/dashboard_state.py`**, a pure function over the page's
  flight stream, fed by `utils/state_reader.py`. Prefer it over any DOM scraping.
  Selectors anchor on URL signatures (`BTDSUOID`, `filters=BTEPOKey`, `REWARDSQUIZ`)
  and fall back to classes only when that finds nothing; preserve that ordering.
- **The "Daily Set" activity ring shows *yesterday's* completions.** Gate work on the
  cards' own `isCompleted` and nothing else.
- **Queries must be typed into the search box.** Navigating to `bing.com/search?q=…`
  is not credited at all. `_search_once()` always types.
- **8-12 searches, drawn per day, trimmed by what the day has left** — never the full
  allowance of 20, and never a fixed count. Streaks need one search. Inter-search gaps
  come from the heavy-tailed mixture in `search_gap()`.
- **Direct navigation to an offer's destination has never completed anything** (0 for
  12). The credit is the click on the Rewards card. When the keep-earning fallback is
  next touched: bounded wait, one reload, "card not found" — never a `goto`.
- **`playwright` is pinned to `==1.61.0`.** Bumping it needs `playwright install
  chromium` in the same breath.
- **`handle_quiz_or_poll_on_page()` clicks the first option**, not the correct one. A
  known stub. Polls need exactly one click and return early; quizzes loop.
- **Task 2 is `task_keep_earning.py`.** It was once called `task_explore`, which made a
  clean run read as a failure; do not reintroduce "explore" as its name. Old
  `runs.jsonl` records use the old key and are remapped on read.
- **Explore on Bing** (task 4, `RUN_EXPLORE_ON_BING`): click the tile to *activate*,
  then search inside what opens, typed. `VERIFIED_QUERIES` holds only measured
  entries; `SHELVED_TOPICS` holds topics given up on — reported, never attempted.

## Never commit `browser_session/`

It is a live Chromium profile holding Microsoft session cookies (`_U`, `WLSSC`,
`MSPAuth`). On Linux these are encrypted with a hardcoded key, so anyone with the
directory can read them. It was committed once and had to be stripped from history; it is
now in `.gitignore` alongside `debug_*.png`, `logs/` and `captures/`. Keep it that way,
and never `git add -f` it.

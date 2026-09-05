# The observation window

Start date: **not yet — see below.** Purpose: establish that a daily run is boring before anything is
automated. Nothing here is about adding capability — it is about accumulating evidence.

## Why this is starting from zero, not continuing

`logs/runs.jsonl` holds one record, from 2026-08-17 13:07. Every commit below it
postdates that run:

| Commit | Change |
|---|---|
| `8302caa` `0c5283d` | Explore rewritten around parsed state; the pending pot is claimed |
| `ce32f8e` | Daily search count narrowed from 8-15 to 8-12 |
| `2cb695f` | Retries with backoff; a card whose flag did not flip is re-attempted |
| `e4ef9ef` `48c4c34` | Shortfall verdicts; `--history` |

So that record shows 15 searches and no Explore or claim columns — it does not describe
what the code now does. **Sample size for the current code is zero.** Do not read its
95-point total as a baseline.

## Status: 2 of 14 — counting from 2026-09-03

| Run | Result |
|---|---|
| 2026-08-22 … 09-01 | Eleven consecutive clean runs. **Ended by the next line.** |
| 2026-09-02 | `keep_earning` 1/6. Five `RewardsApp` offers — completable only in the phone app — filled the six-item cap and pushed a real offer out of the run. **Broke the sequence.** Cause removed in `d9b3d9e`. |
| **2026-09-03** | **Clean.** 3/3, 12/12, 4/4, +119. **1 of 14.** |
| **2026-09-04** | **Clean.** 3/3, 10/10, 3/3, +158. **2 of 14.** |

The eleven-run streak was not carried over, by decision on 2026-09-04. The failure was
real — work was attempted and not done, and an offer that would have completed was never
reached — and the new count starts on the code that fixes it, which is worth more than a
number spanning a known fault.

## What v1.0.0 means

Two conditions, both measurable, neither met yet:

1. **This window closes at 14 of 14.**
2. **`explore_on_bing.py` folds into the daily run**, so there is one command again. It
   is separate only because a topic the query map has not learned fails once before it
   can be added, and such a failure must not dirty an otherwise clean daily run. The
   result type already matches the other tasks; merging is three lines in
   `rewards_bot.py`.

They arrive together: the map needs roughly the same fortnight to settle.

`v0.2.0` was tagged 2026-08-25 for the closed-loop rewrite. Its tag message is the
release note.

## Open threads, as of 2026-09-04

| Thread | State |
|---|---|
| `recipe` tile | Failed twice, unexplained — the non-breaking space was not the cause. Normalisation strips those (`0b078ee`), and the 09-04 18:09 retry typed the corrected `new recipes` and still did not complete, so the override was deleted (`740dfd9`). Starts clean on its next appearance, like `lyrics`. |
| `lyrics` tile | Failed twice, unexplained. Its empty description was a red herring — tiles lose that after activation. No override; next appearance starts clean. |
| `hotel`, `realestate` | Never validly tried. They run on their own prompts now, which is the test — **both unlock 2026-09-06**, so the next run answers it. |
| Q2 — what the Daily Set ring counts | Reopened 2026-08-19; one reading (08-17 02:13) fits no model. |
| Q8 — the `Edge` 0/30 counter | Untouched, still frozen. |

## Exit criterion## Exit criterion

Not a duration — a measurement, because the instrument already exists:

> **14 consecutive recorded runs with an empty `Flags` column and no unexplained
> `overall_delta`.**

`Flags` is empty only when every task cleared all three of: a verdict that is not
`zero` / `short` / `unknown`, no recorded errors, and `done == attempted`.

The last two were added on 2026-08-19, because the first alone was not enough. That
run failed a daily-set card outright and still recorded `verdict: ok`, since 20 points
of an advertised 30 clears the 0.6 tolerance in `utils/shortfall.py`. The tolerance is
correct — advertised values are a guide, not a contract, and an Explore run has
measured 50 against 40 stated — but a run carrying a recorded error is never clean,
whatever it earned. Leaning on the verdict alone reintroduced exactly the silent
failure this project exists to remove.

**A missed day extends the window by a day; it does not restart the count.** Absence of
evidence is not evidence of instability. Only an **unexplained** flag restarts it.

Why 14 and not 3: the search count is drawn 8-12 daily, Explore offers rotate at a rate
still unknown ([Q7](DEVELOP.md#q7)), and the Daily Set ring reflects *yesterday*
([Q2](DEVELOP.md#q2)) — so "yesterday was completed" and "yesterday was not" are
different code paths and both need to be walked. Fourteen runs also covers a full streak
cycle, which the docs note dwarfs the daily tasks.

## The daily routine

Once a day, at roughly the same time, at a consistent offset after the daily reset
([Q3](DEVELOP.md#q3) settled when that is). A run at 23:50 and one at 00:10 are not
comparable — "outstanding today" means different things.

One-time setup:

```bash
mkdir -p logs/observation
```

Then, once a day:

```bash
uv run python rewards_bot.py 2>&1 | tee -a logs/observation/$(date +%F).log
```

Reading that: `2>&1` merges the error channel into the normal one so that a traceback
reaches the log rather than only the screen — which is the whole point, since nobody is
watching the screen. `tee -a` writes to the file *and* passes the output through, and
appends rather than truncating, so a second run on a day does not erase the first one's
failure. `$(date +%F)` expands to `2026-08-18`, giving one file per day that sorts
chronologically by name.

The `tee` is not optional. `runs.jsonl` captures the structured result, but the shortfall
warning and the "compare against an earlier capture" hint are console-only — and the
point of a window is that nobody is watching the console.

`HEADLESS = False` stays. Headless has never been validated against Microsoft's
detection; trying it here would move two variables at once.

**Reporting: by exception, from 2026-08-26.** Daily updates are not needed — the run
says out loud when something is wrong. Worth raising:

- **`Flags` is not empty**, or a task shows `done` below `attempted`. The run prints a
  red warning for the first; the second is visible in its own column.
- **An Explore on Bing tile did not complete.** That is not a fault so much as a signal:
  a topic the query map has not learned. Name the topic and it can be added.
- **Day 14**, to close the window.

Otherwise the two logs accumulate and can be read in one pass whenever it suits.

Read three things, in this order:

1. Is the `Flags` column empty?
2. Does `done == attempted` for every task?
3. Is `overall_delta` plausible against the per-task points?

## Day by day

Days 3(21)-13(31) are identical on purpose. Only these differ:

| Day | In addition to the daily run |
|---|---|
| 1 | `uv run python rewards_bot.py --dry-run` first. Write down what it says is outstanding — that is the baseline. Then the real run. |
| 2 | The first run *after* a completed day: the [Q2](DEVELOP.md#q2) path. Confirm it still finds outstanding cards rather than concluding the day is done. |
| 7 | `uv run python rewards_bot.py --history` — read the pattern across runs, not the day. |
| 14 | `--history` again. If the exit criterion holds, the window closes. |

Any day you are unsure what state the account is in, `--dry-run` first. It reads and
changes nothing.

Leave `monitor.py` running throughout as the read-only baseline; it costs nothing.
`contrib/systemd/` carries timer units **for the monitor, not for the bot.**

## Reading a flag

The three verdicts need opposite responses, so do not treat them alike:

- **`unknown`** — the totals could not be read. That is a *parser* problem: the page
  shape changed. Run `recon.py` and diff against `captures/`. It says nothing about the
  account.
- **`zero` / `short`** — the work did not pay what it was worth. First ask whether you
  had already done tasks by hand that day; a genuine shortfall is one with no such
  explanation. Only those restart the count.

**The cheapest signal that Microsoft's posture changed is re-authentication.** If
`browser_session/` starts asking for a sign-in mid-window, note the date. That is more
informative than any single zero-point run.

**A bad Explore on Bing day is not that signal, and will look like one.** 2026-09-05
completed 1 of 4 and the obvious reading was enforcement. Three checks ruled it out
inside the same run's own numbers, and they are the ones to repeat:

1. **Do the searches still pay?** `+22` measured against one confirmed tile is 10 for the
   tile and 3 for each of four searches. Every search still credited at full rate —
   throttling stops that first.
2. **Did anything complete in the same run?** `mattress` did, same browser, same minute.
   That rules out the mechanism and leaves the queries.
3. **Was the daily run clean?** It was: 3/3, 9/9, 1/1, no errors, no sign-in prompt.

The cause was the batch: three of that day's four prompts named an unfilled placeholder
Bing cannot resolve — "a word you don't understand", "a different time zone", "a specific
stock". Substituting a real entity into each and re-running the same three tiles six
hours later completed **3 of 3** (`c0a5904`). Batch composition, not a trend.

## Frozen for the duration

Time-boxed to this window — distinct from the permanent deferrals in `CLAUDE.md`. Each
of these changes account behaviour mid-baseline, which is exactly what the window exists
to hold still:

- ❌ **Probing Q8, the `Edge` 0/30 counter.** The most tempting one — it is flagged as
  the largest unexplored surface on the account. Probing it adds a new activity type
  mid-window and contaminates the baseline. Park it until the window closes; it is first
  in the Roadmap's "Next" list for after.
- ❌ **Headless mode.**
- ❌ **Scheduling the bot.** Blocked anyway on the login `input()` call.
- ❌ **Bumping `playwright`.** The pin is load-bearing; a bump needs
  `playwright install chromium` in the same breath.

**Not frozen for any account-related reason: enabling CI on push.** CI runs the offline
suite on a clean machine — no browser, no account, no network — so it cannot affect the
baseline. It waits only because the workflow's own comment asks for suite stability
first. That is a taste call. Flipping it early breaks nothing.

## After the window

In order: enable CI on push → answer Q8 → an out-of-band shortfall alert → then, and
only then, unattended operation. The alert belongs *before* scheduling: a shortfall
currently prints to a console nobody is watching, which is not much use once nobody is
watching by design.

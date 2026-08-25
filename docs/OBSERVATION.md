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

## Status: 4 of 14 — counting from 2026-08-22

| Run | Result |
|---|---|
| 2026-08-17 | Pre-dates the verdict fields. Not counted. |
| 2026-08-18 | Clean, +105 — but the sequence it started was broken the next day. |
| 2026-08-19 | `daily_set` 2/3, `Child1` never registered. **Broke the sequence.** |
| 2026-08-20 | Clean, +99 — broken the next day. |
| 2026-08-21 | `daily_set` 2/3, `explore` 1/3 `short`, +57. Broke the sequence. |
| 2026-08-22 | Clean, 3/3, 8/8, 1/1, +159. **1 of 14.** |
| 2026-08-23 | Clean, 3/3, 10/10, 2/2, +76. **2 of 14.** |
| 2026-08-24 | Clean, 3/3, 9/9, 5/5, +138. **3 of 14.** |
| **2026-08-25** | **Clean.** 3/3, 12/12, 3/3, +114. **4 of 14.** |

**2026-08-21 paid for the window a second time.** It surfaced three defects that had
been costing points silently, all fixed in `6992da7` with regression tests:

1. A daily-set card whose URL used lowercase percent-encoding matched no anchor, so it
   fell through to direct navigation and never registered. The page mixes both cases.
2. Two Explore offers whose queries began with the same word both resolved to the first
   card, so the second reported a successful click while never being opened.
3. A five-point offer reported failed at 11:21 was complete at 11:31. The per-item check
   runs before credit lands, so the run recorded an error and a `short` verdict for work
   that had succeeded.

The third is the one that threatens this document directly: `Flags` fires on a recorded
error, and the exit criterion reads `Flags`. Left alone it would have made clean runs
look dirty and the count unreachable.

Note what the fixes do **not** do. Two of the three failures were real — the card and
the offer genuinely did not complete — so 08-21 stays a broken run. A change that made
it look clean in hindsight would have been over-reaching.

Two things it also confirmed, incidentally: the parser fix holds on a live page for a
second day (`3 outstanding`, not six), and the allowance read `0/60` on a fresh day.

The `Child1` referral hypothesis is **still untested** — that slot held an ordinary
search card today, so no `referandearn` card has appeared since. See `DEVELOP.md`.

## How day one went

Day 1 was attempted on 2026-08-19 and held. The `--dry-run` reported **six**
outstanding daily-set cards for a three-card set — `Child1`, `Child2` and `Child3`
each listed twice, once populated and once with `None` for both points and title.
A run would have recorded `daily_set 3/6` with three errors: a first data point known
in advance to be bad.

Cause, settled offline against a fresh `recon.py` capture: the dashboard ships each
card as **two** objects, the rendered element and the data behind it, and the parser's
dedup key was built from the very fields those two halves disagree on, so both
survived. Fixed in `952f854`, with the shape now reproduced in the synthetic fixture.

**This is the cheapest outcome the window can produce.** A read-only `--dry-run`
caught it before any task ran — zero account exposure, and the fix arrived with a
regression test rather than a guess. It is the argument for having a window at all.

The dry-run listing now prints `offer_id` per offer and warns on an impossible count,
because the slot alone could not distinguish the two candidate explanations.

**Before starting: run `--dry-run` once more and confirm it reads three.**

## Exit criterion

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

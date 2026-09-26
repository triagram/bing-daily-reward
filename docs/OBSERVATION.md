# The observation window

**A closed record.** Ran 2026-09-03 to 2026-09-16, closed at 14 of 14; a seven-day test
period followed and closed clean on 09-23; the run was scheduled on 09-26. Purpose:
establish that a daily run is boring before anything is automated. Nothing here is
about adding capability — it is about accumulating evidence. Kept as written, including
the instructions that no longer apply; the routine now is in the
[README](../README.md#let-it-run-itself).

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

## Status: closed 2026-09-16 at 14 of 14 — counting from 2026-09-03

| Run | Result |
|---|---|
| 2026-08-22 … 09-01 | Eleven consecutive clean runs. **Ended by the next line.** |
| 2026-09-02 | `keep_earning` 1/6. Five `RewardsApp` offers — completable only in the phone app — filled the six-item cap and pushed a real offer out of the run. **Broke the sequence.** Cause removed in `d9b3d9e`. |
| **2026-09-03** | **Clean.** 3/3, 12/12, 4/4, +119. **1 of 14.** |
| **2026-09-04** | **Clean.** 3/3, 10/10, 3/3, +158. **2 of 14.** |
| **2026-09-05** | **Clean.** 3/3, 9/9, 1/1, +65. **3 of 14.** Explore ran 1 of 4 and then 3 of 3 on a retry — outside the daily run, so outside this count. See *Reading a flag*. |
| **2026-09-06** | **Clean.** 3/3, 9/9, 2/2, +73. **4 of 14.** Explore 3 of 4; `hotel` outstanding. |
| **2026-09-07 … 09-12** | **Six clean runs**, no errors and no flags on any. Explore ran **4 of 4 every one of those days**, +52 against 40 each, with no retry needed. **10 of 14.** |
| **2026-09-13 … 09-16** | **Four clean runs**; every `overall_delta` reconciles to its per-task sum (82, 147, 111, 85). **14 of 14 — the exit criterion is met.** Explore 4 of 4 on three of the four days; `lyrics` failed on 09-16, outside the count, and is the subject of *Open threads*. |

**The window closed on 2026-09-16.** Condition 1 of v1.0.0 holds. The test period that
followed — seven runs, 09-17 to 09-23 — has been clean on 09-17 … 09-21 (five). **09-22
flagged `keep_earning:1err`, explained the same day:** a new "follow us on TikTok"
offer's card was not on the page at the instant the task looked, because the account
holder had just closed the bot's Instagram tab by hand; a retry of that task alone,
undisturbed, completed it on the card click, +10 (see
[DEVELOP.md](DEVELOP.md#direct-navigation-has-never-completed-anything--and-a-hand-on-the-browser-costs-a-card)).
**Counted as day 6, by the user's decision the same day** — the code was not at fault
and nothing was changed. **09-23 was day 7, clean (+82): the test period is complete.**
09-24 was run by hand and clean (+112) — the enablement did not happen that day. 09-25
was clean too (+135, Explore 4 of 4), and is the first run made under systemd: the user
was away and asked for it, and the harness driving the session could not keep a
browser alive under the machine's memory pressure, so both scripts ran as transient
user units (`systemd-run --user`), DISPLAY from the user manager, nobody at the
keyboard. Both exited 0. That is step 5 below, verified a day early on a transient
unit rather than the installed one. 09-26 was run by hand and clean (+165, the
Saturday search-streak payout) before enablement began that afternoon. Condition 2 — folding
`explore_on_bing.py` into the daily run — **waits, by decision the same day**, for a
further period of clean runs on the same two commands; nothing changes in the routine
meanwhile. The user's words: merge after the test period, not before.

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

## Open threads, as of 2026-09-16

| Thread | State |
|---|---|
| `recipe` tile | **Closed 2026-09-18.** Returned with its description present (06:04, 13:16 — so the 09-16 persistence prediction was one for two, see [DEVELOP.md](DEVELOP.md#how-an-explore-on-bing-tile-actually-credits)), failed a third time on `new recipes` at 14:57, then completed at 20:47 on `new chicken curry recipes`, +13 against 10. Eighth entry in the map — and the cleanest: its plain same-day retry had already failed on 09-04, so the retry is not what fixed it. |
| `lyrics` tile | **Shelved 2026-09-16.** Reappeared on 09-16 already activated from 09-02 — the description was gone before anything ran — and failed twice more, the second time on the shape three forum posters say works. Four failures, three query shapes, every search credited. On `SHELVED_TOPICS`: reported, never attempted, never a flag. See [DEVELOP.md](DEVELOP.md#how-an-explore-on-bing-tile-actually-credits). |
| `realestate` tile | **Closed 2026-09-06.** Completed on its own prompt, placeholder and all. No override; nothing further to watch. |
| `hotel` tile | Completed on an override 2026-09-06, **but not closed.** Its own prompt passed on 08-30 and failed on 09-06 — same query, same topic, opposite results a week apart. See below. |
| Whether any override is what fixed its tile | **Open, and it reaches all seven.** Every entry was verified by a same-day retry on an already-activated tile, and `hotel` now shows the same query failing and then passing with nothing changed. Only a re-test on an unactivated tile separates them; none has had one. |
| Why some topics need an override | **Wider open than it was.** `hotel` failed on "your next adventure"; `rentalcars` completed on the same phrase 08-25. The discriminator is not the prompt text — see [DEVELOP.md](DEVELOP.md#how-an-explore-on-bing-tile-actually-credits). |
| A tile can credit without a search | `couponcodes`, 2026-09-06: the click opened nothing, no query was typed, and it credited 10 anyway. **Not reproduced** — the same tile ran normally on 09-10. One sighting, unexplained, method unchanged. |
| Two jumps in `opening_total` between runs | **Closed 2026-09-12.** 09-01 → 09-02 opened 1,894 above the previous close; 09-11 → 09-12 opened 1,164 above. Neither is a flag — the criterion reads the *within-run* delta — but both were unexplained until the monitor's archives were read back: the first is the September monthly bonus landing in the pot (1,830, claimed next run), the second the twelfth stamp paying 1,000 plus the Saturday streak's 100. The weekly `100 / 30` on Fridays is the same mechanism. See [DEVELOP.md](DEVELOP.md#streak-payouts-measured--the-weekly-overshoots-and-the-stamp-bonus). |
| Q2 — what the Daily Set ring counts | Reopened 2026-08-19; one reading (08-17 02:13) fits no model. |
| Q8 — the `Edge` 0/30 counter | Untouched, still frozen. |

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

*Historical — the window was run by hand; since 2026-09-26 the timer runs it and the
bot writes its own day log. What follows is what the window did.*

Once a day, at roughly the same time, at a consistent offset after the daily reset
([Q3](DEVELOP.md#q3) settled when that is). A run at 23:50 and one at 00:10 are not
comparable — "outstanding today" means different things.

One-time setup:

```bash
mkdir -p logs/observation
```

Then, once a day:

```bash
uv run python rewards_bot.py
```

**Since 2026-09-17 the bot writes the day's file itself**: everything the terminal
showed — table, warnings, a traceback if it crashed — is appended as plain text to
`logs/observation/<date>.log` when the run ends, one file per day, a second run on the
same day appended below the first. The `tee -a logs/observation/$(date +%F).log` the
window ran with is no longer needed (it is harmless, but doubles the file). The
structured result still goes to `runs.jsonl`; the day file is what a person reads, and
the reason it exists is that the shortfall warning and the "compare against an earlier
capture" hint are console-only — and nobody is watching the console.

`explore_on_bing.py` does not do this; keep `tee` for it while it is still run
separately.

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

A run that *opens* far above the previous close is not one of the three. Streak and
monthly bonuses land between runs — 1,830 on the first of the month, 1,000 when the
stamp card fills — and the criterion deliberately does not read them.

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

**Status 2026-09-18:** the alert and the scheduling are built and switched off —
`contrib/systemd/` for the units, `RUN_EXPLORE_ON_BING` in `config.py` for the merge.
CI runs on push (enabled 09-17, first run green). Q8 stays after all of it.

**Enablement happened 2026-09-26** (set for 09-24 on 09-18, moved on 09-25 — the user
was away), walked through one step at a time. Two things did not go as the list below
was written, and are worth more than the list:

- **Linger was already on** for this user, for the monitor's sake, so "no linger for
  the bot" was never a choice. `rewards-bot.service` now runs through
  `contrib/systemd/run-with-display.sh`, which waits up to three hours for the desktop
  session and exits 5 without one; see `contrib/systemd/README.md`.
- **Step 5 could not be a real run**, because the day had already been run by hand and
  **a second run on a day is not idle**: the search task sizes itself to what is left
  of the allowance, so a re-run fills the day to exactly 20 — the one figure the
  varying count exists to avoid. The daily set, keep-earning and Explore are idempotent;
  searches are not. Step 5 was done as a `--dry-run` through the wrapper under
  `systemd-run`, plus a start of `rewards-alert.service` by hand; the real launch
  under systemd had been proved the day before, twice, on transient units. The first
  run of the installed unit is the 09-27 timer run.
- The Telegram push is pending: the user's account is currently refused new bots
  (`NEWBOT_BLOCKED`); ntfy is back in the script as the alternative.

The steps as planned, kept so the record reads against them:

1. `uv run python rewards_bot.py --history` — confirm 09-17 … 09-23 are seven clean
   rows. A flag on any of them stops here.
2. Phone push: if the user has a Telegram bot token and has messaged the bot, swap
   the ntfy block in `contrib/systemd/rewards-alert.sh` for a Telegram `sendMessage`
   and put the token and chat id in `~/.config/bing-daily-reward/alert.env`. If not,
   desktop notification only; the push can be added any day.
3. `RUN_EXPLORE_ON_BING = True` in `config.py`; `uv run pytest -q`;
   `uv run python rewards_bot.py --dry-run`.
4. Install the units: copy the five `rewards-bot` / `rewards-alert` / `rewards-check`
   files from `contrib/systemd/` to `~/.config/systemd/user/`, then
   `systemctl --user daemon-reload`. **No `enable-linger`.**
5. `systemctl --user start rewards-bot.service` with
   `journalctl --user -u rewards-bot.service -f` alongside, the user watching. This
   one run verifies three things at once: the merged Explore inside the daily run,
   a real browser window launched by systemd, and the exit code reaching
   `OnFailure=` (fire `rewards-alert.sh failed` by hand once if the run is clean, to
   see the notification arrive from under systemd).
6. Clean → commit the switch, tag `v1.0.0` with the release note in the tag message.
7. `systemctl --user enable --now rewards-bot.timer rewards-check.timer`;
   `systemctl --user list-timers 'rewards-*'`.
8. Push.
9. From 09-25 the routine is nothing: no hand runs, no `explore_on_bing.py`, no
   `tee`. `explore_on_bing.py --dry-run` remains the way to look at the tiles.

**Profile changes, agreed 2026-09-16 and deliberately not started with the window:** a
survey of what gets accounts suspended (see `CLAUDE.md`, *Never*) found every named
signal to be behavioural, and no source claiming Microsoft fingerprints the browser. So
no stealth patches. The two candidates worth a measured change, one at a time and only
after v1.0.0 has run clean for a week, are the inter-search gap — median ~15 s here
against defaults of 3-5 min in the most-used community script, which runs three times as
many searches — and an occasional click on a result rather than a scroll alone. Neither
has evidence of *need* behind it: four weeks, zero flags, no re-authentication prompt.
When scheduling arrives it must jitter the start time; the community default is 5-50
minutes.

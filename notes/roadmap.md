# Roadmap

Decisions about what comes next, so they are not re-litigated. Dated when made; each
gives its reason.

## Done (v1.0.0, 2026-09-26)

- Point verification through the dashboard's own state; a verdict per task and one
  flag judgement per run (`flags_for()`).
- Re-runs are safe for the tasks gated on `isCompleted`; the claim step; retries with
  backoff.
- Explore on Bing inside the daily run, its searches reserved from the allowance, and a
  shelf for topics given up on.
- `--login`; a sign-in page with nobody at the terminal is an exit code, not a crash.
- systemd units: a timer with a random delay, a wrapper that waits for the desktop, a
  failure alert and an evening check that the day was recorded. CI on every push.
- An installable package was declined: one account, one machine at a time.

## Decided since

- **2026-10-02 - the timer fires at 09:30, not 07:30.** The two featured cards on
  /earn rotate between 08:49 and 09:19 local time; a run before that sees the previous
  day's pair, and a run before plus a run after loses a pair outright.
- **2026-10-05 - optional push notifications, Telegram or ntfy, either or both**,
  configured outside the repository (`contrib/systemd/alert.env.example`).
- **2026-10-05 - a report to the phone after every run, with the figures**: times,
  per-task done and points, totals, every error in full. Shaped for a phone screen
  (aligned lines under thirty characters). The failure alert still carries no figures.
- **2026-10-11 - an item that fails twice is a warning, not a flag.** Any failed item
  is retried once; if the retry fails too, the daily report lists it as a warning and
  the day stays clean. Reason: a retry has usually fixed it. A task of two or more
  items with none done, a task that earns nothing, an unreadable total, a crash or a
  sign-in still flag (`MIN_ITEMS_FOR_BREAKAGE`). The accepted cost: on a one-item day a
  broken page and an unlucky card look the same.
- **2026-10-21 - the units name no paths** (`bd539dd`): linked, not copied, using
  systemd's `%Y` and `%h`, so a clone can live anywhere.
- **2026-10-26 - the daily run moves to a Raspberry Pi 4**; the desktop's timers are
  disabled. Only one machine has enabled timers at a time. Setup: `docs/raspberry-pi.md`.
- **2026-10-26 - `monitor.py` removed** (`f06dcd8`). The daily report says what each
  run did. Kept: `recon.py`, the diagnostic for the next page redesign, and
  `explore_on_bing.py`, the way to retry the tiles alone.
- **2026-10-27 - Bing's cookie banner.** A fresh profile earned nothing from search
  until the banner was answered (`docs/DEVELOP.md`). Prevention, one change at a time
  after a clean stretch: `--login` has the person answer it (`e74de06`); the search
  task looks for it before searching and stops with an error that names it
  (`d051bd5`).
- **2026-11-18 - a second run is harmless and visible.** It makes no searches when the
  day already has `DAILY_SEARCH_MIN` credited, and says so in the report (`4dc8783`);
  the report names the machine that ran (`cba1235`), first label of the host name only.
  A switch script for moving between machines was declined: disable on the old machine,
  stamp the new one if the day already ran (README, Automation).
- **2026-11-18 - smaller fixes**: no `notify-send` where the desktop has no
  notification service (`27ab407`); the side tools use the bot's `sign_in_required()`
  (`67f8937`).
- **2026-11-19 - the Pi's journal stays in RAM** (Raspberry Pi OS's default). After the
  2026-11-01 power cut it would have shown only the log stopping; its cost in SD card
  writes is unmeasured. Reopen only after an outage that a power cut does not explain.
- **2026-11-19 - development notes made public in condensed form**: findings in
  `docs/DEVELOP.md`, decisions here, the Pi in `docs/raspberry-pi.md`; no account
  figures in any of them.

## Next, one at a time, after a clean week

1. A wider inter-search gap (community defaults run minutes; this runs about 15 s
   median).
2. An occasional click on a result rather than a scroll alone.
3. Q8, the `Edge` 0/30 counter (`docs/DEVELOP.md`).

## Known weak spots, not fixed

- Keep-earning's fallback for a card it cannot find is direct navigation, which has
  never completed anything (0 for 12). When touched: bounded wait, one reload, then
  "card not found", never a `goto`.
- A card that is not on the page when the run happens is invisible to it: nothing
  outstanding, nothing to fail, no flag. The 09:30 timer removes the known cause, not
  the blindness.

## Not planned

- Multi-account, VPN or proxy (ruled out 2026-09-16): the most cited causes of
  suspension; see `docs/DESIGN.md`.
- Real quiz answering: quizzes pay for wrong answers too, and the gain is small.
- WebMCP (evaluated 2026-09-05): it needs the site to declare its tools, and Rewards
  never will; the dashboard's own state, already parsed, is the same idea.
- Headless mode and stealth patches (`docs/DESIGN.md`, Ruled out).

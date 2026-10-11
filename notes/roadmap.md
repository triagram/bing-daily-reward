# Roadmap

Decisions about what comes next, so they are not re-litigated. Dated when made.

## Done (v1.0.0, 2026-09-26)

- Closed-loop point verification through the dashboard's own state; structured task
  results; verdicts on a run (`shortfall.py`) and one flag judgement (`flags_for()`).
- Cards re-queried per iteration and identified by offer id; the day's offers filtered
  by date.
- Idempotent re-runs for the flag-gated tasks; the claim step; retries with backoff.
- Explore on Bing inside the daily run, behind `RUN_EXPLORE_ON_BING`, with its
  searches reserved from the allowance and a shelf for topics given up on.
- `--login`; a sign-in page with no terminal is an exit code, not a crash.
- The daily log written by the bot itself; a flagged run exits 2.
- The profile lock shared with the monitor; the bot waits instead of crashing.
- systemd units: timer with random delay, wait-for-display wrapper, failure alert,
  evening absence check; desktop notification plus ntfy or Telegram.
- CI on every push.
- Tidy-up (2026-09-26): `legacy/` and `experiments/` removed (git history keeps them),
  dead constants dropped. This is what "packaging" turned out to mean; an installable
  package was declined — one machine, one account, absolute paths in the units.

## Decided since v1.0.0

- **2026-10-02 — the timer fires at 09:30, not 07:30** (plus the same 0–3 h spread).
  Reason: the two featured-topic cards on /earn rotate between 08:49 and 09:19 local, a
  run before that sees only the previous day's pair, and a before-run followed by an
  after-run loses a pair outright (09-25/26, 20 points). 09:30–12:30 is also the
  observation window's regime, 14 for 14 clean. Winter time moves the rotation earlier
  in local terms, so the hour holds through the clock change. Scheduling only — nothing
  about what the bot does on the page changed, so the one-at-a-time list below is not
  consumed by it.
- **2026-10-05 — push notifications go through Telegram.** BotFather accepted a new bot for the
  account (it had refused on 2026-09-26, `NEWBOT_BLOCKED`); the token and chat id live
  in `~/.config/bing-daily-reward/alert.env`, outside the repository, and the test line
  arrived on the phone. The chat id is the `chat.id` field of `getUpdates`, not
  `update_id` — the first attempt used the wrong one and got 400. By decision the same
  day, the push is an **optional layer with two equal channels**, chosen per
  installation: Telegram or ntfy, either or both. This installation uses Telegram; its
  ntfy line was dropped the same evening, once the first report had arrived on the
  phone, so a day is one copy of each message. Nothing about ntfy needed keeping — the
  topic name was its only secret. Template: `contrib/systemd/alert.env.example`.
- **2026-10-05 — a report to the phone after every run, with the figures.** Asked for
  by the account holder, who wants the end-of-run table plus times and every error in
  full, which supersedes the earlier rule that no push carries a point figure (the
  failure sentence still carries none). Rendered by `rewards_bot.py --report` from
  `runs.jsonl`, sent by `rewards-alert.sh report` under `ExecStopPost=`, phone only.
  Shaped for Telegram's monospace block on a phone: aligned lines under thirty
  characters, long detail below. The account holder's stated fallback, if the table
  cannot be made to render across phone and desktop clients, is to drop the table;
  the proposed shape of that is one `label value` line per task, unaligned, which no
  client can break — not yet needed, not yet agreed. On a flagged day the report
  replaces the phone copy of the failure sentence.
- **2026-10-11 — a failure that keeps coming back at random is a warning, not an
  error.** The account holder's rule, stated after the `jewelry` failure: once a kind of
  failure has been seen enough times to be sure it cannot be reliably fixed (likely
  Microsoft's side), report it as a warning rather than a flag; missing one Explore tile
  is acceptable. It was remembered as agreed earlier, but nothing on record said it —
  the nearest thing is the shelf (`SHELVED_TOPICS`), which goes further: a shelved topic
  is not attempted at all. **Not implemented, because nothing qualifies yet.** Of the 14
  tile failures since 08-25: 8 were followed by a pass once the query named something
  concrete (whether the wording or the second attempt did it is unseparated for most,
  see DEVELOP.md); 2 were the parser gap of 2026-10-11; 1, `personalloan` 09-28, same
  words failing then passing, was fixed by a plain retry; the last 3 are `lyrics`,
  already on the shelf, which never flags. So every topic that has failed now
  completes except the one already shelved, and each flag so far led to a fix. The rule
  applies from the first topic that fails repeatedly with nothing found to fix it. Its
  shape then is a warn-only list beside the shelf: attempted, a failure shown in the
  daily report, no exit 2 and no alert.
  **Refined the same evening, superseding "seen enough times":** whenever an item fails,
  retry it once; if the retry fails too, it is a warning, not an error. The account
  holder's reason: a retry has usually fixed it. The ledger half-agrees — 8 of 11
  same-day retries passed, but 7 of those also changed the query; with the same words
  it is 1 for 2 (`personalloan` ✓, `recipe` ✗). Item-level only: a task that earns
  nothing, an unreadable total, a crash or a sign-in stays an error. **Implemented the
  same evening, on the account holder's go-ahead:** the daily set retries any failure
  at once, as it already did for one kind; keep-earning and Explore retry after the
  late-credit wait, then wait again; an Explore retry is skipped when it would leave
  fewer than one search in the day's allowance, and that tile is a warning too. It also
  retires the 20:00 re-check proposed for the late credits of 10-01 and 10-04: an offer
  whose credit lags past its retry is now a warning, not an alert.
  **Relaxed the same evening, by the account holder's choice:** a task with only one
  item that fails its retry is a warning too; "nothing done" flags only from two items
  up (`MIN_ITEMS_FOR_BREAKAGE`). The cost, stated before the choice: on a one-item day
  a broken page and a lone unlucky card look the same, and now both are only a warning.

## Next, one at a time, after a clean week under the timer

1. Wider inter-search gap (community defaults run minutes; this runs ~15 s median).
2. An occasional click on a result rather than a scroll alone.
3. Q8 — the `Edge` 0/30 counter, the largest unexplored surface on the account.

## Known weak spot, not fixed

- Keep-earning's fallback for a card it cannot find is direct navigation, which is
  0 for 12 lifetime. When touched: bounded wait, one reload, then "card not found" —
  never a `goto`.
- A card that is not on the page when the run happens is invisible to the run: nothing
  outstanding, nothing to fail, no flag. A pair lost to timing (09-25/26) is therefore
  silent; only the monitor's samples show it afterwards. The 09:30 timer removes the
  known cause, not the blindness.

## Not planned

- Multi-account, VPN/proxy (ruled out 2026-09-16 — see `CLAUDE.md`).
- Real quiz answering — quizzes pay for wrong answers; the gain is small.
- pip/uv packaging.

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
- **2026-10-05 — the phone push is Telegram.** BotFather accepted a new bot for the
  account (it had refused on 2026-09-26, `NEWBOT_BLOCKED`); the token and chat id live
  in `~/.config/bing-daily-reward/alert.env`, outside the repository, and the test line
  arrived on the phone. The chat id is the `chat.id` field of `getUpdates`, not
  `update_id` — the first attempt used the wrong one and got 400. By decision the same
  day, the push is an **optional layer with two equal channels**, chosen per
  installation: Telegram or ntfy, either or both; this installation uses Telegram and
  may keep or drop the ntfy line at will. Nothing about ntfy needs keeping — the topic
  name was its only secret. Template: `contrib/systemd/alert.env.example`.
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

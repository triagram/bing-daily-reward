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

## Next, one at a time, after a clean week under the timer

1. Wider inter-search gap (community defaults run minutes; this runs ~15 s median).
2. An occasional click on a result rather than a scroll alone.
3. Q8 — the `Edge` 0/30 counter, the largest unexplored surface on the account.

## Pending on the outside

- Telegram push: the account is refused new bots (`NEWBOT_BLOCKED`, 2026-09-26). ntfy
  is in use meanwhile; both channels are wired.

## Known weak spot, not fixed

- Keep-earning's fallback for a card it cannot find is direct navigation, which is
  0 for 12 lifetime. When touched: bounded wait, one reload, then "card not found" —
  never a `goto`.

## Not planned

- Multi-account, VPN/proxy (ruled out 2026-09-16 — see `CLAUDE.md`).
- Real quiz answering — quizzes pay for wrong answers; the gain is small.
- pip/uv packaging.

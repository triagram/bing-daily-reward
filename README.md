# Bing Daily Reward Automation

> Runs your Microsoft Rewards daily tasks in a real browser, measures what they
> earned, and tells you only when something went wrong.

Microsoft Rewards pays points for a handful of repetitive daily actions: the three
"Daily set" cards, a batch of Bing searches, the "Keep earning" offers and the
"Explore on Bing" tiles. This project drives a real Chromium window through all four
with [Playwright](https://playwright.dev/python/), reusing a persistent browser profile
so you sign in once. Every task reads the dashboard's own state, confirms each item
individually, and reports the point delta it actually measured — or says "unknown"
rather than inventing a number. Verified against a live account; the parser and the
behavioural choices are covered by an offline test suite.

Once installed it runs itself: a systemd user timer starts it every morning at a
random time, and a day that is not clean becomes a desktop notification and,
optionally, a message on your phone.

- **How it is built and why:** [docs/DESIGN.md](docs/DESIGN.md)
- **What the dashboard actually returns, open questions, findings:** [docs/DEVELOP.md](docs/DEVELOP.md)
- **Scheduling and alerts in detail:** [contrib/systemd/README.md](contrib/systemd/README.md)

---

## Install

Requirements: Python 3.13+, [uv](https://docs.astral.sh/uv/), and — for scheduled
operation — a Linux desktop session managed by systemd (the bot opens a real window).

```bash
git clone https://github.com/triagram/bing-daily-reward.git
cd bing-daily-reward
uv sync                              # virtual environment and dependencies
uv run playwright install chromium   # the browser build Playwright drives
```

> [!IMPORTANT]
> The second step is easy to miss and does not fail loudly: `uv sync` installs the
> Playwright *library*, not the *browser*. Skipping it produces an "Executable doesn't
> exist" error at launch. `playwright` is pinned to an exact version for the same
> reason — each release expects a matching Chromium build.

## Sign in once

```bash
uv run python rewards_bot.py --login
```

A Chromium window opens on the Rewards dashboard. Sign in there; the command confirms
the session works by reading your balance, then exits. The session lives in
`browser_session/` and is reused from then on.

> [!CAUTION]
> **`browser_session/` must never be committed or shared.** It is a live Chromium
> profile holding your Microsoft session cookies, which on Linux are trivially readable
> by anyone who obtains the directory. It is git-ignored; keep it that way.

## Run it

By hand, once, to see it work:

```bash
uv run python rewards_bot.py
```

The four tasks run in sequence — Daily set, searches, Keep earning, Explore on Bing —
then the "Ready to claim" pot is collected. A run takes about ten minutes, most of it
deliberate pacing between searches. It ends with a table of measured points per task.

**Do not run it a second time on a day that was clean.** The tasks that read
completion flags are idempotent, but the search task draws a fresh count and adds it,
stopping only four searches short of the quota. Nothing is lost, but the day ends with
two bursts and a near-full allowance, which is the pattern the varying count exists to
avoid. Repeat a failed run; leave a clean one alone.

## Let it run itself

```bash
cp contrib/systemd/rewards-*.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now rewards-bot.timer rewards-check.timer
```

`rewards-bot.timer` fires at 09:30 local plus a random delay of up to three hours,
then waits for your desktop session if you are not logged in yet. Leave the window it
opens alone — tabs to instagram.com or tiktok.com are it working a "follow us" offer.
`rewards-check.timer` asks at 20:00 whether today was recorded at all. Details,
including the phone push, are in [contrib/systemd/README.md](contrib/systemd/README.md).

You will hear from it only when something is wrong:

| Notification | Meaning | What to do |
|---|---|---|
| *Today's run finished with flags — read logs/observation/\<date\>.log* | It ran, but a task earned nothing or too little, recorded an error, or did less than it attempted | Read the day's log; usually an Explore tile whose query has not been learned |
| *Sign-in required — run: uv run python rewards_bot.py --login* | The session lapsed | Run `--login` in a terminal |
| *Browser profile was busy for five minutes* | Something else holds `browser_session/` — usually a window left open | Close it |
| *No desktop session this morning* | Nobody was logged in for three hours after the trigger; nothing was done | Log in and run `rewards_bot.py` by hand — this day has not run |
| *Today's run crashed (exit N)* | An unhandled error: page redesign, browser failed to start, network | `journalctl --user -u rewards-bot.service` |
| *No run recorded today* (20:00) | The timer did not fire, or the machine was off | If the machine was on, look at the journal |

A clean day sends nothing. So does a machine that is off all day — the evening check
can only run on a machine that is on.

## Look at what happened

```bash
uv run python rewards_bot.py --history       # every recorded run, per task, with flags
uv run python rewards_bot.py --dry-run       # read today's state, change nothing
uv run python explore_on_bing.py --dry-run   # which Explore tiles are open, and what would be searched
uv run python explore_on_bing.py             # retry the Explore tiles alone — after a failed day, not a clean one
uv run python monitor.py --history           # the read-only state samples
```

Every run appends one line to `logs/runs.jsonl` and everything it printed to
`logs/observation/<date>.log`. `--history` renders the records, one row per run with
the time it finished; its `Flags` column is the one to read — empty means clean.
`logs/` and `captures/` are git-ignored.

The timer's own view of the same days:

```bash
systemctl --user list-timers 'rewards-*'                          # last and next trigger
journalctl --user -u rewards-bot.service -S -7d --no-pager \
  | grep -E "Starting|Finished|Failed|Flags"                       # start, end, outcome per day
```

## Configuration

Everything tunable is in `config.py`:

| Constant | Default | Meaning |
|---|---|---|
| `DAILY_SEARCH_MIN` / `MAX` | `8` / `12` | Range the day's search count is drawn from — deliberately short of the allowance, and different every day |
| `DAILY_SEARCH_ALLOWANCE` / `POINTS_PER_SEARCH` | `20` / `3` | The measured ceiling. The run reads the day's real figure from the dashboard; these document it and anchor the tests |
| `KEEP_EARNING_MAX_PER_RUN` | `6` | Most Keep-earning offers in one run |
| `RUN_EXPLORE_ON_BING` | `True` | Work the Explore on Bing tiles inside the daily run |
| `EXPLORE_ON_BING_TILES_PER_DAY` | `4` | Searches held back from the allowance for the tiles |
| `HEADLESS` | `False` | Run without a window. Untested against Microsoft's detection; leave it |

Point values and allowances differ by market; the ones here were measured on the
account this was built against.

## Limitations

- **Signing in is a person's job.** A scheduled run that meets the sign-in page stops
  and tells you, rather than waiting on a prompt nobody will answer.
- **Headless mode is untested.** It launches, but its detectability has not been
  checked. The scheduled run uses a real window inside your desktop session.
- **Quizzes are answered by clicking the first option.** They pay for wrong answers
  too, but less.
- **Selectors will break** when Microsoft redesigns the dashboard. Reading the page's
  own state is far more durable than matching CSS, but that state is not a published
  contract either.
- **Single account, no VPN or proxy — permanently.** Both are the most-cited causes of
  suspension, and neither will be made easy here.

## Tests

```bash
uv run pytest -q
```

The suite parses an archived page and never opens a browser or touches an account, so
it is free to run — and proves nothing about a live run. CI runs it on every push.

---

## Disclaimer

Automating Microsoft Rewards very likely violates the
[Microsoft Rewards Terms of Service](https://www.microsoft.com/rewards/terms).
Accounts found to be using automation can have their points revoked or be suspended
entirely. This project was written as a personal exercise in browser automation. Use
it on your own account, at your own risk, and be aware that the risk includes losing
whatever balance that account has accumulated.

## License

[MIT](LICENSE) © 2026 Triagram

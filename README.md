# Bing Daily Reward Automation

> Does the Microsoft Rewards daily tasks in a real browser, checks what they earned,
> and sends you a short daily report.

Microsoft Rewards gives points for a few repetitive daily actions: the three "Daily
set" cards, a batch of Bing searches, the "Keep earning" offers and the "Explore on
Bing" tiles. This project works through all four in a real Chromium window using
[Playwright](https://playwright.dev/python/). It keeps a persistent browser profile, so
you only sign in once. Each task reads the dashboard's own state, checks every item
individually, and reports the points it actually measured. If a total could not be
read, it says so instead of guessing. The parser and the timing and volume choices have
an offline test suite; the rest was checked against a live account.

It can run on a systemd user timer, every morning at a random time. After each run it
sends a short report as a push notification (Telegram or ntfy), and a desktop
notification if something went wrong.

- **How it is built and why:** [docs/DESIGN.md](docs/DESIGN.md)
- **What the dashboard actually returns, open questions, findings:** [docs/DEVELOP.md](docs/DEVELOP.md)
- **Automation and notifications in detail:** [contrib/systemd/README.md](contrib/systemd/README.md)

---

## Installation

Requirements: Python 3.13+, [uv](https://docs.astral.sh/uv/), and, if you want it to
run on a schedule, a Linux desktop session with systemd user units (the bot opens a
real browser window).

```bash
git clone https://github.com/triagram/bing-daily-reward.git
cd bing-daily-reward
uv sync                              # virtual environment and dependencies
uv run playwright install chromium   # the browser build Playwright drives
```

> [!IMPORTANT]
> Don't skip the second step. `uv sync` installs the Playwright library but not the
> browser, and without it the bot fails at launch with "Executable doesn't exist".
> `playwright` is pinned to an exact version because each release expects a matching
> Chromium build.

## Login

```bash
uv run python rewards_bot.py --login
```

A Chromium window opens on the Rewards dashboard. Sign in there. The command reads your
balance to confirm the session works, then exits. The session is kept in
`browser_session/` and reused after that.

> [!CAUTION]
> Never commit or share `browser_session/`. It is a Chromium profile with your
> Microsoft session cookies, and on Linux anyone who gets the directory can read them.
> It is in `.gitignore`; leave it there.

## Usage

To run it once by hand:

```bash
uv run python rewards_bot.py
```

It does the four tasks in order (Daily set, searches, Keep earning, Explore on Bing),
then claims the "Ready to claim" pot. A run takes about ten minutes, most of it waiting
between searches, and ends with a table of points per task.

**Don't run it twice on a day that went fine.** The other tasks only do what is still
outstanding, but the search task picks a new count each time and adds it, stopping four
searches short of the daily quota. You don't lose anything, but the day ends up with two
bursts of searches and a nearly full quota, which is exactly the pattern the random
count is meant to avoid. Re-run a failed day; leave a clean one alone.

## Automation

```bash
cp contrib/systemd/rewards-*.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now rewards-bot.timer rewards-check.timer
```

`rewards-bot.timer` starts the run at 09:30 local time plus a random delay of up to
three hours. If you are not logged in yet, it waits for your desktop session. Leave the
browser window alone while it runs; a tab opening instagram.com or tiktok.com is the bot
working a "follow us" offer, not a stray click. `rewards-check.timer` checks at 20:00
that today's run was recorded. Details are in
[contrib/systemd/README.md](contrib/systemd/README.md).

After each run it sends a short report as a push notification, if you have set that
up (see below): when it ran, what each task did and earned, the totals, and any errors
in full. On the desktop you only hear from it when something went wrong:

| Notification | Meaning | What to do |
|---|---|---|
| *Today's run finished with flags — read logs/observation/\<date\>.log* | It ran, but a task earned nothing or too little, hit an error, or did less than it attempted | Read the day's log. Often it is an Explore tile whose search phrase isn't known yet |
| *Sign-in required — run: uv run python rewards_bot.py --login* | The session expired | Run `--login` in a terminal |
| *Browser profile was busy for five minutes* | Something else has `browser_session/` open, usually a window left behind | Close it |
| *No desktop session this morning* | Nobody was logged in for three hours after the trigger; nothing was done | Log in and run `rewards_bot.py` by hand; this day has not run |
| *Today's run crashed (exit N)* | An unhandled error: page redesign, browser failed to start, network | `journalctl --user -u rewards-bot.service` |
| *No run recorded today* (20:00) | The timer did not fire, or the machine was off | If the machine was on, look at the journal |

A clean day sends no desktop notification. Neither does a machine that was off all day,
since the evening check can only run if the machine is on.

### Notifications

There are three ways to use this:

1. **Manual**: run `uv run python rewards_bot.py` when you think of it. No timer, no
   notifications; the table at the end is your report.
2. **Automated**: the systemd units above. You get a desktop notification when a day
   fails, and nothing otherwise.
3. **Automated, with push notifications**: the failure notification is also pushed
   through Telegram or ntfy (or both), to whatever devices you have them on, and you
   get a short report after every run, good or bad. The report is the only message
   that includes point numbers.

The settings live in `~/.config/bing-daily-reward/alert.env`, outside the repository.
Copy `contrib/systemd/alert.env.example` there, `chmod 600` it, and fill in one or
both:

- **Telegram**: create a bot with @BotFather (`/newbot`), open the chat it links to and
  press *Start*, and put the token in `TELEGRAM_BOT_TOKEN`. Send the bot any message,
  run `curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates"`, and copy
  the number from `"chat":{"id":…}` (not `update_id`) into `TELEGRAM_CHAT_ID`.
- **ntfy**: pick a long random topic name, subscribe to it in the ntfy app, and put it
  in `NTFY_TOPIC`. No account needed; the topic name is the only secret.

`contrib/systemd/rewards-alert.sh test` then sends a test message to every channel you
configured. A longer walkthrough, including the error codes you might see, is in
[contrib/systemd/README.md](contrib/systemd/README.md#push-notifications).

## Logs

```bash
uv run python rewards_bot.py --history       # every recorded run, per task, with flags
uv run python rewards_bot.py --report        # today's report, as it is pushed (or --report 2026-10-04)
uv run python rewards_bot.py --dry-run       # read today's state, change nothing
uv run python explore_on_bing.py --dry-run   # which Explore tiles are open, and what would be searched
uv run python explore_on_bing.py             # retry the Explore tiles alone, after a failed day, not a clean one
uv run python monitor.py --history           # the read-only state samples
```

Each run adds one line to `logs/runs.jsonl` and saves everything it printed to
`logs/observation/<date>.log`. `--history` shows the records, one row per run with the
finishing time. The `Flags` column is the one to look at: empty means clean. `logs/`
and `captures/` are git-ignored.

The same days as systemd saw them:

```bash
systemctl --user list-timers 'rewards-*'                          # last and next trigger
journalctl --user -u rewards-bot.service -S -7d --no-pager \
  | grep -E "Starting|Finished|Failed|Flags"                       # start, end, outcome per day
```

## Configuration

Everything tunable is in `config.py`:

| Constant | Default | Meaning |
|---|---|---|
| `DAILY_SEARCH_MIN` / `MAX` | `8` / `12` | Range the day's search count is picked from. Deliberately below the quota, and different every day |
| `DAILY_SEARCH_ALLOWANCE` / `POINTS_PER_SEARCH` | `20` / `3` | The measured daily quota. The run reads the real figure from the dashboard; these constants document it and are used by the tests |
| `KEEP_EARNING_MAX_PER_RUN` | `6` | Maximum number of Keep earning offers per run |
| `RUN_EXPLORE_ON_BING` | `True` | Do the Explore on Bing tiles as part of the daily run |
| `EXPLORE_ON_BING_TILES_PER_DAY` | `4` | Searches kept back from the quota for the tiles |
| `HEADLESS` | `False` | Run without a window. Not tested against Microsoft's detection; leave it off |

Point values and quotas differ by market; the ones here were measured on the account
this was built against.

## Limitations

- **Signing in has to be done by hand.** A scheduled run that lands on the sign-in page
  stops and tells you, instead of waiting at a prompt nobody will answer.
- **Headless mode is untested.** It starts, but nobody has checked whether Microsoft
  detects it. The scheduled run uses a real window in your desktop session.
- **Quizzes are answered by clicking the first option.** They pay for wrong answers
  too, but less.
- **Selectors will break** when Microsoft redesigns the dashboard. Reading the page's
  own state lasts longer than matching CSS classes, but it isn't a published API
  either.
- **One account, no VPN or proxy, and that won't change.** Both are the most commonly
  reported causes of suspension, and this project won't make either easy.

## Testing

```bash
uv run pytest -q
```

The suite parses an archived copy of the page. It never opens a browser or touches an
account, so it is safe to run anywhere, but it also proves nothing about a live run. CI
runs it on every push.

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

# Scheduling

Two things run on a timer here: the read-only monitor (below, the original), and since
2026-09-17 the daily run itself. Both are user units — no root, nothing system-wide.

## The daily run

`rewards-bot.timer` fires at 09:30 local and adds a random delay of up to three hours,
so the run starts somewhere in 09:30–12:30, different every day — after the featured
cards on /earn have rotated, which they do between 08:49 and 09:19 local; a run before
that only sees the previous day's pair. `rewards-bot.service`
runs `rewards_bot.py`, which writes `logs/observation/<date>.log` itself and exits
non-zero when the day is not clean; `OnFailure=` then runs `rewards-alert.service`,
which turns the exit code into a sentence and shows it as a desktop notification.
`ExecStopPost=` runs `rewards-alert.sh report` after every exit: the day's report,
rendered by `rewards_bot.py --report` from the run just recorded, to the phone
channels below. A run that stopped before recording anything has no report, and the
failure sentence speaks for it.
`rewards-check.timer` is the other half: at 20:00 it asks whether today was recorded at
all, because a run that never started cannot report its own absence.

```bash
cp rewards-bot.{service,timer} rewards-alert.service rewards-check.{service,timer} \
   ~/.config/systemd/user/
systemctl --user daemon-reload

systemctl --user start rewards-bot.service      # one run now, while you watch
journalctl --user -u rewards-bot.service -f     # ... and its output

systemctl --user enable --now rewards-bot.timer rewards-check.timer
systemctl --user list-timers 'rewards-*'        # when each next fires
```

**Linger is on for this user** (the monitor needs it), so the bot's timer fires whether
or not you are logged in — and the bot opens a real window, which needs your desktop
session. `rewards-bot.service` therefore runs through `run-with-display.sh`: it waits
up to three hours for the session's display to answer, re-reading `DISPLAY` from the
user manager each minute (a fresh login re-imports it), then runs the bot in it. Log
in at 09:15 and the run starts within the minute; stay away all morning and it exits
5, which the alert words as "no desktop session this morning". A day the machine was
off is caught up at boot (`Persistent=true`) and then waits for you the same way.

Enabling the timer for the first time after 09:30 fires a catch-up run at once, and so
does moving `OnCalendar=` to a time that has already passed today. To skip that, stamp
the timer as already run today before enabling (or restarting) it:
`mkdir -p ~/.local/share/systemd/timers && touch ~/.local/share/systemd/timers/stamp-rewards-bot.timer`.

```bash
./rewards-alert.sh missing                       # silent if today is recorded
systemctl --user disable --now rewards-bot.timer # stop scheduling the run
```

## Phone push (optional)

Alerts are worded and sent in one place, `rewards-alert.sh`. The desktop notification
is unconditional — the run needs the desktop session anyway, so if the notification
cannot reach you, neither could the run. A phone push is added on top, through one or
both of two channels, chosen per installation, and carries two kinds of message:

- **The failure sentence**, the same one the desktop shows, never with a point figure.
- **The day's report**, after every run, clean or not: times, each task's done count
  and points, the totals, and every error in full with its task and offer. Shaped for
  a phone — aligned lines under thirty characters, long detail below them. On Telegram
  it goes as a monospace block; ntfy shows it in a proportional font, so its columns
  come out ragged there. On a flagged day the report replaces the phone copy of the
  failure sentence, so a day is one push either way. `uv run python rewards_bot.py
  --report` prints what would be sent, from `logs/runs.jsonl`, without sending.

Configuration is `~/.config/bing-daily-reward/alert.env`, outside the repository, read
as shell (`NAME=value`, no spaces, no quotes). Start from the template:

```bash
mkdir -p ~/.config/bing-daily-reward
cp alert.env.example ~/.config/bing-daily-reward/alert.env
chmod 600 ~/.config/bing-daily-reward/alert.env
```

**Telegram.** Message @BotFather: `/newbot`, a display name, then a username ending in
`bot`. It answers with the token — a password; it lives in this file and nowhere else.
Open the `t.me/…` link in that answer and press *Start*: a bot cannot message someone
who has never messaged it. Put the token in `TELEGRAM_BOT_TOKEN`, send the bot any
message, then ask it who wrote:

```bash
. ~/.config/bing-daily-reward/alert.env && \
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates"
```

The number at `"chat":{"id":…}` is `TELEGRAM_CHAT_ID`. Not `update_id` — that is the
message's serial number, and using it gets `400 chat not found`. An empty `result`
means the bot has not received your message yet.

**ntfy.** Pick a long random topic name, subscribe to it in the ntfy app, put it in
`NTFY_TOPIC`. No account, no token: the name is the only secret, and dropping the
channel later means deleting the line and unsubscribing — nothing to keep.

**Test**, through every configured channel at once:

```bash
./rewards-alert.sh test
```

The script swallows delivery errors on purpose — an alert must not fail by alerting —
so if nothing arrives, send one message by hand and read the server's answer:

```bash
. ~/.config/bing-daily-reward/alert.env && \
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
     --data-urlencode "chat_id=$TELEGRAM_CHAT_ID" --data-urlencode "text=test"
```

| Answer | Cause |
|---|---|
| `401 Unauthorized` | the token is wrong |
| `400 Bad Request: chat not found` | wrong chat id, or *Start* was never pressed |
| `403 Forbidden: bot was blocked by the user` | unblock the bot in its chat |

The bot and the monitor share one browser profile. The monitor skips a sample while
the bot holds it; the bot waits up to five minutes for the monitor, which holds it for
seconds. Neither needs the other to be running.

## Scheduled sampling

`monitor.py` is worth running on a schedule rather than by hand — the questions in
[../../docs/DEVELOP.md](../../docs/DEVELOP.md#open-questions) are about change over
time, and change needs regular observations.

```bash
cp rewards-monitor.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now rewards-monitor.timer

# Run when not logged in
loginctl enable-linger "$USER"
```

Adjust `WorkingDirectory` and the `uv` path in the service file if the repository
lives elsewhere.

```bash
systemctl --user list-timers rewards-monitor.timer   # when it next fires
journalctl --user -u rewards-monitor.service -n 30   # what it did
systemctl --user start rewards-monitor.service       # sample now
systemctl --user disable --now rewards-monitor.timer # stop scheduling
```

Four samples a day bracket the daily reset and give enough resolution to see credit
arriving late. Once the reset time is pinned down, one a day is plenty.

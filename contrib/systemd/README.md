# Scheduling

Two things run on a timer here: the read-only monitor (below, the original), and since
2026-09-17 the daily run itself. Both are user units — no root, nothing system-wide.

## The daily run

`rewards-bot.timer` fires at 07:30 local and adds a random delay of up to three hours,
so the run starts somewhere in 07:30–10:30, different every day. `rewards-bot.service`
runs `rewards_bot.py`, which writes `logs/observation/<date>.log` itself and exits
non-zero when the day is not clean; `OnFailure=` then runs `rewards-alert.service`,
which turns the exit code into a sentence and shows it as a desktop notification.
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

**Do not `enable-linger` for the bot.** It opens a real browser window, which needs
your desktop session; the user manager only carries `DISPLAY` while you are logged in.
With linger the timer would fire while you are logged out, the launch would fail, and
the alert would be a false one. Without it, a day you were logged out is a day that
did not run, and `Persistent=true` runs it at your next login.

Alerts are worded and sent in one place, `rewards-alert.sh`. The desktop notification
is unconditional. To add a phone push, create `~/.config/bing-daily-reward/alert.env`
containing `NTFY_TOPIC=<a long random topic name>` and subscribe to that topic in the
ntfy app; the file is outside the repository, and the topic name is the only secret.

```bash
./rewards-alert.sh missing                       # silent if today is recorded
systemctl --user disable --now rewards-bot.timer # stop scheduling the run
```

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

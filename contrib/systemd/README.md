# Scheduled sampling

`monitor.py` is worth running on a schedule rather than by hand — the questions in
[../../docs/DEVELOP.md](../../docs/DEVELOP.md#open-questions) are about change over
time, and change needs regular observations.

These are user units, so no root is involved and nothing is installed system-wide.

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

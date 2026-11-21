# Running on a Raspberry Pi

The daily run has lived on a Raspberry Pi 4 since 2026-10-26. This is what it needed
beyond the README, and what it taught.

## System

- A Pi 4 with 4 GB of RAM, on Raspberry Pi OS bookworm, 64-bit. A Pi 3 (1 GB) is too
  small for Chromium.
- The README's installation steps work as written. `uv sync` fetches Python 3.13 (the
  system has 3.12). Install the browser with its system libraries:
  `uv run playwright install --with-deps chromium`.
- `sudo loginctl enable-linger "$USER"`, so the user's timers run from boot.
- Keep it up to date with `sudo apt full-upgrade` about monthly, outside 09:30-12:30.
  Debian 12 is on LTS until 2028-06-30; install a newer release before then.

## A desktop that logs itself in

The bot opens a real browser window, so the Pi has to boot into a desktop session.

- On an image without the desktop, install `raspberrypi-ui-mods`.
- Autologin into the Wayland (labwc) session, run as the user who will run the bot:
  `sudo raspi-config nonint do_wayland W3` and
  `sudo raspi-config nonint do_boot_behaviour B4`. raspi-config takes the user from
  `SUDO_USER`, so not from a root shell.
- Stay on Wayland: Raspberry Pi Connect screen-shares only Wayland, and `--login`
  needs the window seen.

## No monitor

Without a screen the HDMI output stays off and the browser has nowhere to draw. Force
it on by adding `video=HDMI-A-1:1920x1080M@60D` to the single line in
`/boot/firmware/cmdline.txt`, or plug in a dummy HDMI adapter. Check the file first:
ours arrived empty, and the Pi had booted on the firmware's fallback line.

## Remote access

- Raspberry Pi Connect is enough: a remote shell, and screen sharing for `--login`.
  It must be the full `rpi-connect`; `rpi-connect-lite` has no screen sharing.
- **Never purge `rpi-connect-lite` after the swap.** Its purge removes
  `~/.config/systemd/user/default.target.wants/rpi-connect.service`, which the full
  package also starts from, and Connect does not come back after the next reboot.
- The swap stops Connect mid-install, and with it the shell you typed the command in.
  Run it detached, so a dropped shell cannot interrupt the package manager:
  `sudo systemd-run --unit=<name> --collect /bin/sh <script>`, logging to a file.
  Afterwards `rpi-connect on` turned screen sharing on.
- Sign in from the Connect shell, watching through screen sharing:
  `DISPLAY=:0 ~/.local/bin/uv run python rewards_bot.py --login`.

## Logs

- Raspberry Pi OS keeps the system journal in RAM (`Storage=volatile`, set by its
  image builder), so nothing in it survives a reboot, and `journalctl --user` finds
  nothing. For the current boot:
  `sudo journalctl -b 0 -o short-iso --no-pager | grep -E 'rewards-bot\.(timer|service)'`.
  The bot's own `logs/` are on the card and survive. The journal was left in RAM on
  purpose (`notes/roadmap.md`, 2026-11-19).
- The desktop has no notification service, so alerts reach the phone only.

## After a power cut

- The Pi has no clock that runs unpowered. It boots on the last saved time
  (fake-hwclock, hourly) and runs on it until the network corrects it. Read boot times
  from `uptime -s`, not from `last`, which stamps a boot with the restored time.
- The timer is `Persistent=true`, so a day missed while the power was off runs once it
  is back, within the three-hour random delay. Seen once (2026-11-01): the report came
  in the evening, and it was the day's only run.

## Moving the run onto the Pi

One machine with enabled timers at a time. Disable them on the old one first. Then, on
the Pi: install, `alert.env` and `contrib/systemd/rewards-alert.sh test`, `--login`
(answer Bing's cookie banner if it shows), and the README's three Automation lines. Do
it before 09:30 with no stamp, or after 20:00 with one: the evening check is not
persistent, so in between it reads an empty log and reports a day that ran elsewhere.

## Risks accepted

- No SD card image. Little lives on the card, so a dead card means a fresh install from
  this page. A run touches about 54 MB of the browser profile, so wear is negligible;
  corruption from power loss or the card itself is the real risk.
- The card holds the Microsoft session and the alert token, and the desktop logs itself
  in. Keep the Pi where only you can reach it.
- A dead Pi is silent, because the evening check runs on it too. No report by about
  13:00 is the alarm.

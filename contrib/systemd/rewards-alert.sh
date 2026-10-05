#!/bin/sh
# The one place anything is worded and sent. Four callers:
#
#   rewards-alert.sh failed <unit>   OnFailure= of the run: turn its exit code into words
#   rewards-alert.sh missing         the evening check: was today recorded at all?
#   rewards-alert.sh report          ExecStopPost= of the run: the day's report
#   rewards-alert.sh test            send one line through every channel, by hand
#
# Delivery: alerts go to the desktop always (the run needs the desktop session anyway,
# so if the notification cannot reach you, neither could the run) and to the phone
# when ~/.config/bing-daily-reward/alert.env, outside this repository, configures a
# channel: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID for Telegram, NTFY_TOPIC for ntfy —
# either, or both. An alert is one sentence and never carries a point figure.
#
# The report is the exception, by the account holder's decision on 2026-10-05: it
# carries the day's figures, goes to the phone only, and is sent after every run.
# The bot renders it (rewards_bot.py --report); this script only delivers it. On a
# flagged day the report already says what the flag is, so "failed 2" keeps the
# desktop notification and skips the phone — one push, not two.
set -u
REPO=/projects/bing-daily-reward
ENV_FILE="$HOME/.config/bing-daily-reward/alert.env"
today=$(date +%F)
# systemd's environment has no ~/.local/bin on PATH; the service names uv by path too.
UV="${UV:-$HOME/.local/bin/uv}"
[ -x "$UV" ] || UV=$(command -v uv) || UV=""

desktop=yes   # notify-send
phone=yes     # the channels in alert.env
mono=no       # send as a monospace block (Telegram <pre>) rather than a sentence

case "${1:-}" in
  failed)
    unit="${2:-rewards-bot.service}"
    code=$(systemctl --user show -p ExecMainStatus --value "$unit")
    case "$code" in
      2) msg="Today's run finished with flags — read logs/observation/$today.log"
         phone=no ;;
      3) msg="Sign-in required — run: uv run python rewards_bot.py --login" ;;
      4) msg="Browser profile was busy for five minutes — is a browser window open?" ;;
      5) msg="No desktop session this morning — the run needs you logged in; it did nothing" ;;
      *) msg="Today's run crashed (exit $code) — journalctl --user -u $unit" ;;
    esac ;;
  test)
    msg="Test message — the alert channel works" ;;
  report)
    # No record for today means the run stopped before recording one (sign-in, busy
    # profile, no desktop); that is the failure alert's business. Say nothing.
    [ -n "$UV" ] || exit 0
    msg=$(cd "$REPO" && "$UV" run python rewards_bot.py --report 2>/dev/null) || exit 0
    [ -n "$msg" ] || exit 0
    desktop=no; mono=yes ;;
  missing)
    # Still running, or already recorded: nothing to say.
    systemctl --user is-active --quiet rewards-bot.service && exit 0
    grep -q "\"date\": \"$today\"" "$REPO/logs/runs.jsonl" 2>/dev/null && exit 0
    msg="No run recorded today — the timer did not fire, or the machine was off" ;;
  *)
    echo "usage: $0 failed <unit> | missing | report | test" >&2; exit 2 ;;
esac

if [ "$desktop" = yes ]; then
  notify-send -u critical "Microsoft Rewards" "$msg" || true
fi
[ "$phone" = yes ] && [ -r "$ENV_FILE" ] || exit 0
. "$ENV_FILE"

if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
  if [ "$mono" = yes ]; then
    # A <pre> block keeps the report's columns aligned on a phone; HTML parse mode
    # needs the three characters it reserves escaped.
    html=$(printf '%s' "$msg" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')
    curl -fsS --max-time 20 "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
      --data-urlencode "chat_id=$TELEGRAM_CHAT_ID" \
      --data-urlencode "parse_mode=HTML" \
      --data-urlencode "text=<pre>$html</pre>" >/dev/null || true
  else
    curl -fsS --max-time 20 "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
      --data-urlencode "chat_id=$TELEGRAM_CHAT_ID" \
      --data-urlencode "text=Microsoft Rewards: $msg" >/dev/null || true
  fi
fi
if [ -n "${NTFY_TOPIC:-}" ]; then
  # ntfy shows this in a proportional font, so the report's columns come out ragged.
  curl -fsS --max-time 20 -H "Title: Microsoft Rewards" -d "$msg" \
    "https://ntfy.sh/$NTFY_TOPIC" >/dev/null || true
fi

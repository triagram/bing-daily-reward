#!/bin/sh
# The one place an alert is worded and sent. Two callers:
#
#   rewards-alert.sh failed <unit>   OnFailure= of the run: turn its exit code into words
#   rewards-alert.sh missing         the evening check: was today recorded at all?
#   rewards-alert.sh test            send one line through every channel, by hand
#
# Delivery: a desktop notification always (the run needs the desktop session anyway,
# so if the notification cannot reach you, neither could the run). A Telegram message
# in addition when ~/.config/bing-daily-reward/alert.env defines TELEGRAM_BOT_TOKEN
# and TELEGRAM_CHAT_ID — the token is a secret, the file is outside this repository,
# and only the sentence below is sent, never a point figure.
set -u
REPO=/projects/bing-daily-reward
ENV_FILE="$HOME/.config/bing-daily-reward/alert.env"
today=$(date +%F)

case "${1:-}" in
  failed)
    unit="${2:-rewards-bot.service}"
    code=$(systemctl --user show -p ExecMainStatus --value "$unit")
    case "$code" in
      2) msg="Today's run finished with flags — read logs/observation/$today.log" ;;
      3) msg="Sign-in required — run: uv run python rewards_bot.py --login" ;;
      4) msg="Browser profile was busy for five minutes — is a browser window open?" ;;
      *) msg="Today's run crashed (exit $code) — journalctl --user -u $unit" ;;
    esac ;;
  test)
    msg="Test message — the alert channel works" ;;
  missing)
    # Still running, or already recorded: nothing to say.
    systemctl --user is-active --quiet rewards-bot.service && exit 0
    grep -q "\"date\": \"$today\"" "$REPO/logs/runs.jsonl" 2>/dev/null && exit 0
    msg="No run recorded today — the timer did not fire, or the machine was off" ;;
  *)
    echo "usage: $0 failed <unit> | missing | test" >&2; exit 2 ;;
esac

notify-send -u critical "Microsoft Rewards" "$msg" || true
if [ -r "$ENV_FILE" ]; then
  . "$ENV_FILE"
  if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    curl -fsS --max-time 20 "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
      --data-urlencode "chat_id=$TELEGRAM_CHAT_ID" \
      --data-urlencode "text=Microsoft Rewards: $msg" >/dev/null || true
  fi
fi

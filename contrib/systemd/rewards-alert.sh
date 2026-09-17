#!/bin/sh
# The one place an alert is worded and sent. Two callers:
#
#   rewards-alert.sh failed <unit>   OnFailure= of the run: turn its exit code into words
#   rewards-alert.sh missing         the evening check: was today recorded at all?
#
# Delivery: a desktop notification always (the run needs the desktop session anyway,
# so if the notification cannot reach you, neither could the run). A phone push in
# addition when ~/.config/bing-daily-reward/alert.env defines NTFY_TOPIC — the topic
# name is the only secret, and it is not in this repository.
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
  missing)
    # Still running, or already recorded: nothing to say.
    systemctl --user is-active --quiet rewards-bot.service && exit 0
    grep -q "\"date\": \"$today\"" "$REPO/logs/runs.jsonl" 2>/dev/null && exit 0
    msg="No run recorded today — the timer did not fire, or the machine was off" ;;
  *)
    echo "usage: $0 failed <unit> | missing" >&2; exit 2 ;;
esac

notify-send -u critical "Microsoft Rewards" "$msg" || true
if [ -r "$ENV_FILE" ]; then
  . "$ENV_FILE"
  if [ -n "${NTFY_TOPIC:-}" ]; then
    curl -fsS -H "Title: Microsoft Rewards" -d "$msg" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null || true
  fi
fi

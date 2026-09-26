#!/bin/sh
# Wait for the desktop session's display, then exec the command given.
#
#   run-with-display.sh /home/mengyuan/.local/bin/uv run python rewards_bot.py
#
# Why this exists: the user manager lingers (the read-only monitor needs it), so the
# bot's timer fires whether or not anyone is logged in — and the bot opens a real
# window. Without this, a logged-out morning is a failed launch, a false "crashed"
# alert, and no catch-up, since the timer did fire. With it, the run waits for you:
# log in at 09:15 and it starts within the minute; stay away all morning and it
# stops with exit 5, which the alert turns into "no desktop session this morning".
#
# The manager's DISPLAY is re-read on every poll rather than taken once at start:
# a new login re-imports it, and a wait that began before the login would otherwise
# hold a stale value forever.
#
# Testing seams: DISPLAY_WAIT_S (window, default three hours), POLL_S, and
# DISPLAY_PROBE (default `xset q`; `false` forces the no-display path).
set -u
WINDOW_S=${DISPLAY_WAIT_S:-10800}
POLL_S=${POLL_S:-60}
PROBE=${DISPLAY_PROBE:-xset q}
EXIT_NO_DISPLAY=5

[ $# -ge 1 ] || { echo "usage: $0 <command...>" >&2; exit 2; }
deadline=$(( $(date +%s) + WINDOW_S ))

while :; do
  session_display=$(systemctl --user show-environment 2>/dev/null | sed -n 's/^DISPLAY=//p')
  session_xauth=$(systemctl --user show-environment 2>/dev/null | sed -n 's/^XAUTHORITY=//p')
  if [ -n "$session_display" ] \
     && DISPLAY="$session_display" XAUTHORITY="$session_xauth" $PROBE >/dev/null 2>&1; then
    export DISPLAY="$session_display"
    [ -n "$session_xauth" ] && export XAUTHORITY="$session_xauth"
    exec "$@"
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "No desktop session answered within ${WINDOW_S}s — nobody logged in; nothing was done." >&2
    exit $EXIT_NO_DISPLAY
  fi
  sleep "$POLL_S"
done

"""
One Chromium process per profile.

Chromium refuses to open a user-data-dir another process holds, and marks the hold
with two files inside it. The scheduled run shares `browser_session/` with the tools
run by hand (`--dry-run`, `explore_on_bing.py`, `recon.py`), and one of them may be
finishing when the timer fires. The bot cannot skip a day cheaply, so it waits.
"""

import asyncio
from pathlib import Path

LOCK_FILES = ("SingletonLock", "SingletonSocket")


def profile_in_use(user_data_dir: Path) -> bool:
    """True when something already has the browser profile open."""
    return any((user_data_dir / name).exists() for name in LOCK_FILES)


async def wait_for_profile(user_data_dir: Path, max_wait_s: float = 300.0,
                           poll_s: float = 5.0) -> bool:
    """
    Wait for the profile to be free. True once it is; False if it stayed held for
    `max_wait_s` - which means a browser window or another run is open.
    """
    waited = 0.0
    while profile_in_use(user_data_dir):
        if waited >= max_wait_s:
            return False
        await asyncio.sleep(poll_s)
        waited += poll_s
    return True

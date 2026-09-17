"""
One Chromium process per profile.

Chromium refuses to open a user-data-dir another process holds, and marks the hold
with two files inside it. Two things share `browser_session/`: the daily run and the
read-only monitor, and on a schedule their windows overlap. The monitor skips when the
profile is busy — its next sample is hours away. The bot cannot skip a day so cheaply,
so it waits: the monitor holds the profile for seconds.
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
    `max_wait_s` — which means a browser or another run is open, not the monitor.
    """
    waited = 0.0
    while profile_in_use(user_data_dir):
        if waited >= max_wait_s:
            return False
        await asyncio.sleep(poll_s)
        waited += poll_s
    return True

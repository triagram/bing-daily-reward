"""
Two processes, one browser profile: the bot must wait for the monitor, not crash.
"""

import asyncio

from utils.profile_lock import profile_in_use, wait_for_profile


def test_a_profile_with_no_lock_files_is_free(tmp_path):
    assert profile_in_use(tmp_path) is False


def test_either_lock_file_means_in_use(tmp_path):
    (tmp_path / "SingletonSocket").write_text("")
    assert profile_in_use(tmp_path) is True


def test_waiting_on_a_free_profile_returns_at_once(tmp_path):
    assert asyncio.run(wait_for_profile(tmp_path, max_wait_s=1, poll_s=0.01)) is True


def test_a_lock_that_never_lifts_is_given_up_on(tmp_path):
    (tmp_path / "SingletonLock").write_text("")
    assert asyncio.run(wait_for_profile(tmp_path, max_wait_s=0.03, poll_s=0.01)) is False


def test_the_wait_ends_when_the_lock_lifts(tmp_path):
    lock = tmp_path / "SingletonLock"
    lock.write_text("")

    async def scenario():
        async def release():
            await asyncio.sleep(0.02)
            lock.unlink()
        asyncio.get_running_loop().create_task(release())
        return await wait_for_profile(tmp_path, max_wait_s=1, poll_s=0.01)

    assert asyncio.run(scenario()) is True

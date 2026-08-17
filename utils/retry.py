"""
Bounded retry with backoff, for operations that are safe to repeat.

A single slow page load currently costs a whole task, and the tasks are worth 10-30
points each. Most of what fails here is transient — a navigation timing out, a page
still hydrating — and simply doing it again a moment later works.

**Only idempotent operations belong here.** Loading a page and reading state can be
repeated freely; clicking a task card cannot. If a click succeeded but the check that
followed it failed, retrying the click repeats work that was already done. The tasks
handle that case differently: they re-read state first and only re-attempt a card that
is still genuinely incomplete, which is a re-attempt rather than a retry.
"""

import asyncio
import logging
import random
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger("bing_rewards")

T = TypeVar("T")


async def retry_async(
    action: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 2.0,
    what: str = "operation",
) -> T:
    """
    Run `action`, retrying on exception with exponential backoff and jitter.

    Jitter matters for more than thundering herds here: a fixed retry cadence is
    itself a pattern, and these retries happen against the same host the rest of the
    run is talking to.

    Raises the last exception if every attempt fails — a caller that wanted a default
    should use `retry_or_none`.
    """
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await action()
        except Exception as e:  # noqa: BLE001 — the point is to survive anything transient
            last = e
            if attempt == attempts:
                break
            delay = base_delay * (2 ** (attempt - 1)) * random.uniform(0.8, 1.4)
            logger.warning(
                f"   {what} failed ({attempt}/{attempts}): {e}. Retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)
    assert last is not None
    logger.error(f"   {what} failed after {attempts} attempts: {last}")
    raise last


async def retry_or_none(
    action: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 2.0,
    what: str = "operation",
) -> T | None:
    """As `retry_async`, but returns None instead of raising when all attempts fail."""
    try:
        return await retry_async(action, attempts=attempts, base_delay=base_delay, what=what)
    except Exception:
        return None

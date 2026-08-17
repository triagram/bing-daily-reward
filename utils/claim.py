"""
Collect points sitting in "Ready to claim".

Earnings do not all land in the balance. A sizeable share arrives in a separate pot
shown as "Ready to claim", and that pot **does not drain on its own** — it was observed
holding 115-121 points across several days and an overnight boundary without moving.
Left alone it simply accumulates unspendable.

This is not a task in the Rewards sense: it earns nothing, it moves what was already
earned. It belongs at the end of a run, after everything that might add to the pot.
"""

import asyncio
import logging
from dataclasses import dataclass

from playwright.async_api import Page

from config import REWARDS_URL
from utils.state_reader import fetch_state

logger = logging.getLogger("bing_rewards")


@dataclass
class ClaimResult:
    pending_before: int | None = None
    pending_after: int | None = None
    balance_before: int | None = None
    balance_after: int | None = None
    clicked: bool = False
    error: str | None = None

    @property
    def claimed(self) -> int | None:
        """How much actually moved out of the pot."""
        if self.pending_before is None or self.pending_after is None:
            return None
        return self.pending_before - self.pending_after

    def summary(self) -> str:
        if self.error:
            return f"claim failed: {self.error}"
        if not self.clicked:
            return "nothing to claim"
        moved = self.claimed
        if moved is None:
            return "clicked Claim, but the result could not be read"
        if moved <= 0:
            return f"clicked Claim, but the pot did not move (still {self.pending_after})"
        return (f"claimed {moved} points "
                f"(pot {self.pending_before} → {self.pending_after}, "
                f"balance {self.balance_before} → {self.balance_after})")


async def claim_pending(page: Page) -> ClaimResult:
    """
    Click the "Ready to claim" tile and verify the pot actually drained.

    The tile is itself a button whose text reads "Ready to claim / <n> / Claim", so it
    is matched on the word rather than on a class name. Success is judged by the pot
    shrinking, not by the click landing — the same rule the tasks follow.
    """
    result = ClaimResult()

    try:
        before = await fetch_state(page)
        result.pending_before = before.ready_to_claim
        result.balance_before = before.balance
    except Exception as e:
        result.error = f"could not read state: {e}"
        return result

    if not result.pending_before:
        logger.info("💰 [Claim] Nothing pending.")
        result.pending_after = result.pending_before
        result.balance_after = result.balance_before
        return result

    logger.info(f"💰 [Claim] {result.pending_before} points pending — claiming ...")

    try:
        await page.goto(REWARDS_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3.0)

        # Claiming takes two steps. The "Ready to claim" tile is itself a button, but
        # pressing it only opens a panel — the pot does not move. The panel then
        # carries a separate "Claim points" control that performs the claim. An
        # earlier version stopped after the first click and would have reported
        # success; the pot not shrinking is what caught it.
        tile = page.locator("button:has-text('Ready to claim')").first
        if not await tile.is_visible(timeout=6000):
            result.error = "no 'Ready to claim' tile visible"
            return result
        await tile.click()
        await asyncio.sleep(3.0)

        confirm = page.locator("button:has-text('Claim points')").first
        if not await confirm.is_visible(timeout=6000):
            result.error = "panel opened but no 'Claim points' control appeared"
            return result
        await confirm.click()
        result.clicked = True
        await asyncio.sleep(5.0)
    except Exception as e:
        result.error = str(e)
        return result

    try:
        after = await fetch_state(page)
        result.pending_after = after.ready_to_claim
        result.balance_after = after.balance
    except Exception as e:
        result.error = f"could not verify: {e}"

    logger.info(f"💰 [Claim] {result.summary()}")
    return result

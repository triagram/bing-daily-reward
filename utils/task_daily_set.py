import re
import asyncio
import logging
from playwright.async_api import Page, BrowserContext
from utils.humanizer import random_sleep, execute_action_and_cleanup_new_tab, dismiss_all_modals_and_drawers
from config import REWARDS_URL, REWARDS_EARN_URL

logger = logging.getLogger("bing_rewards")

async def claim_ready_points(page: Page):
    """
    Deterministic Claim Points Protocol:
    1. Check if 'Ready to claim' or 'Claim' buttons exist.
    2. If present: Click to claim points, then close side drawer / modal.
    3. If absent: Skip claim and close any open side drawer/modal to clear the view.
    """
    logger.info("🔍 [Claim Protocol] Checking for Ready to Claim points & Claim buttons...")
    try:
        claimed_any = False

        # 1. Target 'Ready to claim' top card Claim button
        ready_card = page.locator("div, section").filter(has_text=re.compile(r"Ready\s+to\s+claim", re.I)).first
        if await ready_card.is_visible(timeout=2000):
            claim_btn = ready_card.locator("a, button, [role='button']").filter(has_text=re.compile(r"Claim", re.I)).first
            if await claim_btn.is_visible(timeout=1500):
                btn_txt = (await claim_btn.inner_text()).strip()
                logger.info(f"🎁 Claiming points: Clicking '{btn_txt}' in Ready to Claim card...")
                await claim_btn.click(force=True)
                claimed_any = True
                await random_sleep(2.0, 3.0)

        # 2. Target 'Claim offer' under 'Your perks'
        perk_claim = page.locator("button:has-text('Claim offer'), a:has-text('Claim offer')").first
        if await perk_claim.is_visible(timeout=1500):
            logger.info("🎁 Claiming Perk: Clicking 'Claim offer' button...")
            await perk_claim.click(force=True)
            claimed_any = True
            await random_sleep(2.0, 3.0)

        # 3. Target bottom claim buttons
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await random_sleep(1.0, 1.5)
        bottom_claims = page.locator("button:has-text('Claim points'), a:has-text('Claim points'), [aria-label*='Claim points' i]")
        bcnt = await bottom_claims.count()
        for idx in range(bcnt):
            btn = bottom_claims.nth(idx)
            if await btn.is_visible():
                txt = (await btn.inner_text()).strip()
                logger.info(f"🎁 Claiming footer points: Clicking '{txt}'...")
                await btn.click(force=True)
                claimed_any = True
                await random_sleep(1.5, 2.5)

        # Scroll back to top
        await page.evaluate("window.scrollTo(0, 0)")
        await random_sleep(1.0, 1.5)

        if not claimed_any:
            logger.info("No pending points to claim.")

        # Always close side drawer/modal after claim (or if skipped)
        await dismiss_all_modals_and_drawers(page)
    except Exception as e:
        logger.debug(f"Claim points note: {e}")
        await dismiss_all_modals_and_drawers(page)

async def locate_daily_set_individual_cards(page: Page):
    """
    Precision Daily Set locator targeting URL signatures (BTDSUOID, filters=BTEPOKey, REWARDSQUIZ)
    and excluding section header containers or navigation links.
    """
    card_links = []
    url_selectors = [
        "a[href*='BTDSUOID']",
        "a[href*='filters=BTEPOKey']",
        "a[href*='REWARDSQUIZ']",
        "a[href*='DailySet']",
        "a[href*='bing.com/search']"
    ]
    
    for sel in url_selectors:
        try:
            locs = page.locator(sel)
            cnt = await locs.count()
            if cnt > 0:
                for i in range(cnt):
                    node = locs.nth(i)
                    txt = (await node.inner_text()).strip()
                    if txt and txt not in ["Earn more", "Earn", "Dashboard"] and node not in card_links:
                        card_links.append(node)
                if len(card_links) >= 3:
                    break
        except Exception:
            continue

    # Fallback matching
    if not card_links:
        try:
            daily_section = page.locator("div, section").filter(has_text=re.compile(r"^Daily set", re.I)).first
            if await daily_section.is_visible(timeout=3000):
                raw_nodes = daily_section.locator("a[href], div[class*='cursor-pointer']").filter(has_not_text=re.compile(r"^(Earn\s+more|Earn|Dashboard)$", re.I))
                cnt = await raw_nodes.count()
                for i in range(cnt):
                    node = raw_nodes.nth(i)
                    txt = (await node.inner_text()).strip()
                    if txt and txt not in ["Earn more", "Earn", "Dashboard"] and node not in card_links:
                        card_links.append(node)
                logger.info(f"Found {len(card_links)} card container nodes inside Daily set section.")
        except Exception as e:
            logger.debug(f"Daily set section query note: {e}")

    return card_links

async def run_daily_set_streak(context: BrowserContext, main_page: Page):
    """
    Task 1: Daily Set Completion
    1. Navigates to Rewards dashboard.
    2. Runs Claim Protocol (claims pending points and dismisses side drawers).
    3. Locates Card #1, Card #2, Card #3 distinctly via URL signatures, clicks uncompleted cards, and closes tabs.
    """
    logger.info("⚡ [Task 1] Starting Daily Set tasks...")
    
    # 1. Primary navigation
    await main_page.goto(REWARDS_URL, wait_until="domcontentloaded")
    await random_sleep(3.0, 4.0)

    # Claim points before starting & dismiss side drawers
    await claim_ready_points(main_page)

    # Scroll slightly for hydration
    await main_page.evaluate("window.scrollBy(0, 250)")
    await random_sleep(1.5, 2.0)

    # 2. Query individual Daily Set card links
    card_links = await locate_daily_set_individual_cards(main_page)

    # Fallback navigation to /earn if no cards found on main dashboard
    if not card_links:
        logger.info("Navigating to fallback URL https://rewards.bing.com/earn ...")
        await main_page.goto(REWARDS_EARN_URL, wait_until="domcontentloaded")
        await random_sleep(3.0, 4.0)
        await main_page.evaluate("window.scrollBy(0, 250)")
        card_links = await locate_daily_set_individual_cards(main_page)

    logger.info(f"Identified total {len(card_links)} Daily Set activity links.")

    # 3. Process Card #1, Card #2, Card #3 distinctly
    target_count = min(3, len(card_links))
    for idx in range(target_count):
        # Ensure no modal drawer is blocking pointer events
        await dismiss_all_modals_and_drawers(main_page)

        # Ensure main page is on Rewards dashboard
        if "rewards.bing.com/dashboard" not in main_page.url and main_page.url != "https://rewards.bing.com/":
            await main_page.goto(REWARDS_URL, wait_until="domcontentloaded")
            await random_sleep(2.0, 3.0)

        # Re-query if index exceeds current list length
        if idx >= len(card_links):
            card_links = await locate_daily_set_individual_cards(main_page)

        if idx < len(card_links):
            card = card_links[idx]
            try:
                if not await card.is_visible():
                    continue

                card_text = await card.inner_text()
                card_html = await card.inner_html()

                # Skip if already completed
                if "Completed" in card_text or "check-mark" in card_html or "CheckMark" in card_html:
                    logger.info(f"⏩ Daily Set Activity #{idx + 1} is already completed. Skipping.")
                    continue

                logger.info(f"Executing Daily Set Activity #{idx + 1} [{card_text.replace('\n', ' ')[:40]}...]...")

                async def click_act():
                    await card.click(force=True, timeout=4000)

                await execute_action_and_cleanup_new_tab(context, click_act, stay_seconds=3.0)
                logger.info(f"✓ Daily Set Activity #{idx + 1} completed & tab cleaned up.")
            except Exception as e:
                logger.warning(f"Note on Daily Set Activity #{idx + 1}: {e}")

        await random_sleep(1.5, 2.5)

    # Claim points again after completing Daily Set & dismiss drawers
    await claim_ready_points(main_page)
    logger.info("✅ [Task 1] Daily Set tasks finished.")

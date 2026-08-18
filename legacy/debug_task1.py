import asyncio
import logging
from playwright.async_api import async_playwright
from config import USER_DATA_DIR, HEADLESS

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("debug_task1")

async def debug_rewards_daily_set():
    logger.info("🔍 Starting Daily Set Diagnostics...")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,  # Headful mode for visual debugging
            channel="chromium",
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Step 1: Navigate directly to Rewards dashboard
        logger.info("Navigating to https://rewards.bing.com/ ...")
        await page.goto("https://rewards.bing.com/", wait_until="domcontentloaded")
        await asyncio.sleep(4.0)

        # Step 2: Take screenshot
        screenshot_path = "debug_daily_set.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        logger.info(f"📸 Saved full-page screenshot to '{screenshot_path}'")

        # Step 3: Scan for Daily Set section & cards
        logger.info("\n--- DOM Inspection Results ---")
        
        # Check for mee-card elements
        mee_cards = page.locator("mee-card")
        mee_count = await mee_cards.count()
        logger.info(f"Found {mee_count} <mee-card> elements on page.")
        for idx in range(mee_count):
            card = mee_cards.nth(idx)
            text = (await card.inner_text()).replace("\n", " ")
            logger.info(f"  [mee-card #{idx + 1}]: {text[:100]}...")

        # Check for daily set containers
        containers = page.locator("#daily-set, [data-bi-name='daily-set'], [id*='dailySet']")
        cont_count = await containers.count()
        logger.info(f"\nFound {cont_count} daily-set container elements.")
        for idx in range(cont_count):
            cont = containers.nth(idx)
            html = await cont.inner_html()
            logger.info(f"  Container #{idx + 1} HTML snippet: {html[:200]}...")

        # Check for links with bing.com or rewards
        bing_links = page.locator("a[href*='bing.com/search']")
        link_count = await bing_links.count()
        logger.info(f"\nFound {link_count} Bing search links (`a[href*='bing.com/search']`).")
        for idx in range(min(5, link_count)):
            lnk = bing_links.nth(idx)
            href = await lnk.get_attribute("href")
            txt = (await lnk.inner_text()).replace("\n", " ")
            logger.info(f"  Link #{idx + 1} [{txt}]: {href}")

        await context.close()
        logger.info("\n✅ Diagnostic inspection complete.")

if __name__ == "__main__":
    asyncio.run(debug_rewards_daily_set())

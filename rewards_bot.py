import asyncio
import logging
import sys
from pathlib import Path
from playwright.async_api import async_playwright
from rich.console import Console
from rich.logging import RichHandler

from config import USER_DATA_DIR, HEADLESS, REWARDS_URL
from utils.task_daily_set import run_daily_set_streak
from utils.task_explore import run_explore_on_bing
from utils.task_searches import run_daily_searches

# Setup Rich Console & Logger
console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)]
)
logger = logging.getLogger("bing_rewards")

async def main():
    console.print("\n[bold cyan]🚀 Microsoft Bing Rewards Automation Bot[/bold cyan]")
    console.print("[dim]Powered by Python, Playwright & uv[/dim]\n")

    # Ensure user data dir exists for session persistence
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Using Session Data Dir: {USER_DATA_DIR}")

    async with async_playwright() as p:
        logger.info(f"Launching Chromium (Headless: {HEADLESS})...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=HEADLESS,
            channel="chromium",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ],
            viewport={"width": 1280, "height": 800}
        )

        main_page = context.pages[0] if context.pages else await context.new_page()

        # Step 0: Check Rewards Login Session
        logger.info("Opening Microsoft Rewards dashboard...")
        await main_page.goto(REWARDS_URL, wait_until="domcontentloaded")
        await asyncio.sleep(3.0)

        # Check if user is logged in
        if "login.live.com" in main_page.url or "signin" in main_page.url:
            console.print("\n[bold yellow]⚠️ Login Required![/bold yellow]")
            console.print("Please sign in to your Microsoft Account in the opened browser window.")
            console.print("Once signed in, press [bold green]ENTER[/bold green] in this terminal to continue...\n")
            # Wait for user confirmation in interactive terminal
            await asyncio.to_thread(input, "Press ENTER after completing login > ")
            logger.info("Proceeding with tasks...")

        # Step 1: Run Task 1 (Daily Set Streak)
        try:
            await run_daily_set_streak(context, main_page)
        except Exception as e:
            logger.error(f"Error in Task 1 (Daily Set): {e}")

        # Step 2: Run Task 2 (Explore on Bing)
        try:
            await run_explore_on_bing(context, main_page)
        except Exception as e:
            logger.error(f"Error in Task 2 (Explore on Bing): {e}")

        # Step 3: Run Task 3 (20 Bing Searches)
        try:
            await run_daily_searches(context, search_count=20)
        except Exception as e:
            logger.error(f"Error in Task 3 (20 Searches): {e}")

        logger.info("Cleaning up session...")
        await context.close()
        console.print("\n[bold green]🎉 All Bing Rewards tasks finished successfully![/bold green]\n")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Execution interrupted by user.[/yellow]")
        sys.exit(0)

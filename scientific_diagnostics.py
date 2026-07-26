import re
import json
import asyncio
import logging
from pathlib import Path
from playwright.async_api import async_playwright
from rich.console import Console
from rich.table import Table

from config import USER_DATA_DIR, REWARDS_URL, REWARDS_EARN_URL

console = Console()
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("scientific_diagnostics")

async def extract_points(page):
    """Scientific point extractor for Available Points and Ready to Claim points."""
    points_info = {"available_points": None, "ready_to_claim": None}
    try:
        page_text = await page.inner_text("body")
        
        # Match Available points (e.g. 102,922 or 102922)
        avail_match = re.search(r"Available\s+points[^\d]*([\d,]+)", page_text, re.IGNORECASE)
        if avail_match:
            points_info["available_points"] = int(avail_match.group(1).replace(",", ""))

        # Match Ready to claim points (e.g. Ready to claim 2,917 or 0)
        claim_match = re.search(r"Ready\s+to\s+claim[^\d]*([\d,]+)", page_text, re.IGNORECASE)
        if claim_match:
            points_info["ready_to_claim"] = int(claim_match.group(1).replace(",", ""))
    except Exception as e:
        logger.warning(f"Error extracting points: {e}")
    return points_info

async def run_scientific_diagnostics():
    console.print("\n[bold cyan]🔬 Scientific Diagnostics & Empirical Debugging Tool[/bold cyan]")
    console.print("[dim]Collecting visual evidence, DOM selectors & point assertions...[/dim]\n")

    report = {"timestamp": "", "points": {}, "task1": {}, "task2": {}, "claim_buttons": []}

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            channel="chromium",
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Step 1: Open Dashboard & Capture Baseline Points
        logger.info("Step 1: Navigating to Rewards Dashboard...")
        await page.goto(REWARDS_URL, wait_until="domcontentloaded")
        await asyncio.sleep(4.0)
        
        points_baseline = await extract_points(page)
        report["points"]["baseline"] = points_baseline
        logger.info(f"📊 Baseline Points: Available={points_baseline['available_points']} | ReadyToClaim={points_baseline['ready_to_claim']}")
        
        await page.screenshot(path="01_dashboard_baseline.png", full_page=True)
        logger.info("📸 Saved screenshot: '01_dashboard_baseline.png'")

        # Step 2: Inspect Page Bottom & Claim Buttons
        logger.info("\nStep 2: Inspecting Page Bottom for Claim Buttons...")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2.0)
        await page.screenshot(path="05_claim_points_footer.png", full_page=True)
        
        claim_btns = page.locator("button, a, [role='button']").filter(has_text=re.compile(r"claim", re.I))
        btn_count = await claim_btns.count()
        logger.info(f"Found {btn_count} elements with 'claim' text at page bottom.")
        for i in range(btn_count):
            btn = claim_btns.nth(i)
            txt = (await btn.inner_text()).replace("\n", " ")
            vis = await btn.is_visible()
            report["claim_buttons"].append({"text": txt, "visible": vis})
            logger.info(f"  [Claim Btn #{i + 1}]: Visible={vis} | Text='{txt}'")

        # Scroll back up
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1.5)

        # Step 3: Scientific Inspection of Task 1 (Daily Set) Cards
        logger.info("\nStep 3: Inspecting Task 1 Daily Set Cards...")
        daily_set_selectors = [
            "a[href*='BTDSUOID']",
            "a[href*='DailySet']",
            "a[href*='REWARDSQUIZ']",
            "a[href*='filters=BTEPOKey']",
            "div:has-text('Daily set') a[href]"
        ]
        
        task1_items = []
        for sel in daily_set_selectors:
            locs = page.locator(sel)
            cnt = await locs.count()
            if cnt > 0:
                logger.info(f"  Selector '{sel}' matched {cnt} elements.")
                for i in range(cnt):
                    item = locs.nth(i)
                    txt = (await item.inner_text()).replace("\n", " ")
                    html = await item.inner_html()
                    href = await item.get_attribute("href") or ""
                    completed = ("Completed" in txt or "check-mark" in html or "CheckMark" in html)
                    task1_items.append({"text": txt[:60], "href": href[:80], "completed": completed})
                    logger.info(f"    Item #{i + 1}: Completed={completed} | Text='{txt[:40]}'")
                break

        report["task1"]["items"] = task1_items

        # Step 4: Scientific Inspection of Task 2 (Explore on Bing) Cards
        logger.info("\nStep 4: Inspecting Task 2 Explore Cards...")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        await asyncio.sleep(2.0)
        
        explore_cards = page.locator("[data-bi-name='explore'] .c-card, .explore-card, [id*='explore'], a[href*='bing.com']:has-text('Search')")
        ecnt = await explore_cards.count()
        logger.info(f"Found {ecnt} Explore card elements.")
        task2_items = []
        for i in range(ecnt):
            card = explore_cards.nth(i)
            txt = (await card.inner_text()).replace("\n", " ")
            html = await card.inner_html()
            completed = ("Completed" in txt or "check-mark" in html or "CheckMark" in html)
            task2_items.append({"text": txt[:60], "completed": completed})
            logger.info(f"  Card #{i + 1}: Completed={completed} | Text='{txt[:50]}'")

        report["task2"]["items"] = task2_items

        await context.close()

    # Write report JSON
    with open("diagnostics_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    console.print("\n[bold green]✅ Scientific Diagnostics Complete![/bold green]")
    console.print("Report saved to [yellow]diagnostics_report.json[/yellow]")
    console.print("Screenshots saved: [yellow]01_dashboard_baseline.png[/yellow], [yellow]05_claim_points_footer.png[/yellow]\n")

if __name__ == "__main__":
    asyncio.run(run_scientific_diagnostics())

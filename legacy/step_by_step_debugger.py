import re
import asyncio
import logging
from playwright.async_api import async_playwright
from rich.console import Console

from config import USER_DATA_DIR, REWARDS_URL, REWARDS_EARN_URL

console = Console()
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("step_debugger")

EDGE_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"

async def pause_step(step_num: int, title: str, details: str):
    """Interactive Breakpoint: Pauses execution and waits for user ENTER key press."""
    console.print(f"\n[bold yellow]========================================[/bold yellow]")
    console.print(f"[bold green]⏸️ [STEP {step_num}] {title}[/bold green]")
    console.print(f"[dim]{details}[/dim]")
    console.print(f"[bold cyan]👉 Look at the opened browser window, then press ENTER to proceed...[/bold cyan]")
    await asyncio.to_thread(input, f"Press [ENTER] for Step {step_num} > ")

async def highlight_locator(locator):
    """
    Directly highlights the Playwright locator in the browser DOM
    with a 6px glowing red outline and scrolls it into view.
    """
    try:
        await locator.evaluate("""
            el => {
                el.style.outline = '6px solid red';
                el.style.boxShadow = '0 0 25px red';
                el.style.backgroundColor = 'rgba(255, 0, 0, 0.25)';
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        """)
    except Exception as e:
        logger.debug(f"Highlight note: {e}")

async def cleanup_extra_tabs(context, main_page):
    """Closes all extra opened search tabs, keeping only the main page open."""
    for page in context.pages:
        if page != main_page:
            try:
                await page.close()
            except Exception:
                pass

async def locate_all_daily_set_links(page):
    """
    Precision locator targeting EXACT Daily Set activity card links
    using URL signatures (BTDSUOID, filters=, bing.com/search).
    Excludes parent section containers and header navigation links.
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

    # Fallback to cards inside Daily set section that are not header links
    if not card_links:
        try:
            daily_sec = page.locator("div, section").filter(has_text=re.compile(r"^Daily set", re.I)).first
            if await daily_sec.is_visible():
                raw_nodes = daily_sec.locator("a[href], div[class*='cursor-pointer']").filter(has_not_text=re.compile(r"^(Earn\s+more|Earn|Dashboard)$", re.I))
                cnt = await raw_nodes.count()
                for i in range(cnt):
                    node = raw_nodes.nth(i)
                    txt = (await node.inner_text()).strip()
                    if txt and txt not in ["Earn more", "Earn", "Dashboard"] and node not in card_links:
                        card_links.append(node)
        except Exception:
            pass

    return card_links

async def locate_all_explore_links(page):
    """
    Precision locator targeting Explore task cards on https://rewards.bing.com/earn
    using Bing search URLs and Task card signatures.
    Excludes top navigation links like 'Dashboard', 'Earn', and 'Earn more'.
    """
    cards = []
    selectors = [
        "a[href*='bing.com/search']",
        "a[href*='filters=']:has-text('Search')",
        "div.c-card:has-text('Search')",
        "div[class*='cursor-pointer']:has-text('Search')"
    ]
    for sel in selectors:
        try:
            locs = page.locator(sel).filter(has_not_text=re.compile(r"^(Earn\s+more|Dashboard|Earn|Redeem|About)$", re.I))
            cnt = await locs.count()
            if cnt > 0:
                for i in range(cnt):
                    node = locs.nth(i)
                    txt = (await node.inner_text()).strip()
                    html = await node.inner_html()
                    if txt and "logo" not in html.lower() and txt not in ["Dashboard", "Earn", "Earn more"] and node not in cards:
                        cards.append(node)
                if len(cards) > 0:
                    break
        except Exception:
            continue
    return cards

async def run_step_by_step_debugger():
    console.print("\n[bold cyan]🔬 Zero-Misalignment Precision Debugger (URL Signatures & Tab Cleanup)[/bold cyan]")
    console.print("[dim]Strictly isolating Card #1, Card #2, Card #3 & closing opened tabs cleanly[/dim]\n")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            channel="chromium",
            user_agent=EDGE_USER_AGENT,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ],
            viewport={"width": 1280, "height": 850}
        )
        
        page = context.pages[0] if context.pages else await context.new_page()

        # ==========================================
        # STEP 1: Dashboard Baseline & Claim
        # ==========================================
        await pause_step(1, "Load Dashboard & Test Claim", "Navigating to https://rewards.bing.com/")
        await page.goto(REWARDS_URL, wait_until="domcontentloaded")
        await asyncio.sleep(3.0)

        ready_card = page.locator("div, section").filter(has_text=re.compile(r"Ready\s+to\s+claim", re.I)).first
        if await ready_card.is_visible():
            claim_btn = ready_card.locator("a, button, [role='button']").filter(has_text=re.compile(r"Claim", re.I)).first
            if await claim_btn.is_visible():
                await highlight_locator(claim_btn)
                console.print("🔴 [RED HIGHLIGHT] Ready to Claim button highlighted on screen!")

        # ==========================================
        # STEP 2: Inspect Daily Set Cards (Precision URL Signatures)
        # ==========================================
        await pause_step(2, "Task 1: Inspect Daily Set Cards", "Locating Daily Set Card #1, #2, #3 distinctly...")
        await page.evaluate("window.scrollBy(0, 250)")
        await asyncio.sleep(1.5)

        card_links = await locate_all_daily_set_links(page)
        console.print(f"Total Daily Set Cards Found: [bold yellow]{len(card_links)}[/bold yellow]")

        # ==========================================
        # STEP 3: Test Daily Set Card #1
        # ==========================================
        await pause_step(3, "Task 1: Test Daily Set Card #1", "Highlighting & clicking Card #1...")
        card_links = await locate_all_daily_set_links(page)

        if len(card_links) >= 1:
            card1 = card_links[0]
            await highlight_locator(card1)
            txt1 = (await card1.inner_text()).replace("\n", " ")
            console.print(f"🔴 [RED HIGHLIGHT] Daily Set Card #1: '[yellow]{txt1[:50]}[/yellow]'")

            initial_pages = set(context.pages)
            await card1.click(force=True)
            await asyncio.sleep(2.5)
            await cleanup_extra_tabs(context, page)
            console.print("✓ Tab #1 closed cleanly!")

        # ==========================================
        # STEP 4: Test Daily Set Card #2
        # ==========================================
        await pause_step(4, "Task 1: Test Daily Set Card #2", "Highlighting & clicking Card #2...")
        # Ensure main page is on dashboard
        if "rewards.bing.com/dashboard" not in page.url and page.url != "https://rewards.bing.com/":
            await page.goto(REWARDS_URL, wait_until="domcontentloaded")
            await asyncio.sleep(2.0)

        card_links = await locate_all_daily_set_links(page)

        if len(card_links) >= 2:
            card2 = card_links[1]
            await highlight_locator(card2)
            txt2 = (await card2.inner_text()).replace("\n", " ")
            console.print(f"🔴 [RED HIGHLIGHT] Daily Set Card #2: '[yellow]{txt2[:50]}[/yellow]'")

            initial_pages = set(context.pages)
            await card2.click(force=True)
            await asyncio.sleep(2.5)
            await cleanup_extra_tabs(context, page)
            console.print("✓ Tab #2 closed cleanly!")
        else:
            console.print("[yellow]Card #2 already completed or not found.[/yellow]")

        # ==========================================
        # STEP 5: Test Daily Set Card #3
        # ==========================================
        await pause_step(5, "Task 1: Test Daily Set Card #3", "Highlighting & clicking Card #3...")
        if "rewards.bing.com/dashboard" not in page.url and page.url != "https://rewards.bing.com/":
            await page.goto(REWARDS_URL, wait_until="domcontentloaded")
            await asyncio.sleep(2.0)

        card_links = await locate_all_daily_set_links(page)

        if len(card_links) >= 3:
            card3 = card_links[2]
            await highlight_locator(card3)
            txt3 = (await card3.inner_text()).replace("\n", " ")
            console.print(f"🔴 [RED HIGHLIGHT] Daily Set Card #3: '[yellow]{txt3[:50]}[/yellow]'")

            initial_pages = set(context.pages)
            await card3.click(force=True)
            await asyncio.sleep(2.5)
            await cleanup_extra_tabs(context, page)
            console.print("✓ Tab #3 closed cleanly!")
        else:
            console.print("[yellow]Card #3 already completed or not found.[/yellow]")

        # ==========================================
        # STEP 6: Task 2 - Explore on Bing Cards
        # ==========================================
        await pause_step(6, "Task 2: Inspect Explore Cards", "Navigating to https://rewards.bing.com/earn ...")
        await page.goto(REWARDS_EARN_URL, wait_until="domcontentloaded")
        await asyncio.sleep(3.0)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        await asyncio.sleep(1.5)

        explore_links = await locate_all_explore_links(page)
        console.print(f"Found [bold green]{len(explore_links)}[/bold green] Explore task card links.")
        
        # Step 7: Test Explore Card #1 Search & Activation
        await pause_step(7, "Task 2: Test Explore Card #1 Search & Activation", "Highlighting Explore Card #1 and testing activation...")
        if len(explore_links) > 0:
            ecard1 = explore_links[0]
            await highlight_locator(ecard1)
            etxt1 = (await ecard1.inner_text()).replace("\n", " ")
            console.print(f"🔴 [RED HIGHLIGHT] Explore Card Container #1: '[yellow]{etxt1[:50]}[/yellow]'")

            initial_pages = set(context.pages)
            await ecard1.click(force=True)
            await asyncio.sleep(2.0)
            new_pages = [p for p in context.pages if p not in initial_pages]
            if new_pages:
                etab = new_pages[0]
                await etab.wait_for_load_state("domcontentloaded")
                sbox = etab.locator("#sb_form_q, textarea[name='q'], input[name='q']").first
                if await sbox.is_visible():
                    await highlight_locator(sbox)
                    console.print("🔴 [RED HIGHLIGHT] Search box highlighted on Explore tab!")
                    await sbox.fill("popular video games 2026")
                    await etab.keyboard.press("Enter")
                    await asyncio.sleep(3.0)
                await etab.evaluate("window.scrollBy(0, 400)")
                console.print("Waiting 3.5s for Microsoft Rewards server point activation confirmation...")
                await asyncio.sleep(3.5)
                await etab.close()
                console.print("✓ Explore Tab closed cleanly!")

        # Step 8: Test Explore Card #2 Search & Activation
        await cleanup_extra_tabs(context, page)
        if "rewards.bing.com/earn" not in page.url:
            await page.goto(REWARDS_EARN_URL, wait_until="domcontentloaded")
            await asyncio.sleep(2.0)

        explore_links = await locate_all_explore_links(page)
        if len(explore_links) > 1:
            await pause_step(8, "Task 2: Test Explore Card #2 Search & Activation", "Highlighting Explore Card #2 and testing activation...")
            ecard2 = explore_links[1]
            await highlight_locator(ecard2)
            etxt2 = (await ecard2.inner_text()).replace("\n", " ")
            console.print(f"🔴 [RED HIGHLIGHT] Explore Card Container #2: '[yellow]{etxt2[:50]}[/yellow]'")

            initial_pages = set(context.pages)
            await ecard2.click(force=True)
            await asyncio.sleep(2.0)
            await cleanup_extra_tabs(context, page)
            console.print("✓ Explore Tab #2 closed cleanly!")

        # ==========================================
        # STEP 9: Task 3 - Bing Search Verification
        # ==========================================
        await pause_step(9, "Task 3: Test Bing Search Execution", "Navigating to https://www.bing.com to test search submission...")
        search_tab = await context.new_page()
        await search_tab.goto("https://www.bing.com", wait_until="domcontentloaded")
        await asyncio.sleep(1.5)

        bing_box = search_tab.locator("#sb_form_q, textarea[name='q'], input[name='q']").first
        if await bing_box.is_visible():
            await highlight_locator(bing_box)
            console.print("🔴 [RED HIGHLIGHT] Bing homepage search box highlighted!")
            
            await pause_step(10, "Task 3: Submit Bing Search", "Submitting query 'space exploration news'...")
            await bing_box.fill("space exploration news 2026")
            await search_tab.keyboard.press("Enter")
            await asyncio.sleep(3.0)
            await search_tab.evaluate("window.scrollBy(0, 350)")
            console.print("Search result loaded & page scrolled! Waiting 6s cooldown...")
            await asyncio.sleep(6.0)

        await search_tab.close()

        await pause_step(11, "Finish Debugging", "Closing debugger context...")
        await context.close()
        console.print("\n[bold green]✅ Precision Debugging Completed![/bold green]\n")

if __name__ == "__main__":
    asyncio.run(run_step_by_step_debugger())

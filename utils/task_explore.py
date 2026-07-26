import re
import asyncio
import logging
from playwright.async_api import Page, BrowserContext
from utils.humanizer import random_sleep, human_type, handle_quiz_or_poll_on_page

logger = logging.getLogger("bing_rewards")

def extract_search_query(card_text: str) -> str:
    """
    Extracts a clean, meaningful search query from Explore task card text.
    Example: 'Search on Bing to explore videogames' -> 'popular video games'
    """
    if not card_text:
        return "trending news today"

    # Specific override for videogames or common categories
    if "videogame" in card_text.lower() or "video game" in card_text.lower() or "gaming" in card_text.lower():
        return "popular video games"

    # Pattern 1: Look for "Search on Bing to..."
    match = re.search(r"search\s+on\s+bing\s+(?:to\s+)?([^\.\!\?\n]+)", card_text, re.IGNORECASE)
    if match:
        query = match.group(1).strip()
        query = re.sub(r"^(book|find|discover|search|look up|get|learn about|explore)\s+", "", query, flags=re.IGNORECASE)
        if len(query) > 2:
            return query

    # Pattern 2: Split by hyphen or colon
    parts = re.split(r"[-:\n]", card_text)
    if len(parts) > 1:
        clean_part = parts[0].strip()
        clean_part = re.sub(r"^(explore|search)\s+", "", clean_part, flags=re.IGNORECASE)
        if len(clean_part) > 2:
            return clean_part

    # Fallback: sanitize card text
    clean_text = re.sub(r"[^\w\s]", " ", card_text)
    words = [w for w in clean_text.split() if w.lower() not in ["search", "on", "bing", "to", "explore", "for"]]
    return " ".join(words[:4]) if words else "popular games"

async def locate_explore_cards(page: Page):
    """
    Precision locator anchored on <h2 class="truncate text-sectionHeader">Explore on Bing</h2>
    targeting div.cursor-pointer / bg-bgCardOnPrimaryDefaultRest card containers.
    Excludes top-left Microsoft Rewards logo image link completely.
    """
    cards = []
    
    # Strategy 1: Anchor on <h2 class="truncate text-sectionHeader">Explore on Bing</h2>
    try:
        explore_h2 = page.locator("h2").filter(has_text=re.compile(r"Explore\s+on\s+Bing", re.I)).first
        if not await explore_h2.is_visible():
            explore_h2 = page.locator("h2, h3, div").filter(has_text=re.compile(r"Explore|More activities", re.I)).first

        if await explore_h2.is_visible(timeout=3000):
            explore_sec = page.locator("div, section").filter(has=explore_h2).first
            if await explore_sec.is_visible():
                raw_nodes = explore_sec.locator("div[class*='cursor-pointer'], a.cursor-pointer, [class*='bg-bgCardOnPrimaryDefaultRest']").filter(has_not_text=re.compile(r"^Earn\s+more", re.I))
                cnt = await raw_nodes.count()
                for i in range(cnt):
                    node = raw_nodes.nth(i)
                    txt = (await node.inner_text()).strip()
                    html = await node.inner_html()
                    # Exclude top-left logo link
                    if txt and "logo" not in html.lower() and txt != "Earn more" and txt != "Earn":
                        cards.append(node)
                logger.info(f"Found {len(cards)} Explore cards under <h2>Explore on Bing</h2> heading.")
    except Exception as e:
        logger.debug(f"Explore h2 section query note: {e}")

    # Fallback matching
    if not cards:
        try:
            raw_nodes = page.locator("div[class*='cursor-pointer'][class*='rounded-cornerCardDefault']").filter(has_not_text=re.compile(r"^Earn\s+more", re.I))
            cnt = await raw_nodes.count()
            for i in range(cnt):
                node = raw_nodes.nth(i)
                html = await node.inner_html()
                if "logo" not in html.lower():
                    cards.append(node)
            logger.info(f"Found {len(cards)} Explore task cards via fallback class.")
        except Exception:
            pass

    return cards

async def run_explore_on_bing(context: BrowserContext, main_page: Page):
    """
    Task 2: Explore on Bing Execution & Activation Protocol
    1. Navigate to https://rewards.bing.com/earn
    2. Locate individual Explore card elements anchored on <h2>Explore on Bing</h2>.
    3. Click uncompleted cards, fill search query, submit Enter, scroll page, solve Quiz/Poll, and wait 3.5s for server activation!
    """
    logger.info("⚡ [Task 2] Starting Explore on Bing tasks...")
    await main_page.goto("https://rewards.bing.com/earn", wait_until="domcontentloaded")
    await random_sleep(2.5, 3.5)

    # Scroll down to ensure Explore section is hydrated
    await main_page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
    await random_sleep(1.5, 2.5)

    cards = await locate_explore_cards(main_page)
    logger.info(f"Identified total {len(cards)} Explore task cards.")

    for idx in range(len(cards)):
        # Re-query cards if page DOM updated
        if idx >= len(cards):
            cards = await locate_explore_cards(main_page)
        if idx >= len(cards):
            break

        card = cards[idx]
        try:
            if not await card.is_visible():
                continue

            card_text = await card.inner_text()
            card_html = await card.inner_html()
        except Exception:
            card_text = ""
            card_html = ""

        # Skip completed Explore tasks
        if "Completed" in card_text or "check-mark" in card_html or "CheckMark" in card_html:
            logger.info(f"⏩ Explore Task #{idx + 1} is already completed. Skipping.")
            continue

        search_term = extract_search_query(card_text)
        logger.info(f"Executing Explore Task #{idx + 1} [{card_text.replace('\n', ' ')[:40]}...] | Term: '{search_term}'")

        initial_pages = set(context.pages)
        try:
            await card.click(force=True)
        except Exception as e:
            logger.warning(f"Could not click Explore Task card #{idx + 1}: {e}")
            continue

        await asyncio.sleep(1.5)
        new_pages = [p for p in context.pages if p not in initial_pages]

        if new_pages:
            search_page = new_pages[0]
            try:
                await search_page.wait_for_load_state("domcontentloaded", timeout=6000)
                
                # Type search query into Bing search box
                search_box = search_page.locator("#sb_form_q, textarea[name='q'], input[name='q']").first
                if await search_box.is_visible(timeout=3000):
                    await human_type(search_box, search_term)
                    await search_page.keyboard.press("Enter")
                    await random_sleep(2.0, 3.0)

                # Scroll search page to trigger view & point server registration
                await search_page.evaluate("window.scrollBy(0, 400)")

                # Auto-solve Quiz or Poll if present on opened search tab
                await handle_quiz_or_poll_on_page(search_page)
                
                # Stay 3.5s for Microsoft Rewards server XHR point confirmation
                await random_sleep(3.5, 4.5)
                logger.info(f"✓ Explore Task #{idx + 1} search executed & activated (+10 pts).")
            except Exception as e:
                logger.warning(f"Error performing search on Explore tab: {e}")
            finally:
                try:
                    await search_page.close()
                except Exception:
                    pass
        else:
            logger.info(f"No new tab opened for Explore Task #{idx + 1}.")

        await random_sleep(1.5, 2.5)

    logger.info("✅ [Task 2] Explore on Bing tasks finished.")

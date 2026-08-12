"""
Read-only reconnaissance of the Microsoft Rewards dashboard.

Opens the existing signed-in session, visits the dashboard and /earn, and records
what the page actually fetches — every JSON response, any promising data object the
page hangs off `window`, full-page screenshots, and the DOM subtrees around the task
cards. Everything lands in captures/<timestamp>/.

This script NEVER completes an activity. It does not click task cards, does not
search, and does not claim points. The only interactions are navigation and
scrolling, which is indistinguishable from opening the dashboard by hand.

The point of the capture is to replace guessed CSS selectors with the data the page
renders from, so the task list and its completion state become facts rather than
inferences.

Usage:
    uv run python capture_state.py              # redact identifiers (default)
    uv run python capture_state.py --no-redact  # keep raw values, local eyes only
"""

import re
import sys
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from config import USER_DATA_DIR, REWARDS_URL, REWARDS_EARN_URL

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
logger = logging.getLogger("capture")

OUT_ROOT = Path(__file__).parent / "captures"

# Only responses from these hosts are worth keeping; everything else is ads and telemetry.
INTERESTING_HOSTS = ("rewards.bing.com", "www.bing.com", "bing.com", "login.live.com")

# Values under keys matching this are replaced with a placeholder. Point totals and
# completion flags are deliberately NOT redacted — they are the whole reason for the
# capture, and they say nothing about who the account belongs to.
SENSITIVE_KEY = re.compile(
    r"(token|auth|secret|password|cookie|session|signature|"
    r"email|mail|phone|firstname|lastname|givenname|surname|"
    r"userid|puid|cid|muid|anid|uuid|guid|hashed)",
    re.IGNORECASE,
)

# Long opaque strings are almost always identifiers even when the key looks harmless.
OPAQUE_VALUE = re.compile(r"^[A-Za-z0-9+/=_-]{40,}$")


def redact(node):
    """Recursively replace identifier-ish values, preserving structure and types."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if SENSITIVE_KEY.search(key) and not isinstance(value, (dict, list)):
                out[key] = f"<redacted:{type(value).__name__}>"
            else:
                out[key] = redact(value)
        return out
    if isinstance(node, list):
        return [redact(item) for item in node]
    if isinstance(node, str) and OPAQUE_VALUE.match(node):
        return f"<redacted:str:{len(node)}>"
    return node


def safe_name(url: str, index: int) -> str:
    """Build a readable, filesystem-safe filename from a URL."""
    stem = re.sub(r"^https?://", "", url).split("?")[0]
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", stem)[:80]
    return f"{index:03d}_{stem}.json"


async def capture(out_dir: Path, do_redact: bool):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "network").mkdir(exist_ok=True)
    (out_dir / "dom").mkdir(exist_ok=True)

    json_hits = []      # responses we saved
    request_log = []    # every request, for spotting the endpoint even if the body failed

    async with async_playwright() as p:
        logger.info(f"Opening session from {USER_DATA_DIR} ...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            channel="chromium",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            viewport={"width": 1280, "height": 900},
        )

        async def on_response(response):
            url = response.url
            if not any(h in url for h in INTERESTING_HOSTS):
                return
            ctype = (response.headers or {}).get("content-type", "")
            request_log.append({"url": url, "status": response.status, "content_type": ctype})
            if "json" not in ctype.lower():
                return
            try:
                body = await response.json()
            except Exception:
                return  # streamed, cancelled, or not really JSON

            payload = redact(body) if do_redact else body
            fname = safe_name(url, len(json_hits) + 1)
            (out_dir / "network" / fname).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            json_hits.append({"file": fname, "url": url, "status": response.status})
            logger.info(f"  📥 JSON  {url.split('?')[0][:88]}")

        context.on("response", lambda r: asyncio.create_task(on_response(r)))

        page = context.pages[0] if context.pages else await context.new_page()

        for label, url in (("dashboard", REWARDS_URL), ("earn", REWARDS_EARN_URL)):
            logger.info(f"Navigating to {url} ...")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.warning(f"Navigation issue on {label}: {e}")
                continue

            # Let the client-side app hydrate and fire its data requests.
            await asyncio.sleep(5.0)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await asyncio.sleep(2.5)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2.5)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1.5)

            if "login.live.com" in page.url or "signin" in page.url:
                logger.error("Session is not signed in — run rewards_bot.py once to log in first.")
                await context.close()
                return None

            await page.screenshot(path=str(out_dir / f"{label}.png"), full_page=True)
            logger.info(f"  📸 {label}.png")

            (out_dir / "dom" / f"{label}.html").write_text(
                await page.content(), encoding="utf-8"
            )

            # Probe for data the page parked on `window` — some dashboards stash their
            # whole state there, which would be an even cleaner source than the network.
            try:
                globals_found = await page.evaluate(
                    """() => {
                        const out = {};
                        for (const key of Object.keys(window)) {
                            let v;
                            try { v = window[key]; } catch (e) { continue; }
                            if (!v || typeof v !== 'object') continue;
                            let s;
                            try { s = JSON.stringify(v); } catch (e) { continue; }
                            if (!s || s.length < 500 || s.length > 2000000) continue;
                            if (!/promotion|offer|pointProgress|dailySet|userStatus|complete/i.test(s)) continue;
                            out[key] = JSON.parse(s);
                        }
                        return out;
                    }"""
                )
                if globals_found:
                    payload = redact(globals_found) if do_redact else globals_found
                    (out_dir / f"globals_{label}.json").write_text(
                        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                    logger.info(f"  🌐 globals_{label}.json — keys: {', '.join(globals_found)}")
                else:
                    logger.info(f"  🌐 no promising window globals on {label}")
            except Exception as e:
                logger.debug(f"globals probe note: {e}")

        (out_dir / "requests.json").write_text(
            json.dumps(request_log, indent=2), encoding="utf-8"
        )
        (out_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "captured_at": datetime.now().isoformat(timespec="seconds"),
                    "redacted": do_redact,
                    "json_responses": json_hits,
                    "request_count": len(request_log),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        logger.info("Closing browser...")
        await context.close()

    return json_hits, request_log


async def main():
    do_redact = "--no-redact" not in sys.argv
    out_dir = OUT_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S")

    console.print("\n[bold cyan]🔍 Rewards state capture (read-only)[/bold cyan]")
    console.print(
        "[dim]Navigation and scrolling only — no clicks, no searches, no claims.[/dim]"
    )
    console.print(
        f"[dim]Redaction: {'on' if do_redact else '[bold red]OFF[/bold red]'}"
        f"  ·  Output: {out_dir}[/dim]\n"
    )

    result = await capture(out_dir, do_redact)
    if result is None:
        return
    json_hits, request_log = result

    table = Table(title="Captured JSON responses", show_lines=False)
    table.add_column("File", style="cyan", no_wrap=True)
    table.add_column("URL", overflow="fold")
    if json_hits:
        for hit in json_hits:
            table.add_row(hit["file"], hit["url"].split("?")[0])
        console.print(table)
    else:
        console.print("[yellow]No JSON responses captured.[/yellow]")
        console.print(
            f"[dim]{len(request_log)} requests were logged to requests.json — "
            "the data may arrive as HTML or as a non-JSON content type. "
            "Check that file and the DOM dumps.[/dim]"
        )

    console.print(f"\n[bold green]✅ Capture written to {out_dir}[/bold green]")
    console.print("[dim]Review it before sharing — then hand over the directory.[/dim]\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(0)

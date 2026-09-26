"""
Entry point — runs the day's Rewards tasks and reports what they actually earned.

Each task returns a structured result rather than only logging, and the run ends with
a table of measured point deltas. Nothing here prints a point figure it did not
observe: where a total could not be read it says so.

    uv run python rewards_bot.py            # run today's tasks
    uv run python rewards_bot.py --dry-run  # read state and report, change nothing
    uv run python rewards_bot.py --history  # what past runs earned
    uv run python rewards_bot.py --login    # sign in by hand; confirms the session works

Exit codes: 0 clean (or nothing to do); 1 crashed; 2 ran but Flags is not empty;
3 no session and no terminal to sign in from; 4 the browser profile stayed busy.
A scheduled run that finds the sign-in page stops there and records nothing —
somebody has to run --login in a terminal.

Everything the terminal shows is also appended, as plain text, to
logs/observation/<date>.log when the run ends, so a run nobody watched can still be
read the next day. (The systemd journal has the same text, streamed.)
"""

import sys
import json
import asyncio
import logging
from datetime import datetime, date
from pathlib import Path

from playwright.async_api import async_playwright
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from config import (
    EXPLORE_ON_BING_TILES_PER_DAY,
    HEADLESS,
    REWARDS_URL,
    RUN_EXPLORE_ON_BING,
    USER_DATA_DIR,
)
from utils.claim import claim_pending
from utils.profile_lock import wait_for_profile
from utils.shortfall import Verdict, assess, flags_for
from utils.state_reader import fetch_state
from utils.task_daily_set import run_daily_set
from utils.task_explore_on_bing import run_explore_on_bing
from utils.task_keep_earning import run_keep_earning
from utils.task_searches import run_daily_searches

RUN_LOG = Path(__file__).parent / "logs" / "runs.jsonl"
OBSERVATION_DIR = Path(__file__).parent / "logs" / "observation"

# The run finished, but a task is flagged — the observation window's criterion, from
# flags_for(). Under a timer this is the difference between "boring" and "look".
EXIT_FLAGGED = 2
# No session, and no terminal to wait for one in. Distinct from a crash (1) so that
# whatever watches a scheduled run can say "sign in" rather than "look at the log".
EXIT_SIGN_IN_REQUIRED = 3
# The profile stayed held for the whole wait: a browser or another run has it open.
EXIT_PROFILE_BUSY = 4

# Recorded so the day's log file can be written from what was actually shown, table
# and warnings included — the tee that the observation window relied on, built in.
console = Console(record=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
)
logger = logging.getLogger("bing_rewards")


def load_runs() -> list[dict]:
    if not RUN_LOG.exists():
        return []
    out = []
    for line in RUN_LOG.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                run = json.loads(line)
            except ValueError:
                continue
            # Runs recorded before 2026-08-22 call this task "explore". The name was
            # dropped because the page has a differently-named section that this task
            # does not do; the old records are still perfectly good measurements.
            tasks = run.get("tasks") or {}
            if "explore" in tasks and "keep_earning" not in tasks:
                tasks["keep_earning"] = tasks.pop("explore")
            out.append(run)
    return out


def print_history():
    """
    What each past run earned, per task.

    Runs were already being recorded structurally and nothing read them back, so a
    bad day was only visible to whoever happened to watch that run's console. The
    question this answers is the one worth asking daily: did today fall short?
    """
    runs = load_runs()
    if not runs:
        console.print("[yellow]No runs recorded yet.[/yellow]")
        return

    table = Table(title=f"Runs ({len(runs)})")
    table.add_column("Finished", style="cyan", no_wrap=True)
    table.add_column("Daily set", justify="right")
    table.add_column("Searches", justify="right")
    table.add_column("Keep earning", justify="right")
    table.add_column("Explore", justify="right")
    table.add_column("Claimed", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Flags", style="yellow")

    for run in runs:
        tasks = run.get("tasks", {})

        def cell(name: str) -> str:
            task = tasks.get(name)
            if not task:
                return "[dim]—[/dim]"
            points = task.get("points")
            done, attempted = task.get("done"), task.get("attempted")
            if points is None:
                return f"[yellow]?[/yellow] {done}/{attempted}"
            colour = {"zero": "red", "short": "yellow", "unknown": "yellow"}.get(
                task.get("verdict"), "green" if points else "dim")
            shelved = task.get("shelved") or []
            note = f" [dim]({len(shelved)} shelved)[/dim]" if shelved else ""
            return f"[{colour}]{points:+d}[/{colour}] {done}/{attempted}{note}"

        claim = run.get("claim") or {}
        moved = claim.get("moved")
        flags = " ".join(flags_for(tasks))
        overall = run.get("overall_delta")
        # Under the timer the start moves every day; the record carries the finish.
        finished = f"{run.get('date', '?')} {run.get('at', '')[11:16]}".strip()
        table.add_row(
            finished,
            cell("daily_set"), cell("searches"), cell("keep_earning"),
            cell("explore_on_bing"),
            f"{moved:+d}" if moved else "[dim]—[/dim]",
            f"[bold]{overall:+d}[/bold]" if overall is not None else "[yellow]?[/yellow]",
            flags or "",
        )
    console.print(table)

    earned = [r["overall_delta"] for r in runs if isinstance(r.get("overall_delta"), int)]
    if earned:
        console.print(
            f"[dim]{len(earned)} measured runs · best {max(earned)} · "
            f"worst {min(earned)} · mean {sum(earned) / len(earned):.0f} points[/dim]"
        )


def build_run_record(run_date: str, opening_total: int | None, closing_total: int | None,
                     results: dict) -> dict:
    """
    The line runs.jsonl gets: one entry per task, in the shape --history reads.

    Explore on Bing carries two extras — the per-tile detail, which is the output that
    matters for a task whose crediting rule is unknown, and the topics shelved rather
    than attempted, so that a day with a shelved tile is not read as a day with one
    fewer tile.
    """
    overall = (closing_total - opening_total
               if closing_total is not None and opening_total is not None else None)
    claim = results.get("claim")
    tasks = {}
    for name, res in results.items():
        if name == "claim":
            continue
        entry = {
            "attempted": res.attempted,
            "done": getattr(res, "completed", getattr(res, "submitted", None)),
            "points": res.points_earned,
            "expected": res.expected_points,
            "verdict": assess(res.expected_points, res.points_earned,
                              res.attempted).verdict.value,
            "errors": res.errors,
        }
        if name == "explore_on_bing":
            entry["tiles"] = res.per_tile
            entry["shelved"] = res.shelved
        tasks[name] = entry
    return {
        "date": run_date,
        "opening_total": opening_total,
        "closing_total": closing_total,
        "overall_delta": overall,
        "claim": (
            {"clicked": claim.clicked, "moved": claim.claimed, "error": claim.error}
            if claim is not None else None
        ),
        "tasks": tasks,
    }


def sign_in_required(url: str) -> bool:
    """Microsoft bounced the dashboard load to its sign-in flow."""
    return "login.live.com" in url or "signin" in url


async def wait_for_sign_in(page, context) -> None:
    """
    Block until a person has signed in — or stop, if there is no person.

    The persistent profile keeps the session for weeks, so this is rare, but when it
    happens under a timer there is nobody at the keyboard: input() on a stdin that is
    /dev/null raises EOFError, which reads as a crash. Say what is needed instead, and
    leave with a code that means exactly that.
    """
    if not sys.stdin.isatty():
        logger.error("Sign-in required, and no terminal to wait in. Run "
                     "`uv run python rewards_bot.py --login` by hand, then retry.")
        await context.close()
        sys.exit(EXIT_SIGN_IN_REQUIRED)
    console.print("\n[bold yellow]Sign-in required.[/bold yellow]")
    console.print("Sign in to the Microsoft account in the open browser window,")
    console.print("then press [bold green]ENTER[/bold green] here to continue.\n")
    await asyncio.to_thread(input, "ENTER once signed in > ")


_day_log: Path | None = None


def start_day_log() -> None:
    """Everything printed from here on is appended to today's observation log at exit."""
    global _day_log
    OBSERVATION_DIR.mkdir(parents=True, exist_ok=True)
    _day_log = OBSERVATION_DIR / f"{date.today().isoformat()}.log"
    console.print(f"[dim]{datetime.now():%Y-%m-%d %H:%M:%S}[/dim]")


def flush_day_log() -> None:
    if _day_log is None:
        return
    text = console.export_text(clear=True)
    with _day_log.open("a", encoding="utf-8") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")


def record_run(payload: dict):
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"),
                             **payload}, ensure_ascii=False) + "\n")


async def main():
    if "--history" in sys.argv:
        print_history()
        return

    dry_run = "--dry-run" in sys.argv
    login_mode = "--login" in sys.argv

    console.print("\n[bold cyan]Microsoft Rewards[/bold cyan]")
    mode = ("signing in" if login_mode
            else "dry run — reading state only" if dry_run
            else "running today's tasks")
    console.print(f"[dim]{mode}[/dim]")
    start_day_log()
    console.print()

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # The monitor holds the profile for seconds; wait it out rather than lose the day.
    if not await wait_for_profile(USER_DATA_DIR):
        logger.error("The browser profile is still in use after five minutes — a browser "
                     "window or another run has it open. Nothing was done.")
        sys.exit(EXIT_PROFILE_BUSY)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=HEADLESS,
            channel="chromium",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto(REWARDS_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3.0)

        if sign_in_required(page.url):
            await wait_for_sign_in(page, context)
        elif login_mode:
            console.print("[dim]Already signed in.[/dim]")

        opening = await fetch_state(page)

        if login_mode:
            # Success means the session is usable, not that ENTER was pressed: the
            # balance has to be readable, which is what every run needs from it.
            if opening.total_points is None:
                console.print("[bold red]Signed in, but the balance cannot be read — "
                              "the session is not usable yet.[/bold red]")
                await context.close()
                sys.exit(1)
            console.print(f"  session works — balance [bold]{opening.balance}[/bold], "
                          f"total [bold]{opening.total_points}[/bold]\n")
            await context.close()
            return
        console.print(
            f"  balance [bold]{opening.balance}[/bold]  ·  "
            f"unclaimed [bold]{opening.ready_to_claim}[/bold]  ·  "
            f"total [bold]{opening.total_points}[/bold]"
        )
        outstanding = opening.outstanding(date.today())
        console.print(f"  daily set outstanding today: {len(outstanding)}\n")

        if dry_run:
            # The offer id is printed because the slot alone cannot distinguish two
            # entries for the same card: on 2026-08-19 a dry run listed six
            # outstanding for a three-card set, and diagnosing it needed a second
            # trip to the account purely to see the ids.
            for offer in outstanding:
                console.print(
                    f"    would do  {offer.slot}  {offer.points}pts  {offer.title}\n"
                    f"              [dim]{offer.offer_id}[/dim]"
                )
            ids = [o.offer_id for o in outstanding]
            if len(set(ids)) != len(ids):
                console.print("\n[bold red]⚠ The same offer id is listed more than "
                              "once — the parser is double-counting.[/bold red]")
            elif len(outstanding) > 3:
                console.print(f"\n[bold yellow]⚠ {len(outstanding)} outstanding for a "
                              "three-card set, with distinct ids — more than one offer "
                              "family is matching is_daily_set.[/bold yellow]")
            await context.close()
            return

        results: dict[str, object] = {}

        try:
            results["daily_set"] = await run_daily_set(context, state_page=page)
        except Exception as e:
            logger.error(f"Daily Set failed outright: {e}")

        try:
            results["searches"] = await run_daily_searches(
                context, state_page=page,
                reserve_searches=EXPLORE_ON_BING_TILES_PER_DAY if RUN_EXPLORE_ON_BING else 0,
            )
        except Exception as e:
            logger.error(f"Searches failed outright: {e}")

        try:
            results["keep_earning"] = await run_keep_earning(context, state_page=page)
        except Exception as e:
            logger.error(f"Keep earning failed outright: {e}")

        # Behind a switch so the tiles can be taken out of the daily run again if a
        # topic the query map has not learned starts flagging days; see config.py.
        if RUN_EXPLORE_ON_BING:
            try:
                results["explore_on_bing"] = await run_explore_on_bing(context, state_page=page)
            except Exception as e:
                logger.error(f"Explore on Bing failed outright: {e}")

        # Claiming goes last: the pot only stops growing once the tasks are done.
        try:
            results["claim"] = await claim_pending(page)
        except Exception as e:
            logger.error(f"Claim failed outright: {e}")

        closing = await fetch_state(page)

        table = Table(title="Measured this run")
        table.add_column("Task", style="cyan")
        table.add_column("Done", justify="right")
        table.add_column("Points", justify="right")
        table.add_column("Errors", justify="right")
        for name, res in results.items():
            if name == "claim":
                moved = res.claimed
                table.add_row("claim (moved, not earned)",
                              "yes" if res.clicked else "—",
                              f"{moved:+d}" if moved else "0",
                              "1" if res.error else "0")
                continue
            earned = res.points_earned
            done = (f"{res.submitted}/{res.attempted}" if name == "searches"
                    else f"{res.completed}/{res.attempted}")
            table.add_row(name, done,
                          f"{earned:+d}" if earned is not None else "unknown",
                          str(len(res.errors)))
        overall = (closing.total_points - opening.total_points
                   if closing.total_points is not None and opening.total_points is not None
                   else None)
        table.add_row("[bold]overall[/bold]", "",
                      f"[bold]{overall:+d}[/bold]" if overall is not None else "unknown", "")
        console.print()
        console.print(table)

        # A broken run is otherwise indistinguishable from an idle one: both print
        # zeros and exit successfully.
        problems = []
        for name, res in results.items():
            if name == "claim":
                continue
            verdict = assess(res.expected_points, res.points_earned, res.attempted)
            if verdict.is_problem:
                problems.append((name, verdict))

        if problems:
            console.print()
            for name, v in problems:
                colour = "red" if v.verdict is Verdict.ZERO else "yellow"
                console.print(f"[bold {colour}]⚠ {name}: {v.message}.[/bold {colour}]")
            console.print(
                "[dim]Check whether the page layout changed (run recon.py and compare "
                "against an earlier capture) before assuming the account is limited.[/dim]"
            )

        if closing.ready_to_claim:
            console.print(
                f"\n[yellow]{closing.ready_to_claim} points are still in "
                f"'Ready to claim'.[/yellow] The pot does not drain on its own."
            )

        record = build_run_record(date.today().isoformat(), opening.total_points,
                                  closing.total_points, results)
        record_run(record)
        console.print(f"[dim]Run recorded in {RUN_LOG.relative_to(Path(__file__).parent)}[/dim]")

        flags = flags_for(record["tasks"])
        if flags:
            console.print(f"[bold yellow]⚠ Flags: {' '.join(flags)}[/bold yellow]")
        console.print()

        await context.close()
        if flags:
            sys.exit(EXIT_FLAGGED)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(0)
    except Exception:
        # Rendered through the console so the traceback reaches the day's log too.
        console.print_exception()
        sys.exit(1)
    finally:
        flush_day_log()

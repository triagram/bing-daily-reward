"""
Parse the Microsoft Rewards dashboard's embedded state out of its HTML.

The dashboard is a Next.js app using React Server Components. It makes no separate
data request — the state arrives serialised inside the HTML document, in a stream of
`self.__next_f.push([1, "<chunk>"])` calls that concatenate into React's flight
format. That stream is the ground truth behind every card the page draws.

This module reads that stream and returns structured offers, so callers can ask
"which tasks are outstanding today?" instead of guessing at CSS class names. It is a
pure function of the HTML: no network, no browser, no I/O. That makes it testable
offline against a captured page (see recon.py).

    from utils.dashboard_state import parse_dashboard
    state = parse_dashboard(await page.content())
    for offer in state.daily_set(today):
        if not offer.is_completed:
            ...
"""

import re
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterator, Any
from urllib.parse import parse_qs, unquote, urlparse

logger = logging.getLogger("bing_rewards")

# offerId is self-describing, e.g. Gamification_DailySet_ENGB_20260811_Child2
OFFER_ID_PATTERN = re.compile(
    r"^(?P<family>[A-Za-z]+)_(?P<kind>[A-Za-z]+)_(?P<market>[A-Z]{4})_"
    r"(?P<day>\d{8})_(?P<slot>[A-Za-z0-9]+)$"
)


@dataclass
class Offer:
    """One task card, as the dashboard itself describes it."""

    offer_id: str
    title: str | None = None
    description: str | None = None
    points: int | None = None
    is_completed: bool | None = None
    date_text: str | None = None       # the payload's own "date" field, e.g. "08/11/2026"
    destination: str | None = None     # where the card sends you
    cta_text: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    # --- derived from the offerId itself, which is more structural than any field ---

    @property
    def market(self) -> str | None:
        """Market code baked into the id, e.g. ENGB."""
        m = OFFER_ID_PATTERN.match(self.offer_id)
        return m.group("market") if m else None

    @property
    def slot(self) -> str | None:
        """Which card of the set, e.g. Child1 / Child2 / Child3."""
        m = OFFER_ID_PATTERN.match(self.offer_id)
        return m.group("slot") if m else None

    @property
    def day(self) -> date | None:
        """The date the id encodes. Preferred over date_text: it is part of the key."""
        m = OFFER_ID_PATTERN.match(self.offer_id)
        if not m:
            return None
        try:
            return datetime.strptime(m.group("day"), "%Y%m%d").date()
        except ValueError:
            return None

    @property
    def is_daily_set(self) -> bool:
        m = OFFER_ID_PATTERN.match(self.offer_id)
        return bool(m) and m.group("kind").lower() == "dailyset"

    @property
    def query(self) -> str | None:
        """
        The search term this offer sends you to, if any.

        Every daily-set destination points at bing.com/search, so the path identifies
        nothing — the query does. Two shapes occur and both have to be handled: a
        direct `…/search?q=Sport+events+near+me`, and a redirect
        `…/rewards/checkuser?ru=%2Fsearch%3Fq%3DNelson+mandela…` that hides the real
        target one level down. Without unwrapping `ru`, two of the three cards each
        day have no distinguishing feature at all.

        Used to locate a card's anchor by href, which beats matching on CSS classes
        that the dashboard rewrites without notice.
        """
        if not self.destination:
            return None
        # The flight stream escapes ampersands; urlparse needs them real.
        url = self.destination.replace("\\u0026", "&")
        params = parse_qs(urlparse(url).query)
        if params.get("q"):
            return params["q"][0]
        if params.get("ru"):
            inner = unquote(params["ru"][0])
            inner_params = parse_qs(urlparse(inner).query)
            if inner_params.get("q"):
                return inner_params["q"][0]
        return None


@dataclass
class DashboardState:
    balance: int | None = None
    level: int | None = None
    # Points earned but not yet collected. They sit outside the balance, so a
    # before/after balance comparison can read zero for a task that did earn.
    # Any measurement of "what did this run earn" has to add both.
    ready_to_claim: int | None = None
    offers: list[Offer] = field(default_factory=list)
    counters: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total_points(self) -> int | None:
        """Balance plus anything waiting to be claimed."""
        if self.balance is None:
            return None
        return self.balance + (self.ready_to_claim or 0)

    def daily_set(self, day: date | None = None) -> list[Offer]:
        """Daily-set offers for one day, ordered by slot. Defaults to today."""
        day = day or date.today()
        found = [o for o in self.offers if o.is_daily_set and o.day == day]
        return sorted(found, key=lambda o: o.slot or "")

    def outstanding(self, day: date | None = None) -> list[Offer]:
        """Daily-set offers for the day that are not yet marked complete."""
        return [o for o in self.daily_set(day) if o.is_completed is False]

    @property
    def markets(self) -> set[str]:
        return {m for m in (o.market for o in self.offers) if m}


# --------------------------------------------------------------------------- #
# Merging the copies of one offer
# --------------------------------------------------------------------------- #

# The fields an Offer actually reads. Used to rank copies, so that "richest" means
# richest in the data we need rather than in incidental React bookkeeping.
INFORMATIVE_KEYS = (
    "title", "description", "points", "isCompleted", "date",
    "destination", "ctaUrl", "ctaText", "href",
)


def is_present(value: Any) -> bool:
    """
    Whether a flight-stream field carries a value.

    The stream writes an absent optional as the literal string `"$undefined"`, not as
    null, so a plain `is not None` test counts it as data and lets it win a merge.
    """
    return value is not None and value != "$undefined"



# Zero-width spaces are baked into the rendered strings; they break equality and make a
# query nonsense if it is typed with them still in.
ZERO_WIDTH = "\u200b\u200c\u200d\ufeff"


def strings_in(node: Any, out: list[str] | None = None) -> list[str]:
    """Every human-readable string under a React children tree, in document order."""
    out = [] if out is None else out
    if isinstance(node, str):
        text = node.strip().strip(ZERO_WIDTH).strip()
        # React's own placeholders ($L13, $undefined, $5f:props:...) are not text.
        if text and not text.startswith("$"):
            out.append(text)
    elif isinstance(node, list):
        # A React element is ["$", tag, key, props]: the tag and key are markup, not
        # text, and including them made every tile's title come out as "div".
        items = node[3:] if len(node) >= 4 and node[0] == "$" else node
        for item in items:
            strings_in(item, out)
    elif isinstance(node, dict):
        for key in ("alt", "children"):
            if key in node:
                strings_in(node[key], out)
        for key, value in node.items():
            if key not in ("alt", "children") and isinstance(value, (list, dict)):
                strings_in(value, out)
    return out


def text_from_children(obj: dict) -> tuple[str | None, str | None]:
    """
    Recover an offer's title and description from its rendered subtree.

    Some offer families ship no `title` and no `description` of their own — the
    "Explore on Bing" tiles are the case that forced this — and render both inside
    `children`, the title as an image `alt` and the description as a text node. Guessing
    what such a tile is about from its id produced searches like `timezonedates`, which
    is not something a person would type; the page had "Search on Bing to see what time
    it is in a different time zone" written on it the whole time.

    Returns (title, description), either of which may be None.
    """
    texts = strings_in(obj.get("children"))
    if not texts:
        return None, None
    title = texts[0]
    description = next((t for t in texts[1:] if len(t) > len(title)), None)
    return title, description


def merge_offer_objects(objs: list[dict]) -> dict:
    """
    Combine every object the stream ships for one offer id into a single dict.

    A card is not one object. On 2026-08-19 each daily-set card arrived as two: the
    rendered element, carrying `offerId`, `isCompleted`, `href` and `children`, and the
    data behind it, carrying `title`, `points`, `destination` and `date`. Neither is
    complete alone — the element has no points, the data has no children.

    The previous version deduplicated on `(offerId, title, points, isCompleted)`. Since
    the two copies disagree on exactly those fields, both survived, and a three-card
    daily set parsed as six outstanding — three of them with no title, no points and no
    destination to open. The comment there already said "keep the richest copy"; this is
    that, implemented.

    Richest wins per field, and earlier-ranked copies are not overwritten by poorer
    ones, so a populated `title` is never replaced by a missing one.
    """
    ranked = sorted(
        objs,
        key=lambda o: sum(is_present(o.get(k)) for k in INFORMATIVE_KEYS),
        reverse=True,
    )
    merged: dict = {}
    for obj in ranked:
        for key, value in obj.items():
            if is_present(value):
                merged.setdefault(key, value)

    # Completion is the one field where disagreement must not be resolved by rank.
    # Re-doing a finished card costs a wasted navigation; skipping an unfinished one
    # loses the points silently, and the per-card confirmation catches the first case
    # anyway. So when the copies disagree, treat the card as still to do.
    flags = {o["isCompleted"] for o in objs if isinstance(o.get("isCompleted"), bool)}
    if len(flags) > 1:
        logger.warning(
            "Offer %s reports both complete and incomplete; treating it as outstanding.",
            merged.get("offerId"),
        )
        merged["isCompleted"] = False

    return merged


# --------------------------------------------------------------------------- #
# Flight-stream extraction
# --------------------------------------------------------------------------- #


def extract_flight_stream(html: str) -> str:
    """
    Reassemble the React flight stream from the page's __next_f.push() calls.

    Each call looks like `self.__next_f.push([1,"…"])`. The argument is valid JSON,
    so it is parsed rather than unescaped by hand — the chunks contain quotes and
    backslashes that ad-hoc unescaping gets wrong.
    """
    chunks: list[str] = []
    needle = "self.__next_f.push("
    pos = 0

    while True:
        start = html.find(needle, pos)
        if start == -1:
            break
        open_paren = start + len(needle) - 1
        end = _match_bracket(html, open_paren, "(", ")")
        if end == -1:
            pos = start + len(needle)
            continue
        try:
            payload = json.loads(html[open_paren + 1 : end])
            if isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], str):
                chunks.append(payload[1])
        except (ValueError, TypeError):
            pass
        pos = end + 1

    return "".join(chunks)


def _match_bracket(text: str, start: int, opener: str, closer: str) -> int:
    """Index of the bracket closing the one at `start`, or -1. String-aware."""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i
    return -1


def iter_objects_containing(text: str, key: str) -> Iterator[dict]:
    """
    Yield the smallest balanced JSON object around each occurrence of `key`.

    Scanning with a stack means inner objects close first, so each occurrence is
    claimed by the tightest object that encloses it — an outer wrapper holding the
    same key is skipped rather than returned as a duplicate. This is what makes the
    result trustworthy where a regex window would bleed into the neighbouring object.
    """
    marker = f'"{key}"'
    claimed: set[int] = set()
    stack: list[int] = []
    in_str = False
    esc = False

    for i, c in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue

        if c == '"':
            in_str = True
        elif c == "{":
            stack.append(i)
        elif c == "}" and stack:
            start = stack.pop()
            segment = text[start : i + 1]
            hits = [start + m.start() for m in re.finditer(re.escape(marker), segment)]
            if not hits or all(h in claimed for h in hits):
                continue
            try:
                obj = json.loads(segment)
            except ValueError:
                continue  # let an enclosing object try instead
            if isinstance(obj, dict):
                claimed.update(hits)
                yield obj


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #


def extract_ready_to_claim(stream: str) -> int | None:
    """
    Recover the "Ready to claim" total from the flight stream.

    Unlike the balance, which arrives as a clean `{"balance": N}` field, this number
    exists only inside the rendered element tree: a label node carrying the text
    "Ready to claim", followed by a heading node holding the digits. Matching on
    presentation is more fragile than reading a field — a restyle breaks it — so this
    returns None rather than guessing, and callers should treat None as "unknown"
    rather than "zero".
    """
    for match in re.finditer(r'"children":"Ready to claim"', stream):
        window = stream[match.end() : match.end() + 1500]
        hit = re.search(r'"text-pageHeader","children":"?(\d[\d,]*)"?', window)
        if hit:
            try:
                return int(hit.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


def parse_dashboard(html: str) -> DashboardState:
    """Parse a dashboard or /earn HTML document into structured state."""
    stream = extract_flight_stream(html)
    if not stream:
        logger.warning("No __next_f flight stream found — page layout may have changed.")
        return DashboardState()

    state = DashboardState()

    # One card ships as more than one object, so group by id before building Offers.
    grouped: dict[str, list[dict]] = {}
    for obj in iter_objects_containing(stream, "offerId"):
        offer_id = obj.get("offerId")
        if not isinstance(offer_id, str) or not offer_id:
            continue
        grouped.setdefault(offer_id, []).append(obj)

    for offer_id, objs in grouped.items():
        obj = merge_offer_objects(objs)
        points = obj.get("points")
        completed = obj.get("isCompleted")

        # A tile with neither renders both inside its children; without this it parses
        # as a nameless, valueless card that looks exactly like a banner.
        title, description = obj.get("title"), obj.get("description")
        if title is None or description is None:
            from_children = text_from_children(obj)
            title = title if title is not None else from_children[0]
            description = description if description is not None else from_children[1]

        state.offers.append(
            Offer(
                offer_id=offer_id,
                title=title,
                description=description,
                points=points if isinstance(points, int) else None,
                is_completed=completed if isinstance(completed, bool) else None,
                date_text=obj.get("date"),
                # href is the element copy's name for the same URL; measured equal to
                # destination on every card of the 2026-08-19 capture. Kept as a last
                # fallback because a card with no destination cannot be opened at all.
                destination=obj.get("destination") or obj.get("ctaUrl") or obj.get("href"),
                cta_text=obj.get("ctaText"),
                raw=obj,
            )
        )

    state.ready_to_claim = extract_ready_to_claim(stream)

    for obj in iter_objects_containing(stream, "balance"):
        if isinstance(obj.get("balance"), int):
            state.balance = obj["balance"]
            if isinstance(obj.get("level"), int):
                state.level = obj["level"]
            break

    for obj in iter_objects_containing(stream, "maxValue"):
        if isinstance(obj.get("maxValue"), int) and isinstance(obj.get("value"), int):
            state.counters.append(
                {
                    "value": obj["value"],
                    "maxValue": obj["maxValue"],
                    "label": obj.get("aria-label") or obj.get("label"),
                }
            )

    return state


def parse_dashboard_file(path) -> DashboardState:
    """Convenience wrapper for offline work against a capture."""
    from pathlib import Path

    return parse_dashboard(Path(path).read_text(encoding="utf-8", errors="replace"))

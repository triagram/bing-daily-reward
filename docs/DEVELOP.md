# Development notes

Working notes for people changing this project, as opposed to using it. The README
is the user-facing document; this is the lab notebook.

Three sections, each with its own trigger for going stale:

- **[Data contract](#data-contract)** — what the dashboard actually returns. Goes
  stale when Microsoft redeploys the dashboard.
- **[Open questions](#open-questions)** — hypotheses not yet settled. This is the real
  work queue; an entry leaves only when an experiment settles it.
- **[Tooling](#tooling)** — which script is for what, and why there are three.

---

## Data contract

### The dashboard ships its state inside the HTML

`rewards.bing.com` is a Next.js app using React Server Components. Confirmed by
capture on 2026-08-11: of 144 requests during a dashboard load, **none was a data
API**. The only non-static responses were the HTML documents themselves.

State arrives serialised in the document as a sequence of

```js
self.__next_f.push([1, "<chunk>"])
```

whose chunks concatenate into React's flight stream. `utils/dashboard_state.py`
reassembles that stream and pulls structured objects out of it.

This matters because it contradicts what older Microsoft Rewards projects assume.
Field names from the previous dashboard API — `pointProgress`, `pointProgressMax`,
`promotionType`, `dailySetPromotions`, `availablePoints` — **all return zero matches**
against the current page. Do not port a schema from another project; capture and look.

### Offer objects

Real field names, verified against a live capture:

| Field | Type | Notes |
|---|---|---|
| `offerId` | str | Self-describing, see below |
| `title` | str | Display name, e.g. "Bonus Quiz" |
| `description` | str | Sub-line, e.g. "3 answers = 30 points" |
| `points` | int | Value of the task. `null` on promo banners |
| `isCompleted` | bool | **The completion flag** |
| `date` | str | `MM/DD/YYYY`. Prefer the id's date, see below |
| `destination` | str | Where the card sends you |
| `ctaUrl` / `ctaText` | str | Used by banners instead of `destination` |

### `offerId` is structured, and is the reliable key

```
Gamification_DailySet_ENGB_20260811_Child2
└────┬─────┘ └───┬───┘ └┬─┘ └───┬───┘ └─┬──┘
   family      kind   market   day     slot
```

Parsed by `OFFER_ID_PATTERN` into `Offer.market`, `Offer.day`, `Offer.slot`.

**Take the date from the id, not from the `date` field.** The id is a key and cannot
drift from the offer it names; the `date` field is display data. They have been seen
to disagree.

### The page carries several days at once

A dashboard load returned 13 offers spanning **three dates** (yesterday, today,
tomorrow); `/earn` returned 36 offers across four. Anything that picks tasks without
filtering by date will act on the wrong day's offers. This is why
`DashboardState.daily_set()` takes a day and defaults to today.

### Category counters are daily gates, not search counts

The four progress rings, recovered as `{label, value, maxValue}`, render the
dashboard's **"Your activity"** section. Confirmed against the capture screenshot,
which prints the sub-label of each ring:

| `aria-label` | On-screen sub-label | Observed | Meaning |
|---|---|---|---|
| `Bing` | **"Search: 1/1"** | 1 / 1 | Did any qualifying search happen today. Binary |
| `Daily Set` | "Activity: 0/3" | 0–1 / 3 | Daily-set cards done. Disagrees with the cards, see Q2 |
| `Edge` | "How to activate" | 0 / 30 | Not activated on this account |
| `Mobile App` | "Check-in: 0/1" | 0 / 1 | Binary |

**There is no search-count counter anywhere on the dashboard.** "Search: 1/1" has a
maximum of one: it records *that* you searched, not *how many times*. Anything
wanting to know the daily search allowance has to establish it by measurement — the
page will not report it.

Streaks are tracked separately, under **"Your progress"**: a `Daily streak` reading
28 days at capture time, plus a stamp card. So the rings are not streak counters
either; they are today's completion gates.

The allowance therefore cannot be read off the page — it has to be measured, and it
was (Q6): **20 searches at 3 points each, 60 in total.** That is exactly what
`DAILY_SEARCH_COUNT = 20` and its comment already said. Earlier revisions of this
file called those numbers unfounded guesswork; they were correct, and the fault lay
in how queries were issued (Q1), not in the parameters.

### Earnings land in "Ready to claim", not the balance

An accidental single mobile search, with clean samples either side and nothing else
happening that day:

| Sample | balance | unclaimed | total | `Bing` | `Mobile App` |
|---|---|---|---|---|---|
| 12:01 | 107345 | 9 | 107354 | 0/1 | 0/1 |
| 18:00 | 107345 | **12** | **107357** | **1/1** | 0/1 |

Three findings from one search:

1. **The balance did not move. The unclaimed pot rose by 3.** Measuring the balance
   alone would have scored this run as earning nothing — a false negative. Any
   measurement must compare `balance + ready_to_claim`; `SearchResult` now does.
2. A **mobile browser search satisfies the `Bing` gate**, so that ring is not
   desktop-specific.
3. It does **not** satisfy `Mobile App`, which presumably wants the Bing app itself.

This also puts Q1's original reading in doubt from the other side: that run saw the
balance move by 3, where this one saw the pot move instead. Whether the routing
differs by device, by point type, or by when the pot flushes is not yet known.

**Answered in part, 2026-09-12:** it is by point type. The pot's `pointClaim.entries`
carry a `category`, and the 3 here was `ds` — the search *streak's* daily credit, not
the search's own 3, which the bot's typed searches put straight into the balance. See
[Streak payouts, measured](#streak-payouts-measured--the-weekly-overshoots-and-the-stamp-bonus).

### Other things the dashboard shows that the parser does not yet read

Visible in the capture screenshot, absent from `DashboardState`:

- **"Ready to claim"** — a separate pot of unclaimed points (6 at capture time).
  Points can sit here without being in the balance, which matters for any
  before/after measurement.
- **An active 2x perk** — "For a limited time, search 2x more per day to earn more
  points", with a Claim offer button. This changes search economics while it lasts
  and would confound Q1 if it expires mid-experiment.
- **Monthly bonuses** — Bing Star bonus 2,100, monthly level-up 420, default search
  bonus 210, all shown as fully earned last month.

### Streaks and the stamp card dwarf the daily tasks

Visible on `/earn`, 2026-08-16, and absent from every value estimate made before then:

| Source | Reward | Progress at capture |
|---|---|---|
| **Bing Search Streak** | **100 points** per 6 consecutive days | 3 of 6 |
| **Stamp Bonus** | **1,000 points** for 12 stamps | 5 of 12 |
| Daily streak | (feeds the above) | 34 days |

Against 60 a day from searches and 30 from a daily set, these change what is worth
optimising. **Consistency beats extraction**: the streak needs the daily activity gate
satisfied, and that gate is `Search: 1/1` — *one* search. Running the full 20-search
allowance does nothing for it.

That aligns with lowering the profile rather than trading against it: turning up every
day, modestly, is both what the streak rewards and what looks least like a script.

### The /earn sections, and why only two need code

Examined 2026-08-18. The page has seven headings, but they are presentation, not
distinct task types:

| Section | Status |
|---|---|
| **Explore on Bing** | ❌ **not covered** — corrected 2026-08-20, see below |
| **Keep earning** | covered by `run_keep_earning`, which is named for it |
| **Quests** | multi-task bundles; progress is a by-product of the daily work |
| **Level up activities** | long-running achievements, not clickable tasks |
| **Streaks / Stamp Bonus** | earned by turning up daily; nothing to click |

**Keep earning needed no work at all.** Its items on 2026-08-18 were Dinner delight,
South African vistas, Complete this puzzle and Book Flights with Bing — precisely the
four `run_keep_earning` had completed the day before. Selecting offers by *having a point
value and being incomplete*, rather than by which heading renders them, covers the
page's sections without knowing they exist. Worth preserving: a section-anchored
selector would have missed these and needed a module per heading.

**Correction, 2026-08-20: "Explore on Bing" was never covered.** The claim above was
made by matching titles across headings and it matched the wrong ones. What
`run_keep_earning` — called `run_explore` until 2026-08-22, which is how the confusion
started — actually does is `WW_Bing_MonthlyFeaturedTopic_*` and
`ENstar_Rewards_DailyGlobalOffer_*` — Gong instrument music, Explore the reef, Quote of
the day — which render under other headings. The literal "Explore on Bing" section is a
different offer family and the bot has never touched one.

Observed on the live page, 2026-08-20: the section reads **`0/40`** and carries tiles
worth **+10 each** — Take off soon, Park with ease, Send a smile, Stream your
favourites, Know your score, plus others marked "Unlocks tomorrow".

Two reasons it is skipped, and the second is the interesting one:

1. **`outstanding_offers()` filters them out.** Their payload has no `points` field at
   all, and that selector treats a missing point value as the signature of a banner.
   The rendered `+10` comes from somewhere other than the object the parser reads.
   Their ids are `ENUS_<topic>_exploreonbing_activation_Evergreen…`, and their payload
   keys are `children, hash, href, isCompleted, isDisabled, isLocked, successToast` —
   a different shape from every offer the bot handles.

2. **They are not links to a search result.** Every offer `run_keep_earning` completes points
   at `bing.com/search?q=…`; these point at
   `https://www.bing.com/?…&rwAutoFlyout=exb` — the Bing **home page**, with a flyout
   parameter.

**Mechanism, from the account holder who has completed these by hand (2026-08-20): the
tile must be opened *and* the topic searched — both, together.** Not the tile alone, and
not a search on its own either. `rwAutoFlyout=exb` reads as arming the offer for the
session it opens; the search then has to happen in that context. This supersedes the
inference recorded first, which had it as a search *instead of* opening the tile.

**Worth roughly 40 points a day** — comparable to an entire daily set, against the ~99
a current run measures. This is the largest known gap in coverage, ahead of Q8.

**Structure to build on**, from the 2026-08-19 `/earn` capture:

| Where | What |
|---|---|
| `instrument.name` | `"ExploreOnBing_Card"` — a clean family marker, steadier than an id substring |
| `offerId` | carries the topic: `airlinetickets`, `airportparking`, `flowerdelivery`, `streamingservices`, `bankaccounts`, `concerttickets`, `lyrics`, `rentalcars` |
| `isLocked` / `isDisabled` | **both `true` on the airlinetickets tile on 08-19** |
| nested image `alt` | the title — "Take off soon" |
| `href` | the Bing home page with `rwAutoFlyout=exb` |

**Tiles unlock progressively, and the lock state explains the cap.** Read off a capture
taken 2026-08-20 20:54, before any of them was completed:

| Topic | `isCompleted` | `isLocked` / `isDisabled` |
|---|---|---|
| `airlinetickets`, `airportparking`, `flowerdelivery`, `streamingservices` | False | **false — open** |
| `creditreport`, `health`, `recipe`, `videogames` | False | true — locked |

Four open at 10 points each is exactly the **`0/40`** the section header shows, so the cap
counts the unlocked tiles rather than all eight.

**The pool rotates daily, and "Unlocks tomorrow" is literal.** Captures a day apart:

| Capture | Open | Locked |
|---|---|---|
| 08-19 22:19 | `bankaccounts`, `concerttickets`, `lyrics`, `rentalcars` | `airlinetickets`, `airportparking`, `flowerdelivery`, `streamingservices` |
| 08-20 20:54 | **`airlinetickets`, `airportparking`, `flowerdelivery`, `streamingservices`** | `creditreport`, `health`, `recipe`, `videogames` |

Yesterday's locked four are today's open four, and four fresh topics arrive locked. So
the section is worth a steady **40 points a day**, not a backlog to clear, and a run
should take exactly the unlocked four and leave the rest — they are tomorrow's work, not
missed work. Four captures across 34 minutes on 08-20 were identical, so the rotation is
not drifting within a day. Locked ones render greyscale with a
padlock and the caption "Unlocks tomorrow". A run must therefore read
`isLocked`/`isDisabled` and skip, or it will spend effort on tiles that cannot pay — and
must not infer availability from what the section lists.

**First attempt failed, on a locked tile (2026-08-20).** The account holder opened
`creditreport` — "Know your score", which renders first in the section — reported that
it led to a blank Bing page requiring them to type the query themselves, and searched
related terms. Captures either side, 20:54 and 21:11:

- **No tile changed.** `isCompleted` False on all eight before and after; `isLocked` and
  `isDisabled` unchanged; not one field differed on any tile.
- **The balance rose 21 points** in the same window — seven ordinary searches at three.
  So the searching did earn, through the normal allowance, and nothing reached the offer.

`creditreport` was `isLocked: true` in both captures, so the simplest reading is that a
locked tile cannot pay however it is searched, and the attempt tested nothing about the
mechanism. Rendering order is not availability: it sits at the top of the section while
locked, with "Unlocks tomorrow" beside it. **Retest on one of the four open tiles before
concluding anything about how these credit.**

**Reported unreliable by hand.** The account holder describes credit for this offer type
as hit-and-miss with an apparent delay, across attempts predating this project. If that
holds, it changes whether the task is worth building at all: a task that often does the
work and earns nothing would drive `shortfall` to `zero`/`short` on ordinary days, and
`Flags` is the instrument the observation window's exit criterion reads. Building it
would mean giving it a best-effort verdict of its own rather than the standard
comparison — otherwise the fix for silent failure becomes a source of false alarms.

**Built 2026-08-22, unproven by design.** `utils/task_explore_on_bing.py`, run from
`explore_on_bing.py` rather than from the daily run, so an assumption that may be wrong
cannot put a verdict into the Flags column the observation window reads.

It encodes everything settled above: select on `exploreonbing`, skip anything `isLocked`
or `isDisabled`, take the topic from the offer id, open the tile, and type the query into
whatever the tile opened **without navigating first** — navigating would discard the
session `rwAutoFlyout=exb` establishes, which is the one thing this offer type appears to
need. Verified against every capture on disk: it picks exactly the four open tiles each
day, and follows the rotation across 08-20 to 08-21 without being told about it.

What it cannot do is prove the mechanism. That comes from the first real run: because
each tile is confirmed by its own `isCompleted`, a wrong assumption shows up as an honest
`0/4`, not as a fabricated success. The entry point says so in as many words when nothing
completes.

**2026-08-23 — the mechanism is right; the query is what fails.** First run with queries
taken from the tiles' own prompts: **1 of 4**, up from 0 of 4 the day before.

Every tile recorded `tile-click+search:'…'`, meaning all four were opened, found a search
box, were typed into and submitted. So the assumed mechanism — open the tile, then search
its topic inside what it opens — **executed identically on all four**, and something
other than the mechanism decides whether it pays.

| Topic | Query typed | Result |
|---|---|---|
| `couponcodes` | the latest coupon codes and discounts | **✓ +10** |
| `hotel` | hotels to stay at on **your next adventure** | ✗ |
| `realestate` | real-estate available in **your dream town** | ✗ |
| `shopping` | items on **your shopping list** | ✗ |

The one that paid is the only one whose prompt contains no placeholder. "your next
adventure", "your dream town" and "your shopping list" are instructions to substitute
something concrete, not strings to type — and hotels, property and shopping are Bing
verticals that need a real entity before they render anything. A capture 3½ hours later
had all three still `isCompleted: false`, so this is not crediting lag.

Measured points corroborate the one success: +22 for the run is the tile's 10 plus four
ordinary searches at 3.

**2026-08-23, later — the placeholder hypothesis was never tested, and the real cause is
found.** The retry with concrete queries returned 0 of 3. Not a falsification: those
three tiles had never been activated in either run.

**Every tile in the section shares one href.** Seven tiles,
`…bing.com/?…&rwAutoFlyout=exb` for all seven. The task located tiles the way everything
else in this project does — match the whole destination URL — which here resolves to
whichever card the page renders first, every time.

So what actually happened both runs:

| Attempt | Asked for | Clicked | Result |
|---|---|---|---|
| 11:42 #1 | `couponcodes` | `couponcodes` — first in the DOM | ✓ |
| 11:42 #2-4 | hotel, realestate, shopping | `couponcodes` again, already finished | ✗✗✗ |
| 15:30 #1-3 | hotel, realestate, shopping | `couponcodes` again | ✗✗✗ |

One success, and it is the one tile that happened to be first. Nothing about queries was
ever measured.

**The mechanism was right from the start.** The completed tile's `successToast` reads
**"Activated! · Search on Bing to complete this activity"** — click to activate, search
to complete, exactly as the account holder described.

**Fixed by locating on the tile's own title**, which is unique where the URL is not:
measured against the same capture, each open tile matched exactly one anchor by its
text and each locked tile matched none, a locked tile not being a link. Exactly one
match is required, since clicking the first of several is precisely how this looked from
the outside.

Worth generalising: *matching the whole URL is the strongest signature only while URLs
distinguish things.* This family is the counter-example, and it produced a failure that
imitated a wrong hypothesis about crediting for a full day.

**2026-08-24 — 2 of 4, and the first data about queries that means anything.** With the
right tile being clicked, the day split cleanly:

| Topic | Query | Result |
|---|---|---|
| `creditcards` | credit cards with top rewards and rates | **✓** |
| `insurance` | the best insurance plans for **your needs** | **✓** |
| `flight` | a flight to **your perfect vacation** | ✗ |
| `shopping` | items on **your shopping list** | ✗ |

Points reconcile exactly: +32 is two tiles at 10 plus four ordinary searches at 3.

**The placeholder hypothesis is now properly dead.** `insurance` carries "your needs"
and paid. Wording is not the variable.

**What replaces it: whether the topic needs a concrete entity.** Credit cards and
insurance are informational searches Bing answers as they stand. Flights and shopping
are verticals that render nothing without a route or a product — and a tile that
completes on "search this topic" plausibly wants that vertical experience to appear. The
split held on 08-23 too: `couponcodes` paid; `hotel` and `realestate`, both of which need
a place, did not.

**Confirmed the same day, 2/2.** `flights from London to Paris` and
`buy wireless headphones` both completed, on the same two tiles that had just failed on
their prompt text, with nothing else changed. +26 reconciles as two tiles at ten plus two
searches at three. The day finished 4 of 4 — the full 40.

### How an Explore on Bing tile actually credits

Settled, after four days and four wrong turns:

1. **Click the tile.** This *activates* it — the toast says so: "Activated! · Search on
   Bing to complete this activity". Locate it by its own title; all tiles share one href
   and matching that clicks whichever renders first.
2. **Search its topic in what the tile opened**, typed, without navigating away first —
   navigating discards the session the tile established.
3. **Search the tile's own prompt.** This is usually enough — 2026-08-25 completed 4 of
   4 on prompt text alone, placeholders and all.
4. **A few topics need more, and which ones is not understood.** `flight` and `shopping`
   both stayed incomplete on their prompts and completed once given a concrete entity —
   a route, a product. The obvious generalisation, that Bing verticals need an entity
   before they render anything, **is false**: `rentalcars`, `concerttickets` and
   `internetproviders` are verticals too, were searched with placeholders and no entity,
   and all three completed. So these are exceptions with no known common factor, and the
   map that holds them is a list of measurements, not a rule.
5. Only unlocked tiles can pay, and four unlock a day.

**Step 2 is not always required, 2026-09-06.** `couponcodes` was clicked, and the click
did not open Bing — the page stayed on `rewards.bing.com/earn`, where there is no search
box, and the run logged `no search box on https://rewards.bing.com/earn`. **No query was
ever typed for that tile.** It credited anyway, ~2.5 minutes later, on the re-read the
run does before calling a tile failed.

The arithmetic is what makes this more than a guess. The run measured **+39** for three
confirmed tiles: 3 × 10 for the tiles, plus 3 × 3 for the searches — and only three
searches were typed all run (`hotel`, `realestate`, `shopping`). `couponcodes` earned its
10 with zero searches.

So activation alone can credit a tile. It plainly does not always: every failed tile in
this log was also clicked, and therefore also activated, without crediting. What decides
it is unknown, and one sighting is not enough to change the method — searching after the
click stays, because it is what the other tiles need. Recorded so the next session does
not read "the search is what credits" as settled.

It also costs the 2026-09-05 retry some of its force. That run was read as "the query
fixed those three tiles"; if activation can credit on its own, a second activation is a
live alternative explanation for the same outcome. The clean test is unchanged — those
topics recur, and will arrive unactivated.

So the default query is the tile's prompt, and `VERIFIED_QUERIES` is an exception list
grown one measured entry at a time.

**A sharper reading of which topics need help, 2026-08-28.** `jobs` failed on
"open roles at **a specific company**" while `restaurant` completed on "a restaurant
**near you**" the same run. Both prompts carry a placeholder; the difference is whether
Bing can resolve it unaided. Location it can — "near you", "in your area" — and those
tiles complete. A company, a route, a product it cannot, and those are the three topics
that have ever needed an override.

That is a better account than "verticals need an entity", which 08-25 disproved, but it
is still a description of five observations rather than a rule. The map stays a list of
measurements.

**And that reading breaks too, 2026-09-06.** `hotel` failed on "hotels to stay at on
**your next adventure**". `rentalcars` completed on 2026-08-25 searching "book rental cars
for **your next adventure**" — the same placeholder, in the same unresolvable-by-Bing
class, with the opposite outcome.

Two topics, one wording, and the results disagree. **So the discriminator is not in the
prompt text at all**, and every attempt so far to find a rule in the wording — "verticals
need an entity", "Bing must be able to resolve the placeholder" — has been reading a
property of the topic off the only thing that varies visibly. `VERIFIED_QUERIES` still
works as an exception list because substituting an entity does fix the topics on it. It
just is not evidence for why.

What has not been ruled out, and is cheap to watch for: that the tiles differ in what the
click opens. `couponcodes` opened nothing at all the same day.

**Sharper still, and it undercuts the map itself — noticed 2026-09-12 on the ledger, not
on a new run.** The comparison above used two topics. `hotel` supplies it with one:

```
08-30 12:43  'hotels to stay at on your next adventure'  ✓
09-06 12:30  'hotels to stay at on your next adventure'  ✗
```

Same topic, same query, a week apart, opposite outcomes — both well after the mechanism
was settled, so neither is an artefact of the 08-23 era. **There is a per-attempt failure
that no property of the query explains**, and the map has been reading structure into it.

This does not make `VERIFIED_QUERIES` wrong to keep: every entry has been measured to
work, and a query that works is worth keeping whatever the reason. It makes the *claim*
wrong. Each entry was verified by a **second attempt on the same day**, on a tile the
first attempt had already activated, and `hotel` shows an attempt can fail and then
succeed with nothing changed at all. So "the entity fixed it" and "the retry fixed it"
are both still live for all seven.

What keeps "a retry always fixes it" from being the answer: `recipe` and `lyrics` each
failed their same-day retries. Something real is topic-specific. It is simply not the
wording, and the size of the random component is unmeasured.

**The test that would settle it costs nothing but patience.** Topics recur — the gap
between sightings clusters hard at 7 and 14 days across 26 observed pairs. So each of the
seven will return on an unactivated tile. Let it run on its own prompt when it does,
rather than on its override, and the answer arrives on its own. Until then, do not add an
entry on the strength of one failure alone.

**A tile loses its description once activated — corrected 2026-09-04.** `lyrics` was
written off on 09-02 as a malformed card, on the evidence that its whole subtree held one
string where a working tile holds four. That reading was **wrong**, and the captures say
so plainly:

| Capture | Tile | Description | Attempted yet? |
|---|---|---|---|
| 08-19 | `lyrics` | **present** | no |
| 08-20 ×5, 08-21 | `recipe` | **present** | no |
| 09-02 | `lyrics` | absent | yes, and failed |
| 09-04 | `recipe` | absent | yes, and failed |

The text disappears **after** the tile is activated. So an empty description is a
consequence of having tried, never a cause of failing, and `lyrics` remains unexplained
rather than explained.

Two things follow. A tile's prompt has to be read *before* working it, which the task
already does. And a same-day retry cannot re-derive the query from the page — the text
is gone by then — so an override has to carry it, which is what `recipe` is doing now.

**It holds nothing unmeasured, deliberately.** `hotel` and `realestate` were briefly given
predicted entries on the entity reasoning; they came out on 2026-08-25 when that reasoning
failed. The stronger objection is that a guessed override destroys the observation it is
guessing at: with "hotels in Edinburgh" in the map, whether `hotel` completes on its own
prompt can never be found out. Letting the default run costs one tile once and buys a real
data point.

**What was wrong along the way, and worth remembering.** The mechanism was doubted for a
day when it had been right from the start; crediting lag was suspected and ruled out; the
placeholder wording was blamed twice and is not the cause; and the whole picture was
obscured by clicking the wrong tile, which produced results that imitated a plausible
theory about crediting rules. Every one of those was settled by the same move — change
one thing, keep the rest fixed, and let the per-tile `isCompleted` answer.

**How this gets answered at all.** Microsoft's crediting rules are not observable; only
behaviour is. What makes the question tractable is that each tile is its own trial with
`isCompleted` as ground truth, four arrive daily, a failed one can be retried the same
day, and `logs/explore_on_bing.jsonl` now records the query and method per tile. So the
method is ordinary: change one thing, keep the rest fixed, write down what happened, and
prefer a hypothesis that survives several days of it over one that explains a single day.

**Original sketch, before it was written:** select on `exploreonbing` and not locked; open the
tile with `execute_action_and_cleanup_new_tab`; in the tab it opens, type a query derived
from the topic in the offer id — typed, never navigated (Q1) — and confirm that tile's own
`isCompleted` flipped before counting it, as every other task does. The topic comes from
the id rather than from the description prose, on the same reasoning that anchors
selectors on URL signatures rather than CSS.

**Quests** are bundles like "Make this August more rewarding, +50, 0/4 tasks" and
"Spotify playlists on the house, 0/6 tasks", with an expiry. Their sub-tasks are the
daily activities themselves, so they advance by doing the ordinary work. Some reward
perks rather than points.

**Level up activities** read "Search with Bing for 7 days in a row" (in progress) and
"Set Bing as your default search engine for 14 days" (completed) — conditions met by
persistence, with nothing to automate.

### Streak arithmetic, which favours consistency over extraction

Read off `/earn` on 2026-08-18:

```
Bing Search Streak    Day 2 of 7 — complete the next day to earn 3 points    → 100 at 7
Daily Set Streak      Day 1 of 7 — complete the next day to earn 30 points   → 100 at 7
Stamp Bonus           5 of 12 stamps                                          → 1,000
```

A daily set is worth 30-50 points on its own; sustaining its streak is advertised at
30 points for the next day alone, before the 100 at seven. Against that, the marginal
value of squeezing the last searches out of a day is small — which is why the search
count was narrowed rather than maximised, and why an unbroken run of modest days beats
an occasional exhaustive one.

Out of reach by architecture, not merely unimplemented: `Mobile App 0/1`, the "Download
Bing app to earn 500 points" offer, and anything else needing the Bing phone app. This
project drives a desktop browser. Excluded from the task inventory by decision on
2026-08-16 rather than left looking like an oversight.

**That decision was walked past on 2026-09-02**, by a family that carries a point value
like any other offer: `WW_Moreactivities_RewardsApp_offer_*`, titled "… (Rewards App
only)", five of them at 10 points, with perfectly ordinary `bing.com/search?q=…`
destinations. `outstanding_offers()` selects on having points and being incomplete, so
they qualified.

The damage was not the five failed navigations. Being the highest-valued things
outstanding they sorted to the front of a run capped at six, and **"Quote of the day"
was never attempted at all** — a real offer lost to five impossible ones. `keep_earning`
finished 1 of 6 and flagged, breaking an eleven-run clean streak.

Now excluded by both signals the page gives, the id and the title, since a redesign is
likelier to keep one than both. Worth remembering as a shape: *a rule that selects on a
property rather than an enumeration will pick up whatever new thing shares that
property.* The property here was "has points and is not done", and it was correct right
up until Microsoft shipped offers that have points and cannot be done.

### Streak payouts, measured — the weekly overshoots and the stamp bonus

Read off `captures/samples/earn-*.html.gz` (the monitor archives `/earn` every sample,
and the streak cards carry "Day N of 7" plus the stamp card's `activityProgress`), then
matched against `logs/runs.jsonl` and the observation logs. Seven sightings, every one
exact:

| Date | Streak reaching day 7 | Where the money went |
|---|---|---|
| 08-22 Sat | Bing Search | 8 searches: balance +21, pot +100 |
| 08-28 Fri | Daily Set | balance +100 against three 10-point cards |
| 08-29 Sat | Bing Search | 9 searches: balance +24, pot +100 |
| 09-04 Fri | Daily Set | balance +100 against three 10-point cards |
| 09-05 Sat | Bing Search | a search by hand before the run: pot +100; the bot's 9 then paid 27 |
| 09-11 Fri | Daily Set | balance +100 against three 10-point cards |
| 09-12 Sat | Bing Search | a search by hand before the run: pot +100, **balance +1000** |

Three rules follow:

1. **On day 7, the gate activity pays 100 instead of its normal value.** The daily set
   pays 100 into the balance in place of 30; the gate search pays 100 into the pot in
   place of 3 — which is why 08-22 and 08-29 each show one search's 3 missing from the
   balance. This is the streak card's own promise ("Complete the next day to earn 100
   points" on day 6, 3 or 30 on the other days), and it is why `daily_set` reads
   `100 / 30` and `searches` reads `+100` over on those days. **Both are expected, not
   overshoots.**
2. **The cadence is weekly and fixed** on this account: the Daily Set Streak completes
   every Friday, the Bing Search Streak every Saturday. Each completion also adds a
   stamp, so two a week.
3. **Twelve stamps pay 1,000 straight into the balance**, then the card resets. Seen
   once, 2026-09-12: `activityProgress` 11 → 0 and the balance +1000 between the 12:28
   monitor sample and the 15:39 run start, with the bot idle. Two stamps a week puts the
   next one about six weeks out.

Where the streak credit lands is visible in the dashboard's `pointClaim.entries`, each
carrying a `category`: `ds` is the streak's daily credit (3 on days 1-6, 100 on day 7),
which is the "3 pending" seen at the top of so many runs. That is also what the
2026-08-13 mobile search in *Earnings land in "Ready to claim"* measured — the streak's
3 for the day, not the search's own.

**Monthly bonuses land the same way, and are the largest single deposit on the account.**
On 2026-09-01, between the 13:34 run and the 18:57 sample, the pot went 0 → 1,830:
`mtb` 420, `gub` 1,200, `bseb` 210, all dated `2026-09` and all expiring 2026-10-04. The
codes are not documented anywhere on the page; against the "last month" figures at
*Other things the dashboard shows*, 420 is the monthly level-up and 210 the default
search bonus, which leaves 1,200 as the Bing Star bonus (2,100 in August). The next
run's claim moved all of it (09-02, `moved: 1833`), which is the strongest argument yet
for that step: an unclaimed pot **expires**, and this one was eighteen days of ordinary
earning.

### Market

This account is `ENGB` (UK). Task sets and point values differ by market, so numbers
found in projects targeting the US market do not transfer.

---

## Open questions

Each entry leads with its answer, then the cause and what was changed. **This is the
work queue** — an entry closes only when an experiment settles it.

| # | Question | Status |
|---|---|---|
| [Q1](#q1) | Why did four searches earn only 3 points? | ✅ Resolved 2026-08-14 |
| [Q2](#q2) | The Daily Set ring disagrees with the cards | 🔴 **Reopened 2026-08-19** |
| [Q3](#q3) | When does the daily reset happen? | ✅ Resolved 2026-08-14 |
| [Q4](#q4) | Does point crediting lag? | 🟡 Partly answered |
| [Q5](#q5) | Why does `/earn` yield no counters? | ✅ Resolved 2026-08-13 |
| [Q6](#q6) | What is the daily search allowance? | ✅ Resolved 2026-08-16 |
| [Q7](#q7) | Are the Explore offers today's, or a backlog? | 🟡 Partly — they rotate; the daily rate is unknown |
| [Q8](#q8) | What is the `Edge` 0/30 counter? | 🔴 **Open** — largest unexplored surface |

<a id="q1"></a>
### Q1 — Why did four searches earn only 3 points?

**Status:** Resolved 2026-08-14.

**Answer:** Queries issued by navigating to `bing.com/search?q=…` are **never
credited**. Queries typed into the search box pay **3 points each, within about
fifteen seconds**. Of the original four searches only the last was typed, and 3
points is exactly one search's worth.

**Cause:** `_search_once()` chose its input method at random, sending roughly 70% of
every run by navigation. Most of each run was unpaid work that still accumulated
behavioural signal — the worst of both.

**Fix:** `_search_once()` now always types. `force_input_mode` is kept so the
comparison can be repeated if Rewards changes.

**Evidence** — same account, same machine, seventeen minutes apart:

| Input mode | Queries | Per search | Total | `Bing` gate |
|---|---|---|---|---|
| `url` (12:55) | 6 | +0 each | **0** | 0/1 → 0/1 |
| `type` (13:12) | 3 | **+3 each** | **+9** | 0/1 → 1/1 |

The gate not moving in the `url` run is what rules out a filled quota: a spent
allowance would still have registered the search. The typed run settling in seconds
also disposes of "counts but credits late".

The typed run used **fresh terms deliberately**. Reusing the morning's queries could
not have separated "this input mode does not work" from "this query was already spent
today", so `run_daily_searches` takes a `terms` override.

<a id="q2"></a>
### Q2 — The Daily Set ring disagrees with the Daily Set cards

**Status:** 🔴 **Reopened 2026-08-19.** The answer below fits every observation up to
08-17 and none after it.

**What reopened it.** `logs/state_samples.jsonl` records the ring tracking *today*, in
near real time:

| Sample | Ring | Cards done that day | Cards done previous day |
|---|---|---|---|
| 08-18 06:24 | 0/3 | 0 so far | 3 (08-17) |
| 08-18 12:18 | **3/3** | 3, at 10:16 | 3 (08-17) |
| 08-18 18:20 | 3/3 | 3 | 3 |
| 08-19 06:40 | **0/3** | 0 so far | **3 (08-18)** |
| 08-19 19:03 | 0/3 | 0 so far | 3 (08-18) |

The 08-18 pair is decisive in the opposite direction from the pair below: the ring went
0/3 → 3/3 within two hours of the cards being completed **on the same day**. And on
08-19 it read 0/3 all day without carrying over 08-18's three, which "shows yesterday"
requires it to do.

So the ring is not a summary of yesterday, and it is not simply today either — the
08-16/08-17 pair below is real and rules that out too. Neither model fits all seven
observations. What differs about the later ones is that the completions were made by the
rewritten task code; the earlier ones were not.

**What does not change:** gate work on `isCompleted` on the cards, never on the ring.
That rule was right for a reason that survives its justification being wrong — the ring
has now been observed disagreeing with the cards in *both* directions, which is worse
than lagging.

**Possibly the same phenomenon:** the account holder's own browser showing "Today's
points 0" on 2026-08-19 while the balance agreed exactly — see Unexplained observations.
Both are summary widgets disagreeing with the ledger. The open measurement is what the
automation profile's ring reads *after* a run, which no sample has ever captured: every
08-19 sample predates the 22:31 run.

---

**Superseded answer (2026-08-17): the ring shows the *previous* day's completions.**
Four observations fit it without exception at the time:

| Observed | Ring | Cards done **that** day | Cards done the **previous** day |
|---|---|---|---|
| 08-11 | 0/3 | 1 | 0 (08-10) ✓ |
| 08-12 | 1/3 | 0 | 1 (08-11) ✓ |
| 08-16 23:39 | 0/3 | 3 | 0 (08-15) ✓ |
| 08-17 02:13 | 3/3 | 0 | 3 (08-16) ✓ |

The 08-16 pair is the decisive one, and it came free from adding `/earn` sampling
rather than from the experiment written to chase it. At 23:39 the ring still read 0/3
hours after three cards had been completed, which rules out a short delay; by 02:13,
past the UTC reset, it read 3/3 while that day's cards were all untouched.

**Consequence (still stands, for a broader reason):** `isCompleted` on the cards is the
only source for "is this done today".

`experiments/q2_daily_set_counter.py` was written to settle this by completing one card
and watching both sources. It is unnecessary now and was never run; kept because it
would still be the right instrument if the semantics change.

<a id="q3"></a>
### Q3 — When does the daily reset happen, and in what timezone?

**Status:** Resolved 2026-08-14.

**Answer: midnight UTC** — 01:00 local during British Summer Time.

**Evidence** — samples either side of the boundary:

| Sample (BST) | UTC | `Bing` |
|---|---|---|
| 08-14 00:16 | 08-13 23:16 | 1/1 |
| 08-14 01:16 | 08-14 00:16 | **0/1** |

**Consequence:** any sample after 01:00 BST sees a fresh day, so the 06:00 sample is a
safe clean baseline. The temporary 00:15/01:15/02:15 timer entries were removed once
this closed.

<a id="q4"></a>
### Q4 — Does point crediting lag?

**Status:** 🟡 Partly answered. New evidence 2026-08-19: a run closed at 22:41 measuring
a total of 108,080, and a read-only sample at 23:26 read 108,083 — **3 points arrived
after the run had finished measuring**. So a run's own `overall_delta` can understate
what the day earned, and a small shortfall against expectation is not automatically a
failure. Not enough to characterise the lag; enough to stop treating the closing read as
final.

**Settled:** crediting is **fast** — typed searches showed up within about fifteen
seconds (Q1). And **nothing drifts on its own**: from 06:08 to 12:01 on 08-13 with no
activity, balance, unclaimed and every counter held still. The balance sat frozen at
107345 for over thirty hours while the unclaimed pot moved.

**Still open:** what moves points from the unclaimed pot into the balance, and
whether that is what the +12 and +21 on the evening of 08-12 were. Those two jumps
remain unexplained; manual account use that evening is the likeliest cause but was
never confirmed.

<a id="q5"></a>
### Q5 — Why does `/earn` yield no counters?

**Status:** Resolved 2026-08-13.

**Answer:** not a parser bug — `/earn` genuinely does not carry them. Its flight
stream contains `maxValue` **once**, against five on the dashboard, and none of those
belongs to a progress ring.

**Consequence:** read activity state from `rewards.bing.com/`; treat `/earn` as a
source of offers only.

<a id="q6"></a>
### Q6 — What is the daily search allowance?

**Status:** Resolved 2026-08-16.

**Answer: 20 searches at 3 points each, 60 points in total.** Searches 21, 22 and 23
earned nothing, in a single run from a clean post-reset state with the balance read
after every query.

```
#1 … #20   +3 each   cumulative 60
#21 #22 #23   +0      run stopped
```

**This is exactly what `config.py` already said.** `DAILY_SEARCH_COUNT = 20` (since
renamed `DAILY_SEARCH_ALLOWANCE`) and its
"3 pts each = 60 pts" comment were correct from the start. Earlier revisions of this
document, the README and CLAUDE.md all called them unfounded guesswork on the strength
of a four-search run that earned 3 — but that run was measuring the wrong thing, since
three of its four queries were navigated and therefore uncredited (Q1). **The
parameters were right; the execution was broken.** Worth remembering as a caution: a
measurement taken through a broken method discredits the parameter rather than the
method.

The dashboard publishes no search counter — the `Bing` ring is a binary gate — so this
number is only knowable by measurement, and it differs by market.

**How to settle it:** from a clean post-reset state, run typed queries with
`per_search_balance=True` and `stop_after_zero=3`. The index where the gain goes to
zero is the allowance. **Run it in the background** — the attempt on 2026-08-15 was
killed by a ten-minute command timeout before it could write its per-search log, and
a run of this length needs roughly fifteen.

**Partial observation, 2026-08-15 (measurement lost).** The interrupted run left the
account changed even though its breakdown was not captured:

| | 06:03 | 10:31 |
|---|---|---|
| balance | 107351 | 107408 (**+57**) |
| unclaimed | 15 | 115 (**+100**) |
| total | 107366 | 107523 (**+157**) |

Two things this does not explain and should not be assumed away:

- **The +100 has no visible source.** Diffing the two archived pages shows no new
  offer and no completion change; offers went 12 → 11. So it came from something
  outside the daily tasks — a search milestone, a level bonus, or the active 2x
  perk are all candidates, with no evidence for any of them.
- **+57 is more than the run should have produced** at 3 points a query: ten minutes
  at roughly 38 s per measured search is about fifteen or sixteen queries, worth 45
  to 48. Either some queries pay more than 3, or part of the gain is from elsewhere.

Both are reasons to re-run cleanly rather than to reason backwards from these
totals.

<a id="q7"></a>
### Q7 — Are the Explore offers today's, or an accumulated backlog?

**Status:** 🟡 Partly answered 2026-08-16. **They rotate** — but the daily rate is
still unknown, and the figure this question was raised to support turned out to be a
one-day snapshot.

**Answer to the question as asked:** not an indefinite backlog. Five of the eight
Explore offers present on 08-11 were **gone from the page** five days later — absent,
not marked complete:

```
rotated out   Evergreen_Monday, Evergreen_Tuesday,
              MonthlyFeaturedTopic_20260811_13 and _14,
              locked_level2_Aug26w2_offer2
completed     Evergreen_Sunday, locked_level2_Aug26w2_offer1
reset         EN_Bing_moreactivities_flight_202606   (was complete, now incomplete)
```

So "complete everything outstanding" is bounded rather than a month of work.

**But the value estimate that motivated reordering the roadmap does not hold.** On
08-11 six offers were outstanding, worth 55 points; on 08-16 one is outstanding, worth
5. Two snapshots, an order of magnitude apart. **The daily rate for Explore is not
established**, and it should not be compared against the settled 60 from searches
until it is.

This comparison is also confounded: the account holder completed Explore cards
manually on 08-16, so completions and rotation cannot be separated within it.

**Why this could not be answered from history:** `monitor.py` samples only the
dashboard, and Explore offers live on `/earn`. There is no series to compute a rate
from. Sampling `/earn` too is the fix, and is worth more than another guess.

<a id="q8"></a>
### Q8 — What is the `Edge` 0/30 counter?

**Status:** 🔴 Open. Largest unexplored surface on the account.

Its on-screen sub-label reads "How to activate", so the category is inactive here and
its semantics are unknown. **Do not assume 30 searches at 3 points.** The Bing ring is
a 1/1 gate rather than a search count, so a denominator of 30 cannot be read as a
search quota by analogy.

**How to settle it:** read what the "How to activate" link says, and sample the ring
after activating. Both read-only up to the activation itself.

**Out of scope, and worth saying so:** `Mobile App 0/1`, and the "Download Bing app to
earn 500 points" offer, need the Bing mobile app. This project drives a desktop
browser, so they are unreachable by architecture rather than merely unimplemented.

### Yield per action, and what to cut when trading volume for profile

| Action | Points | Notes |
|---|---|---|
| One search | **3** | lowest yield on the account |
| One Explore offer | **5–15** | |
| One daily-set card | **10–30** | |

Cutting searches costs the least per action removed, which is why the daily count was
narrowed to 8-12 rather than trimming the other tasks. It also happens to be the
noisiest activity in volume terms.

### Known gap: the bot does not know what the account already did today

`daily_search_count()` drew 8-15 (now 8-12) without regard to searches made by hand
earlier the same day. On 2026-08-17 the account holder searched 5 times and the draw was 15,
landing on exactly 20 — the quota, which is the one number the varying count exists to
avoid.

Harmless once, but it defeats the purpose whenever manual use precedes a run. The fix
is to derive the remaining allowance from observation rather than assume a clean start;
the balance delta since the day's first sample is one route, and `monitor.py` already
records what would be needed.

**Closed 2026-08-17 (`8302caa`)**, by a shorter route than either: the dashboard's own
points breakdown reports the day's search points so far, `fetch_search_progress()` reads
it, and the drawn count is trimmed to what is left. The run logs it as "Allowance so far
today: 3/60 — room for 19 more searches". Left here because the section title is what a
reader would search for.

## Unexplained observations

Neither of these blocks anything, and neither has an explanation. Recorded so they are
not rediscovered from scratch, and so a future sighting can be recognised as a repeat.

### CLOSED 2026-08-20 — it was one local Chrome profile, not Rewards behaviour

An incognito window on the same machine agrees with the automation profile. So the
server serves one truth, the automation profile reads it correctly, and the account
holder's ordinary Chrome profile is the only thing disagreeing. Nothing here was ever a
Rewards behaviour, and nothing in this project was affected.

**A stale cache is ruled out, and so is a wrong clock.** The first because a cache
serves older data and never newer, while that profile shows *tomorrow's* unlocked four.
The second by measurement: `new Date()` returns the same correct
`Thu Aug 20 2026 22:45 GMT+0100` in the ordinary profile and in incognito, so nothing is
overriding the page's notion of now.

| Symptom in that profile | Stale cache | Fast clock |
|---|---|---|
| "Today's points 0" while the account had earned 120 | possible | possible |
| Explore tiles showing **tomorrow's** unlocked four | **no** | possible |
| `new Date()` identical to incognito | — | **no** |

What survives is per-profile *server-side* differentiation: a cookie in that profile —
an experiment or flight assignment — putting it on a different build or a different
offer rotation. Incognito carries no such cookie and lands on the default, which is what
the automation profile also sees. That fits both symptoms without needing the client to
be wrong about anything, and it predicts that clearing the site's storage restores
agreement.

The "mornings were fine" pattern dissolves either way: shortly after the 00:00 UTC reset
both today and tomorrow read zero, and `0 == 0` is not agreement.

**Consequence worth keeping.** Availability must be read from the payload's `isLocked`,
never from what a browser renders. The account holder's failed attempt on `creditreport`
is explained: their profile showed it unlocked while the server had it locked until the
next day, so no amount of searching could have credited it.

**And the machine's timezone is not involved:** `Europe/London` (BST, UTC+1), NTP
synchronised, with both browsers on the same machine.

---

**Three wrong answers were given before that one, and each is worth one line.**

| Explanation | Killed by |
|---|---|
| Each browser reports only what it earned | The automation profile read "Today's points 120" — the run's 99 *plus* 21 the account holder earned in the other browser. It counts both. |
| The page's clock runs a day fast | `new Date()` returned the same correct BST timestamp in both profiles. |
| A stale cache | A hard refresh changed nothing, and the profile was showing *newer* data — tomorrow's unlocked tiles — which a cache cannot do. |

The 2026-08-16 sighting that started it — the account holder's browser reading
`Today's points 110 · Bing search 0/60` while the automation profile read
`60 · 60/60`, with identical History rows — is subsumed: two profiles disagreeing about
a daily panel, one of them wrong, with account-wide figures agreeing throughout.

**The one thing to carry forward:** read availability and completion from the payload —
`isLocked`, `isCompleted` — never from what a browser renders. A failed manual attempt on
a `creditreport` tile is explained entirely by that profile showing it as open while the
server had it locked.

### Hypothesis: a referral daily-set card may not be completable at all

2026-08-19: `Child1`, "Turn referrals into rewards", destination
`rewards.bing.com/referandearn`. It has no `?q=` — every other daily-set card points at
a Bing search — so `_open_card` found no anchor, navigated directly, and the card did
not register. The retry navigated again and it still did not register.

The card recurs: the 2026-08-11 capture carries the same title in the 2026-08-12
`Child1` slot, also with `query=None`.

**Hypothesis:** a referral card is completed by somebody accepting a referral, not by
visiting the page, and so is structurally uncompletable by any amount of automation.
If so this is behaviour to recognise, not a bug to fix — and the follow-up is to detect
the card type and skip the two wasted navigations rather than to try harder.

**What would confirm it:** the next daily-set card whose destination is `referandearn`
fails identically. One sighting is not enough to conclude it, and assuming it early
would mean writing off a card that a different approach might complete.

### A per-task figure is only as clean as the window it was measured over

2026-08-22: `searches` reported **+121** against 24 advertised, from eight searches. The
balance moved 108,311 → 108,332, which is +21 — seven searches credited, the eighth
late. The other hundred appeared in "Ready to claim" during the same minutes: a streak
bonus, unrelated to searching, landing inside the task's before/after window and
attributed to it.

The day's total was right. The split was not, and the error is structural: any task's
delta absorbs whatever else credits while it runs.

Inflation is the harmless direction, and it is the one seen here. The dangerous one is
the same mechanism inverted — a task that earns nothing while a bonus lands would be
judged `ok`, which is precisely the silent failure `shortfall.py` exists to catch. Not
worth solving on one sighting, but worth knowing before trusting a per-task number in
isolation. The per-item `isCompleted` checks are unaffected: they never look at points.

**Second sighting, 2026-09-04 — so "not worth solving on one sighting" above no longer
holds.** `daily_set` reported **+100** against 30 advertised. The day's `overall_delta`
of 158 reconciles exactly against the per-task sum (100 + 30 + 28), which places the
extra 70 inside the daily set's own before/after window rather than in a gap between
tasks. What credited it was not identified: 70 matches no advertised value on the page,
and unlike 2026-08-22 there is no observed bonus of the right size to attribute it to.
Recorded as unexplained rather than assigned to a streak.

Two sightings a fortnight apart, on two different tasks, is the useful part: a per-task
delta that overshoots is a normal event on this account, not a curiosity. Read
`overall_delta` against the per-task sum before believing any single task's figure.

**Both explained, 2026-09-12, and both readings above were wrong in detail.** The
08-22 extra was not "seven credited, the eighth late": all eight credited, and the
gate search paid 100 into the pot in place of 3 because the Bing Search Streak reached
day 7 that day. The 09-04 extra 70 is the Daily Set Streak reaching day 7 — the set
pays 100 in place of 30. The streak cards on `/earn` promise exactly this on day 6, and
the monitor's archives show both streaks stepping to 7 on those dates. They recur
weekly — Fridays for the daily set, Saturdays for searches — so a `100 / 30` on a
Friday and a `+100` over on a Saturday are the account working, not a curiosity. The
conclusion stands: read `overall_delta` against the per-task sum. See
[Streak payouts, measured](#streak-payouts-measured--the-weekly-overshoots-and-the-stamp-bonus).

### An Explore run that measured more than it advertised

2026-08-17: four offers stating 15+15+5+5 = 40 measured **+50**. The Daily Set run the
same day matched its stated total exactly, so this is not a systematic offset. A
single Explore offer the next day matched exactly too (10 stated, 10 measured).

This is why the shortfall check tolerates a wide band: advertised values are a guide,
not a contract.

## Tooling

Three things with similar-sounding jobs. The distinction is depth versus frequency.

| | `utils/dashboard_state.py` | `recon.py` | `monitor.py` |
|---|---|---|---|
| Kind | Library | Script | Script |
| Job | HTML → structured state | "What is even in this page?" | "What changed since last time?" |
| Network | **None** | Yes | Yes |
| Output | Objects | Screenshots, DOM, request log, globals (~2 MB) | One JSONL record + gzipped HTML (~50 KB) |
| When | Everywhere | Microsoft redesigns; new investigation | Daily |

`dashboard_state` is a pure function — no browser, no network, no I/O — which is what
lets it be developed and tested offline against archived pages. Keep it that way;
`utils/state_reader.py` exists to hold the part that touches a live page.

`monitor.py` runs on a systemd user timer at 06:00, 12:00, 18:00 and 23:30, with
`RandomizedDelaySec=5400`. The jitter is wide on purpose: four dashboard loads at the
same four times every day is a pattern in itself, even though any individual load is
something a person does. Ninety minutes keeps the morning/midday/evening/night
coverage while scattering when they land. Units are in `contrib/systemd/`; the same
consideration will matter far more if `rewards_bot.py` is ever scheduled, since that
executes tasks rather than loading a page.

`.github/workflows/tests.yml` exists but is **manual-only** (`workflow_dispatch`), by
decision on 2026-08-18: written now, enabled once the suite has been stable for a
while. Uncomment the `push:` trigger to turn it on. What it catches that a local
`pytest` does not is the clean machine — a dependency used but never declared, or a
version assumption the development box happens to satisfy. It never touches an
account: the tests parse a synthetic fixture and make no network requests.

`monitor.py` archives the raw HTML of every sample. When the parser turns out to have
missed a field (see Q5), archived samples can be re-parsed rather than re-collected.
Collect once, analyse many times.

### Safety rules for experiments

- **Read-only work is free.** `recon.py` and `monitor.py` only navigate and scroll;
  running them is equivalent to opening the dashboard by hand.
- **Anything that searches or clicks spends real account risk.** Automating Rewards
  violates Microsoft's terms and enforcement is account-level, so run live experiments
  deliberately, in small samples, one variable at a time.
- **The code lives on Microsoft's infrastructure.** GitHub is Microsoft-owned, so a
  tool for violating Microsoft's Rewards terms is stored on that same company's
  servers. The repository is private and there is no known precedent for GitHub
  content being correlated with Rewards enforcement — different products, different
  organisations — but the structural fact is worth stating rather than discovering.
  Two things follow. If the GitHub account is signed in with the *same* Microsoft
  account used for Rewards, the association is direct rather than inferred. And if
  this matters to you, the answer is to host the repository elsewhere, not to avoid
  CI: CI runs the test suite, which never launches a browser or contacts Bing.
- **Sample before acting, not after.** A sample taken after a run cannot serve as that
  run's baseline. The 2026-08-12 sample is contaminated this way: the searches had
  already happened, so `Bing 1/1` cannot be attributed.

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
| **Keep earning** | **already covered** — same offers, different heading |
| **Quests** | multi-task bundles; progress is a by-product of the daily work |
| **Level up activities** | long-running achievements, not clickable tasks |
| **Streaks / Stamp Bonus** | earned by turning up daily; nothing to click |

**Keep earning needed no work at all.** Its items on 2026-08-18 were Dinner delight,
South African vistas, Complete this puzzle and Book Flights with Bing — precisely the
four `run_explore` had completed the day before. Selecting offers by *having a point
value and being incomplete*, rather than by which heading renders them, covers the
page's sections without knowing they exist. Worth preserving: a section-anchored
selector would have missed these and needed a module per heading.

**Correction, 2026-08-20: "Explore on Bing" was never covered.** The claim above was
made by matching titles across headings and it matched the wrong ones. What
`run_explore` actually does is `WW_Bing_MonthlyFeaturedTopic_*` and
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

2. **They are not links to a search result.** Every offer `run_explore` completes points
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
counts the unlocked tiles rather than all eight. Locked ones render greyscale with a
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

**Sketch, when the window allows it and the mechanism is confirmed:** select on `exploreonbing` and not locked; open the
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

## Unexplained observations

Neither of these blocks anything, and neither has an explanation. Recorded so they are
not rediscovered from scratch, and so a future sighting can be recognised as a repeat.

### RESOLVED — the daily widgets are scoped to the browser, not the account

Confirmed 2026-08-19, 23:30ish, by reading the same widget in both browsers at once:

| Ring | Automation profile | Account holder's Chrome |
|---|---|---|
| Bing | **1/1** | 0/1 |
| Daily Set | **2/3** | 0/3 |
| Bing search (on `/earn`) | — | 0/60 |
| Offers | — | 0 |
| **Balance** | **108,083** | **the same** |

The bot had just earned 81 points in the automation profile. The account holder's
Chrome, same account, same minute, reported a day in which nothing happened — while
agreeing exactly on the balance.

**So "Today's points", the four rings and the `/earn` activity breakdown all answer
"what did *this browser* earn today", not "what did this account earn today".** Balance,
"Ready to claim" and the History rows are account-wide, which is why those never
disagreed.

The cleanest demonstration is already in the samples, in a *single* page load. At
2026-08-16 23:39 the automation profile read the three daily-set cards as `DDD` — all
complete — and the Daily Set ring as `0/3`, in the same document. The balance had risen
107,465 → 107,575 in the preceding hours, the +110 the account holder earned doing
offers by hand in their own browser. Card flags are account state; the ring is session
state; one page carried both, disagreeing.

**Consequence for using this project:** the account holder cannot verify a run from
their own browser, and should not try — that page will only ever show what they did by
hand. Use `--history`, `monitor.py`, or the balance.

**Q2 is narrowed but not closed by this.** It explains the 08-16 pair — the automation
profile correctly read `0/3` for a day whose cards it had not touched. It does not
explain 08-17 02:13, where the same profile read `3/3` just after the reset having
earned nothing (balance flat at 107,575 across the boundary). Something still changes at
the reset that session scoping alone does not account for.

### Superseded framing: a points breakdown that read 0/60 while the same account read 60/60

On 2026-08-16 the account holder saw, in their own browser:

```
Today's points 110 · Bing search 0/60 · Offers 110
```

At the same time, three reads from the automation profile — two pages, half an hour
apart — all showed `Today's points 60 · Bing search 60/60 · Offers 0`. The History
rows (month 3,925, year 40,160, lifetime 107,575) were **identical** in both, which is
what makes it strange: same account, same data source, different "today".

**Explained by the entry above.** Each browser was reporting its own share: the account
holder's had done the offers (110), the automation profile the searches (60). The
"direction mismatch" that made this look strange was an artefact of reading "today" as
account-wide. Recorded as originally written, below, because the reasoning shows what
the wrong assumption cost.

Never reproduced at the time. It did not recur the following day, when searches credited
normally in real time, so it was not a restriction — the 60 points that day had simply already
been spent by an experiment before the manual searches. Candidates never eliminated:
the History rows lag and so cannot date a reading; the modal distinguishes "Bing
search" (combined) from "Desktop Bing search" and the two may render differently by
context; or a stale client-side render.

### Second sighting: the account holder's browser showed a different "today"

2026-08-19, 22:41. A run measured +81 and the balance moved 107999 → 108080. Minutes
later the account holder's own Chrome showed that same **108080 available**, and at the
same time `Today's points 0` with no activity listed.

The arithmetic reconciles exactly — 107999 + 20 + 33 + 28 = 108080 — so no points are
missing; only the "today" panel disagrees between the two browsers, which is the same
shape as the 2026-08-16 sighting above. Note it does not repeat that sighting's
*direction*: there the account holder's browser read high (110) and the automation
profile low (60); here the account holder's reads zero.

Both first candidates are eliminated. A hard refresh changed nothing, so it is not a
stale render; and a one-day lag would have shown 105, since 2026-08-18 earned that — not
zero.

**Leading hypothesis: the daily widgets report what *that browser* earned, not what the
account earned.** A `monitor.py` sample at 23:26 from the automation profile read
`Bing 1/1` and `Daily Set 2/3` — it sees the run perfectly well. The same account in the
account holder's Chrome, minutes earlier, showed nothing.

This is the first hypothesis that explains the 2026-08-16 sighting too, including the
direction that made it look strange. Re-read those figures as per-browser shares:

| | Account holder's browser | Automation profile |
|---|---|---|
| Offers | **110** | 0 |
| Bing search | 0/60 | **60/60** |

Each browser reported exactly its own contribution. The offers were done by hand in one;
the searches by the bot in the other. Nothing was disagreeing — the two were answering
different questions, and "today" was never account-wide. The identical History rows fit:
those *are* account-wide.

**What would confirm it, at no cost:** compare the four rings themselves, not the
"Today's points" panel, in both browsers at the same moment. The automation profile read
`Bing 1/1 · Daily Set 2/3 · Edge 0/30 · Mobile App 0/1` at 23:26. If the account
holder's Chrome reads `0/1` and `0/3` for the first two at that time, the same widget is
demonstrably session-scoped and this closes.

**If it holds, it probably also explains [Q2](#q2)** — ring readings would depend on what
the sampling profile itself had done, not on what the account had done, which is why no
account-level model ("today", "yesterday") fits all seven observations.

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

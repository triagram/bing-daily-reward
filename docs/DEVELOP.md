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
| [Q2](#q2) | The Daily Set ring disagrees with the cards | 🔴 **Open** — blocks the Daily Set rewrite |
| [Q3](#q3) | When does the daily reset happen? | ✅ Resolved 2026-08-14 |
| [Q4](#q4) | Does point crediting lag? | 🟡 Partly answered |
| [Q5](#q5) | Why does `/earn` yield no counters? | ✅ Resolved 2026-08-13 |
| [Q6](#q6) | What is the daily search allowance? | ✅ Resolved 2026-08-16 |
| [Q7](#q7) | Are the Explore offers today's, or a backlog? | 🔴 **Open** — scopes the Explore rewrite |
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

**Status:** 🔴 Open. **Blocks the Daily Set rewrite** — building on a completion test
that is known to be wrong reproduces the failure the rewrite exists to fix.

**What is known:** the disagreement runs in both directions, which rules out a fixed
offset or a simple off-by-one.

| Date | Ring | Cards | Direction |
|---|---|---|---|
| 2026-08-11 | 0 / 3 | one card visibly marked **Completed** | ring undercounts |
| 2026-08-12 | 1 / 3 | all three `isCompleted: false` | ring overcounts |

**Not a parser artifact.** The 08-11 case is legible on the capture screenshot: the
ring reads "Activity: 0/3" while the "Upcoming comedy events" card carries a
Completed badge on the same page.

**Candidate causes, none eliminated:** the ring updates on a lag or a different
schedule; it counts a different notion of "done" than the cards; or it is scoped to a
different day boundary than the offer ids are.

**How to settle it:** complete exactly one daily-set card from a clean post-reset
state, then sample immediately, at +5 minutes and at +1 hour. If the ring trails the
card, it is a lag; if it never agrees, the two count different things. Requires
clicking a task, so it is the first experiment that is not read-only.

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

**Status:** 🟡 Partly answered.

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

**This is exactly what `config.py` already said.** `DAILY_SEARCH_COUNT = 20` and its
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

**Status:** 🔴 Open. **Scopes the Explore rewrite** — "complete everything outstanding"
is a very different action against six offers than against a month of them, on an
account where activity volume is the risk.

Daily-set ids carry a date, which is what makes date-filtering possible. Explore ids
do not, so a single capture cannot say whether what is outstanding belongs to today.

**Evidence pointing at a backlog.** Three of the outstanding offers are keyed by
weekday and all three were outstanding at once:

```
ENstar_Rewards_DailyGlobalOffer_Evergreen_Monday
ENstar_Rewards_DailyGlobalOffer_Evergreen_Tuesday
ENstar_Rewards_DailyGlobalOffer_Evergreen_Sunday
WW_Rewards_locked_level2_Aug26w2_offer1     (month + week)
WW_Bing_MonthlyFeaturedTopic_20260811_14    (dated)
```

Monday, Tuesday and Sunday cannot all be today. Either they accumulate, or "Evergreen"
means they are permanently available and the weekday is decorative.

**How to settle it:** re-run `recon.py` (read-only) and diff `/earn` against the
2026-08-11 capture. If the same ids persist across five days it is a backlog; if the
set rotates, they are current. Costs nothing and uses an archive already on disk.

**Value at stake:** the six outstanding offers are worth 55 points — 5, 10 and 15
each, not the "~10 each" the README claimed until 08-16.

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

`monitor.py` archives the raw HTML of every sample. When the parser turns out to have
missed a field (see Q5), archived samples can be re-parsed rather than re-collected.
Collect once, analyse many times.

### Safety rules for experiments

- **Read-only work is free.** `recon.py` and `monitor.py` only navigate and scroll;
  running them is equivalent to opening the dashboard by hand.
- **Anything that searches or clicks spends real account risk.** Automating Rewards
  violates Microsoft's terms and enforcement is account-level, so run live experiments
  deliberately, in small samples, one variable at a time.
- **Sample before acting, not after.** A sample taken after a run cannot serve as that
  run's baseline. The 2026-08-12 sample is contaminated this way: the searches had
  already happened, so `Bing 1/1` cannot be attributed.

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

Consequently `DAILY_SEARCH_COUNT = 20` in `config.py`, and its comment claiming 3
points each for 60 total, are **inherited guesswork with nothing on the page to
support them** (see Q1).

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

Each entry names the hypothesis, how to falsify it, and where the evidence stands.
**This is the work queue.** Resolve before building on top of the affected area.

### Q1 — Why did four searches earn only 3 points? — **RESOLVED 2026-08-14**

Measured 2026-08-12: four searches submitted, balance `107309 → 107312`.

The run read the balance only at the start and end, so it **cannot attribute the gain
to a particular search**. Two live hypotheses:

- **(a) Quota already filled.** The `Bing` counter read `1/1` afterwards; if it was
  already `1/1` before the run, only the first search could earn and the rest were
  wasted. If true, `DAILY_SEARCH_COUNT = 20` does not merely overshoot — it spends
  behavioural budget for nothing.
- **(b) Navigated queries do not count.** Three of the four searches went straight to
  `bing.com/search?q=…`; only the fourth was typed into the search box. If Bing only
  credits queries issued through the UI, the typed one earned the 3 points.

**Result 2026-08-14, from a clean post-reset state:** six searches, all issued by
navigating to `bing.com/search?q=…`, measured after each.

```
#1..#6   total 107357 → 107357   (+0 each)
Bing gate:  0/1 before  →  0/1 after
```

**Nothing registered.** Not a filled quota — the gate never moved, so these requests
were not counted as searches at all. Against the previous day, where a *single*
mobile browser search flipped the same gate and earned 3:

| | 08-13 | 08-14 |
|---|---|---|
| Searches | 1, mobile browser | 6, URL navigation |
| `Bing` gate | 0/1 → **1/1** | 0/1 → **0/1** |
| Points | **+3** | **+0** |

This supports (b) and retroactively explains Q1: of those four searches only the
last was typed, and 3 points is exactly one search's worth.

**If it holds, the current Task 3 earns nothing.** Twenty navigated searches a day
would accumulate behavioural signal for zero return.

**Confirmed the same hour** by a typed-mode run with fresh terms — fresh because a
repeated query might not be credited, which would have made a same-terms comparison
unreadable:

| Input mode | Queries | Per-search | Total | Gate |
|---|---|---|---|---|
| `url` (12:55) | 6 | +0 each | **0** | 0/1 → 0/1 |
| `type` (13:12) | 3 | **+3 each** | **+9** | 0/1 → 1/1 |

Same account, same machine, seventeen minutes apart. **Navigating to
`bing.com/search?q=…` is not credited. Typing into the search box is, at 3 points a
query, within about fifteen seconds.**

That timing also disposes of hypothesis (c): typed queries settled in seconds, so
navigated ones would have too had they counted at all.

The 9 points split 6 to the balance and 3 to the unclaimed pot, which is further
reason to measure the sum rather than either side.

**Consequence:** `_search_once` now always types. The previous default sent 70% of
queries by navigation, so most of every run was unpaid.

**Still unknown: the daily search allowance.** Three typed queries all paid, so the
ceiling is above three. Finding it means continuing to search until payment stops.

### Q2 — The Daily Set ring disagrees with the Daily Set cards

Observed in both directions, which rules out a simple offset:

| Date | Ring | Cards | Direction |
|---|---|---|---|
| 2026-08-11 | 0 / 3 | one card visibly marked **Completed** | ring undercounts |
| 2026-08-12 | 1 / 3 | all three `isCompleted: false` | ring overcounts |

**Not a parser artifact.** The 08-11 case is confirmed on the screenshot: the ring
reads "Activity: 0/3" while the "Upcoming comedy events" card carries a Completed
badge on the same page.

Possible causes, none eliminated: the ring updates on a lag or a different schedule;
it counts a different notion of "done" than the cards do; or it is scoped to a
different day boundary than the offer ids are.

**Must be settled before rewriting the Daily Set task** — otherwise the new code
inherits a broken completion test, which is the same failure the rewrite is meant to
fix, in a new place.

### Q3 — When does the daily reset happen? — **RESOLVED 2026-08-14**

**Midnight UTC.** Bracketed to a single hour by samples either side:

| Sample (BST) | UTC | `Bing` |
|---|---|---|
| 08-14 00:16 | 08-13 23:16 | 1/1 |
| 08-14 01:16 | 08-14 00:16 | **0/1** |

During British Summer Time that is 01:00 local, so a "morning" sample any time
after 01:00 BST sees a fresh day. The 00:15/01:15/02:15 timer entries have done
their job and can be removed.

### Earnings land in "Ready to claim", not the balance — **CONFIRMED 2026-08-13**

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

### Q4 — Does point crediting lag?

Balance was read ~10 s after the last search. If credit lands later, Q1's measurement
undercounts. Spaced samples on a day with known activity will show it.

**Evidence, 2026-08-12.** Two samples five hours apart, with no automated activity
between them:

| | 15:46 | 20:42 |
|---|---|---|
| balance | 107312 | **107324** (+12) |
| `Bing` | 1/1 | 1/1 |
| `Daily Set` | 1/3 | 1/3 |
| `Edge` | 0/30 | 0/30 |
| `Mobile App` | 0/1 | 0/1 |

Twelve points arrived while **every counter stayed still**. Three readings are
consistent with that, and this sample cannot separate them: the points are delayed
credit for the earlier searches; the account holder used Bing by hand in that window;
or points accrue from something none of these four counters track. Note the second
reading would also mean the +3 attributed to the search run in Q1 is unsafe — manual
activity contaminates that measurement the same way.

Whichever it is, **balance movement and counter movement are not coupled**, so a
counter cannot stand in for the balance as a success signal.

**Clean control obtained 2026-08-13.** From 06:08 to 12:01 with no activity at all,
balance, unclaimed and every counter held still. The balance has now been frozen at
107345 since 08-12 23:31 — over 30 hours — while the unclaimed pot moved. So the
balance does not drift on its own, and it is not where day-to-day earnings arrive.

What remains open is what moves points from the pot into the balance, and whether
that is what the +12 and +21 on 08-12 evening were.

### Q5 — Why does `/earn` yield no counters? — **RESOLVED 2026-08-13**

Not a parser bug: `/earn` genuinely does not carry them. Its flight stream contains
`maxValue` **once**, against five occurrences on the dashboard, and none of those
belongs to a progress ring.

The counters are dashboard-only. Read activity state from `rewards.bing.com/`, and
treat `/earn` as a source of offers alone.

---

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

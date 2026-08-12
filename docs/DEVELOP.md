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

### Category counters

Progress rings, recovered as `{label, value, maxValue}`:

| Label | Observed | Meaning |
|---|---|---|
| `Bing` | 1 / 1 | Unconfirmed — max of 1 suggests a daily gate, not a search count |
| `Daily Set` | 1 / 3 | Contradicts the offers, see open questions |
| `Edge` | 0 / 30 | Unconfirmed |
| `Mobile App` | 0 / 1 | Unconfirmed |

None of these has been confirmed to be the PC search counter. `config.py` still
carries `DAILY_SEARCH_COUNT = 20` with a comment claiming 3 points each for 60 total;
**those numbers are inherited guesswork and have not survived contact with
measurement** (see below).

### Market

This account is `ENGB` (UK). Task sets and point values differ by market, so numbers
found in projects targeting the US market do not transfer.

---

## Open questions

Each entry names the hypothesis, how to falsify it, and where the evidence stands.
**This is the work queue.** Resolve before building on top of the affected area.

### Q1 — Why did four searches earn only 3 points?

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

**Experiment:** from a clean morning state, run
`run_daily_searches(ctx, 6, per_search_balance=True, force_input_mode="url")`.

| Result | Conclusion |
|---|---|
| Each search earns, then earning stops | (a) — and the stopping point is the real quota |
| Nothing earns at all | (b) — rerun with `force_input_mode="type"` to confirm |
| Only the first earns | Neither is settled; quota was already spent before the run |

### Q2 — `Daily Set 1/3` contradicts three incomplete offers

Same sample: the counter said one of three done, while all three of that day's offers
reported `isCompleted: false`.

Possible causes, none eliminated: the counter refers to a different day; `isCompleted`
updates on a lag; the counter counts something other than offers; or `daily_set()`'s
date matching is wrong.

**Must be settled before rewriting the Daily Set task** — otherwise the new code
inherits a broken completion test, which is the same failure the rewrite is meant to
fix, in a new place.

### Q3 — When does the daily reset happen, and in what timezone?

Unknown. `monitor.py` sampling four times a day is intended to bracket it.

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

Next: a sample pair across a window with *no* human use of the account at all.

### Q5 — Why does `/earn` yield no counters?

`parse_dashboard` recovers four counters from the dashboard and **zero** from
`/earn`, though `/earn` has nearly three times the offers. Either that page genuinely
has none, or the parser misses their shape. Worth checking before trusting `/earn`
parsing anywhere.

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

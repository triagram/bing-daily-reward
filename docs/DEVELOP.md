# Development notes

What the Rewards dashboard returns and what was measured on a live UK (`ENGB`) account
in 2026, so none of it has to be re-learned on one; values differ by market. Why it is
built this way: [DESIGN.md](DESIGN.md). Usage: the [README](../README.md).

## Data contract

**State ships inside the HTML, not from an API.** `rewards.bing.com` is a Next.js app
(React Server Components); `self.__next_f.push([1, "<chunk>"])` chunks concatenate into
the flight stream that `utils/dashboard_state.py` parses. Evidence: 2026-08-11, none of
144 requests during a load was a data API. Old dashboard API names (`pointProgress`,
`promotionType`, `dailySetPromotions`, `availablePoints`) match nothing: do not port a
schema from another project.

**A `$L<n>` reference can be content.** A tile may hold only `"$L75"` while row 75 of the
stream carries its title and prompt; `strings_in()` follows such references to JSON rows.
Evidence: 2026-10-11, a tile was searched by its title because its prompt sat in such a
row; re-parsing every archived page (472 pages) filled 29 empty descriptions, leaving 0
of 1761 tile observations without a prompt.

**Offer fields:** `offerId`, `title`, `description`, `points` (`null` on banners),
`isCompleted` (the completion flag), `date` (`MM/DD/YYYY`), `destination`, and
`ctaUrl`/`ctaText` on banners.

**`offerId` is the key.** `Gamification_DailySet_ENGB_20260811_Child2` reads family,
kind, market, day, slot (`OFFER_ID_PATTERN`). Take the date from the id, never from
`date`: the two have been seen to disagree.

**The page carries several days at once.** Evidence: a dashboard load held offers for
yesterday, today and tomorrow; `/earn` for four dates. So `DashboardState.daily_set()`
takes a day, defaulting to today.

**The four rings are daily gates, not counts** (`{label, value, maxValue}`): `Bing`
"Search: 1/1" (any qualifying search today); `Daily Set` "Activity: n/3" (unreliable,
Q2); `Edge` "How to activate" 0/30 (Q8); `Mobile App` "Check-in: 0/1" (needs the phone
app, out of reach). Streaks live apart, under "Your progress". `/earn` has no rings (Q5).

**The stream has no search count; the points breakdown does.**
`fetch_search_progress()` reads the rendered "Bing search earned / cap" row at
`?modal=pointbreakdown` (the combined row, not "Desktop Bing search"), and the run trims
its drawn count to what is left. Evidence: 2026-08-17, searches made by hand before a run
plus the run's draw landed exactly on the quota.

**Earnings land in "Ready to claim" as often as in the balance.** Pot entries
(`pointClaim.entries`) carry a `category`: `ds` is the search streak's daily credit;
`mtb`, `gub`, `bseb` are monthly bonuses (codes inferred). Entries are dated and expire,
so the claim step matters; a typed search's own points go to the balance. Evidence:
2026-08-13, one search raised the pot by 3 and not the balance (the `ds` credit, read
2026-09-12); 2026-09-01, bonuses dated 2026-09 arrived expiring 2026-10-04. Hence
balance plus unclaimed ([DESIGN.md](DESIGN.md#principles)).

**Nothing drifts on its own.** Evidence: 2026-08-13, six idle hours, balance, pot and
rings unchanged.

**`/earn` headings are presentation.** Keep earning selects offers with `points` that
are not complete, under any heading.

**App-only offers carry points and cannot be done.** `WW_Moreactivities_RewardsApp_offer_*`,
"... (Rewards App only)", with ordinary search destinations; `is_app_only()` excludes them
by id and by title. Evidence: 2026-09-02, five sorted to the front of a run capped at six
and pushed a real offer out.

### Explore on Bing tiles

Id `ENUS_<topic>_exploreonbing_activation_Evergreen…`, `instrument.name`
`"ExploreOnBing_Card"`, keys `children, hash, href, isCompleted, isDisabled, isLocked,
successToast`, title in a nested image's `alt`. No `points` field, so
`outstanding_offers()` never selects them.

- **Four unlock a day at 10 points; the header (`0/40`) counts only those.** Tomorrow's
  four render locked, first in the section. Read `isLocked`/`isDisabled`, never render
  order; a locked tile cannot pay. Evidence: 2026-08-19 to 08-21, each day's locked four
  opened the next day; a manual attempt on a locked tile (08-20) changed nothing.
- **All tiles share one `href`** (`bing.com/?…&rwAutoFlyout=exb`), so URL matching clicks
  the first. Locate by title, exactly one match; a locked tile is not a link. Evidence:
  2026-08-23, three "failures" were the first tile clicked again.
- **Click to activate, then type the search in what opened, without navigating.** The
  toast reads "Activated! · Search on Bing to complete this activity". Evidence:
  2026-08-24, once the right tile was clicked two completed on their prompts, and
  `flight` and `shopping` once given a route and a product.
- **The default query is the tile's prompt.** `VERIFIED_QUERIES` holds measured
  exceptions only; `SHELVED_TOPICS` holds `lyrics` (2026-09-16: four failures, three query
  shapes, including the `<artist> <song> lyrics` form forum posts recommend). Evidence:
  2026-08-25, 4 of 4 on prompts alone, placeholders included.
- **Some attempts fail for no reason in the query; both cures are observed.** A plain
  retry (`personalloan`, 2026-09-28, failed then passed minutes later on the same words);
  only an entity (`recipe`: plain retry failed 09-04, a named dish passed 09-18). The same
  `hotel` query passed 08-30 and failed 09-06. So a first failure on a query that has
  completed before calls for a retry, not an override.
- **Activation alone credited a tile once.** Evidence: 2026-09-06, the click opened no
  search box, nothing was typed, and the tile credited about 2.5 minutes later. Searching
  stays: other tiles need it.
- **Topics recur** at 7- and 14-day gaps (26 pairs), so a re-test arrives on its own.
- Tile searches count against the allowance; the search task holds back
  `EXPLORE_ON_BING_TILES_PER_DAY`.

## Measured rules

**20 typed searches at 3 points, 60 a day.** Evidence: 2026-08-16, balance read after each
query from a clean day: #1-#20 paid 3, #21-#23 nothing. The run reads the live cap from
the breakdown; a "search 2x more" perk (seen 2026-08-11) changes it while it lasts.

**Typed searches are credited; navigated ones never are.** Evidence: 2026-08-14, fresh
terms 17 minutes apart: six loaded as `bing.com/search?q=…` earned 0 and left the `Bing`
gate at 0/1 (so not a spent quota); three typed paid 3 each within about 15 s. Code:
`_search_once()` always types; `force_input_mode` keeps the test repeatable.

**Direct navigation to an offer's destination never credits; the card click does.**
Evidence: all twelve direct navigations in the logs, 2026-08-19 to 09-22, failed; on 09-22
two "follow us" cards completed on the click with nothing followed. Code: a `page.goto`
fallback remains in `task_daily_set.py` and `task_keep_earning.py`; when next touched,
make it a bounded wait, one reload, then "card not found".

**A hand on the browser costs a card.** Evidence: 2026-09-22, a tab closed by hand between
a reload and a lookup made a card "not found"; re-run alone, it completed.

**The Daily Set ring is neither reliably today's nor yesterday's.** Evidence: to
2026-08-17 four readings fit "yesterday" (08-16 23:39 read 0/3 after three cards were
done); on 08-18 it went to 3/3 within two hours of same-day completions, and on 08-19 read
0/3 instead of 08-18's three. Code: work is gated on each card's `isCompleted`.

**Streak day 7 pays 100 instead of the gate activity's value**: the daily set 100 into the
balance in place of 30, the gate search 100 into the pot in place of 3. Each completed
streak adds a stamp; twelve stamps pay 1,000 and the card resets. Evidence: seven
sightings in August and September matched to the "Day N of 7" cards; two stamp payouts
six weeks apart, as two stamps a week predicts. So `100 / 30` on the daily set, or
searches far over, is expected on such a day.

**A task's delta absorbs whatever credits during its window**, so check the overall
delta against the per-task sum. Advertised values are a guide (2026-08-17, four offers
measured a quarter over; quizzes add per-question credits): hence the wide band in
`shortfall.py`.

**Searches credit in seconds; card clicks sometimes take minutes.** Evidence: a card
incomplete 20 s after its click was complete ten minutes later (08-21); keep-earning cards
credited over five minutes after the click, after the run closed (2026-10-01, by the
balance rising by exactly the card's value, the account holder having touched nothing;
10-04, read as `isCompleted: true`). Code: `reconcile_late_completions()` re-checks once
after 25 s, then one retry, then a warning ([DESIGN.md](DESIGN.md#principles)).

**The two `WW_Bing_MonthlyFeaturedTopic_*` cards rotate between 07:49 and 08:19 UTC**,
yesterday's pair staying until then. Evidence: September 2026 runs either side; a run
before and a run after on 09-25/26 lost a pair outright. Code: the timer fires after
it. A card absent at run time is invisible: no flag.

**A browser not signed in lands on `/about`, not the sign-in page.** Evidence:
2026-10-26, a fresh profile read as signed in; an empty throwaway profile gets
`rewards.bing.com/about` within 0.3 s and stays; `login.live.com` is reached only from its
*Sign in* button. Code: `sign_in_required()` knows `/about`.

**A fresh UK profile earns nothing from search until Bing's cookie banner is answered.**
Card clicks still credit. Evidence: 2026-10-27, the first run on a fresh profile (the run
had moved to a Raspberry Pi): card tasks completed, typed searches earned nothing, no
Explore tile flipped. The sign-in and Rewards cookies (`_U`, `WLS`, `_RwBf`, `_Rwho`) were
present; the banner (`#bnp_container`) was the difference. After one *Accept* it stayed
away, and the account holder reported a re-run credited. `MSCC` did not appear, so it
is not the consent cookie. On throwaway profiles the answers are links, shown 0.24-0.46 s
after load.
Code (`utils/bing_consent.py`): `--login` has the person answer it and checks it stays
gone on reload; the search task checks first and, if it is there, searches nothing
and records an error.

**A phone-browser search satisfies the `Bing` gate, not `Mobile App`.** Evidence:
2026-08-13, one moved `Bing` to 1/1 and left `Mobile App` at 0/1.

**Availability comes from the payload, never from what a browser renders.** Evidence:
2026-08-20, an ordinary profile showed tomorrow's tiles as open while incognito and the
automation profile agreed; 2026-10-16, its Bing region was another market's. A recurrence
shows as the Daily Set turning over at an odd local hour, or `ENGB` missing from the page.

## Questions

**Settled**

- **Q1** Four searches earned 3: three were navigated (2026-08-14).
- **Q3** When does the day reset? Midnight UTC: `Bing` read 1/1 at 23:16 UTC and 0/1 at
  00:16 UTC (2026-08-14).
- **Q5** Why does `/earn` yield no counters? It has none: `maxValue` once against five on
  the dashboard, none a ring (2026-08-13). Read rings from `rewards.bing.com/`.
- **Q6** Allowance: 20 at 3 (2026-08-16).

**Partly answered**

- **Q4** Does crediting lag? Seconds for searches, over five minutes for some card
  clicks; what decides it is unknown.
- **Q7** Are the offers then called "Explore" (today's keep-earning offers) a backlog?
  No: they rotate out unfinished (2026-08-16, five of eight seen on 08-11 gone, not
  completed). Their daily value is not established.

**Open**

- **Q8** `Edge` 0/30, "How to activate". Inactive here; do not read 30 as a search quota
  by analogy. To settle: read what the link says, then sample the ring after activating.
  Deferred ([DESIGN.md](DESIGN.md#deferred)).
- **Q2** What the Daily Set ring counts. Neither model fits; the code does not depend on it.
- **Referral card** (hypothesis). `Child1` "Turn referrals into rewards" points at
  `rewards.bing.com/referandearn`, no `?q=`, and twice did not complete (2026-08-19);
  likely completed only by someone accepting a referral. Confirm on the next one before
  adding a skip.

## Disproved

- "20 at 3 is guesswork": a broken method (Q1) made the right figure look wrong.
- Explore, "a search alone completes a tile": the click activates, the search completes.
- Explore, "placeholder wording fails": 2026-08-24, a placeholder prompt paid.
- Explore, "verticals need an entity": 2026-08-25, three verticals completed without one.
- Explore, "Bing must resolve the placeholder": 2026-09-06, one placeholder passed on one
  topic and failed on another.
- Explore, "crediting lag": 2026-08-23, still incomplete 3.5 h later; the wrong tile had
  been clicked.
- Explore, "a tile loses its description once activated", "activation outlives
  rotation", "`lyrics` is malformed": parser gaps (2026-10-11).
- "Per-task overshoots are late credits or stray bonuses": day-7 streak payouts.
- "Each profile shows only its own earnings", "the page clock is a day fast", "a stale
  cache": disproved 2026-08-20; it was the profile's market.
- "A fresh profile is slow to redirect to sign-in": it lands on `/about`.
- "Searches earn nothing because bing.com is not signed in": it was the banner; the
  differing interface language was not the cause either.

## Experiment safety rules

- Read-only work is free: `--dry-run`, `explore_on_bing.py --dry-run`, `recon.py`, the
  offline tests. Observe logged-out behaviour on an empty throwaway profile.
- Anything that searches or clicks spends account risk: small samples, one variable at a
  time, never a second full run on a day that ran clean.
- Sample before acting; a baseline read afterwards cannot attribute anything.
- Compare methods on fresh query terms, so a failing method is not confused with a spent
  query.
- Never add a guessed entry to `VERIFIED_QUERIES`; it destroys the observation.
- Before attributing a late credit, ask the account holder whether they touched the
  account; a hand completion leaves the same evidence.
- Run long measurements detached: a 20-plus-search run takes about fifteen minutes.
- GitHub is Microsoft-owned: do not sign in to it with the Rewards account.

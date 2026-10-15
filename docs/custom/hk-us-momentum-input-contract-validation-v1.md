# HK/US Momentum Input Contract Validation v1

Audit date: 2026-10-14 (Asia/Shanghai).
Source revision: `3c6d4eff54e3012e9e5a39cf2eaff15392dd2056`, branch `main`.

**READ-ONLY INPUT AUDIT COMPLETE — MOMENTUM INPUT NOT READY.**

## 1. Scope and evidence boundaries

This audit checks inputs before any Momentum Engine. It adds this report only
to the project. No engine, score, ladder, provider integration, subscription,
QuoteService/archive semantics, production policy or runtime data is changed.
No commit/push, application restart, fixture injection or backfill was performed.

Evidence classes are kept separate:

- **Current local data:** read-only inspection of project `data/` Parquet and
  explicitly selected SQLite databases opened with `mode=ro`.
- **Current code/SDK contract:** application source, installed yfinance 1.7.0
  and Longbridge 5.2.0 source/interfaces. No credentials/config secrets read.
- **Historical recorded probes:** existing project reports, explicitly dated;
  not fresh provider requests or evidence of a persisted dataset today.
- **Offline calendar replay:** exact frozen artifacts queried in memory at
  explicit timestamps. These are calendar queries, not synthetic market bars
  or observations of actual trading/availability.

No `fetch_daily`, `Ticker.history`, `security_list`, quote API, Dashboard endpoint
or authentication probe was executed. Live provider symbol coverage, entitlement
and current response completeness therefore remain UNKNOWN. Existing test and
verification directories were excluded from production coverage counts.

This is documentation-only work, outside an implementation L1/L2/L3 change.
The upgrade's existing main push pending state is unrelated and untouched.

## 2. Current local historical coverage

All existing files in these application datasets were inspected for HK/US
symbol membership, dates and available volume fields:

| Dataset | Parquet partitions | HK rows | US rows | Read errors |
| --- | ---: | ---: | ---: | ---: |
| `data/kline_daily` | 246 | 0 | 0 | 0 |
| `data/kline_daily_enriched` | 246 | 0 | 0 | 0 |
| `data/kline_etf_daily` | 0 | 0 | 0 | 0 |
| `data/kline_etf_enriched` | 0 | 0 | 0 | 0 |
| `data/kline_ext` | 0 | 0 | 0 | 0 |

The ordinary Daily schema has symbol/date/OHLC/volume/amount; enriched also has
raw_close. Those column names do not establish HK/US data, units, finality,
split-only adjustment or vintage.

Required market output, scoped specifically to **current inspected persisted
Daily data**, not the complete provider offering:

| market | symbol_count | date_range | volume_available_ratio | adjustment_status | pit_status |
| --- | ---: | --- | --- | --- | --- |
| HK | 0 | null | null | BLOCKED | BLOCKED |
| US | 0 | null | null | BLOCKED | BLOCKED |

`volume_available_ratio` means finite, nonnegative non-null volume observations
divided by inspected market Daily rows. With zero rows its denominator is zero:
the ratio is **null, not 0%**. This numerical presence statistic would not prove
the units/comparability of any nonempty dataset.

`data/user_data/anomaly_historical_context.sqlite3` contains 0 baselines and 0
event contexts. It is not an alternative persisted OHLCV source.
`data/research` has no existing files. No other user directories or provider
account data were searched to manufacture coverage.

### Snapshot Archive is a separate dataset

| market | archived observations | distinct symbols | non-null volume | volume_unit |
| --- | ---: | ---: | ---: | --- |
| HK | 3245 | 1 | 0 | unknown |
| US | 911 | 1 | 0 | unknown |

Archive rows contain price, quote/receive timestamps, provider, session and
quality metadata. They do not supply completed Daily OHLCV. A last archived
price, a Dashboard `close` alias or many intraday rows cannot be counted as a
completed-session Daily bar. No archive writer or quality gate was changed.

## 3. Historical Daily providers

### HK

- `get_historical_provider` supports CN/US and rejects HK. No HK implementation
  is registered in this research factory.
- Longbridge's production plugin declares **realtime only**, not daily.
  Quantity diagnostic helpers expose a possible SDK candlestick call, but a
  diagnostic helper is not an approved Daily OHLCV provider.
- `quantity.py` explicitly marks daily quantity contracts as blocked for every
  market, with unknown units. Integer-valued volume is not shares/lot evidence.
- Current HK Daily symbol/date coverage and completed bars: none in the
  inspected application datasets. Provider-wide coverage/permissions: UNKNOWN,
  not proven unsupported by the vendor.

**HK Daily data availability: UNAVAILABLE. HK production input contract: BLOCKED.**

### US: existing yfinance research path

Source: `YFinanceDailyProvider`, not a production synchronization registration.

| Requirement | Actual contract | Finding |
| --- | --- | --- |
| Symbol | `.US` stripped; remaining ticker must match `[A-Z][A-Z0-9-]{0,19}` | Explicit subset; no dot-class alias inference |
| Metadata | Exact symbol, instrumentType=EQUITY, exchangeTimezoneName=America/New_York | Identity/type checks exist; not historical common-share master |
| Dates | Exchange-local midnight Date index; request end made inclusive | Returned dates validated/sorted; no complete historical coverage guarantee |
| OHLC | Base `open/high/low/close`; independent `adjusted_*` when requested | Structure present, semantic equivalence unproven |
| Base price method | `yfinance_auto_adjust_false` | Source base prices; not a proof of historical as-traded or split-only basis |
| Adjusted method | `yfinance_auto_adjust` | SDK adjusted prices, not established split-only |
| Volume | Source Volume retained; ambiguous SDK zero converted to null | `volume_unit=unknown` |
| Currency | Read from validated history metadata | Not inferred from suffix; not historical currency evidence |
| Actions | Dividends and Stock Splits retained when returned | No complete corporate-action/vintage proof |
| Time | Local `fetched_at`, `observed_at=null` | Fetch time is not historical publication time |
| Vintage | No source_vintage / raw response evidence identifier in schema | Strict PIT BLOCKED |

Actual history request flags are interval=1d, auto_adjust=False/True by mode,
back_adjust=False, actions=True, repair=False, keepna=True, rounding=False,
prepost=False and explicit date bounds. Source `Adj Close` is retained separately
as `source_adjusted_close` when returned; it is not renamed into base close.

The normalizer flags current/future local-date rows `daily_bar_not_final`, even
after the regular close on that date. This is a conservative existing rule,
not a source finality certificate for older rows. It does not read an exact
immutable calendar ID/version/hash for each source result.

Crucially, `status=completed` describes the adapter's successful normalization.
`volume_unit_unknown` and `as_traded_raw_not_established` can remain diagnostics
without making that status partial. Consumers must validate the required
semantics themselves; `completed` is not Momentum READY.

### Prior successful source observations (not rerun)

Existing [historical Daily report](historical-market-data-v1.md) records real
read-only probes dated 2026-10-12:

| Symbol | Recorded requested/returned window | Rows | Meaning |
| --- | --- | ---: | --- |
| AAPL.US | 2024-05-06 .. 2024-05-17 | 10 | Source OHLC/independent adjusted rows received; units unknown |
| NVDA.US | 2024-06-03 .. 2024-06-14 | 10 | Same structural success; not split-only validation |

[Historical anomaly context report](historical-anomaly-context-v1.md) separately
records AAPL.US and NVDA.US baseline inputs spanning 2026-06-15 .. 2026-10-09,
82 eligible bars each. Those prior probes demonstrate limited past access,
not a current stored Universe or fresh entitlement result. Their volume
availability ratios were not established and cannot be reconstructed here.

**US provider structure: PARTIAL. Current persisted Daily data: UNAVAILABLE.
Full US Momentum input contract: BLOCKED.**

## 4. Price basis validation: split_adjusted_price_only

The target must mean consistent split/reverse-split adjusted OHLC on an explicit
comparison basis, excluding cash-dividend total-return adjustment. All relevant
bars must have matching source/method/vintage and no future adjustment evidence.

| Input | Verified fact | Missing proof | Status against target |
| --- | --- | --- | --- |
| HK Daily | No integrated Daily provider/data | Prices, actions, adjustment and metadata | BLOCKED |
| US base close | SDK called with auto_adjust=False | Vendor base-price split policy, vintage and consistency across split dates | BLOCKED |
| US adjusted OHLC | Installed SDK auto_adjust uses Adj Close/Close to transform OHLC | That this ratio excludes cash distributions and represents the target split-only basis | BLOCKED |
| US action fields | Dividend/split fields can be passed through | Completeness, historical availability, mapping to every price/volume series | PARTIAL |
| Provider metadata | Current identity/type/timezone/currency checks | Per-bar adjustment identity, frozen vintage and availability evidence | PARTIAL |

No claim is made that all base rows are wrong or that every adjusted row differs
from split-only. The required equivalence has **not been demonstrated**.
Retaining `Stock Splits`, disabling SDK repair, or finding a numerical jump is
not sufficient proof. No inverse-adjustment, qfq conversion or inferred split
factor was calculated in this audit.

The current [yfinance history API page](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.history.html)
was reachable; exact processing was inspected in the installed 1.7.0 source.
The Yahoo help page linked by the prior audit returned HTTP 429 this round;
it was not retried and is not counted as newly verified vendor semantics.

**PRICE BASIS: BLOCKED for HK and US.**

## 5. Volume validation for VR20

Target definition only (no values calculated):

`VR20(D) = V_D / mean(V_(D-20), ..., V_(D-1))`.

This requires the current completed-session total and 20 prior compatible
session totals; the denominator excludes D. Missing days are not silently
skipped, padded, forward-filled or treated as suspension/zero volume.

| Check | HK | US |
| --- | --- | --- |
| Historical Daily volume rows locally available | None | None |
| Historical unit evidence | No integrated contract | Explicitly unknown |
| Existing normalized realtime volume | Null/unsupported | Null/unsupported |
| Archive volume usable as Daily | No | No |
| Same volume scope across 21 sessions | Unverified | Unverified |
| Split-related volume basis | Unverified | Unverified |
| Half-day comparability | Calendar can identify half-days; volume rule unresolved | Same |
| ETF exclusion | No frozen classified HK Universe | Raw US provider Universe includes ETFs/other securities |
| VR20 readiness | BLOCKED | BLOCKED |

Absolute units can mathematically cancel in a ratio only if the same stable
scale and scope across the whole window are proven. `unknown` alone cannot be
used as that proof. Do not divide by lot_size, apply CN's 100-share convention,
or use price adjustment factors to repair volume without an explicit contract.

Volume counts do not have a currency. Currency is required for monetary
`turnover`/amount and comparable price context; USD/HKD metadata cannot prove
volume units. `turnover` means monetary traded value, not turnover_rate, and
neither amount nor price is used to fabricate share volume.

The yfinance EQUITY metadata guard rejects ETF responses to that adapter if
correctly labeled, but US security_list/Dashboard candidate membership itself
is not ETF-filtered. EQUITY is also not a PIT common-stock/ADR classification.
No numerical ETF count is claimed without an actual typed constituent dataset.

## 6. Universe validation

The IDs below are **audit candidate labels**, not installed Universe definitions.
No actual immutable Universe version is assigned by the current paths.

| Candidate id | Actual version | Source | Observed/declared coverage | Blockers / possible use |
| --- | --- | --- | --- | --- |
| `us-longbridge-security-list` | null | get_realtime_universe(US) -> QuoteContext.security_list | Provider-available US securities; current count UNKNOWN; exchange_complete=False | Includes ETFs/other types; mutable current list, no frozen hash/as-of membership. Possible candidate source after explicit filtering/freezing |
| `hk-longbridge-security-list` | null | No HK branch in existing wrapper | Current wrapper raises unsupported universe market; SDK/account support NOT TESTED | Needs source contract first; does not prove the vendor lacks HK data |
| `us-dashboard-provider-universe` | null | Optional in-memory provider sweep | Up to 100000 input bound, batches of500, provider coverage; no current live request performed | Partial/stale batch handling and latest-date cohort, no durable point-in-time membership/version |
| `us-dashboard-candidates` | null | Six core sample symbols + movers + cached rows/focus | Fallback candidate cap40 | Dynamic outcome-selected sample, instrument types/history absent; not full US market |
| `hk-dashboard-candidates` | null | HK movers + cached rows/focus | Cap20 | Mutable, selection-biased candidate set; not full HK market or common-stock catalog |
| `user-watchlist` | Process-local revision only; no frozen historical version | data/user_data/watchlist.parquet | File absent; current local members0 | Could support an explicitly chosen small user Universe after freezing/type validation; not selected automatically |

Current local instrument catalog inspection: 1 ordinary instrument Parquet
partition with no HK/US members; ETF instrument directory has no partitions.
There is therefore no inspected local HK/US classified security master to fill
these gaps. Watchlist notes, holdings and credentials were not inspected.

No candidate is currently an implementation-ready Momentum Universe. Minimum
contract: explicit market and permitted instrument types; sorted unique members;
universe_id/version/hash; effective date; source/evidence reference;
membership available_at; eligibility version; exclusions and coverage counts.
Partial retrieval must not silently become a different fully covered Universe.
Historical analysis also needs listing/delisting/rename identity evidence to
avoid treating today's survivors as past membership.

## 7. Exact immutable calendar validation

Pure `TradingCalendarContract.from_canonical` and an isolated in-memory
`TradingCalendarBindings` were used. No production registry/policy installation
or SQLite materialization occurred.

| Field | HK | US |
| --- | --- | --- |
| calendar_id | hk-cash-equity-official | us-cash-equity-official |
| version | 2026-v1 | 2026-v1 |
| content_hash | `945fbd11e669fc27d1c76712969871a7151d854da1547f6c05fd71a4fa733b91` | `cfb976ea41ff8037ab0dd5225f061dcb960976cd404bcd10eae2bb74a1084d76` |
| Recomputed hash matches | Yes | Yes |
| Coverage | 2026-01-01 .. 2026-12-31 | 2026-01-01 .. 2026-12-31 |
| Timezone | Asia/Hong_Kong | America/New_York |
| Regular windows | 09:30-12:00;13:00-16:00 | 09:30-16:00 |
| Half-days | Feb16;Dec24;Dec31 | Nov27;Dec24 |
| Early regular close | 12:00 | 13:00 |
| Additional boundary | 10-minute modeled closing-auction window | Pre/post-market modeled separately; overnight unverified boundary retained |

Offline deterministic query results (local offsets are explicit):

| Query | Result |
| --- | --- |
| HK 2026-10-14 16:00+08:00 | READY calendar resolution; state regular (inclusive endpoint) |
| HK 2026-10-14 16:05+08:00 | post_market; detail closing_auction_window |
| HK 2026-10-14 16:10+08:00 | closed |
| HK 2026-12-24 12:05+08:00 | half_day=true; early_close12:00; closing_auction_window |
| HK previous day from 2026-10-19 | 2026-10-16 (weekend/holiday resolved from artifact) |
| US 2026-10-14 16:00-04:00 | regular (inclusive endpoint) |
| US 2026-10-14 16:01-04:00 | post_market |
| US 2026-11-27 13:01-05:00 | half_day=true; early_close13:00; post_market |
| US 2026-11-26 16:01-05:00 | holiday |
| US previous day from 2026-11-27 | 2026-11-25 |
| HK 2027-01-04 | BLOCKED/calendar_date_outside_coverage |

**Calendar artifact identity and schedule replay: READY, within coverage.**

**Completed-session Daily input selection: PARTIAL.** Exact session boundaries
can be derived from the frozen rules, but there is no Momentum binding joining
a final Daily bar and its provider publication evidence to those boundaries.
The current resolver returns session classification, not a final-price certificate.
At exactly the regular end, state remains regular; HK's early_close/16:00 is
not the end of its modeled auction window. US post-market is not extended-hours
Daily inclusion permission. Calendar `closed`/holiday also does not mean that
the queried date had a completed session.

Do not use raw clock comparisons, current provider market status or the last
bar to bypass this distinction. The full lookback, not merely D, must be inside
verified calendar coverage. Early-2026 requests needing 2025 sessions can thus
remain blocked. US's frozen overnight uncertainty from 2026-12-06 is preserved;
do not interpret unknown overnight states as confirmed closure. No calendar
facts, algorithms or versions were modified/reverified from exchange notices
in this audit; this validates the existing artifact's exact identity/behavior.

## 8. Point-in-time validation

Question: after session D, were these exact input values and constituents
already known at the requested cutoff?

| Requirement | Existing evidence | Conclusion |
| --- | --- | --- |
| Trading date bounded by D | Historical adapter validates date labels/ranges | PARTIAL: date filtering only |
| Session ended / final Daily bar | Exact calendar exists, source lacks final publication certificate | PARTIAL for schedule; UNAVAILABLE final bar evidence |
| Actual provider publication/availability time | Historical schema has fetched_at; observed_at always null | BLOCKED |
| Source vintage/revisions | No immutable vintage/raw-response reference in Daily schema | BLOCKED |
| Actions known at cutoff | Optional dividend/split numbers only | BLOCKED |
| Constituents known at cutoff | Mutable provider/Dashboard/watchlist state | BLOCKED |
| Immutable evidence snapshot generated/stored before cutoff | Factor Snapshot has such gates, but no producer/store for these Momentum inputs | UNAVAILABLE; unrelated Foundation cannot certify missing inputs |

`fetched_at` proves when a result was fetched locally, not when it was known
after historical D. Retrieving old dates now cannot backdate availability.
An SDK version identifies software, not a dataset vintage. A price/volume row
can be structurally valid and still fail PIT. Existing historical baseline
explicitly reports pit_capable=False/source_vintage_unverified.

**Strict historical PIT: BLOCKED for HK and US.** Retrospective observations
may eventually be labeled PARTIAL under an explicit retrospective contract;
that does not authorize using them as historical event-time READY evidence.

## 9. Satisfied / missing / blocker matrix

| Domain | Satisfied | Missing | Gate |
| --- | --- | --- | --- |
| HK Daily | Gap located precisely in existing integration | Integrated/accessible completed OHLCV dataset | UNAVAILABLE data; BLOCKED contract |
| US Daily | Explicit source adapter, parameters, structure and prior finite probes | Current persisted bars, full coverage, finality and provenance | PARTIAL capability; UNAVAILABLE local data |
| Split-only price | Base/adjusted fields kept separate | Proven split-only mapping and action/vintage evidence | BLOCKED |
| VR20 | Required21-session input definition explicit | Comparable non-null volumes, unit/scope and split/half-day treatment | BLOCKED |
| Universe | Candidate sources and their boundaries identified | Explicit frozen classified membership/version/hash/availability | BLOCKED |
| Calendar | HK/US exact ID/version/hash and replay | Final bar/publication join; whole-lookback coverage for chosen window | READY artifact; PARTIAL input selection |
| PIT | Date/receipt concepts separated | Historical availability, vintage and historical membership | BLOCKED |

Fixed reason labels for follow-up: hk_daily_provider_not_integrated,
local_hk_us_daily_unavailable, split_only_price_basis_unverified,
volume_basis_unverified, completed_bar_evidence_missing,
momentum_universe_not_frozen, input_source_vintage_unverified,
historical_input_availability_unverified. These labels are report vocabulary,
not new production enums or code.

## 10. Minimum next step

Do **not** start Momentum Engine/Score/Ladder implementation from these inputs.

Recommended next bounded task: **existing-source Daily price/quantity contract
probe and evidence specification**, before production integration:

1. Explicitly choose a small HK/US common-stock validation set with identity/type
   evidence; this is a test scope, not an automatically installed Universe.
2. Validate US's existing yfinance path and an existing-source HK candlestick
   candidate with finite read-only historical requests, if separately in scope.
   Inspect actual volume presence, exact units/scope, metadata and finality.
   Longbridge candlestick capability remains a candidate, not unlocked by a
   successful request. No new provider, token request or paid purchase here.
3. Select action windows from actual split/dividend evidence, then verify
   price-only split adjustment and volume treatment against those records.
   No invented event dates, guessed factors or live quote backfills.
4. Define a frozen, classified Universe and the bar availability/vintage
   evidence needed at a specified knowledge cutoff. Current receipt freezing
   can support future evidence, but cannot repair unknown historical vintages.
5. Re-evaluate each gate before implementing any calculation. Failure to obtain
   the necessary source semantics should stop as DATA CONTRACT REQUIRED;
   unknown entitlement is not PERMISSION_BLOCKED.

HK benchmark/Market Context and Factor producer remain independent limitations;
they must not be changed or silently made dependencies to conceal these gaps.
No source selection, production policy or scoring-profile decision is installed
by this document.

## 11. Audit references and checks

Application source at the stated revision:

- [Historical Daily schema/provider](../../backend/app/data_providers/historical.py):
  schema23, zero-volume ambiguity183, diagnostics251-261, observed_at270,
  YFinanceDailyProvider308, factory347.
- [Longbridge production plugin](../../backend/app/plugins/longbridge/plugin.yaml)
  and [quantity contract](../../backend/app/plugins/longbridge/quantity.py):
  realtime-only registration versus blocked diagnostic daily quantities.
- [Longbridge Universe/normalizer](../../backend/app/plugins/longbridge/provider.py):
  get_realtime_universe325, _normalize332.
- [US Dashboard](../../backend/app/services/us_dashboard_service.py):
  provider sweep104 and fallback candidates246.
- [HK Dashboard](../../backend/app/services/hk_dashboard_service.py): candidates152.
- [Watchlist](../../backend/app/services/watchlist.py): current mutable storage,
  process-local revision and list_symbols171.
- [Calendar artifacts/resolver](../../backend/app/services/evidence_execution.py):
  CalendarContent16, from_canonical101, previous-day134, session151.
- [Frozen session evaluation](../../backend/app/market_session.py):166.
- [Canonical calendars](../../backend/app/market_calendar.py) and
  [immutable calendar contract](immutable-trading-calendar-contract-v1.md).

Installed yfinance 1.7.0 utils.auto_adjust and PriceHistory processing were read
locally; no dependency was installed or modified. Public documentation browsing
was limited to the history API and the prior Yahoo help link (429, no retry).

Validation was Parquet read-only inventory, selected SQLite read-only counts,
SDK/source inspection and offline exact-calendar queries, not an Engine test.
No backend/frontend tests, build or Ruff run is warranted for this new report.
Final document whitespace/sensitive/content review is separate from runtime
validation. No Git stage, commit, push or remote verification was requested.

# Task 401: USD flight count fixture

Task `401`, original ID `20260506024659173066`, asks:

> Set the displayed currency to USD. How many one-way economy flights from San Francisco (SFO) to Seattle (SEA) on 2026-06-15 are priced at $125 or less?

The expected answer is **4 flights**. The price limit is inclusive and there is
no nonstop constraint. Task `073` (`20260502193227163598`) retains its original
wording and accepts 4 in USD or 0 with a consistent default-KRW explanation;
task 401 explicitly requires setting the displayed currency to USD.

## Reproduction identity

Verified on Linux amd64 GCP on 2026-10-21 with `BENCHMARK_PASSCODE=1`:

- Published image index / GCP cached RepoDigest:
  `webarenapro/flight-search@sha256:4c13740e368305234f56cb1856d7121ed32384e7747468286276614f7a99aea1`
- Published linux/amd64 manifest:
  `sha256:e7b078f3f1f1447556aae8445e130e2b03cb23a28fc5b0e72e60d1fcc921694e`
- GCP Docker image inspect `.Id`:
  `sha256:4c13740e368305234f56cb1856d7121ed32384e7747468286276614f7a99aea1`
- Canonical source baseline: `489c8f168a1749947c15aa72d66b7a7efd97d9bf`.
  All 21 backend Python files and `airline_routes.json` match the published
  container byte for byte. Route data SHA-256:
  `7e8d97548f626230927e3e38b8ba9712710612ef90292e9a0696698d20b3bac3`.
- Benchmark clock: **2026-04-01**. The travel date is a fixed fixture; do not
  substitute today's date or a live flight search.

This correction changes evaluation data, not the application or image. No new
image publication is needed to reproduce the corrected answer.

## Exact query and result

Authenticate with `POST /api/auth/verify`, JSON
`{"passkey":"flyingagents"}`, retaining the returned session cookie. Then send
`POST /api/search` with `Content-Type: application/json`:

```json
{
  "trip_type": "one_way",
  "legs": [{"origin": "SFO", "destination": "SEA", "date": "2026-06-15"}],
  "passengers": {"adults": 1, "children": 0, "infants": 0},
  "cabin_class": "economy",
  "filters": {"max_price": 125},
  "sort_by": "cheapest"
}
```

All other filters, including `max_stops`, are unset. Currency is a UI setting;
the API prices and `max_price` are USD.

| Offer ID | USD price | Stops |
| --- | ---: | ---: |
| SFOSEA2026-06-15569DL | 118 | 0 |
| SFOSEA2026-06-15610DL | 120 | 0 |
| SFOSEA2026-06-15915SFO-YVR-SEA3 | 124 | 1 |
| SFOSEA2026-06-15548UA | 125 | 0 |

The unfiltered query (`"filters": {}`) returns nine fares:
118, 120, 124, 125, 131, 136, 138, 139, 141 USD. Setting `max_price=124`
returns 118/120/124. Setting `max_price=125,max_stops=0` returns 118/120/125.
Both alternative constraints return three, but neither expresses task 401.

## Browser verification

Chromium 156.0.8078.4 exercised the published container through the ordinary
passkey login and search form, without response stubs or injected auth cookies:

1. Select USD, One way, Economy, SFO, SEA, and departure 2026-06-15.
2. Search; the initial API request uses `sort_by=best` and all six filter fields
   set to `null` (max stops, price, duration, airlines, departure min/max).
3. Select Cheapest, enter Max price 125, and leave Stops at Any.
4. Confirm **4 results** and the same four offer IDs as the filtered API query.
5. Confirm the 124 maximum and nonstop-only controls each yield three results,
   then restore 125 and Any to return to four.

The UI filters locally and groups offers into Best and Other sections. Thus
screen order can differ from API price order; the offer sets and counts agree.

## Regression check

From `websites/flight-search`:

```sh
python -m pip install -r backend/requirements.txt
python -m unittest discover -s tests -v
```

`tests/test_task_fixtures.py` executes the real API against the checked-in route
data and generator using the fixed benchmark clock. It checks the nine fares,
inclusive equality, the connecting offer, task identity and raw/dev prompt
copies, both active rubric copies, and the reference answer. The
Flight Search task-fixture workflow runs this check for website or task-config
changes. Evaluation continues to use the existing contextual LLM judge, so a
natural-language answer such as "four flights" is not forced into an exact
string match.

Task 401's rubric and reference answer in `splits/dev.json` are corrected to
four. Task IDs, split membership, raw prompts, the separate task 073 DAG, and
legacy archives remain unchanged.

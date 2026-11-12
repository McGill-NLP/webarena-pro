---
title: Flight Search
emoji: ✈️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# Flight Search

## Running with Docker Compose

```bash
docker compose up --build
```

The app will be available at http://localhost:7860.

To run in the background:

```bash
docker compose up --build -d
```

## Running manually (without Docker)

**Backend:**

```bash
cd backend
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 7860
```

**Frontend** (in a separate terminal):

```bash
cd frontend
npm install
npm run dev
```

## Frontend regression tests

```bash
cd frontend
npm ci
npx playwright install chromium
npm test
```

The browser tests start their own Vite server and stub API responses, so a
running backend is not required. They cover airport validation, autocomplete
selection, delayed lookups, and multi-city searches.

## Backend task fixture tests

From this directory, install `backend/requirements.txt`, then run
`python -m unittest discover -s tests -v`. These tests use the fixed benchmark
clock and real route data to keep task answers aligned with the generated
flights. See [task 401's reproduction record](docs/task-401-fixture.md) for the
image identity, exact query, and UI/API checks behind its USD count.
Task 073 accepts 4 flights in USD (118/120/124/125 USD, including the connecting
itinerary and the 125 USD boundary), or 0 when the agent uses the default KRW
currency and explains that consistently. Its rubric does not require applying
the price filter, so manually counting the USD fares is valid.

## Deterministic task 344 evidence

`GET /api/eval/state` is a read-only endpoint protected by `X-Eval-Token` matching
`WP_EVAL_TOKEN`. Core provisions this token when launching the site. When running
the site directly, set the same token for the site and evaluator; the endpoint
returns 503 if it is unconfigured and 403 for a missing/wrong token.

The endpoint returns versioned search-result evidence, booking-creation IDs, and
current bookings without passenger or payment details. Search evidence contains
only offers actually returned after filtering and result limits. Real request
timestamps distinguish executions even when the benchmark clock is frozen.
The journal keeps up to 4096 events and exposes truncation so the evaluator can
report missing evidence instead of silently treating it as a failed action.
`POST /api/reset` clears both bookings and evidence and starts a new generation.

Task 344 uses Core's shared `backend_state` evaluator with the `eval_state` API
template and generic `json_predicate` checks. The task JSON declares evidence
guards, research filters, record joins, and the latest-route/booking rules; there
is no Flight Search grading helper. The deterministic path requires
rebuilding/deploying this image. If the
endpoint is unavailable or its evidence is inconclusive, the evaluator uses the
task's original Tier 2 rubric. Definitive deterministic failures remain final.
The evaluator never issues searches to manufacture its own research evidence.
Use `python -m unittest discover -s tests -v` for the native API tests; the Core
test `test_flight_checkpoint_integration.py` also exercises the actual task DAG
when this site's Python requirements are installed.

## Access

**Passkey:** `flyingagents`

## Accepted Booking Payment Cards

Flight Search validates cardholder name, card number, expiry, and CVV. Card numbers may be entered with spaces or dashes, and expiry may be entered as `MM/YY`, `MMYY`, or `MM/YYYY`.

| Cardholder | Brand | Card Number | Expiry | CVV | Source |
|------------|-------|-------------|--------|-----|--------|
| Jane Smith | Visa | `4111111111111111` | `12/2027` | `123` | Password Manager |
| Jane Smith | Mastercard | `5500005555555559` | `08/2026` | `456` | Password Manager |
| Jane Smith | Amex | `371449635398431` | `03/2028` | `7890` | Password Manager |
| John Smith | Visa | `4111111111111111` | `12/2027` | `123` | Legacy demo |
| John Smith | Visa | `4532015112830366` | `05/2026` | `789` | Password Manager |
| John Smith | Mastercard | `5500000000000004` | `06/2028` | `456` | Legacy demo |
| Jane Doe | Amex | `340000000000009` | `03/2027` | `7890` | Legacy demo |
| Bob Wilson | Visa | `4012888888881881` | `09/2026` | `321` | Legacy demo |

## License

WebArena-Pro's original application code and contributions in this directory are
licensed under the [MIT License](LICENSE).

Dependencies, datasets, media, and other third-party components retain their
respective licenses and attribution requirements. They are not relicensed by
this application's MIT license.

The bundled [airline_routes.json](airline_routes.json) comes from
[Jonty/airline-route-data](https://github.com/Jonty/airline-route-data).
The [referenced upstream revision](https://github.com/Jonty/airline-route-data/tree/ff16a0749fd642e469a5f561a984e77ae3740b7f)
does not include a license file or a license grant in its README. This
application's MIT license does not cover that dataset.

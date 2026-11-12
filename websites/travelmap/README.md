---
title: TravelMap
sdk: docker
app_port: 4230
---

# TravelMap

TravelMap is a lightweight Airbnb-style demo app with browsing, booking, saved homes, trips, messaging, and simple host tools.

## Accounts

All demo accounts use the password `demo123`.

- `avery@example.com` - guest
- `maya@example.com` - host
- `jordan@example.com` - host
- `priya@example.com` - host
- `leo@example.com` - guest

## Docker

```bash
docker compose up --build
```

The app runs on port `4230`.
Open `http://localhost:4230` in your browser.

## Reset Data

Reset the app back to its seeded demo state:

```bash
python3 scripts/reset_data.py
```

## Inside Airbnb catalog

TravelMap contains exactly 10,300 listings: all 300 original synthetic homes
plus 10,000 real-world listing records sampled from the current datasets on
[Inside Airbnb's download page](https://insideairbnb.com/get-the-data/).

The imported catalog is stratified by the city/region labels used by Inside
Airbnb. Every non-empty stratum receives one listing, and all remaining slots
are distributed in proportion to source row counts with Hamilton's
largest-remainder method. The allocation counts come from each summary
`listings.csv`; rows are then sampled from the matching detailed
`listings.csv.gz` without replacement using
deterministic reservoir sampling and random seed `20260718`.

Each imported listing receives an available May 1, 2026 calendar anchor in
the seed. TravelMap creates the rest of a requested date range lazily during
booking, so benchmark dates remain selectable without materializing a full
calendar for all 10,000 imported stays.

Every imported listing also receives three deterministic randomly placed
confirmed reservations: one in early summer, one in late summer, and one in
the off-season. Summer stays run five to ten nights and the off-season stay
runs two to seven nights. These reservations use seed `20260718`, appear as
unavailable calendar dates, and belong to a dedicated system guest so the
normal demo guests' Trips pages stay unchanged. Date ranges used by benchmark
tasks are explicitly kept free.

Imported star ratings retain a signal from the source rating but use a
deterministic seeded transform and per-listing Gaussian jitter to avoid the
source data's unrealistic concentration near five stars. The resulting catalog
includes meaningful lower-, middle-, and higher-rated inventory while remaining
identical across resets.

Rebuild the sample and database with:

```bash
python3 scripts/build_inside_airbnb_seed.py
python3 scripts/reset_data.py
```

Exact source URLs, snapshot dates, source counts, and allocated sample counts
are recorded in `data/inside_airbnb_manifest.json`. Inside Airbnb data is used
under the [Creative Commons Attribution 4.0 International
license](https://creativecommons.org/licenses/by/4.0/).

## Evaluator image compatibility

Before releasing an image, run the [authenticated evaluator image gate](../../docs/source/evaluator-images.md) against an isolated container. A successful source build does not verify the published Docker Hub image.

## License

WebArena-Pro's original application code and contributions in this directory are
licensed under the [MIT License](LICENSE).

Dependencies, datasets, media, and other third-party components retain their
respective licenses and attribution requirements. They are not relicensed by
this application's MIT license.

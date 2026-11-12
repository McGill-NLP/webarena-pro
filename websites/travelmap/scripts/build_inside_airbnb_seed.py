#!/usr/bin/env python3
"""Build TravelMap's deterministic, city-stratified Inside Airbnb sample.

The script reads the latest snapshot links from Inside Airbnb's download page,
counts the summary listing files, allocates the requested sample using a
minimum-one Hamilton (largest remainder) allocation, and reservoir-samples the
detailed listing file for each city/region with a fixed random seed.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
from html import unescape
from html.parser import HTMLParser
import io
import json
import math
from pathlib import Path
import random
import re
import sys
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed


DOWNLOAD_PAGE = "https://insideairbnb.com/get-the-data/"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
DEFAULT_TARGET_TOTAL = 10_300
DEFAULT_BASE_LISTINGS = 300
DEFAULT_SEED = 20260718
DEFAULT_WORKERS = 8
USER_AGENT = "TravelMap data builder (WebArena Pro; source attribution in README)"
FALLBACK_IMAGE = (
    "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85"
    "?auto=format&fit=crop&w=1200&q=80"
)
FALLBACK_AVATAR = (
    "https://images.unsplash.com/photo-1534528741775-53994a69daeb"
    "?auto=format&fit=crop&w=300&q=80"
)


@dataclass(frozen=True)
class Source:
    city: str
    country: str
    heading: str
    detailed_url: str

    @property
    def summary_url(self) -> str:
        return self.detailed_url.replace("/data/listings.csv.gz", "/visualisations/listings.csv")

    @property
    def snapshot_date(self) -> str:
        parts = urlsplit(self.detailed_url).path.strip("/").split("/")
        return parts[-3]

    @property
    def source_key(self) -> str:
        parts = urlsplit(self.detailed_url).path.strip("/").split("/")
        return "/".join(parts[:-3])


class DownloadPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_heading = ""
        self.current_city = ""
        self._in_h3 = False
        self._in_td = False
        self._heading_parts: list[str] = []
        self._td_parts: list[str] = []
        self.sources: list[Source] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "h3":
            self._in_h3 = True
            self._heading_parts = []
        elif tag == "td":
            self._in_td = True
            self._td_parts = []
        elif tag == "a":
            href = attributes.get("href") or ""
            if href.endswith("/data/listings.csv.gz") and self.current_heading:
                city = self.current_city or self.current_heading.split(",", 1)[0]
                country = self.current_heading.rsplit(",", 1)[-1].strip()
                if "," not in self.current_heading:
                    country = self.current_heading
                self.sources.append(
                    Source(
                        city=unescape(city.strip()),
                        country=unescape(country),
                        heading=unescape(self.current_heading),
                        detailed_url=unescape(href),
                    )
                )

    def handle_endtag(self, tag: str) -> None:
        if tag == "h3" and self._in_h3:
            self.current_heading = "".join(self._heading_parts).strip()
            self.current_city = ""
            self._in_h3 = False
        elif tag == "td" and self._in_td:
            cell = "".join(self._td_parts).strip()
            if not self.current_city and cell:
                self.current_city = cell
            self._in_td = False

    def handle_data(self, data: str) -> None:
        if self._in_h3:
            self._heading_parts.append(data)
        if self._in_td:
            self._td_parts.append(data)


def _ascii_safe_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc.encode("idna").decode("ascii"),
            quote(parsed.path, safe="/%"),
            quote(parsed.query, safe="=&%"),
            parsed.fragment,
        )
    )


def _open_url(url: str, retries: int = 4):
    safe_url = _ascii_safe_url(url)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = Request(safe_url, headers={"User-Agent": USER_AGENT})
            return urlopen(request, timeout=240)
        except (HTTPError, URLError, TimeoutError) as error:
            last_error = error
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    assert last_error is not None
    raise last_error


def discover_sources(page_url: str) -> list[Source]:
    with _open_url(page_url) as response:
        page = response.read().decode("utf-8")
    parser = DownloadPageParser()
    parser.feed(page)
    deduped = {source.detailed_url: source for source in parser.sources}
    sources = sorted(deduped.values(), key=lambda item: (item.city.casefold(), item.detailed_url))
    if not sources:
        raise RuntimeError(f"No detailed listing downloads found at {page_url}")
    return sources


def _csv_reader(response, gzipped: bool = False) -> tuple[io.TextIOWrapper, csv.DictReader]:
    binary_stream = gzip.GzipFile(fileobj=response) if gzipped else response
    text_stream = io.TextIOWrapper(binary_stream, encoding="utf-8-sig", newline="")
    return text_stream, csv.DictReader(text_stream)


def count_source(source: Source) -> tuple[Source, int]:
    with _open_url(source.summary_url) as response:
        text_stream, reader = _csv_reader(response)
        try:
            count = sum(1 for _ in reader)
        finally:
            text_stream.close()
    return source, count


def count_sources(sources: list[Source], workers: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(count_source, source): source for source in sources}
        for completed, future in enumerate(as_completed(futures), start=1):
            source, count = future.result()
            counts[source.detailed_url] = count
            print(f"[{completed:03d}/{len(sources):03d}] counted {source.city}: {count:,}", file=sys.stderr)
    return counts


def proportional_allocation(
    sources: list[Source], counts: dict[str, int], sample_size: int
) -> dict[str, int]:
    nonempty = [source for source in sources if counts[source.detailed_url] > 0]
    if sample_size < len(nonempty):
        raise ValueError("Sample size is too small to include at least one row from every non-empty stratum")
    population = sum(counts[source.detailed_url] for source in nonempty)
    if sample_size > population:
        raise ValueError(f"Requested {sample_size:,} rows from a population of only {population:,}")

    allocation = {source.detailed_url: 1 for source in nonempty}
    remaining = sample_size - len(nonempty)
    quotas: list[tuple[float, str]] = []
    assigned = 0
    for source in nonempty:
        count = counts[source.detailed_url]
        quota = remaining * count / population
        floor_value = min(count - 1, math.floor(quota))
        allocation[source.detailed_url] += floor_value
        assigned += floor_value
        quotas.append((quota - math.floor(quota), source.detailed_url))

    leftovers = remaining - assigned
    for _, url in sorted(quotas, key=lambda item: (-item[0], item[1])):
        if leftovers == 0:
            break
        if allocation[url] < counts[url]:
            allocation[url] += 1
            leftovers -= 1
    if leftovers:
        for source in nonempty:
            url = source.detailed_url
            available = counts[url] - allocation[url]
            take = min(available, leftovers)
            allocation[url] += take
            leftovers -= take
            if not leftovers:
                break
    if sum(allocation.values()) != sample_size:
        raise AssertionError("Proportional allocation did not produce the requested sample size")
    return allocation


def _stable_seed(seed: int, source: Source) -> int:
    digest = hashlib.sha256(f"{seed}:{source.source_key}:{source.snapshot_date}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def sample_source(source: Source, sample_count: int, seed: int) -> tuple[Source, int, list[dict[str, str]]]:
    rng = random.Random(_stable_seed(seed, source))
    reservoir: list[dict[str, str]] = []
    seen = 0
    with _open_url(source.detailed_url) as response:
        text_stream, reader = _csv_reader(response, gzipped=True)
        try:
            for seen, row in enumerate(reader, start=1):
                if len(reservoir) < sample_count:
                    reservoir.append(row)
                    continue
                replacement = rng.randrange(seen)
                if replacement < sample_count:
                    reservoir[replacement] = row
        finally:
            text_stream.close()
    if len(reservoir) != sample_count:
        raise ValueError(f"{source.city} yielded {seen:,} rows; expected to sample {sample_count:,}")
    reservoir.sort(key=lambda row: _source_id(row))
    return source, seen, reservoir


def sample_sources(
    sources: list[Source], allocation: dict[str, int], seed: int, workers: int
) -> tuple[dict[str, int], dict[str, list[dict[str, str]]]]:
    detailed_counts: dict[str, int] = {}
    samples: dict[str, list[dict[str, str]]] = {}
    selected_sources = [source for source in sources if allocation.get(source.detailed_url, 0)]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(sample_source, source, allocation[source.detailed_url], seed): source
            for source in selected_sources
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            source, count, rows = future.result()
            detailed_counts[source.detailed_url] = count
            samples[source.detailed_url] = rows
            print(
                f"[{completed:03d}/{len(selected_sources):03d}] sampled {source.city}: "
                f"{len(rows):,}/{count:,}",
                file=sys.stderr,
            )
    return detailed_counts, samples


def _clean_text(value: Any, fallback: str = "", limit: int | None = None) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text or fallback
    return text[:limit].rstrip() if limit else text


def _source_id(row: dict[str, str]) -> int:
    try:
        return int(row.get("id") or 0)
    except ValueError:
        return 0


def _integer(value: Any, default: int, minimum: int = 0, maximum: int = 10_000) -> int:
    try:
        number = int(float(str(value).strip()))
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _number(value: Any, default: float, minimum: float = 0, maximum: float = 10_000) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        number = default
    if not math.isfinite(number):
        number = default
    return max(minimum, min(number, maximum))


def _price(value: Any) -> float:
    cleaned = re.sub(r"[^0-9.\-]", "", str(value or ""))
    return round(_number(cleaned, 100.0, minimum=1.0, maximum=1_000_000.0), 2)


def _rating(value: Any) -> float:
    rating = _number(value, 4.5, minimum=0, maximum=100)
    if rating > 5:
        rating /= 20
    return round(max(1.0, min(rating, 5.0)), 2)


def _amenities(value: Any) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        parsed = []
    if not isinstance(parsed, list):
        parsed = []
    cleaned: list[str] = []
    for item in parsed:
        amenity = _clean_text(item, limit=80)
        if amenity and amenity not in cleaned:
            cleaned.append(amenity)
    return cleaned[:24] or ["Wifi", "Essentials"]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "listing"


def transform_sample(
    sources: list[Source], samples: dict[str, list[dict[str, str]]], listing_id_start: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    host_rows: dict[str, dict[str, str]] = {}
    ordered_rows: list[tuple[Source, dict[str, str]]] = []
    for source in sources:
        for row in samples.get(source.detailed_url, []):
            source_host_id = row.get("host_id") or row.get("host_profile_id") or f"unknown-{_source_id(row)}"
            host_rows.setdefault(str(source_host_id), row)
            ordered_rows.append((source, row))

    host_id_by_source: dict[str, int] = {}
    hosts: list[dict[str, Any]] = []
    for host_id, source_host_id in enumerate(sorted(host_rows, key=lambda value: (_integer(value, 0), value)), start=6):
        row = host_rows[source_host_id]
        host_id_by_source[source_host_id] = host_id
        hosts.append(
            {
                "id": host_id,
                "name": _clean_text(row.get("host_name"), "Inside Airbnb host", 120),
                "email": f"inside-airbnb-host-{source_host_id}@example.invalid",
                "password": "demo123",
                "is_host": True,
                "hometown": _clean_text(row.get("host_location"), "", 120),
                "bio": _clean_text(row.get("host_about"), "Host profile imported from Inside Airbnb."),
                "avatar_url": _clean_text(row.get("host_picture_url"), FALLBACK_AVATAR, 500),
            }
        )

    listings: list[dict[str, Any]] = []
    used_slugs: set[str] = set()
    for listing_id, (source, row) in enumerate(ordered_rows, start=listing_id_start):
        source_listing_id = _source_id(row)
        source_host_id = str(row.get("host_id") or row.get("host_profile_id") or f"unknown-{source_listing_id}")
        neighborhood = _clean_text(
            row.get("neighbourhood_cleansed") or row.get("neighbourhood"), source.city, 120
        )
        room_type = _clean_text(row.get("room_type"), "Home", 80)
        title = _clean_text(row.get("name"), f"{room_type} in {neighborhood}", 200)
        slug_base = _slugify(f"inside-airbnb-{source.source_key}-{source_listing_id}")[:145]
        slug = slug_base
        suffix = 2
        while slug in used_slugs:
            slug = f"{slug_base[:140]}-{suffix}"
            suffix += 1
        used_slugs.add(slug)

        price = _price(row.get("price") or row.get("price_quote_price_per_night"))
        bedrooms = _integer(row.get("bedrooms"), 1, minimum=1, maximum=20)
        beds = _integer(row.get("beds"), bedrooms, minimum=1, maximum=30)
        baths = _number(row.get("bathrooms"), 1.0, minimum=0.5, maximum=20)
        max_guests = _integer(row.get("accommodates"), max(2, beds), minimum=1, maximum=32)
        description = _clean_text(
            row.get("description"),
            f"A {room_type.casefold()} in {neighborhood}, {source.city}, from the Inside Airbnb dataset.",
        )
        picture_url = _clean_text(row.get("picture_url"), FALLBACK_IMAGE, 500)
        listings.append(
            {
                "id": listing_id,
                "slug": slug,
                "host_id": host_id_by_source[source_host_id],
                "title": title,
                "city": source.city,
                "country": source.country,
                "neighborhood": neighborhood,
                "price_per_night": price,
                "cleaning_fee": round(price * 0.15, 2),
                "service_fee": round(price * 0.12, 2),
                "bedrooms": bedrooms,
                "beds": beds,
                "baths": round(baths, 1),
                "max_guests": max_guests,
                "rating": _rating(row.get("review_scores_rating")),
                "review_count": _integer(row.get("number_of_reviews"), 0, maximum=100_000),
                "description": description,
                "amenities": _amenities(row.get("amenities")),
                "house_rules": ["Respect the home and neighborhood", "Follow the host's check-in instructions"],
                "blocked_ranges": [],
                "images": [
                    {
                        "url": picture_url,
                        "alt_text": f"{title} in {source.city}",
                        "display_order": 0,
                    }
                ],
            }
        )
    return hosts, listings


def build_manifest(
    sources: list[Source],
    summary_counts: dict[str, int],
    detailed_counts: dict[str, int],
    allocation: dict[str, int],
    target_total: int,
    base_listing_count: int,
    seed: int,
) -> dict[str, Any]:
    strata = []
    for source in sources:
        url = source.detailed_url
        strata.append(
            {
                "city": source.city,
                "country": source.country,
                "source_heading": source.heading,
                "snapshot_date": source.snapshot_date,
                "population_count": summary_counts[url],
                "detailed_count": detailed_counts.get(url, summary_counts[url]),
                "sample_count": allocation.get(url, 0),
                "source_url": url,
            }
        )
    return {
        "source": "Inside Airbnb",
        "download_page": DOWNLOAD_PAGE,
        "license": "Creative Commons Attribution 4.0 International",
        "license_url": LICENSE_URL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": (
            "City/region strata discovered from the current download page; at least one row per non-empty "
            "stratum, then proportional Hamilton largest-remainder allocation; deterministic reservoir "
            "sampling without replacement within each stratum."
        ),
        "random_seed": seed,
        "allocation_population_field": "population_count (rows in each summary listings.csv)",
        "target_total_listings": target_total,
        "base_demo_listings": base_listing_count,
        "sample_size": target_total - base_listing_count,
        "source_population": sum(item["population_count"] for item in strata),
        "stratum_count": len(strata),
        "strata": strata,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False, separators=(",", ":"))
        output.write("\n")
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-url", default=DOWNLOAD_PAGE)
    parser.add_argument("--target-total", type=int, default=DEFAULT_TARGET_TOTAL)
    parser.add_argument("--base-listings", type=int, default=DEFAULT_BASE_LISTINGS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--sample-output", type=Path, default=project_root / "data" / "inside_airbnb_sample.json")
    parser.add_argument("--manifest-output", type=Path, default=project_root / "data" / "inside_airbnb_manifest.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sample_size = args.target_total - args.base_listings
    if sample_size <= 0:
        raise ValueError("Target total must be greater than the number of base listings")

    sources = discover_sources(args.page_url)
    print(f"Discovered {len(sources)} current listing strata.", file=sys.stderr)
    summary_counts = count_sources(sources, args.workers)
    allocation = proportional_allocation(sources, summary_counts, sample_size)
    detailed_counts, samples = sample_sources(sources, allocation, args.seed, args.workers)
    hosts, listings = transform_sample(sources, samples, args.base_listings + 1)
    if len(listings) != sample_size:
        raise AssertionError(f"Built {len(listings):,} listings instead of {sample_size:,}")

    sample_payload = {
        "source": "Inside Airbnb",
        "license_url": LICENSE_URL,
        "random_seed": args.seed,
        "hosts": hosts,
        "listings": listings,
    }
    manifest = build_manifest(
        sources,
        summary_counts,
        detailed_counts,
        allocation,
        args.target_total,
        args.base_listings,
        args.seed,
    )
    write_json(args.sample_output, sample_payload)
    write_json(args.manifest_output, manifest)
    print(
        f"Wrote {len(listings):,} listings and {len(hosts):,} hosts; "
        f"TravelMap total will be {args.target_total:,} listings.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()

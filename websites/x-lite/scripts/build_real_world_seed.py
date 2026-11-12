#!/usr/bin/env python3
"""Build a compact X-lite seed with bounded real-world Twitter/X data."""

from __future__ import annotations

import argparse
import base64
import csv
import gzip
import hashlib
import heapq
import html
import io
import json
import math
import os
import random
import re
import sys
import time
import tempfile
import urllib.parse
import urllib.request
import urllib.error
import zipfile
from bisect import bisect_right
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from datetime import UTC, datetime, timedelta


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DEFAULT_INPUT = os.path.join(DATA_DIR, "seed.json")
DEFAULT_OUTPUT = os.path.join(DATA_DIR, "seed.generated.json")
DEFAULT_BLUESKY_ROOT_URI_FILE = os.path.join(DATA_DIR, "bluesky_srs_2000_roots.txt")
DEFAULT_BLUESKY_TREE_CACHE_FILE = os.path.join(DATA_DIR, "bluesky_srs_2000_trees.jsonl.gz")
DEFAULT_BLUESKY_EXPLORE_ROOT_CACHE_FILE = os.path.join(DATA_DIR, "bluesky_explore_roots.jsonl.gz")
HF_ROWS_URL = "https://datasets-server.huggingface.co/rows"
BLUESKY_DATASET = "Roronotalt/bluesky-ten-million"
BLUESKY_DATASET_URL = f"https://huggingface.co/datasets/{BLUESKY_DATASET}"
BLUESKY_PARQUET_URL = f"{BLUESKY_DATASET_URL}/resolve/main/data/train-0000.parquet"
CARDIFF_TOPIC_MULTI_DATASET = "cardiffnlp/tweet_topic_multi"
CARDIFF_TOPIC_MULTI_CONFIG = "tweet_topic_multi"
CARDIFF_TOPIC_MULTI_URL = "https://huggingface.co/datasets/cardiffnlp/tweet_topic_multi"
ZENODO_RECORD_API = "https://zenodo.org/api/records/17677813"
ZENODO_DATASET_URL = "https://zenodo.org/records/17677813"
ZENODO_FILE_URL = "https://zenodo.org/api/records/17677813/files/DataSetX.csv/content"
MIDE22_REPO_URL = "https://github.com/metunlp/MiDe22"
MIDE22_EN_TWEETS_URL = "https://raw.githubusercontent.com/metunlp/MiDe22/main/dataset/EN/mide22_en_misinfo_tweets.tsv"
MIDE22_TR_TWEETS_URL = "https://raw.githubusercontent.com/metunlp/MiDe22/main/dataset/TR/mide22_tr_misinfo_tweets.tsv"
RETWEET_KAGGLE_DATASET = "soroosharasteh/retweet"
RETWEET_KAGGLE_URL = f"https://www.kaggle.com/api/v1/datasets/download/{RETWEET_KAGGLE_DATASET}"
RETWEET_REPO_URL = "https://github.com/tayebiarasteh/retweet"
TOXIC_CONVERSATIONS_DATAVERSE_URL = "https://doi.org/10.7910/DVN/TRWPVB"
PASSWORD = "password123"

USERNAME_ADJECTIVES = [
    "amber", "atomic", "bright", "calm", "candid", "cedar", "clear", "clever",
    "cobalt", "cosmic", "daily", "delta", "digital", "direct", "ember", "fast",
    "fresh", "golden", "green", "hidden", "honest", "lunar", "magnetic", "major",
    "modern", "neon", "nimble", "north", "open", "prime", "public", "quiet",
    "rapid", "rebel", "remote", "signal", "silver", "solar", "steady", "urban",
    "vivid", "wide",
]

USERNAME_NOUNS = [
    "archive", "atlas", "beam", "brief", "bulletin", "canvas", "channel",
    "circuit", "dispatch", "field", "file", "filter", "forum", "grid", "index",
    "ledger", "lens", "loop", "marker", "matrix", "metro", "minute", "node",
    "notebook", "orbit", "packet", "page", "panel", "pixel", "portal", "post",
    "pulse", "radar", "relay", "report", "signal", "source", "spark", "stack",
    "stream", "studio", "thread", "ticker", "trace", "vector", "wire",
]

QUOTE_TEXTS = [
    "Adding this to the thread because the original post is still driving discussion.",
    "This is the part of the conversation I want to keep in view.",
    "Useful context from the wider discussion around this post.",
    "Quoting this because the engagement pattern is worth watching.",
    "A good snapshot of how this topic is moving across X.",
    "This post keeps coming up in related replies and reposts.",
]

REPLY_TEXTS = [
    "This is getting a lot of attention in the thread.",
    "The numbers make more sense with the original context.",
    "I saw this circulating in a few related conversations.",
    "The replies are adding useful nuance here.",
    "Worth tracking as more people respond.",
    "This connects with another post from the same topic.",
]

INTERACTION_FIELD_ALIASES = {
    "favorite_count": ("favorite_count", "like_count", "likes", "likes_count", "favorites"),
    "retweet_count": ("retweet_count", "repost_count", "reposts", "retweets"),
    "reply_count": ("reply_count", "replies", "comments", "comment_count"),
    "quote_count": ("quote_count", "quotes", "quote_tweets"),
}

TASK_RELEVANT_TWEET_RE = re.compile(
    r"("
    r"annotation|saturday|confirmed availability|room 214|cedar qa|"
    r"transit|train delay|all-door|protected bike|signal repair|late-night|city desk|"
    r"\bai\b|agent|benchmark|evaluation|recovery|failed intermediate|aiproductpulse|ai daily|"
    r"space|lunar|mars|local news|city hall|weekend|sports|rookie|ranking|front office|"
    r"world news|policy|climate finance|privacy|energy|"
    r"entertainment|concert|festival|indie|screen|streaming|comedy|album|box office"
    r")",
    re.I,
)

RETWEET_SOURCE_TEXT_FIELDS = (
    "source_tweet",
    "source_text",
    "original_tweet",
    "original_text",
    "parent_tweet",
    "parent_text",
    "tweet",
    "tweet_text",
    "post",
    "post_text",
)
RETWEET_REPLY_TEXT_FIELDS = (
    "reply",
    "reply_text",
    "response",
    "response_text",
    "comment",
    "comment_text",
)
RETWEET_REPLY_LIST_FIELDS = ("replies", "reply_texts", "responses", "comments")
RETWEET_SOURCE_ID_FIELDS = (
    "source_id",
    "source_tweet_id",
    "original_tweet_id",
    "parent_tweet_id",
    "parent_id",
    "tweet_id",
    "id",
)
RETWEET_REPLY_ID_FIELDS = ("reply_id", "reply_tweet_id", "response_id", "comment_id")
CARDIFF_TOPIC_PRIORITY = [
    "sports",
    "music",
    "film_tv_&_video",
    "celebrity_&_pop_culture",
    "news_&_social_concern",
    "gaming",
    "arts_&_culture",
    "business_&_entrepreneurs",
    "science_&_technology",
    "food_&_dining",
    "travel_&_adventure",
    "diaries_&_daily_life",
    "fitness_&_health",
    "fashion_&_style",
    "learning_&_educational",
    "relationships",
    "family",
    "other_hobbies",
    "youth_&_student_life",
]
CARDIFF_BLOCKED_TEXT_RE = re.compile(r"\b(russ|russia|russian|ukraine|ukrainian|putin|kremlin)\b", re.I)
TAGGED_DISPLAY_MENTION_RE = re.compile(r"\{@([^@{}]+)@\}")
TAGGED_GENERIC_USERNAME_RE = re.compile(r"\{\{USERNAME\}\}")
PLAIN_MENTION_RE = re.compile(r"(?<![\w/])@([A-Za-z0-9_]{1,15})")
BLUESKY_COLUMNS = ("type", "text", "created_at", "author", "author_did", "uri", "langs", "reply_to")
TOPIC_DEFINITIONS = {
    "sports": {
        "sports", "sport", "game", "team", "teams", "match", "league", "season",
        "football", "soccer", "basketball", "baseball", "hockey", "tennis", "golf",
        "nfl", "nba", "mlb", "nhl", "fifa", "goal", "coach", "player", "playoffs",
    },
    "movies": {
        "movie", "movies", "film", "films", "cinema", "theater", "trailer",
        "premiere", "boxoffice", "oscars", "actor", "actress", "director", "sequel",
        "marvel", "pixar", "screening",
    },
    "tv": {
        "tv", "television", "show", "shows", "series", "episode", "episodes",
        "season", "streaming", "netflix", "hulu", "hbo", "disney", "prime", "finale",
        "sitcom", "documentary",
    },
    "music": {
        "music", "song", "songs", "album", "track", "single", "concert", "tour",
        "festival", "band", "artist", "singer", "playlist", "grammy", "rap", "pop",
        "rock", "jazz",
    },
    "news": {
        "news", "breaking", "report", "reports", "latest", "update", "updates",
        "court", "police", "weather", "storm", "election", "government", "policy",
        "congress", "senate", "minister", "president", "war", "climate",
    },
    "gaming": {
        "game", "gaming", "xbox", "playstation", "ps5", "nintendo", "switch",
        "steam", "twitch", "esports", "pokemon", "minecraft", "fortnite", "zelda",
    },
    "tech": {
        "tech", "technology", "software", "developer", "developers", "code",
        "coding", "ai", "llm", "openai", "apple", "google", "microsoft", "linux",
        "security", "app", "apps",
    },
}
ROOT_TOPIC_ORDER = ("sports", "movies", "tv", "music")
ROOT_VIEW_CHILD_MULTIPLIER = 4200


def fetch_hf_rows(dataset: str, split: str, length: int, offset: int = 0, config: str = "default"):
    rows = []
    remaining = length
    current_offset = offset
    while remaining > 0:
        page_length = min(100, remaining)
        params = urllib.parse.urlencode(
            {
                "dataset": dataset,
                "config": config,
                "split": split,
                "offset": current_offset,
                "length": page_length,
            }
        )
        request = urllib.request.Request(f"{HF_ROWS_URL}?{params}", headers={"User-Agent": "x-lite-seed-builder/1.0"})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                if exc.code != 429 or attempt == 4:
                    raise
                time.sleep(2 + attempt * 3)
        page_rows = [item["row"] for item in payload.get("rows", [])]
        rows.extend(page_rows)
        if len(page_rows) < page_length:
            break
        current_offset += page_length
        remaining -= page_length
    return rows


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "x-lite-seed-builder/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8-sig")


def fetch_bytes(url: str, headers: dict[str, str] | None = None) -> bytes:
    request_headers = {"User-Agent": "x-lite-seed-builder/1.0"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def download_file(url: str, output_path: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "x-lite-seed-builder/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response, open(output_path, "wb") as handle:
        downloaded = 0
        next_report = 64 * 1024 * 1024
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            downloaded += len(chunk)
            if downloaded >= next_report:
                print(f"Downloaded {downloaded // (1024 * 1024)} MB from {url}", file=sys.stderr)
                next_report += 64 * 1024 * 1024


def stable_int(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)


def stable_unit_interval(value: str) -> float:
    # 53 bits fits exactly in a Python float mantissa.
    return ((stable_int(value) & ((1 << 53) - 1)) + 1) / float(1 << 53)


def weighted_sample_key(seed_value: str, weight: int) -> float:
    weight = max(1, int(weight))
    return math.log(stable_unit_interval(seed_value)) / weight


def normalize_external_id(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        if "e" in value.lower() or "." in value:
            return str(int(Decimal(value)))
    except (InvalidOperation, ValueError):
        pass
    return re.sub(r"\D", "", value) or re.sub(r"[^a-zA-Z0-9]+", "", value)


def slug(value: str, fallback: str, max_len: int = 20) -> str:
    out = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
    out = re.sub(r"_+", "_", out)
    return (out or fallback)[:max_len].strip("_") or fallback


def twitter_username(value: str, fallback: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9_]+", "", value or "").lower()
    out = out[:15].strip("_")
    return out or fallback[:15]


def unique_username(base: str, existing_usernames: set[str], seed_value: str) -> str:
    base = twitter_username(base, f"user{stable_int(seed_value) % 100000:05d}")
    if base not in existing_usernames:
        existing_usernames.add(base)
        return base

    suffix = stable_int(seed_value) % 10000
    for width in (2, 3, 4, 5):
        candidate_suffix = f"{suffix:0{width}d}"[-width:]
        candidate = f"{base[:15 - width]}{candidate_suffix}"
        if candidate not in existing_usernames:
            existing_usernames.add(candidate)
            return candidate

    counter = 0
    while True:
        candidate = f"{base[:10]}{counter:05d}"
        if candidate not in existing_usernames:
            existing_usernames.add(candidate)
            return candidate
        counter += 1


def normalize_text(text: str, max_len: int = 280) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "..."


def parse_datetime(value: str, fallback_index: int) -> str:
    if value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None).isoformat()
        except ValueError:
            pass
    return (datetime(2026, 3, 20, 9, 0, 0) + timedelta(minutes=fallback_index * 7)).isoformat()


def parse_twitter_datetime(value: str, fallback_index: int) -> str:
    if value:
        for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=None).isoformat()
            except ValueError:
                pass
    return (datetime(2026, 4, 1, 9, 0, 0) + timedelta(minutes=fallback_index * 5)).isoformat()


def parse_bluesky_datetime(value: str, fallback_index: int) -> str:
    value = (value or "").strip()
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=None).isoformat(timespec="milliseconds")
        except ValueError:
            pass
    return (datetime(2024, 11, 30, 12, 0, 0) + timedelta(seconds=fallback_index)).isoformat()


def imported_created_at(source_index: int, source_offset_minutes: int = 0) -> str:
    return (datetime(2026, 7, 1, 12, 0, 0) - timedelta(minutes=source_offset_minutes + source_index)).isoformat()


def offset_created_at(value: str, minutes: int) -> str:
    try:
        return (datetime.fromisoformat(value) - timedelta(minutes=minutes)).isoformat()
    except ValueError:
        return value


def int_value(value, default: int = 0) -> int:
    try:
        return int(Decimal(str(value or "0")))
    except (InvalidOperation, ValueError):
        return default


def row_count_value(row: dict, field: str) -> int | None:
    for alias in INTERACTION_FIELD_ALIASES[field]:
        if alias in row and str(row.get(alias, "")).strip() != "":
            return int_value(row.get(alias))
    return None


def row_interaction_profile(row: dict) -> dict | None:
    values = {field: row_count_value(row, field) for field in INTERACTION_FIELD_ALIASES}
    if all(value is None for value in values.values()):
        return None
    return {field: max(0, value or 0) for field, value in values.items()}


def build_interaction_distribution(*row_groups: list[dict]) -> dict:
    profiles = []
    for rows in row_groups:
        for row in rows:
            profile = row_interaction_profile(row)
            if profile is not None:
                profiles.append(profile)

    if not profiles:
        profiles = [{"favorite_count": 0, "retweet_count": 0, "reply_count": 0, "quote_count": 0}]

    sorted_counts = {
        field: sorted(profile[field] for profile in profiles)
        for field in INTERACTION_FIELD_ALIASES
    }
    return {"profiles": profiles, "sorted_counts": sorted_counts}


def sample_interaction_profile(distribution: dict, seed_value: str) -> dict:
    profiles = distribution["profiles"]
    sampled = profiles[stable_int(seed_value) % len(profiles)]
    return dict(sampled)


def distribution_row_count(distribution: dict, field: str, raw_count: int, max_rows: int) -> int:
    if raw_count <= 0 or max_rows <= 0:
        return 0
    values = distribution["sorted_counts"].get(field) or [0]
    percentile = bisect_right(values, raw_count) / len(values)
    if percentile <= 0:
        return 0
    return min(max_rows, max(1, round((percentile ** 1.35) * max_rows)))


INTERACTION_NORMALS = {
    "like": {"mean": 4.8, "sd": 2.8, "floor": 0.70},
    "retweet": {"mean": 0.48, "sd": 0.30, "floor": 0.02},
    "bookmark": {"mean": 0.32, "sd": 0.22, "floor": 0.01},
}


def reply_scaled_interaction_count(tweet_id: str, reply_count: int, kind: str, max_rows: int) -> int:
    if reply_count <= 0 or max_rows <= 0:
        return 0
    params = INTERACTION_NORMALS[kind]
    rng = random.Random(f"interaction:{kind}:{tweet_id}:{reply_count}")
    multiplier = rng.normalvariate(params["mean"], params["sd"])
    multiplier = max(params["floor"], multiplier)
    count = int(round(reply_count * multiplier))
    return min(max_rows, max(1, count))


def distribution_summary(distribution: dict) -> dict:
    out = {"profile_count": len(distribution["profiles"])}
    for field, values in distribution["sorted_counts"].items():
        if not values:
            out[field] = {"min": 0, "median": 0, "p90": 0, "max": 0}
            continue
        out[field] = {
            "min": values[0],
            "median": values[len(values) // 2],
            "p90": values[min(len(values) - 1, int(len(values) * 0.9))],
            "max": values[-1],
        }
    return out


def add_user_once(seed: dict, existing_user_ids: set[str], user: dict) -> None:
    if user["id"] in existing_user_ids:
        return
    row = dict(user)
    row["password"] = PASSWORD
    seed["users"].append(row)
    existing_user_ids.add(user["id"])


def add_tweet_once(seed: dict, existing_tweet_ids: set[str], tweet: dict) -> bool:
    if tweet["id"] in existing_tweet_ids or not tweet.get("content"):
        return False
    seed["tweets"].append(tweet)
    existing_tweet_ids.add(tweet["id"])
    return True


def add_edge_once(seed: dict, key: str, seen: set[tuple[str, str]], first: str, second: str) -> None:
    edge = (first, second)
    if edge in seen:
        return
    if key == "follows":
        seed[key].append({"follower_id": first, "followed_id": second})
    else:
        seed[key].append({"user_id": first, "tweet_id": second})


def import_pyarrow_parquet():
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("Bluesky import requires pyarrow. Install pyarrow or use the x-lite Docker build.") from exc
    return pq


def bluesky_parquet_path(cache_dir: str, parquet_url: str) -> str:
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, "bluesky-ten-million-train.parquet")
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        print(f"Downloading Bluesky parquet from {parquet_url}", file=sys.stderr)
        tmp_path = f"{path}.tmp"
        download_file(parquet_url, tmp_path)
        os.replace(tmp_path, path)
    return path


def load_bluesky_root_uris(path: str) -> list[str]:
    if not path:
        return []
    with open(path, "r", encoding="utf-8") as handle:
        uris = [line.strip() for line in handle if line.strip() and not line.startswith("#")]
    seen = set()
    ordered = []
    for uri in uris:
        if uri in seen:
            continue
        seen.add(uri)
        ordered.append(uri)
    return ordered


def iter_bluesky_rows(parquet_path: str, batch_size: int):
    pq = import_pyarrow_parquet()
    parquet_file = pq.ParquetFile(parquet_path)
    for batch in parquet_file.iter_batches(batch_size=batch_size, columns=list(BLUESKY_COLUMNS)):
        columns = {name: batch.column(name).to_pylist() for name in batch.schema.names}
        row_count = batch.num_rows
        for index in range(row_count):
            yield {name: values[index] for name, values in columns.items()}


def iter_bluesky_batch_columns(parquet_path: str, batch_size: int):
    pq = import_pyarrow_parquet()
    parquet_file = pq.ParquetFile(parquet_path)
    for batch in parquet_file.iter_batches(batch_size=batch_size, columns=list(BLUESKY_COLUMNS)):
        yield {name: batch.column(name).to_pylist() for name in batch.schema.names}, batch.num_rows


def bluesky_row_from_columns(columns: dict, index: int) -> dict:
    return {name: values[index] for name, values in columns.items()}


def bluesky_langs(row: dict) -> set[str]:
    langs = row.get("langs") or []
    if isinstance(langs, str):
        return {langs.lower()}
    return {str(lang).lower() for lang in langs if str(lang).strip()}


def bluesky_langs_match(langs, allowed_langs: set[str]) -> bool:
    if not allowed_langs:
        return True
    if isinstance(langs, str):
        return langs.lower() in allowed_langs
    return any(str(lang).lower() in allowed_langs for lang in (langs or []) if str(lang).strip())


def bluesky_text(row: dict) -> str:
    text = normalize_text(row.get("text") or "", max_len=500)
    return text


def is_eligible_bluesky_row(row: dict, allowed_langs: set[str]) -> bool:
    if row.get("type") and row.get("type") != "post":
        return False
    if not row.get("uri") or not bluesky_text(row):
        return False
    if allowed_langs and not (bluesky_langs(row) & allowed_langs):
        return False
    return True


def bluesky_tweet_id(uri: str) -> str:
    return f"bs-t-{hashlib.sha1(uri.encode('utf-8')).hexdigest()[:20]}"


def bluesky_user_id(author_did: str, author: str) -> str:
    key = author_did or author
    return f"bs-u-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:18]}"


def bluesky_display_name(author: str) -> str:
    handle = (author or "Bluesky user").strip()
    base = handle[:-12] if handle.endswith(".bsky.social") else handle
    base = re.sub(r"[._-]+", " ", base).strip()
    return (base.title() or handle)[:50]


def bluesky_author_user(
    seed: dict,
    existing_user_ids: set[str],
    existing_usernames: set[str],
    author_map: dict[str, str],
    row: dict,
) -> str:
    author = str(row.get("author") or "")
    author_did = str(row.get("author_did") or author)
    key = author_did or author
    if key in author_map:
        return author_map[key]

    user_id = bluesky_user_id(author_did, author)
    username_base = author.split(".", 1)[0] or author_did.rsplit(":", 1)[-1] or user_id
    username = unique_username(username_base, existing_usernames, user_id)
    topic = classify_text_topic(bluesky_text(row))
    add_user_once(seed, existing_user_ids, {
        "id": user_id,
        "username": username,
        "display_name": bluesky_display_name(author),
        "bio": f"Imported Bluesky account. Main topic: {topic}. Original handle: {author}.",
    })
    author_map[key] = user_id
    return user_id


def classify_text_topic(text: str) -> str:
    tokens = set(re.findall(r"[a-z][a-z0-9]+", (text or "").lower()))
    hashtag_tokens = {token[1:].lower() for token in re.findall(r"#[A-Za-z][A-Za-z0-9_]+", text or "")}
    tokens |= hashtag_tokens
    scores = {
        topic: len(tokens & terms)
        for topic, terms in TOPIC_DEFINITIONS.items()
    }
    best_topic, best_score = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0]
    return best_topic if best_score else "general"


def classify_root_topic(text: str) -> str:
    topic = classify_text_topic(text)
    if topic in ROOT_TOPIC_ORDER:
        return topic
    return "general"


def tree_view_count(root_id: str, child_count: int) -> int:
    count = max(1, child_count)
    rng = random.Random(f"views:{root_id}:{child_count}")
    multiplier = max(0.35, min(2.40, rng.normalvariate(1.0, 0.28)))
    return max(1_500, min(25_000_000, int(count * ROOT_VIEW_CHILD_MULTIPLIER * multiplier)))


def home_rank_view_count(home_rank: int, child_count: int) -> int:
    rank = max(1, home_rank)
    reply_bonus = min(250_000, max(0, child_count) * 30)
    return max(1_500, 25_000_000 - rank * 9_000 + reply_bonus)


def bluesky_tweet_row(row: dict, user_id: str, reply_to_id: str | None, source_reply_count: int, fallback_index: int) -> dict:
    tweet = {
        "id": bluesky_tweet_id(row["uri"]),
        "user_id": user_id,
        "content": bluesky_text(row),
        "reply_to_id": reply_to_id,
        "view_count": max(500, min(5_000_000, 1_000 + source_reply_count * 350)),
        "source_reply_count": source_reply_count,
        "created_at": parse_bluesky_datetime(row.get("created_at") or "", fallback_index),
    }
    return tweet


def load_bluesky_tree_cache(path: str, allowed_langs: set[str], sample_limit: int) -> tuple[list[dict], dict]:
    if not path or not os.path.exists(path):
        return [], {}

    open_fn = gzip.open if path.endswith(".gz") else open
    rows = []
    roots_seen = set()
    with open_fn(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            root_rank = int(row.get("root_rank") or 0)
            if sample_limit > 0 and root_rank > sample_limit:
                continue
            if not is_eligible_bluesky_row(row, allowed_langs):
                continue
            rows.append(row)
            if int(row.get("depth") or 0) == 0:
                roots_seen.add(row.get("uri"))

    rows.sort(key=lambda row: (
        int(row.get("root_rank") or 0),
        int(row.get("depth") or 0),
        row.get("created_at") or "",
        row.get("uri") or "",
    ))
    return rows, {
        "source": "tree cache",
        "tree_cache_file": os.path.relpath(path, BASE_DIR),
        "rows_loaded": len(rows),
        "roots_loaded": len(roots_seen),
    }


def add_cached_bluesky_tree_dataset(
    seed: dict,
    existing_user_ids: set[str],
    existing_tweet_ids: set[str],
    existing_usernames: set[str],
    rows: list[dict],
    cache_summary: dict,
) -> tuple[list[dict], dict]:
    author_map: dict[str, str] = {}
    imported_posts: list[dict] = []
    imported_post_by_root_uri: dict[str, dict] = {}
    home_rank_by_root_uri: dict[str, int] = {}
    known_uri_to_id: dict[str, str] = {}
    root_uri_by_known_uri: dict[str, str] = {}
    root_child_counts: Counter[str] = Counter()

    root_rows = [row for row in rows if int(row.get("depth") or 0) == 0]
    reply_rows = [row for row in rows if int(row.get("depth") or 0) > 0]

    for index, row in enumerate(root_rows):
        uri = str(row["uri"])
        user_id = bluesky_author_user(seed, existing_user_ids, existing_usernames, author_map, row)
        source_reply_count = int(row.get("descendant_count") or 0)
        tweet = bluesky_tweet_row(row, user_id, None, source_reply_count, index)
        if add_tweet_once(seed, existing_tweet_ids, tweet):
            known_uri_to_id[uri] = tweet["id"]
            root_uri_by_known_uri[uri] = uri
            if row.get("home_srs_rank"):
                home_rank_by_root_uri[uri] = int(row["home_srs_rank"])
            root_topic = classify_root_topic(tweet["content"])
            post_record = {
                "tweet_id": tweet["id"],
                "user_id": user_id,
                "category": f"Bluesky {root_topic}",
                "favorite_count": max(0, source_reply_count // 2),
                "retweet_count": max(0, source_reply_count // 6),
                "reply_count": source_reply_count,
                "quote_count": 0,
                "created_at": tweet["created_at"],
                "has_real_replies": True,
            }
            imported_posts.append(post_record)
            imported_post_by_root_uri[uri] = post_record

    for index, row in enumerate(reply_rows):
        uri = str(row["uri"])
        parent_uri = str(row.get("parent_node") or row.get("reply_to") or "")
        parent_id = known_uri_to_id.get(parent_uri)
        if not parent_id:
            continue
        root_uri = str(row.get("root_node") or root_uri_by_known_uri.get(parent_uri) or "")
        if root_uri not in root_uri_by_known_uri:
            continue
        user_id = bluesky_author_user(seed, existing_user_ids, existing_usernames, author_map, row)
        source_reply_count = int(row.get("descendant_count") or 0)
        tweet = bluesky_tweet_row(row, user_id, parent_id, source_reply_count, index)
        if add_tweet_once(seed, existing_tweet_ids, tweet):
            known_uri_to_id[uri] = tweet["id"]
            root_uri_by_known_uri[uri] = root_uri
            root_child_counts[root_uri] += 1

    tweet_by_id = {tweet["id"]: tweet for tweet in seed["tweets"]}
    for root_uri, child_count in root_child_counts.items():
        root_id = known_uri_to_id.get(root_uri)
        root_tweet = tweet_by_id.get(root_id or "")
        if not root_tweet:
            continue
        root_tweet["source_reply_count"] = child_count
        if root_uri in home_rank_by_root_uri:
            root_tweet["view_count"] = home_rank_view_count(home_rank_by_root_uri[root_uri], child_count)
        else:
            root_tweet["view_count"] = tree_view_count(root_id, child_count)
        post_record = imported_post_by_root_uri.get(root_uri)
        if post_record:
            post_record["reply_count"] = child_count
            post_record["favorite_count"] = max(0, child_count // 2)
            post_record["retweet_count"] = max(0, child_count // 6)
            post_record["category"] = f"Bluesky {classify_root_topic(root_tweet['content'])}"

    summary = {
        **cache_summary,
        "selection": "pinned ranked roots from compact tree cache",
        "roots_imported": len(root_rows),
        "tweets_imported": len([tweet for tweet in seed["tweets"] if str(tweet["id"]).startswith("bs-t-")]),
        "authors_imported": len(author_map),
        "max_tree_child_count": max(root_child_counts.values(), default=0),
        "total_tree_child_count": sum(root_child_counts.values()),
    }
    return imported_posts, summary


def load_bluesky_jsonl_cache(path: str, allowed_langs: set[str], sample_limit: int = 0) -> tuple[list[dict], dict]:
    if not path or not os.path.exists(path):
        return [], {}

    open_fn = gzip.open if path.endswith(".gz") else open
    rows = []
    with open_fn(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if sample_limit > 0 and len(rows) >= sample_limit:
                break
            if not is_eligible_bluesky_row(row, allowed_langs):
                continue
            rows.append(row)

    return rows, {
        "source": "jsonl cache",
        "cache_file": os.path.relpath(path, BASE_DIR),
        "rows_loaded": len(rows),
    }


def add_explore_bluesky_roots(
    seed: dict,
    existing_user_ids: set[str],
    existing_tweet_ids: set[str],
    existing_usernames: set[str],
    rows: list[dict],
) -> tuple[list[dict], dict]:
    author_map: dict[str, str] = {}
    imported_posts: list[dict] = []
    imported_count = 0

    for index, row in enumerate(rows):
        uri = str(row.get("uri") or "")
        if not uri:
            continue
        user_id = bluesky_author_user(seed, existing_user_ids, existing_usernames, author_map, row)
        source_reply_count = int(row.get("source_reply_count") or row.get("imported_descendant_count") or 0)
        tweet = bluesky_tweet_row(row, user_id, None, source_reply_count, index)
        if add_tweet_once(seed, existing_tweet_ids, tweet):
            imported_count += 1
            imported_posts.append({
                "tweet_id": tweet["id"],
                "user_id": user_id,
                "category": f"Bluesky Explore {row.get('explore_category', 'general')}",
                "favorite_count": max(0, source_reply_count // 2),
                "retweet_count": max(0, source_reply_count // 6),
                "reply_count": source_reply_count,
                "quote_count": 0,
                "created_at": tweet["created_at"],
                "has_real_replies": False,
            })

    return imported_posts, {
        "rows_loaded": len(rows),
        "roots_imported": imported_count,
        "authors_imported": len(author_map),
    }


def select_weighted_bluesky_roots(
    parquet_path: str,
    allowed_langs: set[str],
    sample_limit: int,
    batch_size: int,
    sample_seed: str,
) -> tuple[list[dict], Counter, dict]:
    reply_counts: Counter[str] = Counter()
    scanned_rows = 0
    eligible_rows = 0
    for columns, row_count in iter_bluesky_batch_columns(parquet_path, batch_size):
        types = columns.get("type", [])
        texts = columns.get("text", [])
        uris = columns.get("uri", [])
        replies = columns.get("reply_to", [])
        langs = columns.get("langs", [])
        for index in range(row_count):
            scanned_rows += 1
            if types[index] and types[index] != "post":
                continue
            if not uris[index] or not texts[index]:
                continue
            if not bluesky_langs_match(langs[index], allowed_langs):
                continue
            eligible_rows += 1
            if replies[index]:
                reply_counts[str(replies[index])] += 1
        if scanned_rows and scanned_rows % 1_000_000 < row_count:
            print(f"Bluesky pass 1 counted replies through {scanned_rows:,} rows", file=sys.stderr)

    heap: list[tuple[float, str, dict]] = []
    root_candidates = 0
    scanned_rows_pass_2 = 0
    for columns, row_count in iter_bluesky_batch_columns(parquet_path, batch_size):
        types = columns.get("type", [])
        texts = columns.get("text", [])
        uris = columns.get("uri", [])
        replies = columns.get("reply_to", [])
        langs = columns.get("langs", [])
        for index in range(row_count):
            scanned_rows_pass_2 += 1
            if types[index] and types[index] != "post":
                continue
            if not uris[index] or not texts[index] or replies[index]:
                continue
            if not bluesky_langs_match(langs[index], allowed_langs):
                continue
            uri = str(uris[index])
            reply_count = reply_counts.get(uri, 0)
            if reply_count <= 0:
                continue
            root_candidates += 1
            key = weighted_sample_key(f"{sample_seed}:root:{uri}", reply_count)
            item = (key, uri, bluesky_row_from_columns(columns, index))
            if len(heap) < sample_limit:
                heapq.heappush(heap, item)
            elif key > heap[0][0]:
                heapq.heapreplace(heap, item)
        if scanned_rows_pass_2 and scanned_rows_pass_2 % 1_000_000 < row_count:
            print(f"Bluesky pass 2 selected roots through {scanned_rows_pass_2:,} rows", file=sys.stderr)

    selected = [item[2] for item in sorted(heap, key=lambda item: (-reply_counts[str(item[1])], item[1]))]
    summary = {
        "rows_scanned": scanned_rows,
        "eligible_rows": eligible_rows,
        "root_candidates_with_replies": root_candidates,
    }
    return selected, reply_counts, summary


def select_pinned_bluesky_roots(
    parquet_path: str,
    allowed_langs: set[str],
    root_uris: list[str],
    batch_size: int,
) -> tuple[list[dict], Counter, dict]:
    wanted = set(root_uris)
    reply_counts: Counter[str] = Counter()
    scanned_rows = 0
    eligible_rows = 0

    for columns, row_count in iter_bluesky_batch_columns(parquet_path, batch_size):
        types = columns.get("type", [])
        texts = columns.get("text", [])
        uris = columns.get("uri", [])
        replies = columns.get("reply_to", [])
        langs = columns.get("langs", [])
        for index in range(row_count):
            scanned_rows += 1
            if types[index] and types[index] != "post":
                continue
            if not uris[index] or not texts[index]:
                continue
            if not bluesky_langs_match(langs[index], allowed_langs):
                continue
            eligible_rows += 1
            if replies[index]:
                reply_counts[str(replies[index])] += 1
        if scanned_rows and scanned_rows % 1_000_000 < row_count:
            print(f"Bluesky pass 1 counted replies through {scanned_rows:,} rows", file=sys.stderr)

    row_by_uri = {}
    scanned_rows_pass_2 = 0
    for columns, row_count in iter_bluesky_batch_columns(parquet_path, batch_size):
        types = columns.get("type", [])
        texts = columns.get("text", [])
        uris = columns.get("uri", [])
        replies = columns.get("reply_to", [])
        langs = columns.get("langs", [])
        for index in range(row_count):
            scanned_rows_pass_2 += 1
            uri = str(uris[index] or "")
            if uri not in wanted:
                continue
            if types[index] and types[index] != "post":
                continue
            if not uri or not texts[index] or replies[index]:
                continue
            if not bluesky_langs_match(langs[index], allowed_langs):
                continue
            row_by_uri[uri] = bluesky_row_from_columns(columns, index)
        if scanned_rows_pass_2 and scanned_rows_pass_2 % 1_000_000 < row_count:
            print(f"Bluesky pass 2 loaded pinned roots through {scanned_rows_pass_2:,} rows", file=sys.stderr)

    selected = [row_by_uri[uri] for uri in root_uris if uri in row_by_uri]
    missing = [uri for uri in root_uris if uri not in row_by_uri]
    if missing:
        print(f"Warning: {len(missing):,} pinned Bluesky roots were not found in the parquet", file=sys.stderr)
    summary = {
        "rows_scanned": scanned_rows,
        "eligible_rows": eligible_rows,
        "pinned_root_uris": len(root_uris),
        "missing_pinned_root_uris": len(missing),
        "root_candidates_with_replies": len(selected),
    }
    return selected, reply_counts, summary


def select_bluesky_replies_for_parents(
    parquet_path: str,
    allowed_langs: set[str],
    parent_depths: dict[str, int],
    known_uris: set[str],
    depth: int,
    max_replies_per_base: int,
    max_replies_per_reply: int,
    batch_size: int,
    sample_seed: str,
) -> list[dict]:
    heaps: dict[str, list[tuple[float, str, dict]]] = defaultdict(list)
    unlimited_rows: list[dict] = []
    scanned_rows = 0
    for columns, row_count in iter_bluesky_batch_columns(parquet_path, batch_size):
        types = columns.get("type", [])
        texts = columns.get("text", [])
        uris = columns.get("uri", [])
        replies = columns.get("reply_to", [])
        langs = columns.get("langs", [])
        for index in range(row_count):
            scanned_rows += 1
            if types[index] and types[index] != "post":
                continue
            if not uris[index] or not texts[index]:
                continue
            if not bluesky_langs_match(langs[index], allowed_langs):
                continue
            uri = str(uris[index])
            if uri in known_uris:
                continue
            reply_to = str(replies[index] or "")
            parent_depth = parent_depths.get(reply_to)
            if parent_depth is None or parent_depth + 1 != depth:
                continue
            cap = max_replies_per_base if parent_depth == 0 else max_replies_per_reply
            row = bluesky_row_from_columns(columns, index)
            if cap <= 0:
                unlimited_rows.append(row)
                continue
            key = stable_unit_interval(f"{sample_seed}:reply:{depth}:{uri}")
            heap = heaps[reply_to]
            item = (key, uri, row)
            if len(heap) < cap:
                heapq.heappush(heap, item)
            elif key > heap[0][0]:
                heapq.heapreplace(heap, item)
        if scanned_rows and scanned_rows % 1_000_000 < row_count:
            print(f"Bluesky reply pass depth {depth} scanned {scanned_rows:,} rows", file=sys.stderr)

    selected = list(unlimited_rows)
    for heap in heaps.values():
        selected.extend(item[2] for item in heap)
    return sorted(selected, key=lambda row: (row.get("created_at") or "", row.get("uri") or ""))


def add_bluesky_dataset(
    seed: dict,
    existing_user_ids: set[str],
    existing_tweet_ids: set[str],
    existing_usernames: set[str],
    sample_limit: int,
    max_replies_per_base: int,
    max_replies_per_reply: int,
    max_reply_depth: int,
    allowed_langs: set[str],
    parquet_url: str,
    cache_dir: str,
    batch_size: int,
    sample_seed: str,
    root_uris: list[str],
) -> tuple[list[dict], dict]:
    parquet_path = bluesky_parquet_path(cache_dir, parquet_url)
    if root_uris:
        root_rows, reply_counts, summary = select_pinned_bluesky_roots(
            parquet_path,
            allowed_langs,
            root_uris[:sample_limit] if sample_limit > 0 else root_uris,
            batch_size,
        )
        summary["selection"] = "pinned ranked roots"
    else:
        root_rows, reply_counts, summary = select_weighted_bluesky_roots(
            parquet_path,
            allowed_langs,
            sample_limit,
            batch_size,
            sample_seed,
        )
        summary["selection"] = "weighted sample"

    author_map: dict[str, str] = {}
    imported_posts: list[dict] = []
    imported_post_by_root_uri: dict[str, dict] = {}
    known_uri_to_id: dict[str, str] = {}
    known_depths: dict[str, int] = {}
    root_uri_by_known_uri: dict[str, str] = {}
    root_child_counts: Counter[str] = Counter()

    for index, row in enumerate(root_rows):
        uri = str(row["uri"])
        user_id = bluesky_author_user(seed, existing_user_ids, existing_usernames, author_map, row)
        source_reply_count = reply_counts.get(uri, 0)
        tweet = bluesky_tweet_row(row, user_id, None, source_reply_count, index)
        if add_tweet_once(seed, existing_tweet_ids, tweet):
            known_uri_to_id[uri] = tweet["id"]
            known_depths[uri] = 0
            root_uri_by_known_uri[uri] = uri
            root_topic = classify_root_topic(tweet["content"])
            post_record = {
                "tweet_id": tweet["id"],
                "user_id": user_id,
                "category": f"Bluesky {root_topic}",
                "favorite_count": max(0, source_reply_count // 2),
                "retweet_count": max(0, source_reply_count // 6),
                "reply_count": source_reply_count,
                "quote_count": 0,
                "created_at": tweet["created_at"],
                "has_real_replies": True,
            }
            imported_posts.append(post_record)
            imported_post_by_root_uri[uri] = post_record

    depth = 1
    while max_reply_depth <= 0 or depth <= max_reply_depth:
        reply_rows = select_bluesky_replies_for_parents(
            parquet_path,
            allowed_langs,
            known_depths,
            set(known_uri_to_id),
            depth,
            max_replies_per_base,
            max_replies_per_reply,
            batch_size,
            sample_seed,
        )
        if not reply_rows:
            break
        imported_this_depth = 0
        for index, row in enumerate(reply_rows):
            uri = str(row["uri"])
            parent_uri = str(row.get("reply_to") or "")
            parent_id = known_uri_to_id.get(parent_uri)
            if not parent_id:
                continue
            root_uri = root_uri_by_known_uri.get(parent_uri)
            if not root_uri:
                continue
            user_id = bluesky_author_user(seed, existing_user_ids, existing_usernames, author_map, row)
            source_reply_count = reply_counts.get(uri, 0)
            tweet = bluesky_tweet_row(row, user_id, parent_id, source_reply_count, index)
            if add_tweet_once(seed, existing_tweet_ids, tweet):
                known_uri_to_id[uri] = tweet["id"]
                known_depths[uri] = depth
                root_uri_by_known_uri[uri] = root_uri
                root_child_counts[root_uri] += 1
                imported_this_depth += 1
        if imported_this_depth == 0:
            break
        depth += 1

    tweet_by_id = {tweet["id"]: tweet for tweet in seed["tweets"]}
    for root_uri, child_count in root_child_counts.items():
        root_id = known_uri_to_id.get(root_uri)
        root_tweet = tweet_by_id.get(root_id or "")
        if not root_tweet:
            continue
        root_tweet["source_reply_count"] = child_count
        root_tweet["view_count"] = tree_view_count(root_id, child_count)
        post_record = imported_post_by_root_uri.get(root_uri)
        if post_record:
            post_record["reply_count"] = child_count
            post_record["favorite_count"] = max(0, child_count // 2)
            post_record["retweet_count"] = max(0, child_count // 6)
            post_record["category"] = f"Bluesky {classify_root_topic(root_tweet['content'])}"

    summary.update({
        "roots_imported": len(root_rows),
        "tweets_imported": len([tweet for tweet in seed["tweets"] if str(tweet["id"]).startswith("bs-t-")]),
        "authors_imported": len(author_map),
        "max_replies_per_base": max_replies_per_base,
        "max_replies_per_reply": max_replies_per_reply,
        "max_reply_depth": max_reply_depth if max_reply_depth > 0 else "full",
        "max_tree_child_count": max(root_child_counts.values(), default=0),
        "total_tree_child_count": sum(root_child_counts.values()),
        "langs": sorted(allowed_langs),
    })
    return imported_posts, summary


def mention_display_name(value: str) -> str:
    value = re.sub(r"\s+", " ", (value or "").replace("_", " ")).strip()
    return value[:50] or "Tagged User"


def add_tagged_account(
    seed: dict,
    existing_user_ids: set[str],
    existing_usernames: set[str],
    tagged_accounts: dict[str, str],
    display_name: str,
    base_username: str,
    seed_value: str,
    bio: str,
) -> str:
    key = re.sub(r"\s+", " ", display_name.lower()).strip() or base_username.lower()
    if key in tagged_accounts:
        return tagged_accounts[key]

    normalized_base = twitter_username(base_username or display_name, f"tag{stable_int(seed_value) % 100000:05d}")
    if normalized_base in existing_usernames:
        tagged_accounts[key] = normalized_base
        return normalized_base

    username = unique_username(normalized_base, existing_usernames, seed_value)
    user_id = f"tag-{slug(username, 'user', 16)}-{stable_int(seed_value) % 100000:05d}"
    while user_id in existing_user_ids:
        user_id = f"tag-{slug(username, 'user', 16)}-{stable_int(user_id) % 100000:05d}"

    add_user_once(seed, existing_user_ids, {
        "id": user_id,
        "username": username,
        "display_name": mention_display_name(display_name),
        "bio": bio,
    })
    tagged_accounts[key] = username
    return username


def replace_tagged_people(
    seed: dict,
    existing_user_ids: set[str],
    existing_usernames: set[str],
    username_profiles: list[dict],
) -> dict:
    initial_user_count = len(seed["users"])
    tagged_accounts: dict[str, str] = {}
    display_mentions = 0
    generic_mentions = 0
    plain_mentions = 0

    for tweet in seed["tweets"]:
        tweet_id = str(tweet.get("id", "tweet"))
        content = tweet.get("content") or ""

        def replace_display(match: re.Match) -> str:
            nonlocal display_mentions
            display_mentions += 1
            display_name = mention_display_name(match.group(1))
            username = add_tagged_account(
                seed,
                existing_user_ids,
                existing_usernames,
                tagged_accounts,
                display_name,
                display_name,
                f"tag-display:{display_name}",
                "Auto-created from a tagged person in imported seed text.",
            )
            return f"@{username}"

        content = TAGGED_DISPLAY_MENTION_RE.sub(replace_display, content)

        def replace_generic(match: re.Match) -> str:
            nonlocal generic_mentions
            occurrence = generic_mentions
            generic_mentions += 1
            profile = profile_for_user(username_profiles, 12000 + occurrence, f"tag-generic:{tweet_id}:{occurrence}")
            display_name = mention_display_name(f"{profile.get('first', '')} {profile.get('last', '')}")
            username = add_tagged_account(
                seed,
                existing_user_ids,
                existing_usernames,
                tagged_accounts,
                display_name,
                profile.get("username") or display_name,
                f"tag-generic:{tweet_id}:{occurrence}",
                "Auto-created from an anonymized tagged user placeholder in imported seed text.",
            )
            return f"@{username}"

        content = TAGGED_GENERIC_USERNAME_RE.sub(replace_generic, content)

        def replace_plain(match: re.Match) -> str:
            nonlocal plain_mentions
            handle = match.group(1)
            normalized = twitter_username(handle, f"tag{stable_int(f'plain:{handle}') % 100000:05d}")
            username = add_tagged_account(
                seed,
                existing_user_ids,
                existing_usernames,
                tagged_accounts,
                normalized,
                normalized,
                f"tag-plain:{normalized}",
                "Auto-created from a raw @mention in imported seed text.",
            )
            if username != handle:
                plain_mentions += 1
            return f"@{username}"

        content = PLAIN_MENTION_RE.sub(replace_plain, content)
        tweet["content"] = content

    return {
        "accounts_created": len(seed["users"]) - initial_user_count,
        "tag_mappings": len(tagged_accounts),
        "display_placeholders_replaced": display_mentions,
        "generic_placeholders_replaced": generic_mentions,
        "raw_mentions_normalized": plain_mentions,
    }
    seen.add(edge)


def source_user_id(source_name: str, raw_user_id: str) -> str:
    normalized = normalize_external_id(raw_user_id)
    if not normalized:
        normalized = hashlib.sha1(raw_user_id.encode("utf-8")).hexdigest()[:12]
    return f"rw-{source_name}-u-{normalized}"


def source_tweet_id(source_name: str, raw_tweet_id: str, row_index: int) -> str:
    normalized = normalize_external_id(raw_tweet_id) or f"row-{row_index}"
    return f"rw-{source_name}-t-{normalized}-{row_index:05d}"


def load_zenodo_rows(limit: int, offset: int) -> list[dict]:
    csv_text = fetch_text(ZENODO_FILE_URL)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    if offset:
        rows = rows[offset:]
    if limit > 0:
        rows = rows[:limit]
    return rows


def load_optional_csv_rows(url: str, limit: int, offset: int) -> list[dict]:
    if not url:
        return []
    rows = list(csv.DictReader(io.StringIO(fetch_text(url))))
    if offset:
        rows = rows[offset:]
    if limit > 0:
        rows = rows[:limit]
    return rows


def rows_from_csv_text(text: str, delimiter: str = ",") -> list[dict]:
    return [dict(row) for row in csv.DictReader(io.StringIO(text), delimiter=delimiter)]


def rows_from_json_text(text: str) -> list[dict]:
    payload = json.loads(text)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "data", "tweets", "records"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return [payload]
    return []


def rows_from_jsonl_text(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def load_rows_from_archive_bytes(blob: bytes, name_hint: str = "archive") -> list[dict]:
    rows = []
    if zipfile.is_zipfile(io.BytesIO(blob)):
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            members = sorted(
                member for member in archive.namelist()
                if not member.endswith("/") and member.lower().endswith((".csv", ".tsv", ".json", ".jsonl", ".ndjson"))
            )
            for member in members:
                raw = archive.read(member)
                lower = member.lower()
                if lower.endswith(".gz"):
                    raw = gzip.decompress(raw)
                text = raw.decode("utf-8-sig", errors="replace")
                if lower.endswith(".tsv"):
                    rows.extend(rows_from_csv_text(text, delimiter="\t"))
                elif lower.endswith(".csv"):
                    rows.extend(rows_from_csv_text(text))
                elif lower.endswith((".jsonl", ".ndjson")):
                    rows.extend(rows_from_jsonl_text(text))
                elif lower.endswith(".json"):
                    rows.extend(rows_from_json_text(text))
        return rows

    text = blob.decode("utf-8-sig", errors="replace")
    lower = name_hint.lower()
    if lower.endswith(".tsv"):
        return rows_from_csv_text(text, delimiter="\t")
    if lower.endswith((".jsonl", ".ndjson")):
        return rows_from_jsonl_text(text)
    if lower.endswith(".json"):
        return rows_from_json_text(text)
    return rows_from_csv_text(text)


def kaggle_auth_headers(username: str, key: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{key}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def load_retweet_rows(zip_url: str, csv_url: str, limit: int, offset: int, skip: bool) -> tuple[list[dict], str]:
    if skip:
        return [], "skipped"

    source = ""
    rows: list[dict] = []
    try:
        if zip_url:
            rows = load_rows_from_archive_bytes(fetch_bytes(zip_url), zip_url)
            source = zip_url
        elif csv_url:
            rows = load_optional_csv_rows(csv_url, 0, 0)
            source = csv_url
        else:
            username = os.environ.get("KAGGLE_USERNAME", "")
            key = os.environ.get("KAGGLE_KEY", "")
            if username and key:
                rows = load_rows_from_archive_bytes(fetch_bytes(RETWEET_KAGGLE_URL, kaggle_auth_headers(username, key)), RETWEET_KAGGLE_URL)
                source = RETWEET_KAGGLE_URL
    except Exception as exc:
        print(f"Warning: ReTweet import unavailable: {exc}", file=sys.stderr)
        return [], "unavailable"

    if offset:
        rows = rows[offset:]
    if limit > 0:
        rows = rows[:limit]
    return rows, source or "unavailable"


def load_toxic_tree_metric_rows(csv_url: str, limit: int, offset: int, skip: bool) -> tuple[list[dict], str]:
    if skip or not csv_url:
        return [], "skipped" if skip else "unavailable"
    try:
        rows = load_optional_csv_rows(csv_url, limit, offset)
    except Exception as exc:
        print(f"Warning: toxic-conversation structure import unavailable: {exc}", file=sys.stderr)
        return [], "unavailable"
    return rows, csv_url


def load_cardiff_topic_rows(split: str, fetch_limit: int, offset: int, skip: bool) -> tuple[list[dict], str]:
    if skip:
        return [], "skipped"
    parquet_url = f"{CARDIFF_TOPIC_MULTI_URL}/resolve/main/tweet_topic_multi/{split}-00000-of-00001.parquet"
    try:
        import pyarrow.parquet as pq

        table = pq.read_table(io.BytesIO(fetch_bytes(parquet_url)))
        rows = table.to_pylist()
        if offset:
            rows = rows[offset:]
        if fetch_limit > 0:
            rows = rows[:fetch_limit]
        return rows, parquet_url
    except Exception as exc:
        print(f"Warning: CardiffNLP parquet import unavailable, trying rows API: {exc}", file=sys.stderr)

    try:
        rows = fetch_hf_rows(CARDIFF_TOPIC_MULTI_DATASET, split, fetch_limit, offset, CARDIFF_TOPIC_MULTI_CONFIG)
    except Exception as exc:
        print(f"Warning: CardiffNLP topic import unavailable: {exc}", file=sys.stderr)
        return [], "unavailable"
    return rows, f"{CARDIFF_TOPIC_MULTI_URL}/split/{split}"


def load_mide22_rows(limit: int, offset: int, include_turkish: bool) -> list[dict]:
    rows = []
    sources = [("en", MIDE22_EN_TWEETS_URL)]
    if include_turkish:
        sources.append(("tr", MIDE22_TR_TWEETS_URL))
    for language, url in sources:
        text = fetch_text(url)
        for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
            item = dict(row)
            item["language"] = language
            rows.append(item)
    if offset:
        rows = rows[offset:]
    if limit > 0:
        rows = rows[:limit]
    return rows


def load_username_profiles(count: int, csv_url: str, seed: str) -> list[dict]:
    if csv_url:
        rows = list(csv.DictReader(io.StringIO(fetch_text(csv_url))))
        profiles = []
        for row in rows:
            username = (
                row.get("username")
                or row.get("screen_name")
                or row.get("user_screen_name")
                or row.get("login.username")
                or row.get("handle")
                or ""
            )
            first = row.get("first") or row.get("first_name") or row.get("name.first") or ""
            last = row.get("last") or row.get("last_name") or row.get("name.last") or ""
            name = row.get("name") or row.get("display_name") or row.get("user_name") or ""
            if not (first or last) and name:
                parts = name.split()
                first = parts[0] if parts else ""
                last = " ".join(parts[1:]) if len(parts) > 1 else ""
            profiles.append({"username": username, "first": first, "last": last})
        return profiles

    profiles = []
    for index in range(max(count, 1)):
        key = f"{seed}:{index}"
        adjective = USERNAME_ADJECTIVES[stable_int(f"adj:{key}") % len(USERNAME_ADJECTIVES)]
        noun = USERNAME_NOUNS[stable_int(f"noun:{key}") % len(USERNAME_NOUNS)]
        number = stable_int(f"num:{key}") % 1000
        profiles.append({
            "username": f"{adjective}{noun}{number:03d}",
            "first": adjective.title(),
            "last": noun.title(),
        })
    return profiles


def profile_for_user(profiles: list[dict], index: int, user_id: str) -> dict:
    if not profiles:
        short = user_id.rsplit("-", 1)[-1][-8:]
        return {"username": f"user{short}", "first": "X", "last": f"User {short}"}
    return profiles[index % len(profiles)]


def first_row_value(row: dict, fields: tuple[str, ...]) -> str:
    lower_map = {str(key).lower(): value for key, value in row.items()}
    for field in fields:
        value = lower_map.get(field.lower())
        if value is not None and str(value).strip():
            return str(value)
    return ""


def parse_reply_list(value: str) -> list[str]:
    value = (value or "").strip()
    if not value:
        return []
    if value.startswith("["):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, list):
            replies = []
            for item in payload:
                if isinstance(item, dict):
                    text = first_row_value(item, RETWEET_REPLY_TEXT_FIELDS + ("text",))
                else:
                    text = str(item)
                text = normalize_text(text)
                if text:
                    replies.append(text)
            return replies
    if "\n" in value:
        return [normalize_text(part) for part in value.splitlines() if normalize_text(part)]
    if "||" in value:
        return [normalize_text(part) for part in value.split("||") if normalize_text(part)]
    text = normalize_text(value)
    return [text] if text else []


def retweet_conversations(rows: list[dict], max_replies_per_source: int) -> list[dict]:
    conversations: dict[str, dict] = {}
    for index, row in enumerate(rows):
        source_id = normalize_external_id(first_row_value(row, RETWEET_SOURCE_ID_FIELDS)) or f"row-{index}"
        source_text = normalize_text(first_row_value(row, RETWEET_SOURCE_TEXT_FIELDS))
        if not source_text:
            continue
        key = source_id or hashlib.sha1(source_text.encode("utf-8")).hexdigest()[:12]
        conversation = conversations.setdefault(
            key,
            {
                "source_id": key,
                "source_text": source_text,
                "replies": [],
                "label": first_row_value(row, ("label", "sentiment", "polarity", "reply_sentiment")),
            },
        )
        if not conversation["source_text"]:
            conversation["source_text"] = source_text

        reply_text = normalize_text(first_row_value(row, RETWEET_REPLY_TEXT_FIELDS))
        if reply_text:
            conversation["replies"].append(reply_text)

        for field in RETWEET_REPLY_LIST_FIELDS:
            value = first_row_value(row, (field,))
            if value:
                conversation["replies"].extend(parse_reply_list(value))

    out = []
    for conversation in conversations.values():
        seen = set()
        replies = []
        for reply in conversation["replies"]:
            key = re.sub(r"\s+", " ", reply.lower()).strip()
            if key and key not in seen and key != re.sub(r"\s+", " ", conversation["source_text"].lower()).strip():
                replies.append(reply)
                seen.add(key)
            if max_replies_per_source > 0 and len(replies) >= max_replies_per_source:
                break
        if replies:
            conversation["replies"] = replies
            out.append(conversation)
    return out


def add_retweet_dataset(seed: dict, rows: list[dict], existing_user_ids: set[str], existing_tweet_ids: set[str], existing_usernames: set[str], username_profiles: list[dict], max_replies_per_source: int) -> list[dict]:
    conversations = retweet_conversations(rows, max_replies_per_source)
    if not conversations:
        return []

    imported_posts = []
    author_count = min(3500, max(600, len(conversations) // 3))
    author_ids = []
    for index in range(author_count):
        user_id = f"rw-retweet-u-{index + 1:04d}"
        profile = profile_for_user(username_profiles, index + 5000, user_id)
        username = unique_username(profile.get("username") or f"retweetuser{index}", existing_usernames, user_id)
        display_name = normalize_text(f"{profile.get('first', '')} {profile.get('last', '')}", max_len=50).strip() or f"ReTweet User {index + 1}"
        add_user_once(
            seed,
            existing_user_ids,
            {
                "id": user_id,
                "username": username,
                "display_name": display_name,
                "bio": "Generated account for imported ReTweet source or reply text.",
            },
        )
        author_ids.append(user_id)

    for source_index, conversation in enumerate(conversations):
        source_id = conversation["source_id"]
        tweet_id = source_tweet_id("retweet", source_id, source_index)
        author_id = author_ids[stable_int(f"source:{source_id}") % len(author_ids)]
        reply_count = len(conversation["replies"])
        created_at = imported_created_at(source_index, source_offset_minutes=600)
        if not add_tweet_once(
            seed,
            existing_tweet_ids,
            {
                "id": tweet_id,
                "user_id": author_id,
                "content": conversation["source_text"],
                "view_count": max(2_500, reply_count * 4_500),
                "created_at": created_at,
            },
        ):
            continue

        imported_posts.append(
            {
                "tweet_id": tweet_id,
                "user_id": author_id,
                "category": f"ReTweet {conversation.get('label') or 'reply set'}",
                "conversation_id": f"retweet-{source_id}",
                "favorite_count": max(1, reply_count // 3),
                "retweet_count": max(0, reply_count // 12),
                "reply_count": reply_count,
                "quote_count": 0,
                "created_at": created_at,
                "has_real_replies": True,
            }
        )

        for reply_index, reply_text in enumerate(conversation["replies"]):
            actor_id = choose_actor(author_ids, f"retweet-reply:{tweet_id}:{reply_index}", {author_id})
            if not actor_id:
                continue
            add_tweet_once(
                seed,
                existing_tweet_ids,
                {
                    "id": f"{tweet_id}-real-r-{reply_index + 1:03d}",
                    "user_id": actor_id,
                    "content": reply_text,
                    "reply_to_id": tweet_id,
                    "view_count": 0,
                    "created_at": offset_created_at(created_at, -(reply_index + 1)),
                },
            )

    return imported_posts


def cardiff_topic_for_row(row: dict) -> str:
    labels = row.get("label_name") or []
    if isinstance(labels, str):
        labels = [labels]
    for topic in CARDIFF_TOPIC_PRIORITY:
        if topic in labels:
            return topic
    return str(labels[0]) if labels else "general"


def select_balanced_cardiff_rows(rows: list[dict], limit: int, max_per_topic: int) -> list[dict]:
    if limit <= 0:
        limit = len(rows)

    grouped: dict[str, list[dict]] = defaultdict(list)
    seen_texts = set()
    for row in rows:
        content = normalize_text(row.get("text", ""))
        content_key = re.sub(r"\s+", " ", content.lower()).strip()
        if not content or CARDIFF_BLOCKED_TEXT_RE.search(content) or content_key in seen_texts:
            continue
        seen_texts.add(content_key)
        grouped[cardiff_topic_for_row(row)].append(row)

    for topic_rows in grouped.values():
        topic_rows.sort(key=lambda item: stable_int(str(item.get("id") or item.get("text", ""))))

    topics = [topic for topic in CARDIFF_TOPIC_PRIORITY if grouped.get(topic)]
    topics.extend(sorted(topic for topic in grouped if topic not in topics))
    selected = []
    topic_counts: Counter[str] = Counter()
    while len(selected) < limit:
        progressed = False
        for topic in topics:
            if len(selected) >= limit:
                break
            if max_per_topic > 0 and topic_counts[topic] >= max_per_topic:
                continue
            topic_rows = grouped.get(topic) or []
            if topic_counts[topic] >= len(topic_rows):
                continue
            selected.append(topic_rows[topic_counts[topic]])
            topic_counts[topic] += 1
            progressed = True
        if not progressed:
            break
    return selected


def add_cardiff_topic_dataset(seed: dict, rows: list[dict], existing_user_ids: set[str], existing_tweet_ids: set[str], existing_usernames: set[str], username_profiles: list[dict], limit: int, max_per_topic: int) -> list[dict]:
    selected_rows = select_balanced_cardiff_rows(rows, limit, max_per_topic)
    if not selected_rows:
        return []

    topics = sorted({cardiff_topic_for_row(row) for row in selected_rows})
    author_ids_by_topic: dict[str, list[str]] = {}
    user_index = 0
    for topic in topics:
        safe_topic = slug(topic, "topic", max_len=18)
        author_ids_by_topic[topic] = []
        for topic_author_index in range(8):
            user_id = f"rw-cardiff-u-{safe_topic}-{topic_author_index + 1:02d}"
            profile = profile_for_user(username_profiles, user_index + 7500, user_id)
            username = unique_username(profile.get("username") or f"{safe_topic}{topic_author_index}", existing_usernames, user_id)
            display_name = normalize_text(f"{profile.get('first', '')} {profile.get('last', '')}", max_len=50).strip() or f"{topic.replace('_', ' ').title()} User"
            add_user_once(
                seed,
                existing_user_ids,
                {
                    "id": user_id,
                    "username": username,
                    "display_name": display_name,
                    "bio": f"Imported CardiffNLP topic account. Main topic: {topic.replace('_', ' ')}.",
                },
            )
            author_ids_by_topic[topic].append(user_id)
            user_index += 1

    imported_posts = []
    for source_index, row in enumerate(selected_rows):
        topic = cardiff_topic_for_row(row)
        raw_tweet_id = str(row.get("id") or f"row-{source_index}")
        tweet_id = source_tweet_id("cardiff", raw_tweet_id, source_index)
        author_ids = author_ids_by_topic[topic]
        author_id = author_ids[stable_int(raw_tweet_id) % len(author_ids)]
        content = normalize_text(row.get("text", ""))
        if not content:
            continue
        created_at = imported_created_at(source_index, source_offset_minutes=300)
        view_count = 2_000 + (stable_int(f"views:{raw_tweet_id}:{content}") % 55_000)
        if not add_tweet_once(
            seed,
            existing_tweet_ids,
            {
                "id": tweet_id,
                "user_id": author_id,
                "content": content,
                "view_count": view_count,
                "created_at": created_at,
            },
        ):
            continue

        favorite_count = 1 + stable_int(f"likes:{raw_tweet_id}") % 600
        retweet_count = stable_int(f"retweets:{raw_tweet_id}") % 90
        imported_posts.append(
            {
                "tweet_id": tweet_id,
                "user_id": author_id,
                "category": f"CardiffNLP {topic}",
                "conversation_id": f"cardiff-{topic}",
                "favorite_count": favorite_count,
                "retweet_count": retweet_count,
                "reply_count": 0,
                "quote_count": 0,
                "created_at": created_at,
            }
        )
    return imported_posts


def add_csv_twitter_dataset(seed: dict, rows: list[dict], existing_user_ids: set[str], existing_tweet_ids: set[str], existing_usernames: set[str], username_profiles: list[dict], source_name: str, source_label: str) -> tuple[list[dict], dict[str, str]]:
    user_categories: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        raw_user_id = row.get("user_id_str", "")
        if raw_user_id:
            user_categories[source_user_id(source_name, raw_user_id)][row.get("category") or "General"] += 1

    user_id_map = {}
    for index, (user_id, categories) in enumerate(sorted(user_categories.items())):
        top_category = categories.most_common(1)[0][0]
        short = user_id.rsplit("-", 1)[-1][-8:]
        profile = profile_for_user(username_profiles, index, user_id)
        profile_username = profile.get("username") or f"{profile.get('first', '')}{profile.get('last', '')}"
        username = unique_username(profile_username, existing_usernames, user_id)
        display_name = normalize_text(f"{profile.get('first', '')} {profile.get('last', '')}", max_len=50).strip()
        if not display_name:
            display_name = f"X User {short}"
        add_user_once(
            seed,
            existing_user_ids,
            {
                "id": user_id,
                "username": username,
                "display_name": display_name,
                "bio": f"Imported {source_label} user. Main topic: {top_category}.",
            },
        )
        user_id_map[user_id] = user_id

    imported_posts = []
    tweet_by_external_id = {}
    conversation_roots = {}

    seen_texts = set()
    sorted_rows = sorted(
        enumerate(rows),
        key=lambda item: parse_twitter_datetime(item[1].get("created_at", ""), item[0]),
    )
    for source_index, row in sorted_rows:
        raw_user_id = row.get("user_id_str", "")
        raw_tweet_id = row.get("id_str", "")
        user_id = source_user_id(source_name, raw_user_id)
        tweet_id = source_tweet_id(source_name, raw_tweet_id, source_index)
        content = normalize_text(row.get("full_text", ""))
        content_key = re.sub(r"\s+", " ", content.lower()).strip()
        if not content or content_key in seen_texts or user_id not in user_id_map:
            continue
        seen_texts.add(content_key)

        conversation_id = normalize_external_id(row.get("conversation_id_str", ""))
        reply_to_id = None
        if conversation_id:
            root_id = conversation_roots.get(conversation_id)
            if root_id and root_id != tweet_id:
                reply_to_id = root_id
            else:
                conversation_roots[conversation_id] = tweet_id

        favorite_count = int_value(row.get("favorite_count"))
        retweet_count = int_value(row.get("retweet_count"))
        reply_count = int_value(row.get("reply_count"))
        quote_count = int_value(row.get("quote_count"))
        tweet = {
            "id": tweet_id,
            "user_id": user_id,
            "content": content,
            "view_count": max(1_000, favorite_count * 12 + retweet_count * 30 + reply_count * 45 + quote_count * 60),
            "created_at": imported_created_at(source_index),
        }
        if reply_to_id:
            tweet["reply_to_id"] = reply_to_id
        if add_tweet_once(seed, existing_tweet_ids, tweet):
            imported_posts.append(
                {
                    "tweet_id": tweet_id,
                    "user_id": user_id,
                    "category": row.get("category") or "General",
                    "conversation_id": conversation_id,
                    "favorite_count": favorite_count,
                    "retweet_count": retweet_count,
                    "reply_count": reply_count,
                    "quote_count": quote_count,
                    "created_at": tweet["created_at"],
                }
            )
            tweet_by_external_id[normalize_external_id(raw_tweet_id)] = tweet_id

    return imported_posts, tweet_by_external_id


def add_mide22_dataset(seed: dict, rows: list[dict], existing_user_ids: set[str], existing_tweet_ids: set[str], existing_usernames: set[str], username_profiles: list[dict], interaction_distribution: dict) -> list[dict]:
    author_ids = []
    author_count = max(600, min(2500, len(rows) // 4))
    for index in range(author_count):
        user_id = f"rw-mide22-u-{index + 1:04d}"
        profile = profile_for_user(username_profiles, index + 2000, user_id)
        username = unique_username(profile.get("username") or f"mideuser{index}", existing_usernames, user_id)
        display_name = normalize_text(f"{profile.get('first', '')} {profile.get('last', '')}", max_len=50).strip()
        if not display_name:
            display_name = f"MiDe22 User {index + 1}"
        add_user_once(
            seed,
            existing_user_ids,
            {
                "id": user_id,
                "username": username,
                "display_name": display_name,
                "bio": "Generated account for imported MiDe22 tweet text.",
            },
        )
        author_ids.append(user_id)

    imported_posts = []
    seen_texts = set()
    for source_index, row in enumerate(rows):
        content = normalize_text(row.get("text", ""))
        content_key = re.sub(r"\s+", " ", content.lower()).strip()
        if not content or content_key in seen_texts:
            continue
        seen_texts.add(content_key)

        raw_tweet_id = row.get("tweet_id", "")
        tweet_id = source_tweet_id("mide22", raw_tweet_id, source_index)
        author_id = author_ids[stable_int(raw_tweet_id or str(source_index)) % len(author_ids)]
        topic = row.get("topic") or "MiDe22"
        event_id = row.get("event_id") or "event"
        label = row.get("label") or "Unlabeled"
        interaction_profile = sample_interaction_profile(interaction_distribution, f"mide22:{raw_tweet_id}:{source_index}")
        if add_tweet_once(
            seed,
            existing_tweet_ids,
            {
                "id": tweet_id,
                "user_id": author_id,
                "content": content,
                "view_count": max(
                    2_000 + stable_int(tweet_id) % 85_000,
                    interaction_profile["favorite_count"] * 12
                    + interaction_profile["retweet_count"] * 30
                    + interaction_profile["reply_count"] * 45
                    + interaction_profile["quote_count"] * 60,
                ),
                "created_at": imported_created_at(source_index, source_offset_minutes=2_000),
            },
        ):
            created_at = imported_created_at(source_index, source_offset_minutes=2_000)
            imported_posts.append(
                {
                    "tweet_id": tweet_id,
                    "user_id": author_id,
                    "category": f"MiDe22 {topic} {label}",
                    "conversation_id": f"mide22-{event_id}",
                    "favorite_count": interaction_profile["favorite_count"],
                    "retweet_count": interaction_profile["retweet_count"],
                    "reply_count": interaction_profile["reply_count"],
                    "quote_count": interaction_profile["quote_count"],
                    "created_at": created_at,
                }
            )
    return imported_posts


def prune_original_seed_for_tasks(seed: dict, max_recent_per_followed_user: int) -> dict:
    if max_recent_per_followed_user < 0:
        return seed

    followed_by_main = {
        item["followed_id"]
        for item in seed.get("follows", [])
        if item.get("follower_id") == "u41"
    }
    keep_tweet_ids = set()
    per_followed_counts: Counter[str] = Counter()
    tweets_desc = sorted(seed.get("tweets", []), key=lambda item: item.get("created_at", ""), reverse=True)

    for tweet in tweets_desc:
        content = tweet.get("content", "")
        if TASK_RELEVANT_TWEET_RE.search(content):
            keep_tweet_ids.add(tweet["id"])
            if tweet.get("quote_tweet_id"):
                keep_tweet_ids.add(tweet["quote_tweet_id"])
            if tweet.get("reply_to_id"):
                keep_tweet_ids.add(tweet["reply_to_id"])
            continue

        author_id = tweet.get("user_id")
        if author_id in followed_by_main and per_followed_counts[author_id] < max_recent_per_followed_user:
            keep_tweet_ids.add(tweet["id"])
            per_followed_counts[author_id] += 1
            if tweet.get("quote_tweet_id"):
                keep_tweet_ids.add(tweet["quote_tweet_id"])
            if tweet.get("reply_to_id"):
                keep_tweet_ids.add(tweet["reply_to_id"])

    seed["tweets"] = [tweet for tweet in seed.get("tweets", []) if tweet["id"] in keep_tweet_ids]
    for key in ("likes", "bookmarks", "retweets"):
        seed[key] = [item for item in seed.get(key, []) if item.get("tweet_id") in keep_tweet_ids]
    return seed


def toxic_structure_profiles(rows: list[dict]) -> list[dict]:
    profiles = []
    for row in rows:
        reply_count = None
        for field in ("n_replies", "reply_count", "replies", "n_tweets", "num_tweets", "size", "tree_size"):
            if field in row and str(row.get(field, "")).strip():
                reply_count = max(0, int_value(row.get(field)) - (1 if field in {"n_tweets", "num_tweets", "size", "tree_size"} else 0))
                break
        if reply_count is None:
            continue
        profiles.append(
            {
                "favorite_count": max(0, reply_count // 2),
                "retweet_count": max(0, reply_count // 8),
                "reply_count": reply_count,
                "quote_count": 0,
            }
        )
    return profiles


def choose_actor(user_ids: list[str], seed_value: str, excluded: set[str]) -> str | None:
    if not user_ids:
        return None
    start = stable_int(seed_value) % len(user_ids)
    for offset in range(len(user_ids)):
        candidate = user_ids[(start + offset) % len(user_ids)]
        if candidate not in excluded:
            return candidate
    return None


def add_derived_engagement(seed: dict, imported_posts: list[dict], interaction_distribution: dict, max_likes: int, max_retweets: int, max_bookmarks: int, max_quotes: int, max_replies: int) -> None:
    existing_retweets = {(item["user_id"], item["tweet_id"]) for item in seed.get("retweets", [])}
    existing_likes = {(item["user_id"], item["tweet_id"]) for item in seed.get("likes", [])}
    existing_bookmarks = {(item["user_id"], item["tweet_id"]) for item in seed.get("bookmarks", [])}
    existing_follows = {(item["follower_id"], item["followed_id"]) for item in seed.get("follows", [])}
    existing_tweet_ids = {tweet["id"] for tweet in seed.get("tweets", [])}
    imported_user_ids = sorted({post["user_id"] for post in imported_posts})
    engagement_actor_ids = sorted({user["id"] for user in seed.get("users", [])})

    for followed_id in imported_user_ids[:80]:
        add_edge_once(seed, "follows", existing_follows, "techvalueinvestor", followed_id)

    for index, post in enumerate(imported_posts):
        tweet_id = post["tweet_id"]
        author_id = post["user_id"]
        category = post["category"]
        add_edge_once(seed, "likes", existing_likes, "techvalueinvestor", tweet_id)
        if index % 3 == 0:
            add_edge_once(seed, "bookmarks", existing_bookmarks, "techvalueinvestor", tweet_id)

        reply_count = max(0, int(post.get("reply_count") or 0))

        like_actor_count = reply_scaled_interaction_count(tweet_id, reply_count, "like", max_likes)
        for actor_index in range(like_actor_count):
            actor_id = choose_actor(engagement_actor_ids, f"like:{tweet_id}:{actor_index}", {author_id})
            if actor_id:
                add_edge_once(seed, "likes", existing_likes, actor_id, tweet_id)

        retweet_actor_count = reply_scaled_interaction_count(tweet_id, reply_count, "retweet", max_retweets)
        for actor_index in range(retweet_actor_count):
            actor_id = choose_actor(engagement_actor_ids, f"rt:{tweet_id}:{actor_index}", {author_id})
            if actor_id:
                add_edge_once(seed, "retweets", existing_retweets, actor_id, tweet_id)

        bookmark_actor_count = reply_scaled_interaction_count(tweet_id, reply_count, "bookmark", max_bookmarks)
        for actor_index in range(bookmark_actor_count):
            actor_id = choose_actor(engagement_actor_ids, f"save:{tweet_id}:{actor_index}", {author_id})
            if actor_id:
                add_edge_once(seed, "bookmarks", existing_bookmarks, actor_id, tweet_id)

        quote_actor_count = distribution_row_count(interaction_distribution, "quote_count", post["quote_count"], max_quotes)
        for quote_index in range(quote_actor_count):
            actor_id = choose_actor(engagement_actor_ids, f"quote:{tweet_id}:{quote_index}", {author_id})
            if not actor_id:
                continue
            quote_id = f"{tweet_id}-q-{quote_index + 1:02d}"
            created_at = offset_created_at(post["created_at"], 12 * 60 + quote_index)
            add_tweet_once(seed, existing_tweet_ids, {
                "id": quote_id,
                "user_id": actor_id,
                "content": f"{category}: {QUOTE_TEXTS[(stable_int(tweet_id) + quote_index) % len(QUOTE_TEXTS)]}",
                "quote_tweet_id": tweet_id,
                "view_count": 1_200 + quote_index * 211,
                "created_at": created_at,
            })

        if post.get("has_real_replies"):
            reply_actor_count = 0
        else:
            reply_actor_count = distribution_row_count(interaction_distribution, "reply_count", post["reply_count"], max_replies)
        for reply_index in range(reply_actor_count):
            actor_id = choose_actor(engagement_actor_ids, f"reply:{tweet_id}:{reply_index}", {author_id})
            if not actor_id:
                continue
            reply_id = f"{tweet_id}-r-{reply_index + 1:02d}"
            created_at = offset_created_at(post["created_at"], 18 * 60 + reply_index)
            add_tweet_once(seed, existing_tweet_ids, {
                "id": reply_id,
                "user_id": actor_id,
                "content": f"{category}: {REPLY_TEXTS[(stable_int(tweet_id) + reply_index) % len(REPLY_TEXTS)]}",
                "reply_to_id": tweet_id,
                "view_count": 0,
                "created_at": created_at,
            })


def build_seed(args: argparse.Namespace) -> dict:
    with open(args.input, "r", encoding="utf-8") as handle:
        seed = json.load(handle)

    for key in ("users", "tweets", "follows", "likes", "bookmarks", "retweets"):
        seed.setdefault(key, [])

    if args.prune_original_seed:
        seed = prune_original_seed_for_tasks(seed, args.original_recent_per_followed_user)

    existing_tweet_ids = {tweet["id"] for tweet in seed["tweets"]}
    existing_user_ids = {user["id"] for user in seed["users"]}
    existing_usernames = {user["username"] for user in seed["users"]}
    username_profiles = load_username_profiles(args.username_pool_size, args.username_csv_url, args.username_seed)
    imported_posts = []
    bluesky_summary = {}
    if not args.skip_bluesky:
        bluesky_langs = {
            lang.strip().lower()
            for lang in args.bluesky_langs.split(",")
            if lang.strip()
        }
        cached_bluesky_rows, cache_summary = load_bluesky_tree_cache(
            args.bluesky_tree_cache_file,
            bluesky_langs,
            args.bluesky_base_limit,
        )
        if cached_bluesky_rows:
            bluesky_posts, bluesky_summary = add_cached_bluesky_tree_dataset(
                seed,
                existing_user_ids,
                existing_tweet_ids,
                existing_usernames,
                cached_bluesky_rows,
                cache_summary,
            )
        else:
            bluesky_root_uris = load_bluesky_root_uris(args.bluesky_root_uri_file)
            bluesky_posts, bluesky_summary = add_bluesky_dataset(
                seed,
                existing_user_ids,
                existing_tweet_ids,
                existing_usernames,
                args.bluesky_base_limit,
                args.bluesky_max_replies_per_base,
                args.bluesky_max_replies_per_reply,
                args.bluesky_max_reply_depth,
                bluesky_langs,
                args.bluesky_parquet_url,
                args.bluesky_cache_dir,
                args.bluesky_batch_size,
                args.bluesky_sample_seed,
                bluesky_root_uris,
            )
        imported_posts.extend(bluesky_posts)

        explore_root_rows, explore_root_cache_summary = load_bluesky_jsonl_cache(
            args.bluesky_explore_root_cache_file,
            bluesky_langs,
        )
        if explore_root_rows:
            explore_posts, explore_summary = add_explore_bluesky_roots(
                seed,
                existing_user_ids,
                existing_tweet_ids,
                existing_usernames,
                explore_root_rows,
            )
            imported_posts.extend(explore_posts)
            bluesky_summary["explore_roots"] = {
                **explore_root_cache_summary,
                **explore_summary,
            }

    retweet_rows, retweet_source = load_retweet_rows(
        args.retweet_zip_url,
        args.retweet_csv_url,
        args.retweet_limit,
        args.retweet_offset,
        args.skip_retweet,
    )
    toxic_rows, toxic_source = load_toxic_tree_metric_rows(
        args.toxic_tree_metrics_csv_url,
        args.toxic_tree_metrics_limit,
        args.toxic_tree_metrics_offset,
        args.skip_toxic_structure,
    )
    cardiff_fetch_limit = args.cardiff_fetch_limit
    if cardiff_fetch_limit <= 0:
        cardiff_fetch_limit = min(max(args.cardiff_limit * 2, args.cardiff_limit + 400, 100), 2_400)
    cardiff_rows, cardiff_source = load_cardiff_topic_rows(
        args.cardiff_split,
        cardiff_fetch_limit,
        args.cardiff_offset,
        args.skip_cardiff,
    )
    if not args.skip_cardiff and not cardiff_rows:
        raise RuntimeError("CardiffNLP import failed; set X_LITE_SKIP_CARDIFF=1 only if you intentionally want a task-only seed.")
    zenodo_rows = [] if args.skip_zenodo else load_zenodo_rows(args.zenodo_limit, args.zenodo_offset)
    mendeley_rows = load_optional_csv_rows(args.mendeley_csv_url, args.mendeley_limit, args.mendeley_offset)
    interaction_distribution = build_interaction_distribution(zenodo_rows, mendeley_rows, toxic_structure_profiles(toxic_rows))

    if retweet_rows:
        imported_posts.extend(
            add_retweet_dataset(
                seed,
                retweet_rows,
                existing_user_ids,
                existing_tweet_ids,
                existing_usernames,
                username_profiles,
                args.retweet_max_replies_per_source,
            )
        )

    if cardiff_rows:
        imported_posts.extend(
            add_cardiff_topic_dataset(
                seed,
                cardiff_rows,
                existing_user_ids,
                existing_tweet_ids,
                existing_usernames,
                username_profiles,
                args.cardiff_limit,
                args.cardiff_max_per_topic,
            )
        )

    if not args.skip_zenodo:
        zenodo_posts, _ = add_csv_twitter_dataset(
            seed,
            zenodo_rows,
            existing_user_ids,
            existing_tweet_ids,
            existing_usernames,
            username_profiles,
            "zenodo",
            "Zenodo X(Tweeter)",
        )
        imported_posts.extend(zenodo_posts)

    if not args.skip_mide22:
        mide22_rows = load_mide22_rows(args.mide22_limit, args.mide22_offset, args.include_mide22_turkish)
        imported_posts.extend(
            add_mide22_dataset(
                seed,
                mide22_rows,
                existing_user_ids,
                existing_tweet_ids,
                existing_usernames,
                username_profiles,
                interaction_distribution,
            )
        )

    # Mendeley requires auth for its documented API in this environment. Allow a
    # direct CSV export URL when one is available without baking credentials into
    # the image build.
    if mendeley_rows:
        mendeley_posts, _ = add_csv_twitter_dataset(
            seed,
            mendeley_rows,
            existing_user_ids,
            existing_tweet_ids,
            existing_usernames,
            username_profiles,
            "mendeley",
            "Mendeley COP30",
        )
        imported_posts.extend(mendeley_posts)

    add_derived_engagement(
        seed,
        imported_posts,
        interaction_distribution,
        args.max_likes_per_post,
        args.max_retweets_per_post,
        args.max_bookmarks_per_post,
        args.max_quotes_per_post,
        args.max_replies_per_post,
    )

    tagged_account_summary = replace_tagged_people(
        seed,
        existing_user_ids,
        existing_usernames,
        username_profiles,
    )

    seed["source_metadata"] = {
        "generated_by": "websites/x-lite/scripts/build_real_world_seed.py",
        "generated_at": datetime.now(UTC).isoformat(),
        "base_seed": os.path.relpath(args.input, BASE_DIR),
        "real_world_sources": [
            {
                "dataset": "Roronotalt/bluesky-ten-million",
                "license": "mit",
                "url": BLUESKY_DATASET_URL,
                "fields_used": ["type", "text", "created_at", "author", "author_did", "uri", "langs", "reply_to"],
                "rows_requested": args.bluesky_base_limit,
                "weighted_by": "ranked pinned roots by imported descendant count" if args.bluesky_root_uri_file else "direct reply count derived from reply_to",
                "root_uri_file": os.path.relpath(args.bluesky_root_uri_file, BASE_DIR) if args.bluesky_root_uri_file else "",
                "source": bluesky_summary.get("source", "parquet"),
                **bluesky_summary,
            },
            {
                "dataset": "CardiffNLP tweet_topic_multi",
                "license": "other",
                "url": CARDIFF_TOPIC_MULTI_URL,
                "fields_used": ["text", "date", "label_name", "id"],
                "split": args.cardiff_split,
                "rows_requested": args.cardiff_limit,
                "rows_loaded": len(cardiff_rows),
                "rows_imported": len([post for post in imported_posts if post["tweet_id"].startswith("rw-cardiff-t-")]),
                "source": cardiff_source,
            },
            {
                "dataset": "Zenodo 17677813: X(Tweeter)",
                "license": "cc-by-4.0",
                "url": ZENODO_DATASET_URL,
                "fields_used": [
                    "id_str",
                    "conversation_id_str",
                    "user_id_str",
                    "created_at",
                    "full_text",
                    "favorite_count",
                    "retweet_count",
                    "reply_count",
                    "quote_count",
                    "category",
                ],
                "rows_requested": args.zenodo_limit,
                "rows_imported": len([post for post in imported_posts if post["tweet_id"].startswith("rw-zenodo-t-")]),
            },
            {
                "dataset": "ReTweet: How Will Your Tweet Be Received?",
                "license": "kaggle dataset, see source",
                "url": "https://www.kaggle.com/soroosharasteh/retweet/",
                "code_url": RETWEET_REPO_URL,
                "fields_used": ["source tweet text", "reply text", "optional sentiment label"],
                "rows_requested": args.retweet_limit,
                "rows_loaded": len(retweet_rows),
                "rows_imported": len([post for post in imported_posts if post["tweet_id"].startswith("rw-retweet-t-")]),
                "source": retweet_source,
            },
            {
                "dataset": "The Structure of Toxic Conversations on Twitter",
                "license": "cc0-1.0",
                "url": TOXIC_CONVERSATIONS_DATAVERSE_URL,
                "fields_used": ["optional direct tree metrics CSV URL for reply-count distribution"],
                "rows_requested": args.toxic_tree_metrics_limit if args.toxic_tree_metrics_csv_url else 0,
                "rows_loaded": len(toxic_rows),
                "source": toxic_source,
            },
            {
                "dataset": "X-lite local generated username pool",
                "license": "generated",
                "url": "",
                "fields_used": ["adjective", "noun", "number"],
                "rows_requested": args.username_pool_size,
            },
            {
                "dataset": "MiDe22: Annotated Multi-Event Tweet Dataset",
                "license": "mit",
                "url": MIDE22_REPO_URL,
                "fields_used": ["topic", "event_id", "label", "tweet_id", "text"],
                "rows_requested": args.mide22_limit,
                "include_turkish": args.include_mide22_turkish,
                "rows_imported": len([post for post in imported_posts if post["tweet_id"].startswith("rw-mide22-t-")]),
            },
            {
                "dataset": "Mendeley t5kcr3nkfc/1: Twitter/X Dataset on Public Conversation Around COP30",
                "license": "cc-by-sa-4.0",
                "url": "https://data.mendeley.com/datasets/t5kcr3nkfc/1",
                "fields_used": ["optional direct CSV URL only"],
                "rows_requested": args.mendeley_limit if args.mendeley_csv_url else 0,
            },
        ],
        "tagged_accounts": tagged_account_summary,
        "interaction_distribution": distribution_summary(interaction_distribution),
        "notes": [
            "The canonical synthetic X-lite task seed is preserved when X_LITE_PRUNE_ORIGINAL_SEED=0; otherwise it is pruned to task-relevant tweets plus a small recent-post sample for followed accounts.",
            "Every imported source user is inserted as an X-lite user before imported posts are added.",
            "Imported user IDs are preserved internally; usernames/display names are assigned from a seeded external username source.",
            "Tagged people in imported text are normalized to @username handles and inserted as lightweight X-lite accounts.",
            "Bluesky root posts are selected from a small pinned URI file containing the previously ranked top root trees.",
            "Bluesky replies keep their original immediate parent where that parent is part of the sampled tree; full selected trees are imported by default.",
            "Root post source_reply_count is updated to the total number of imported descendant comments, and root views are sampled from that tree size.",
            "ReTweet rows, when available, provide real first-order reply text instead of generated reply templates.",
            "Likes, reposts, and saves are bounded deterministic samples from high-variance normal multipliers times root descendant reply count; generated replies are disabled unless explicitly requested.",
        ],
    }
    return seed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--prune-original-seed", action="store_true", default=os.environ.get("X_LITE_PRUNE_ORIGINAL_SEED", "1") != "0")
    parser.add_argument("--original-recent-per-followed-user", type=int, default=int(os.environ.get("X_LITE_ORIGINAL_RECENT_PER_FOLLOWED_USER", "2")), help="-1 preserves all original tweets")
    parser.add_argument("--skip-bluesky", action="store_true", default=os.environ.get("X_LITE_SKIP_BLUESKY", "0") == "1")
    parser.add_argument("--bluesky-base-limit", type=int, default=int(os.environ.get("X_LITE_BLUESKY_BASE_LIMIT", "2000")))
    parser.add_argument("--bluesky-root-uri-file", default=os.environ.get("X_LITE_BLUESKY_ROOT_URI_FILE", DEFAULT_BLUESKY_ROOT_URI_FILE))
    parser.add_argument("--bluesky-tree-cache-file", default=os.environ.get("X_LITE_BLUESKY_TREE_CACHE_FILE", DEFAULT_BLUESKY_TREE_CACHE_FILE))
    parser.add_argument("--bluesky-explore-root-cache-file", default=os.environ.get("X_LITE_BLUESKY_EXPLORE_ROOT_CACHE_FILE", DEFAULT_BLUESKY_EXPLORE_ROOT_CACHE_FILE))
    parser.add_argument("--bluesky-max-replies-per-base", type=int, default=int(os.environ.get("X_LITE_BLUESKY_MAX_REPLIES_PER_BASE", "0")), help="0 keeps every direct reply for selected roots")
    parser.add_argument("--bluesky-max-replies-per-reply", type=int, default=int(os.environ.get("X_LITE_BLUESKY_MAX_REPLIES_PER_REPLY", "0")), help="0 keeps every reply-to-reply for selected trees")
    parser.add_argument("--bluesky-max-reply-depth", type=int, default=int(os.environ.get("X_LITE_BLUESKY_MAX_REPLY_DEPTH", "0")), help="0 walks selected trees until no more descendants are found")
    parser.add_argument("--bluesky-langs", default=os.environ.get("X_LITE_BLUESKY_LANGS", "en"), help="Comma-separated lang filter; empty string keeps all languages")
    parser.add_argument("--bluesky-parquet-url", default=os.environ.get("X_LITE_BLUESKY_PARQUET_URL", BLUESKY_PARQUET_URL))
    parser.add_argument("--bluesky-cache-dir", default=os.environ.get("X_LITE_BLUESKY_CACHE_DIR", os.path.join(tempfile.gettempdir(), "x-lite-bluesky")))
    parser.add_argument("--bluesky-batch-size", type=int, default=int(os.environ.get("X_LITE_BLUESKY_BATCH_SIZE", "50000")))
    parser.add_argument("--bluesky-sample-seed", default=os.environ.get("X_LITE_BLUESKY_SAMPLE_SEED", "x-lite-bluesky-weighted-srs-v1"))
    parser.add_argument("--skip-retweet", action="store_true", default=os.environ.get("X_LITE_SKIP_RETWEET", "1") != "0")
    parser.add_argument("--retweet-zip-url", default=os.environ.get("X_LITE_RETWEET_ZIP_URL", ""), help="Optional direct ReTweet zip/archive URL. If unset, KAGGLE_USERNAME/KAGGLE_KEY are used when present.")
    parser.add_argument("--retweet-csv-url", default=os.environ.get("X_LITE_RETWEET_CSV_URL", ""), help="Optional direct ReTweet CSV URL.")
    parser.add_argument("--retweet-limit", type=int, default=int(os.environ.get("X_LITE_RETWEET_LIMIT", "0")), help="0 imports all available ReTweet rows")
    parser.add_argument("--retweet-offset", type=int, default=int(os.environ.get("X_LITE_RETWEET_OFFSET", "0")))
    parser.add_argument("--retweet-max-replies-per-source", type=int, default=int(os.environ.get("X_LITE_RETWEET_MAX_REPLIES_PER_SOURCE", "80")), help="0 keeps all replies for each imported ReTweet source tweet")
    parser.add_argument("--skip-cardiff", action="store_true", default=os.environ.get("X_LITE_SKIP_CARDIFF", "1") != "0")
    parser.add_argument("--cardiff-split", default=os.environ.get("X_LITE_CARDIFF_SPLIT", "train_random"))
    parser.add_argument("--cardiff-limit", type=int, default=int(os.environ.get("X_LITE_CARDIFF_LIMIT", "1200")), help="0 imports all fetched Cardiff rows")
    parser.add_argument("--cardiff-fetch-limit", type=int, default=int(os.environ.get("X_LITE_CARDIFF_FETCH_LIMIT", "0")), help="0 fetches a larger candidate pool automatically")
    parser.add_argument("--cardiff-offset", type=int, default=int(os.environ.get("X_LITE_CARDIFF_OFFSET", "0")))
    parser.add_argument("--cardiff-max-per-topic", type=int, default=int(os.environ.get("X_LITE_CARDIFF_MAX_PER_TOPIC", "180")), help="0 disables per-topic cap")
    parser.add_argument("--skip-toxic-structure", action="store_true", default=os.environ.get("X_LITE_SKIP_TOXIC_STRUCTURE") == "1")
    parser.add_argument("--toxic-tree-metrics-csv-url", default=os.environ.get("X_LITE_TOXIC_TREE_METRICS_CSV_URL", ""), help="Optional direct CSV URL for tree_metrics.csv from the CC0 toxic-conversation derived data.")
    parser.add_argument("--toxic-tree-metrics-limit", type=int, default=int(os.environ.get("X_LITE_TOXIC_TREE_METRICS_LIMIT", "0")), help="0 imports all optional toxic-conversation metric rows")
    parser.add_argument("--toxic-tree-metrics-offset", type=int, default=int(os.environ.get("X_LITE_TOXIC_TREE_METRICS_OFFSET", "0")))
    parser.add_argument("--skip-zenodo", action="store_true", default=os.environ.get("X_LITE_SKIP_ZENODO", "1") != "0")
    parser.add_argument("--zenodo-limit", type=int, default=int(os.environ.get("X_LITE_ZENODO_LIMIT", "300")), help="0 imports all Zenodo rows")
    parser.add_argument("--zenodo-offset", type=int, default=int(os.environ.get("X_LITE_ZENODO_OFFSET", "0")))
    parser.add_argument("--skip-mide22", action="store_true", default=os.environ.get("X_LITE_SKIP_MIDE22", "1") != "0")
    parser.add_argument("--mide22-limit", type=int, default=int(os.environ.get("X_LITE_MIDE22_LIMIT", "600")), help="0 imports all selected MiDe22 rows")
    parser.add_argument("--mide22-offset", type=int, default=int(os.environ.get("X_LITE_MIDE22_OFFSET", "0")))
    parser.add_argument("--include-mide22-turkish", action="store_true", default=os.environ.get("X_LITE_INCLUDE_MIDE22_TURKISH", "1") != "0")
    parser.add_argument("--mendeley-csv-url", default=os.environ.get("X_LITE_MENDELEY_CSV_URL", ""))
    parser.add_argument("--mendeley-limit", type=int, default=int(os.environ.get("X_LITE_MENDELEY_LIMIT", "0")), help="0 imports all optional Mendeley CSV rows")
    parser.add_argument("--mendeley-offset", type=int, default=int(os.environ.get("X_LITE_MENDELEY_OFFSET", "0")))
    parser.add_argument("--username-csv-url", default=os.environ.get("X_LITE_USERNAME_CSV_URL", ""), help="Optional direct CSV URL with username/screen_name/name columns")
    parser.add_argument("--username-pool-size", type=int, default=int(os.environ.get("X_LITE_USERNAME_POOL_SIZE", "5000")))
    parser.add_argument("--username-seed", default=os.environ.get("X_LITE_USERNAME_SEED", "x-lite-real-usernames"))
    parser.add_argument("--max-likes-per-post", type=int, default=int(os.environ.get("X_LITE_MAX_LIKES_PER_POST", "10000")))
    parser.add_argument("--max-retweets-per-post", type=int, default=int(os.environ.get("X_LITE_MAX_RETWEETS_PER_POST", "4000")))
    parser.add_argument("--max-bookmarks-per-post", type=int, default=int(os.environ.get("X_LITE_MAX_BOOKMARKS_PER_POST", "2500")))
    parser.add_argument("--max-quotes-per-post", type=int, default=int(os.environ.get("X_LITE_MAX_QUOTES_PER_POST", "0")))
    parser.add_argument("--max-replies-per-post", type=int, default=int(os.environ.get("X_LITE_MAX_REPLIES_PER_POST", "0")))
    args = parser.parse_args()

    seed = build_seed(args)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    tmp_path = f"{args.output}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(seed, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp_path, args.output)

    print(
        "Wrote {output}: {users} users, {tweets} tweets, {retweets} retweets".format(
            output=args.output,
            users=len(seed.get("users", [])),
            tweets=len(seed.get("tweets", [])),
            retweets=len(seed.get("retweets", [])),
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Failed to build real-world X-lite seed: {exc}", file=sys.stderr)
        raise

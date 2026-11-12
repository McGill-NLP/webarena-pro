import os
import sqlite3
import json
import uuid
import re
import shutil
from collections import Counter
from datetime import datetime
from functools import wraps
from flask import session
from markupsafe import Markup, escape


from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, g, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "x-lite-super-secret"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Logic for DB path
if os.path.exists("/data"):
    DB_PATH = "/data/database.db"
else:
    DB_PATH = os.path.join(BASE_DIR, "database.db")

SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")
DEFAULT_SEED_PATH = os.path.join(BASE_DIR, "data", "seed.json")
GENERATED_SEED_PATH = os.path.join(BASE_DIR, "data", "seed.generated.json")
EXPLORE_SELECTION_PATH = os.path.join(BASE_DIR, "data", "explore_root_posts.json")
PREBUILT_DB_PATH = os.path.join(BASE_DIR, "database.db")
SEED_PATH = os.environ.get(
    "X_LITE_SEED_PATH",
    GENERATED_SEED_PATH if os.path.exists(GENERATED_SEED_PATH) else DEFAULT_SEED_PATH,
)
USE_PREBUILT_DB = os.environ.get("X_LITE_USE_PREBUILT_DB", "0") == "1"

SEEDED_COMMENT_TEXTS = [
    "This has been making the rounds in my feed.",
    "The numbers explain why everyone is discussing it.",
    "Useful context, especially after watching the full clip.",
    "This lines up with what I have been hearing elsewhere.",
    "Worth revisiting now that more people have seen it.",
    "The engagement on this one makes sense.",
    "I sent this to a few people who were tracking the same topic.",
    "Strong signal from the audience on this post.",
]

HOME_TIMELINE_LIMIT = 2000
HOME_TIMELINE_PAGE_SIZE = 40
HOME_SEARCH_LIMIT = 2000
MESSAGE_LIST_PAGE_SIZE = 20
MESSAGE_HISTORY_PAGE_SIZE = 50
GENERATE_VIEW_COMMENTS = os.environ.get("X_LITE_GENERATE_VIEW_COMMENTS", "0") == "1"
MENTION_RE = re.compile(r"(?<![\w/])@([A-Za-z0-9_]{1,15})")

# ------------------------------------------------------------------------------
# DB helpers
# ------------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def prebuilt_db_ready(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False
    try:
        con = sqlite3.connect(path)
        try:
            user_count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            tweet_count = con.execute("SELECT COUNT(*) FROM tweets").fetchone()[0]
            return user_count > 0 and tweet_count > 0
        finally:
            con.close()
    except sqlite3.Error:
        return False


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db:
        db.close()

def init_db():
    if (
        DB_PATH != PREBUILT_DB_PATH
        and not os.path.exists(DB_PATH)
        and os.path.exists(PREBUILT_DB_PATH)
    ):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        shutil.copy2(PREBUILT_DB_PATH, DB_PATH)

    if USE_PREBUILT_DB and prebuilt_db_ready(DB_PATH):
        return

    db = get_db()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        db.executescript(f.read())
    ensure_schema(db)
    db.commit()

    # Seed data
    if os.path.exists(SEED_PATH):
        cnt = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if cnt == 0:
            with open(SEED_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            password_hash_cache = {}
            for u in data["users"]:
                password = u["password"]
                if password not in password_hash_cache:
                    password_hash_cache[password] = generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)
                db.execute("""
                    INSERT INTO users (id, username, password_hash, display_name, bio)
                    VALUES (?, ?, ?, ?, ?)
                """, (u["id"], u["username"], password_hash_cache[password], u["display_name"], u.get("bio", "")))

            for t in data["tweets"]:
                ensure_tagged_accounts_for_content(db, t.get("content", ""))
            
            for t in data["tweets"]:
                db.execute("""
                    INSERT INTO tweets (id, user_id, content, quote_tweet_id, reply_to_id, view_count, source_reply_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    t["id"],
                    t["user_id"],
                    t["content"],
                    t.get("quote_tweet_id"),
                    t.get("reply_to_id"),
                    t.get("view_count", seeded_tweet_view_count(t)),
                    t.get("source_reply_count", 0),
                    t.get("created_at", datetime.utcnow().isoformat()),
                ))

            for f in data["follows"]:
                db.execute("INSERT OR IGNORE INTO follows (follower_id, followed_id) VALUES (?, ?)", (f["follower_id"], f["followed_id"]))
            
            for l in data["likes"]:
                db.execute("INSERT OR IGNORE INTO likes (user_id, tweet_id) VALUES (?, ?)", (l["user_id"], l["tweet_id"]))

            for b in data.get("bookmarks", []):
                db.execute("INSERT OR IGNORE INTO bookmarks (user_id, tweet_id) VALUES (?, ?)", (b["user_id"], b["tweet_id"]))

            for r in data.get("retweets", []):
                db.execute("INSERT OR IGNORE INTO retweets (user_id, tweet_id) VALUES (?, ?)", (r["user_id"], r["tweet_id"]))
            
            if "messages" in data:
                for m in data["messages"]:
                    read_at = None if m.get("unread") else m.get("read_at", m.get("created_at"))
                    db.execute("""
                        INSERT INTO messages (id, sender_id, receiver_id, content, read_at, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        m["id"],
                        m["sender_id"],
                        m["receiver_id"],
                        m["content"],
                        read_at,
                        m.get("created_at", datetime.utcnow().isoformat()),
                    ))

            for group_chat in data.get("group_chats", []):
                db.execute("""
                    INSERT INTO group_chats (id, name, created_by, created_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    group_chat["id"],
                    group_chat["name"],
                    group_chat["created_by"],
                    group_chat.get("created_at", datetime.utcnow().isoformat()),
                ))

            for member in data.get("group_chat_members", []):
                db.execute("""
                    INSERT OR IGNORE INTO group_chat_members (chat_id, user_id, created_at)
                    VALUES (?, ?, ?)
                """, (
                    member["chat_id"],
                    member["user_id"],
                    member.get("created_at", datetime.utcnow().isoformat()),
                ))

            for message in data.get("group_messages", []):
                db.execute("""
                    INSERT INTO group_messages (id, chat_id, sender_id, content, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    message["id"],
                    message["chat_id"],
                    message["sender_id"],
                    message["content"],
                    message.get("created_at", datetime.utcnow().isoformat()),
                ))
            
            db.commit()

            if len(data.get("tweets", [])) < 50_000:
                seed_view_based_engagement(db)
            db.commit()


def display_name_from_username(username):
    parts = re.findall(r"[A-Za-z]+|\d+", username.replace("_", " "))
    if not parts:
        return username
    return " ".join(part.capitalize() if not part.isdigit() else part for part in parts)[:50]


def mention_user_id(username):
    return f"tag-{username.lower()}"


def ensure_tagged_accounts_for_content(db, content):
    for username in sorted(set(MENTION_RE.findall(content or "")), key=str.lower):
        if db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            continue
        password_hash = generate_password_hash("password123", method="pbkdf2:sha256", salt_length=16)
        db.execute(
            "INSERT OR IGNORE INTO users (id, username, password_hash, display_name, bio) VALUES (?, ?, ?, ?, ?)",
            (
                mention_user_id(username),
                username,
                password_hash,
                display_name_from_username(username),
                "Auto-created tagged account.",
            ),
        )


@app.template_filter("linkify_mentions")
def linkify_mentions(text):
    safe_text = escape(text or "")

    def replace(match):
        username = match.group(1)
        href = url_for("profile", username=username)
        return Markup(f'<a href="{href}" class="text-blue-500 hover:underline">@{escape(username)}</a>')

    return Markup(MENTION_RE.sub(replace, str(safe_text)))

def ensure_schema(db):
    user_columns = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
    if "bio" not in user_columns:
        db.execute("ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''")

    columns = {row["name"] for row in db.execute("PRAGMA table_info(tweets)").fetchall()}
    if "quote_tweet_id" not in columns:
        db.execute("ALTER TABLE tweets ADD COLUMN quote_tweet_id TEXT")
    if "reply_to_id" not in columns:
        db.execute("ALTER TABLE tweets ADD COLUMN reply_to_id TEXT")
    if "view_count" not in columns:
        db.execute("ALTER TABLE tweets ADD COLUMN view_count INTEGER NOT NULL DEFAULT 0")
    if "source_reply_count" not in columns:
        db.execute("ALTER TABLE tweets ADD COLUMN source_reply_count INTEGER NOT NULL DEFAULT 0")
    message_columns = {row["name"] for row in db.execute("PRAGMA table_info(messages)").fetchall()}
    if "read_at" not in message_columns:
        db.execute("ALTER TABLE messages ADD COLUMN read_at TIMESTAMP")
    db.execute("""
        CREATE TABLE IF NOT EXISTS retweets (
            user_id TEXT,
            tweet_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, tweet_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (tweet_id) REFERENCES tweets(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS group_chats (
            id TEXT PRIMARY KEY,
            name TEXT,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS group_chat_members (
            chat_id TEXT,
            user_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (chat_id, user_id),
            FOREIGN KEY (chat_id) REFERENCES group_chats(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS group_messages (
            id TEXT PRIMARY KEY,
            chat_id TEXT,
            sender_id TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES group_chats(id),
            FOREIGN KEY (sender_id) REFERENCES users(id)
        )
    """)
    for statement in (
        "CREATE INDEX IF NOT EXISTS idx_tweets_created_at ON tweets(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_tweets_view_count ON tweets(view_count DESC)",
        "CREATE INDEX IF NOT EXISTS idx_tweets_reply_to_id ON tweets(reply_to_id)",
        "CREATE INDEX IF NOT EXISTS idx_tweets_user_id ON tweets(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_tweets_source_reply_count ON tweets(source_reply_count DESC)",
        "CREATE INDEX IF NOT EXISTS idx_likes_tweet_id ON likes(tweet_id)",
        "CREATE INDEX IF NOT EXISTS idx_bookmarks_tweet_id ON bookmarks(tweet_id)",
        "CREATE INDEX IF NOT EXISTS idx_retweets_tweet_id ON retweets(tweet_id)",
    ):
        db.execute(statement)
    db.commit()

def stable_int(value):
    total = 0
    for char in str(value):
        total = (total * 131 + ord(char)) % 1_000_000_007
    return total

def row_value(row, key, default=None):
    if hasattr(row, "keys") and key in row.keys():
        return row[key]
    if isinstance(row, dict):
        return row.get(key, default)
    return default

def seeded_tweet_view_count(tweet):
    if row_value(tweet, "reply_to_id"):
        return 0

    tweet_id = row_value(tweet, "id", "")
    digits = re.sub(r"\D", "", tweet_id)
    ordinal = int(digits) if digits else stable_int(tweet_id) % 1000
    jitter = stable_int(row_value(tweet, "content", "")) % 2400
    band = ordinal % 10

    if band == 0:
        base = 160_000
    elif band in {1, 2}:
        base = 72_000
    elif band in {3, 4, 5}:
        base = 24_000
    else:
        base = 4_000
    return base + (ordinal * 193) % 48_000 + jitter

def target_tweet_like_count(view_count, available_user_count):
    if view_count <= 0 or available_user_count <= 0:
        return 0
    return min(available_user_count, max(1, view_count // 8_500))

def target_tweet_comment_count(view_count):
    if view_count < 20_000:
        return 0
    return min(8, max(1, view_count // 45_000))

def seed_view_based_engagement(db):
    db.execute(
        "UPDATE tweets SET content = ? WHERE id LIKE 'vc-%' AND content = ?",
        (
            "This lines up with what I have been hearing elsewhere.",
            "This matches what I have been hearing elsewhere.",
        ),
    )

    users = db.execute("SELECT id FROM users ORDER BY id").fetchall()
    user_ids = [row["id"] for row in users]
    if not user_ids:
        return

    tweets = db.execute("""
        SELECT id, user_id, content, view_count, created_at
        FROM tweets
        WHERE reply_to_id IS NULL
        ORDER BY id
    """).fetchall()

    for tweet in tweets:
        is_imported_tweet = str(tweet["id"]).startswith("rw-")
        view_count = tweet["view_count"] or seeded_tweet_view_count(tweet)
        current_likes = db.execute(
            "SELECT COUNT(*) AS c FROM likes WHERE tweet_id = ?",
            (tweet["id"],),
        ).fetchone()["c"]
        current_comments = db.execute(
            "SELECT COUNT(*) AS c FROM tweets WHERE reply_to_id = ?",
            (tweet["id"],),
        ).fetchone()["c"]
        view_count = max(
            view_count,
            current_likes * 8_500,
            current_comments * 45_000,
        )
        if tweet["view_count"] != view_count:
            db.execute("UPDATE tweets SET view_count = ? WHERE id = ?", (view_count, tweet["id"]))
        if is_imported_tweet:
            continue

        eligible_likers = [uid for uid in user_ids if uid != tweet["user_id"]]
        if not eligible_likers:
            continue

        like_target = target_tweet_like_count(view_count, len(eligible_likers))
        if is_imported_tweet:
            like_target = min(like_target, 30)
        offset = stable_int(tweet["id"]) % len(eligible_likers)
        for index in range(like_target):
            liker_id = eligible_likers[(offset + index) % len(eligible_likers)]
            db.execute(
                "INSERT OR IGNORE INTO likes (user_id, tweet_id) VALUES (?, ?)",
                (liker_id, tweet["id"]),
            )

        comment_target = target_tweet_comment_count(view_count) if GENERATE_VIEW_COMMENTS else 0
        if is_imported_tweet:
            comment_target = 0
        for index in range(comment_target):
            commenter_id = eligible_likers[(offset + like_target + index) % len(eligible_likers)]
            comment_id = f"vc-{tweet['id']}-{index + 1:02d}"
            text = SEEDED_COMMENT_TEXTS[(stable_int(tweet["id"]) + index) % len(SEEDED_COMMENT_TEXTS)]
            db.execute("""
                INSERT OR IGNORE INTO tweets
                (id, user_id, content, reply_to_id, view_count, created_at)
                VALUES (?, ?, ?, ?, 0, ?)
            """, (
                comment_id,
                commenter_id,
                text,
                tweet["id"],
                tweet["created_at"],
            ))

def fetch_tweets(db, viewer_id=None, where="", params=(), extra_join="", order_by="t.created_at DESC", limit=None, offset=0):
    where_sql = f"WHERE {where}" if where else ""
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    offset_sql = f"OFFSET {int(offset)}" if limit and offset else ""
    rows = db.execute(f"""
        SELECT t.*, u.username, u.display_name, u.bio as user_bio,
        (SELECT COUNT(*) FROM likes WHERE tweet_id = t.id AND user_id = ?) as liked,
        (SELECT COUNT(*) FROM bookmarks WHERE tweet_id = t.id AND user_id = ?) as bookmarked,
        (SELECT COUNT(*) FROM retweets WHERE tweet_id = t.id AND user_id = ?) as retweeted,
        (SELECT COUNT(*) FROM retweets WHERE tweet_id = t.id) as retweet_count,
        (SELECT COUNT(*) FROM likes WHERE tweet_id = t.id) as like_count,
        (SELECT COUNT(*) FROM tweets replies WHERE replies.reply_to_id = t.id) as direct_reply_count,
        MAX(t.source_reply_count, (SELECT COUNT(*) FROM tweets replies WHERE replies.reply_to_id = t.id)) as reply_count,
        p.id as parent_id,
        pu.username as parent_username,
        pu.display_name as parent_display_name,
        q.id as quoted_id,
        q.content as quoted_content,
        qu.username as quoted_username,
        qu.display_name as quoted_display_name
        FROM tweets t
        JOIN users u ON t.user_id = u.id
        LEFT JOIN tweets p ON t.reply_to_id = p.id
        LEFT JOIN users pu ON p.user_id = pu.id
        LEFT JOIN tweets q ON t.quote_tweet_id = q.id
        LEFT JOIN users qu ON q.user_id = qu.id
        {extra_join}
        {where_sql}
        ORDER BY {order_by}
        {limit_sql} {offset_sql}
    """, (viewer_id, viewer_id, viewer_id, *params)).fetchall()
    return rows

def fetch_tweet(db, tweet_id, viewer_id=None):
    rows = fetch_tweets(db, viewer_id, "t.id = ?", (tweet_id,), limit=1)
    return rows[0] if rows else None

def fetch_reply_thread(db, tweet, viewer_id=None):
    parents = []
    seen_ids = {tweet["id"]}
    parent_id = tweet["reply_to_id"]

    while parent_id and parent_id not in seen_ids:
        parent = fetch_tweet(db, parent_id, viewer_id)
        if not parent:
            break
        parents.append(parent)
        seen_ids.add(parent["id"])
        parent_id = parent["reply_to_id"]

    parents.reverse()
    replies = fetch_tweets(
        db,
        viewer_id,
        "t.reply_to_id = ?",
        (tweet["id"],),
        order_by="t.created_at ASC",
    )
    return parents, replies

EXPLORE_CATEGORIES = [
    {
        "id": "politics",
        "label": "Politics",
        "source_topics": {"politics", "news"},
        "terms": {
            "politics", "political", "election", "elections", "vote", "voting",
            "voters", "president", "congress", "senate", "senator", "government",
            "policy", "law", "court", "mayor", "governor", "campaign", "minister",
            "democracy", "republican", "democrat", "conservative", "liberal",
            "labour", "tory", "immigration", "trump", "biden", "harris",
        },
    },
    {
        "id": "sports",
        "label": "Sports",
        "source_topics": {"sports"},
        "terms": {
            "sport", "sports", "game", "games", "team", "teams", "match", "league",
            "season", "playoff", "coach", "score", "football", "soccer", "basketball",
            "baseball", "hockey", "tennis", "golf", "nfl", "nba", "mlb", "nhl",
            "fifa", "olympic", "player", "rookie",
        },
    },
    {
        "id": "movies",
        "label": "Movies",
        "source_topics": {"film tv & video"},
        "terms": {
            "movie", "movies", "film", "films", "cinema", "theater", "trailer",
            "premiere", "box", "office", "sequel", "director", "actor", "actress",
            "cast", "screening", "marvel", "pixar", "oscars",
        },
    },
    {
        "id": "tv",
        "label": "TV",
        "source_topics": {"film tv & video"},
        "terms": {
            "tv", "television", "show", "shows", "series", "episode", "episodes",
            "season", "streaming", "netflix", "hulu", "disney", "hbo", "prime",
            "sitcom", "reality", "finale", "documentary",
        },
    },
    {
        "id": "music",
        "label": "Music",
        "source_topics": {"music"},
        "terms": {
            "music", "song", "songs", "album", "albums", "track", "tracks", "single",
            "concert", "tour", "festival", "band", "artist", "artists", "singer",
            "rap", "hip", "hop", "pop", "rock", "playlist", "grammy", "video",
        },
    },
]

EXPLORE_CATEGORY_BY_ID = {category["id"]: category for category in EXPLORE_CATEGORIES}
EXPLORE_CATEGORY_IDS = {category["id"] for category in EXPLORE_CATEGORIES}
EXPLORE_SELECTED_CATEGORY_IDS = ("politics", "movies", "sports")
EXPLORE_TABS = [
    {"id": "for_you", "label": "For You"},
    *({"id": category_id, "label": EXPLORE_CATEGORY_BY_ID[category_id]["label"]} for category_id in EXPLORE_SELECTED_CATEGORY_IDS),
]

EXPLORE_TOPIC_TERMS = {
    "ai": ["ai", "agent", "agents", "benchmark", "benchmarks", "evaluation", "recovery", "failed", "workflow", "workflows"],
    "tech": ["tech", "ai", "agent", "benchmark", "developer", "cloud", "security", "model", "inference"],
    "ai tech": ["ai", "tech", "agent", "benchmark", "developer", "cloud", "security", "model", "inference"],
    "space": ["space", "lunar", "mars", "aurora", "solar", "planetary", "moon"],
    "local news": ["local", "city", "transit", "train", "bike", "signal", "weekend", "hearing", "city hall"],
    "entertainment": ["entertainment", "concert", "festival", "album", "movie", "film", "box office", "screening", "comedy"],
    "world": ["world", "policy", "climate", "finance", "election", "government", "minister", "diplomacy"],
    "world policy": ["world", "policy", "climate", "finance", "election", "government", "minister", "diplomacy"],
    "politics": sorted(EXPLORE_CATEGORY_BY_ID["politics"]["terms"]),
    "sports": sorted(EXPLORE_CATEGORY_BY_ID["sports"]["terms"]),
    "movies": sorted(EXPLORE_CATEGORY_BY_ID["movies"]["terms"]),
    "movie": sorted(EXPLORE_CATEGORY_BY_ID["movies"]["terms"]),
    "tv": sorted(EXPLORE_CATEGORY_BY_ID["tv"]["terms"]),
    "television": sorted(EXPLORE_CATEGORY_BY_ID["tv"]["terms"]),
    "music": sorted(EXPLORE_CATEGORY_BY_ID["music"]["terms"]),
    "film tv & video": ["film", "movie", "tv", "video", "show", "streaming"],
}

EXPLORE_TREND_STOPWORDS = {
    "about", "after", "again", "also", "amp", "and", "any", "are", "around", "because",
    "been", "being", "but", "can", "could", "day", "did", "does", "dont", "even",
    "every", "for", "from", "get", "got", "had", "has", "have", "her", "here", "him",
    "his", "how", "https", "into", "its", "just", "like", "look", "made", "make",
    "more", "much", "new", "now", "one", "only", "our", "out", "over", "people",
    "really", "see", "she", "some", "still", "than", "that", "the", "their", "them",
    "then", "there", "these", "they", "thing", "this", "those", "time", "today", "too",
    "via", "was", "way", "well", "were", "what", "when", "where", "which", "who",
    "why", "will", "with", "would", "you", "your",
}
EXPLORE_TREND_ALLOWED_TERMS = set().union(*(category["terms"] for category in EXPLORE_CATEGORIES))


def row_value(row, key, default=""):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def seeded_source_topic(row):
    bio = (row_value(row, "user_bio") or "").lower()
    match = re.search(r"main topic:\s*([^\.]+)", bio)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    return ""


def tokenize_topic_text(text):
    return re.findall(r"#?[a-z][a-z0-9_]{2,}", (text or "").lower())


def explore_category_for_tweet(row):
    source_topic = seeded_source_topic(row)
    content_terms = set(tokenize_topic_text(row_value(row, "content")))
    scores = {}

    for category in EXPLORE_CATEGORIES:
        score = 0
        if source_topic in category["source_topics"]:
            score += 6
        score += len(content_terms & category["terms"])
        if score:
            scores[category["id"]] = score

    if not scores:
        return None

    if source_topic == "film tv & video" and scores.get("movies") == scores.get("tv"):
        return "tv" if stable_int(row_value(row, "id")) % 2 else "movies"

    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]


def grouped_explore_tweets(rows):
    grouped = {category_id: [] for category_id in EXPLORE_CATEGORY_IDS}
    uncategorized = []
    for row in rows:
        category_id = explore_category_for_tweet(row)
        if category_id in grouped:
            grouped[category_id].append(row)
        else:
            uncategorized.append(row)
    return grouped, uncategorized


def format_post_count(count):
    return f"{count:,} post" if count == 1 else f"{count:,} posts"


def category_topics(grouped):
    topics = []
    for category in EXPLORE_CATEGORIES:
        count = len(grouped.get(category["id"], []))
        if not count:
            continue
        topics.append({
            "category": "Explore category",
            "name": category["label"],
            "query": category["id"],
            "count": format_post_count(count),
            "href": url_for("explore", tab=category["id"]),
        })
    return topics


def pretty_trend_name(term):
    if term.startswith("#"):
        return term
    return " ".join(piece.capitalize() for piece in term.replace("&", "and").split())


def deterministic_trending_topics(rows, limit=5, category_label="Trending", tab_id="trending"):
    source_counts = Counter()
    hashtag_counts = Counter()
    term_counts = Counter()
    for row in rows:
        source_topic = seeded_source_topic(row)
        if source_topic:
            source_counts[source_topic] += 1
        for token in tokenize_topic_text(row_value(row, "content")):
            if token.startswith("#"):
                hashtag_counts[token] += 3
            elif (
                token in EXPLORE_TREND_ALLOWED_TERMS
                and token not in EXPLORE_TREND_STOPWORDS
                and not token.isdigit()
            ):
                term_counts[token] += 1

    counts = source_counts + hashtag_counts
    if len([item for item in counts.items() if item[1] >= 3]) < limit:
        counts.update(term_counts)

    pool = [
        item for item in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:40]
        if item[1] >= 3
    ]
    picked = sorted(pool, key=lambda item: stable_int(f"x-lite-explore-trend:{item[0]}"))[:limit]
    picked = sorted(picked, key=lambda item: (-item[1], item[0]))
    return [
        {
            "category": category_label,
            "name": pretty_trend_name(term),
            "query": term,
            "count": format_post_count(count),
            "href": url_for("explore", tab=tab_id, topic=term),
        }
        for term, count in picked
    ]


def mixed_explore_rows(grouped, uncategorized, limit=60):
    ordered_ids = sorted(EXPLORE_CATEGORY_IDS, key=lambda category_id: stable_int(f"x-lite-explore-category:{category_id}"))
    indexes = {category_id: 0 for category_id in ordered_ids}
    mixed = []

    while len(mixed) < limit:
        added = False
        for category_id in ordered_ids:
            rows = grouped.get(category_id, [])
            index = indexes[category_id]
            if index < len(rows):
                mixed.append(rows[index])
                indexes[category_id] += 1
                added = True
                if len(mixed) >= limit:
                    break
        if not added:
            break

    if len(mixed) < limit:
        mixed.extend(uncategorized[:limit - len(mixed)])
    return mixed[:limit]

def fetch_explore_search(db, viewer_id, query, limit=50):
    query = (query or "").strip()
    terms = EXPLORE_TOPIC_TERMS.get(query.lower())
    if not terms:
        terms = [
            token
            for token in re.findall(r"[A-Za-z][A-Za-z0-9_]{1,}", query)
            if token.lower() not in EXPLORE_TREND_STOPWORDS
        ] or [query]
    where = " OR ".join(["t.content LIKE ?"] * len(terms))
    params = tuple(f"%{term}%" for term in terms)
    return fetch_tweets(db, viewer_id, f"t.reply_to_id IS NULL AND ({where})", params, limit=limit)


def load_explore_selection():
    if not os.path.exists(EXPLORE_SELECTION_PATH):
        return {category_id: [] for category_id in EXPLORE_SELECTED_CATEGORY_IDS}
    with open(EXPLORE_SELECTION_PATH, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return {
        category_id: [
            item["tweet_id"]
            for item in data.get(category_id, [])
            if item.get("tweet_id")
        ][:50]
        for category_id in EXPLORE_SELECTED_CATEGORY_IDS
    }


def fetch_tweets_by_ids(db, viewer_id, tweet_ids):
    if not tweet_ids:
        return []
    rows = fetch_tweets(
        db,
        viewer_id,
        f"t.id IN ({','.join(['?'] * len(tweet_ids))})",
        tuple(tweet_ids),
        limit=len(tweet_ids),
    )
    position = {tweet_id: index for index, tweet_id in enumerate(tweet_ids)}
    return sorted(rows, key=lambda row: position.get(row["id"], len(position)))

# ------------------------------------------------------------------------------
# Auth helpers
# ------------------------------------------------------------------------------
def current_user():
    if "user_id" in session:
        db = get_db()
        return db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    return None

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def fetch_home_timeline(db, user, q="", active_tab="for_you", limit=HOME_TIMELINE_PAGE_SIZE, offset=0):
    viewer_id = user["id"] if user else None
    if active_tab not in {"for_you", "following"}:
        active_tab = "for_you"

    if user:
        if q:
            return fetch_tweets(
                db,
                viewer_id,
                "t.reply_to_id IS NULL AND t.content LIKE ?",
                (f"%{q}%",),
                order_by="t.view_count DESC, t.created_at DESC",
                limit=limit,
                offset=offset,
            )
        if active_tab == "following":
            return fetch_tweets(
                db,
                viewer_id,
                "t.reply_to_id IS NULL AND (t.user_id = ? OR t.user_id IN (SELECT followed_id FROM follows WHERE follower_id = ?))",
                (user["id"], user["id"]),
                order_by="t.view_count DESC, t.created_at DESC",
                limit=limit,
                offset=offset,
            )

    return fetch_tweets(
        db,
        viewer_id,
        "t.reply_to_id IS NULL",
        order_by="t.view_count DESC, t.created_at DESC",
        limit=limit,
        offset=offset,
    )

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            next_url = request.args.get("next")
            if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                parts = next_url.strip("/").split("/")
                if len(parts) == 2 and parts[0] in {"like", "bookmark"}:
                    table = "likes" if parts[0] == "like" else "bookmarks"
                    tweet_id = parts[1]
                    if db.execute("SELECT 1 FROM tweets WHERE id = ?", (tweet_id,)).fetchone():
                        db.execute(
                            f"INSERT OR IGNORE INTO {table} (user_id, tweet_id) VALUES (?, ?)",
                            (user["id"], tweet_id),
                        )
                        db.commit()
                        return redirect(url_for("tweet_detail", tweet_id=tweet_id))
                return redirect(next_url)
            return redirect(url_for("home"))
        
        flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/")
def home():
    user = current_user()
    db = get_db()
    
    q = request.args.get("q", "").strip()
    active_tab = request.args.get("tab", "for_you")
    if active_tab not in {"for_you", "following"}:
        active_tab = "for_you"

    page_size = HOME_TIMELINE_PAGE_SIZE
    tweets = fetch_home_timeline(db, user, q, active_tab, limit=page_size + 1, offset=0)
    has_more = len(tweets) > page_size
    tweets = tweets[:page_size]

    return render_template(
        "index.html",
        user=user,
        tweets=tweets,
        q=q,
        active_tab=active_tab,
        page_size=page_size,
        next_offset=len(tweets),
        has_more=has_more,
    )


@app.route("/api/timeline")
def timeline_page():
    user = current_user()
    db = get_db()

    q = request.args.get("q", "").strip()
    active_tab = request.args.get("tab", "for_you")
    if active_tab not in {"for_you", "following"}:
        active_tab = "for_you"
    try:
        offset = max(0, int(request.args.get("offset", "0")))
    except ValueError:
        offset = 0

    page_size = HOME_TIMELINE_PAGE_SIZE
    hard_limit = HOME_SEARCH_LIMIT if q else HOME_TIMELINE_LIMIT
    if offset >= hard_limit:
        return jsonify({"html": "", "next_offset": offset, "has_more": False})

    limit = min(page_size + 1, hard_limit - offset)
    tweets = fetch_home_timeline(db, user, q, active_tab, limit=limit, offset=offset)
    has_more = len(tweets) > page_size and offset + page_size < hard_limit
    tweets = tweets[:page_size]
    html = render_template("_tweet_list.html", user=user, tweets=tweets)

    return jsonify({
        "html": html,
        "next_offset": offset + len(tweets),
        "has_more": has_more,
    })

@app.route("/explore")
def explore():
    user = current_user()
    db = get_db()
    q = (
        request.args.get("q")
        or request.args.get("query")
        or request.args.get("topic")
        or ""
    ).strip()
    active_tab = request.args.get("tab", "for_you")
    if active_tab not in {"for_you", *EXPLORE_SELECTED_CATEGORY_IDS}:
        active_tab = "for_you"
    viewer_id = user["id"] if user else None
    selection = load_explore_selection()
    topics = [
        {
            "category": "Explore category",
            "name": EXPLORE_CATEGORY_BY_ID[category_id]["label"],
            "query": category_id,
            "count": format_post_count(len(selection.get(category_id, []))),
            "href": url_for("explore", tab=category_id),
        }
        for category_id in EXPLORE_SELECTED_CATEGORY_IDS
    ]
    users = []
    tweets = []
    tab_tweets = []
    page_title = "Explore"
    page_subtitle = "Curated root posts from the sampled Bluesky data."

    if q:
        users = db.execute("""
            SELECT * FROM users
            WHERE username LIKE ? OR display_name LIKE ?
            LIMIT 20
        """, (f"%{q}%", f"%{q}%")).fetchall()
        tweets = fetch_explore_search(db, viewer_id, q, limit=80)
    elif active_tab == "for_you":
        buckets = {
            category_id: fetch_tweets_by_ids(db, viewer_id, selection.get(category_id, []))
            for category_id in EXPLORE_SELECTED_CATEGORY_IDS
        }
        for index in range(50):
            for category_id in EXPLORE_SELECTED_CATEGORY_IDS:
                rows = buckets.get(category_id, [])
                if index < len(rows):
                    tab_tweets.append(rows[index])
        page_subtitle = "Politics, movies, and sports root posts selected from the sampled data."
    else:
        tab_tweets = fetch_tweets_by_ids(db, viewer_id, selection.get(active_tab, []))
        page_title = EXPLORE_CATEGORY_BY_ID[active_tab]["label"]
        page_subtitle = f"{len(tab_tweets)} root posts selected for {page_title.lower()}."

    return render_template(
        "explore.html",
        user=user,
        q=q,
        users=users,
        tweets=tweets,
        active_tab=active_tab,
        tab_tweets=tab_tweets,
        topics=topics,
        explore_tabs=EXPLORE_TABS,
        page_title=page_title,
        page_subtitle=page_subtitle,
    )

@app.route("/notifications")
@login_required
def notifications():
    user = current_user()
    # Placeholder for notifications
    return render_template("notifications.html", user=user)

@app.route("/tweet/<tweet_id>")
def tweet_detail(tweet_id):
    user = current_user()
    db = get_db()
    tweet = fetch_tweet(db, tweet_id, user["id"] if user else None)
    if not tweet:
        return "Post not found", 404

    parent_tweets, replies = fetch_reply_thread(db, tweet, user["id"] if user else None)
    return render_template(
        "tweet_detail.html",
        user=user,
        tweet=tweet,
        parent_tweets=parent_tweets,
        replies=replies,
    )

@app.route("/tweet", methods=["POST"])
@login_required
def post_tweet():
    content = request.form.get("content", "").strip()
    quote_tweet_id = request.form.get("quote_tweet_id") or None
    reply_to_id = request.form.get("reply_to_id") or None
    if content:
        db = get_db()
        if quote_tweet_id and not db.execute("SELECT 1 FROM tweets WHERE id = ?", (quote_tweet_id,)).fetchone():
            flash("Original post not found.", "error")
            return redirect(request.referrer or url_for("home"))
        if reply_to_id and not db.execute("SELECT 1 FROM tweets WHERE id = ?", (reply_to_id,)).fetchone():
            flash("Post to reply to was not found.", "error")
            return redirect(request.referrer or url_for("home"))
        ensure_tagged_accounts_for_content(db, content)
        tweet_id = str(uuid.uuid4())
        db.execute("""
            INSERT INTO tweets (id, user_id, content, quote_tweet_id, reply_to_id, view_count, source_reply_count, created_at)
            VALUES (?, ?, ?, ?, ?, 0, 0, ?)
        """, (tweet_id, session["user_id"], content, quote_tweet_id, reply_to_id, datetime.utcnow().isoformat()))
        db.commit()
        if reply_to_id:
            return redirect(url_for("tweet_detail", tweet_id=reply_to_id))
    return redirect(url_for("home"))

@app.route("/retweet/<tweet_id>", methods=["POST"])
@login_required
def retweet(tweet_id):
    db = get_db()
    if db.execute("SELECT 1 FROM tweets WHERE id = ?", (tweet_id,)).fetchone():
        db.execute("INSERT OR IGNORE INTO retweets (user_id, tweet_id) VALUES (?, ?)", (session["user_id"], tweet_id))
        db.commit()
    return redirect(request.referrer or url_for("home"))

@app.route("/unretweet/<tweet_id>", methods=["POST"])
@login_required
def unretweet(tweet_id):
    db = get_db()
    db.execute("DELETE FROM retweets WHERE user_id = ? AND tweet_id = ?", (session["user_id"], tweet_id))
    db.commit()
    return redirect(request.referrer or url_for("home"))

@app.route("/like/<tweet_id>", methods=["POST"])
@login_required
def like(tweet_id):
    db = get_db()
    db.execute("INSERT OR IGNORE INTO likes (user_id, tweet_id) VALUES (?, ?)", (session["user_id"], tweet_id))
    db.commit()
    return redirect(request.referrer or url_for("home"))

@app.route("/unlike/<tweet_id>", methods=["POST"])
@login_required
def unlike(tweet_id):
    db = get_db()
    db.execute("DELETE FROM likes WHERE user_id = ? AND tweet_id = ?", (session["user_id"], tweet_id))
    db.commit()
    return redirect(request.referrer or url_for("home"))

@app.route("/bookmark/<tweet_id>", methods=["POST"])
@login_required
def bookmark(tweet_id):
    db = get_db()
    db.execute("INSERT OR IGNORE INTO bookmarks (user_id, tweet_id) VALUES (?, ?)", (session["user_id"], tweet_id))
    db.commit()
    return redirect(request.referrer or url_for("home"))

@app.route("/unbookmark/<tweet_id>", methods=["POST"])
@login_required
def unbookmark(tweet_id):
    db = get_db()
    db.execute("DELETE FROM bookmarks WHERE user_id = ? AND tweet_id = ?", (session["user_id"], tweet_id))
    db.commit()
    return redirect(request.referrer or url_for("home"))

@app.route("/bookmarks")
@login_required
def bookmarks_page():
    user = current_user()
    db = get_db()
    
    tweets = fetch_tweets(
        db,
        user["id"],
        "b.user_id = ?",
        (user["id"],),
        extra_join="JOIN bookmarks b ON t.id = b.tweet_id",
        order_by="b.created_at DESC",
    )
    
    return render_template("bookmarks.html", user=user, tweets=tweets)

@app.context_processor
def sidebar_people():
    user = current_user()
    if not user:
        return {"sidebar_people": []}
    people = get_db().execute("""
        SELECT id, username, display_name FROM users
        WHERE id != ? AND id NOT IN (
            SELECT followed_id FROM follows WHERE follower_id = ?
        )
        ORDER BY username
        LIMIT 3
    """, (user["id"], user["id"])).fetchall()
    return {"sidebar_people": people}


@app.route("/follow/<user_id>", methods=["POST"])
@login_required
def follow(user_id):
    if user_id != session["user_id"]:
        db = get_db()
        db.execute("INSERT OR IGNORE INTO follows (follower_id, followed_id) VALUES (?, ?)", (session["user_id"], user_id))
        db.commit()
    return redirect(request.referrer or url_for("home"))

@app.route("/unfollow/<user_id>", methods=["POST"])
@login_required
def unfollow(user_id):
    db = get_db()
    db.execute("DELETE FROM follows WHERE follower_id = ? AND followed_id = ?", (session["user_id"], user_id))
    db.commit()
    return redirect(request.referrer or url_for("home"))

@app.route("/user/<username>")
def profile(username):
    db = get_db()
    profile_user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not profile_user:
        return "User not found", 404

    active_tab = request.args.get("tab", "posts")
    if active_tab not in {"posts", "replies", "media"}:
        active_tab = "posts"
    
    user = current_user()
    is_following = False
    if user:
        is_following = db.execute("SELECT 1 FROM follows WHERE follower_id = ? AND followed_id = ?", (user["id"], profile_user["id"])).fetchone() is not None
    
    following_count = db.execute("SELECT COUNT(*) as c FROM follows WHERE follower_id = ?", (profile_user["id"],)).fetchone()["c"]
    follower_count = db.execute("SELECT COUNT(*) as c FROM follows WHERE followed_id = ?", (profile_user["id"],)).fetchone()["c"]

    post_count = db.execute(
        "SELECT COUNT(*) AS c FROM tweets WHERE user_id = ?",
        (profile_user["id"],),
    ).fetchone()["c"]

    # X-lite does not model media attachments yet. Keep the tab functional and
    # explicit instead of presenting non-interactive UI or guessing from text.
    if active_tab == "media":
        tweets = []
    else:
        reply_filter = "IS NOT NULL" if active_tab == "replies" else "IS NULL"
        tweets = fetch_tweets(
            db,
            user["id"] if user else None,
            f"t.user_id = ? AND t.reply_to_id {reply_filter}",
            (profile_user["id"],),
            limit=50,
        )
    
    return render_template(
        "profile.html",
        user=user,
        profile_user=profile_user,
        tweets=tweets,
        active_tab=active_tab,
        post_count=post_count,
        is_following=is_following,
        following_count=following_count,
        follower_count=follower_count,
    )

@app.route("/follows")
@login_required
def follows_page():
    user = current_user()
    db = get_db()
    
    following = db.execute("""
        SELECT u.* FROM users u
        JOIN follows f ON u.id = f.followed_id
        WHERE f.follower_id = ?
    """, (user["id"],)).fetchall()
    
    followers = db.execute("""
        SELECT u.* FROM users u
        JOIN follows f ON u.id = f.follower_id
        WHERE f.followed_id = ?
    """, (user["id"],)).fetchall()
    
    suggested = db.execute("""
        SELECT * FROM users 
        WHERE id != ? AND id NOT IN (SELECT followed_id FROM follows WHERE follower_id = ?)
        LIMIT 10
    """, (user["id"], user["id"])).fetchall()
    
    return render_template("follows.html", user=user, following=following, followers=followers, suggested=suggested)

def message_page(query, parameters, page_key, *, page=None, page_size=MESSAGE_LIST_PAGE_SIZE, endpoint=None):
    """Fetch one bounded window, with one extra row to discover the next page."""
    if page is None:
        page = request.args.get(page_key, 1, type=int)
    page = max(1, min(page, 2**31))
    rows = get_db().execute(
        query + " LIMIT ? OFFSET ?",
        (*parameters, page_size + 1, (page - 1) * page_size),
    ).fetchall()
    args = {key: request.args[key] for key in ("q", "conversation_page", "user_page", "group_page")
            if key in request.args}
    args.update(request.view_args)
    navigation = {"page": page, "has_next": len(rows) > page_size}
    for direction, target in (("previous", page - 1), ("next", page + 1)):
        enabled = target > 0 and (direction == "previous" or navigation["has_next"])
        navigation[direction] = url_for(endpoint or request.endpoint, **{**args, page_key: target}) if enabled else None
    return rows[:page_size], navigation


@app.route("/chat")
@app.route("/messages")
@login_required
def chat():
    return render_chat()


def render_chat(selected_members=(), member_page=1):
    user = current_user()
    search = request.args.get("q", "").strip()
    user_search = search.removeprefix("@")
    member_search = request.form.get("member_q", "").strip()
    member_name_search = member_search.removeprefix("@")

    # Get conversation users first, then other users so a new DM can be opened.
    conversations, conversation_navigation = message_page("""
        SELECT DISTINCT u.*,
        (SELECT MAX(created_at) FROM messages
         WHERE (sender_id = ? AND receiver_id = u.id) OR (sender_id = u.id AND receiver_id = ?)) as last_message_at,
        (SELECT content FROM messages
         WHERE (sender_id = ? AND receiver_id = u.id) OR (sender_id = u.id AND receiver_id = ?)
         ORDER BY created_at DESC, id DESC
         LIMIT 1) as last_message,
        (SELECT COUNT(*) FROM messages
         WHERE sender_id = u.id AND receiver_id = ? AND read_at IS NULL) as unread_count
        FROM users u
        WHERE u.id IN (
            SELECT receiver_id FROM messages WHERE sender_id = ?
            UNION
            SELECT sender_id FROM messages WHERE receiver_id = ?
        )
        AND (instr(lower(u.username), lower(?)) > 0 OR instr(lower(u.display_name), lower(?)) > 0
             OR EXISTS (SELECT 1 FROM messages m
                        WHERE ((m.sender_id = ? AND m.receiver_id = u.id)
                            OR (m.sender_id = u.id AND m.receiver_id = ?))
                          AND instr(lower(m.content), lower(?)) > 0))
        ORDER BY last_message_at DESC, u.id ASC
    """, (user["id"],) * 7 + (user_search, user_search, user["id"], user["id"], search), "conversation_page", endpoint="chat")

    startable_users, user_navigation = message_page("""
        SELECT * FROM users
        WHERE id != ? AND id NOT IN (
            SELECT receiver_id FROM messages WHERE sender_id = ?
            UNION
            SELECT sender_id FROM messages WHERE receiver_id = ?
        )
        AND (instr(lower(username), lower(?)) > 0 OR instr(lower(display_name), lower(?)) > 0)
        ORDER BY username ASC, id ASC
    """, (user["id"], user["id"], user["id"], user_search, user_search), "user_page", endpoint="chat")

    group_chats, group_navigation = message_page("""
        SELECT gc.*,
        (SELECT COUNT(*) FROM group_chat_members WHERE chat_id = gc.id) as member_count,
        (SELECT MAX(created_at) FROM group_messages WHERE chat_id = gc.id) as last_message_at
        FROM group_chats gc
        JOIN group_chat_members gcm ON gcm.chat_id = gc.id
        WHERE gcm.user_id = ?
        AND (instr(lower(gc.name), lower(?)) > 0
             OR EXISTS (SELECT 1 FROM group_messages gm WHERE gm.chat_id = gc.id
                        AND instr(lower(gm.content), lower(?)) > 0))
        ORDER BY COALESCE(last_message_at, gc.created_at) DESC, gc.id ASC
    """, (user["id"], search, search), "group_page", endpoint="chat")

    group_startable_users, member_navigation = message_page("""
        SELECT * FROM users
        WHERE id != ?
        AND (instr(lower(username), lower(?)) > 0 OR instr(lower(display_name), lower(?)) > 0)
        ORDER BY display_name ASC, username ASC, id ASC
    """, (user["id"], member_name_search, member_name_search), "member_page", page=member_page, endpoint="chat")
    
    return render_template(
        "chat.html",
        user=user,
        conversations=conversations,
        startable_users=startable_users,
        group_chats=group_chats,
        group_startable_users=group_startable_users,
        search=search,
        member_search=member_search,
        selected_members=selected_members,
        selected_member_ids={member["id"] for member in selected_members},
        conversation_navigation=conversation_navigation,
        user_navigation=user_navigation,
        group_navigation=group_navigation,
        member_navigation=member_navigation,
    )

@app.route("/messages/group", methods=["POST"])
@login_required
def create_group_chat():
    current_u = current_user()
    db = get_db()

    name = request.form.get("name", "").strip() or "Private coordination chat"
    initial_message = request.form.get("content", "").strip()
    member_ids = [m for m in request.form.getlist("member_ids") if m != current_u["id"]]
    valid_members = db.execute(
        f"SELECT id, username, display_name FROM users WHERE id IN ({','.join(['?'] * len(member_ids))}) ORDER BY display_name, username, id",
        tuple(member_ids),
    ).fetchall() if member_ids else []
    valid_member_ids = [row["id"] for row in valid_members]

    picker_action = request.form.get("picker_action")
    if picker_action in {"search", "previous", "next"}:
        page = request.form.get("member_page", 1, type=int)
        page = 1 if picker_action == "search" else page + (1 if picker_action == "next" else -1)
        return render_chat(selected_members=valid_members, member_page=page)

    chat_id = str(uuid.uuid4())
    db.execute("""
        INSERT INTO group_chats (id, name, created_by, created_at)
        VALUES (?, ?, ?, ?)
    """, (chat_id, name, current_u["id"], datetime.utcnow().isoformat()))
    db.execute(
        "INSERT OR IGNORE INTO group_chat_members (chat_id, user_id) VALUES (?, ?)",
        (chat_id, current_u["id"]),
    )
    for member_id in valid_member_ids:
        db.execute(
            "INSERT OR IGNORE INTO group_chat_members (chat_id, user_id) VALUES (?, ?)",
            (chat_id, member_id),
        )
    if initial_message:
        db.execute("""
            INSERT INTO group_messages (id, chat_id, sender_id, content, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (str(uuid.uuid4()), chat_id, current_u["id"], initial_message, datetime.utcnow().isoformat()))
    db.commit()
    return redirect(url_for("group_chat_detail", chat_id=chat_id))

@app.route("/messages/group/<chat_id>", methods=["GET", "POST"])
@login_required
def group_chat_detail(chat_id):
    current_u = current_user()
    db = get_db()

    chat = db.execute("""
        SELECT gc.*
        FROM group_chats gc
        JOIN group_chat_members gcm ON gcm.chat_id = gc.id
        WHERE gc.id = ? AND gcm.user_id = ?
    """, (chat_id, current_u["id"])).fetchone()
    if not chat:
        return "Group chat not found", 404

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        if content:
            db.execute("""
                INSERT INTO group_messages (id, chat_id, sender_id, content, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), chat_id, current_u["id"], content, datetime.utcnow().isoformat()))
            db.commit()
        return redirect(url_for("group_chat_detail", chat_id=chat_id))

    members = db.execute("""
        SELECT u.*
        FROM users u
        JOIN group_chat_members gcm ON gcm.user_id = u.id
        WHERE gcm.chat_id = ?
        ORDER BY u.display_name ASC
    """, (chat_id,)).fetchall()
    message_search = request.args.get("q", "").strip()
    messages, message_navigation = message_page("""
        SELECT gm.*, u.display_name, u.username
        FROM group_messages gm
        JOIN users u ON u.id = gm.sender_id
        WHERE gm.chat_id = ?
        AND instr(lower(gm.content), lower(?)) > 0
        ORDER BY gm.created_at DESC, gm.id DESC
    """, (chat_id, message_search), "page", page_size=MESSAGE_HISTORY_PAGE_SIZE)

    return render_template(
        "group_chat_detail.html",
        user=current_u,
        chat=chat,
        members=members,
        messages=list(reversed(messages)),
        message_search=message_search,
        message_navigation=message_navigation,
    )

@app.route("/chat/<user_id>", methods=["GET", "POST"])
@app.route("/messages/<user_id>", methods=["GET", "POST"])
@login_required
def chat_detail(user_id):
    current_u = current_user()
    db = get_db()
    
    other_user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not other_user:
        return "User not found", 404
        
    if request.method == "POST":
        content = request.form.get("content", "").strip()
        if content:
            msg_id = str(uuid.uuid4())
            db.execute("""
                INSERT INTO messages (id, sender_id, receiver_id, content, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (msg_id, current_u["id"], user_id, content, datetime.utcnow().isoformat()))
            db.commit()
        return redirect(url_for("chat_detail", user_id=user_id))
    
    message_search = request.args.get("q", "").strip()
    messages, message_navigation = message_page("""
        SELECT * FROM messages
        WHERE ((sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?))
        AND instr(lower(content), lower(?)) > 0
        ORDER BY created_at DESC, id DESC
    """, (current_u["id"], user_id, user_id, current_u["id"], message_search), "page", page_size=MESSAGE_HISTORY_PAGE_SIZE)
    db.execute("""
        UPDATE messages
        SET read_at = ?
        WHERE sender_id = ? AND receiver_id = ? AND read_at IS NULL
    """, (datetime.utcnow().isoformat(), user_id, current_u["id"]))
    db.commit()
    
    return render_template(
        "chat_detail.html", user=current_u, other_user=other_user,
        messages=list(reversed(messages)), message_search=message_search,
        message_navigation=message_navigation,
    )

@app.route("/reset")
def reset():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    return "Database reset", 200

@app.route("/status")
def status():
    return {"status": "ok"}, 200

@app.route("/me")
def me():
    return {"user": session.get("user_id"), "username": session.get("username")}, 200


# ------------------------------------------------------------------------------
# Read-only evaluation API
# ------------------------------------------------------------------------------
# Exposes backend state as JSON so the WebArena-Pro evaluator can grade tasks
# deterministically (instead of relying on an LLM judge). It is strictly
# read-only and gated by a secret token (WP_EVAL_TOKEN): the agent under test
# never sees the token, so it cannot use this endpoint to read answers. When
# WP_EVAL_TOKEN is unset the endpoint is disabled (403). Sensitive columns
# (e.g. password hashes) are never returned.

EVAL_STATE_QUERIES = {
    "users": "SELECT id, username, display_name, bio FROM users",
    "tweets": "SELECT id, user_id, content, quote_tweet_id, reply_to_id, created_at FROM tweets",
    "follows": "SELECT follower_id, followed_id FROM follows",
    "likes": "SELECT user_id, tweet_id FROM likes",
    "bookmarks": "SELECT user_id, tweet_id FROM bookmarks",
    "retweets": "SELECT user_id, tweet_id FROM retweets",
    "messages": "SELECT id, sender_id, receiver_id, content, created_at FROM messages",
    "group_chats": "SELECT id, name, created_by, created_at FROM group_chats",
    "group_chat_members": "SELECT chat_id, user_id FROM group_chat_members",
    "group_messages": "SELECT id, chat_id, sender_id, content, created_at FROM group_messages",
}


def _eval_authorized():
    token = os.environ.get("WP_EVAL_TOKEN")
    return bool(token) and request.headers.get("X-Eval-Token") == token


@app.route("/api/eval/state")
def eval_state():
    """Return relevant backend tables as JSON (read-only, token-gated)."""
    if not _eval_authorized():
        return jsonify({"error": "forbidden"}), 403
    db = get_db()
    out = {}
    table = request.args.get("table")
    queries = (
        {table: EVAL_STATE_QUERIES[table]}
        if table in EVAL_STATE_QUERIES
        else EVAL_STATE_QUERIES
    )
    for name, query in queries.items():
        try:
            out[name] = [dict(row) for row in db.execute(query).fetchall()]
        except sqlite3.Error:
            out[name] = []  # table may not exist in every seed
    return jsonify(out)


if __name__ == "__main__":
    with app.app_context():
        init_db()
    port = int(os.environ.get("PORT", "7860"))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

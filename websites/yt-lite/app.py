import os
import sqlite3
import json
import re
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, g, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "yt-lite-super-secret"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
FINEVIDEO_DATA_PATH = os.path.join(BASE_DIR, "data", "finevideo_local_seed.json")
VIDEO_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "videos")
THUMBNAIL_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "thumbnails")
VIDEO_EXTENSIONS = {"mp4"}
THUMBNAIL_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
SEEDED_USERS = (
    ("demo", "demo"),
    ("seed_user", "password"),
)


def insert_video_seed(db, v, replace=False):
    thumbnail = v.get("thumbnail")
    verb = "INSERT OR REPLACE" if replace else "INSERT"
    db.execute(f"""
        {verb} INTO videos
        (id, title, channel, views, duration, category,
         video_path, thumbnail, description, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        v["id"],
        v["title"],
        v.get("channel", "Channel"),
        v.get("views", "0 views"),
        v.get("duration", "0:00"),
        v.get("category", "Other"),
        v.get("video_path"),
        thumbnail,
        v.get("description", ""),
        v.get("created_at", datetime.utcnow().isoformat())
    ))

# ------------------------------------------------------------------------------
# DB helpers
# ------------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db:
        db.close()


# ------------------------------------------------------------------------------
# Auth helpers
# ------------------------------------------------------------------------------
def current_user():
    return session.get("username", "guest")

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if current_user() == "guest":
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper



# ------------------------------------------------------------------------------
# Init DB + seed
# ------------------------------------------------------------------------------
def init_db():
    db = get_db()

    # videos: local MP4 files only
    db.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY,
            title TEXT,
            channel TEXT,
            views TEXT,
            duration TEXT,
            category TEXT,
            video_path TEXT,
            thumbnail TEXT,
            description TEXT,
            created_at TEXT
        )
    """)

    video_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(videos)").fetchall()
    }
    if "video_path" not in video_columns:
        db.execute("ALTER TABLE videos ADD COLUMN video_path TEXT")

    # likes / dislikes
    db.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            video_id TEXT,
            username TEXT,
            value INTEGER,
            PRIMARY KEY (video_id, username)
        )
    """)

    # comments
    db.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT,
            username TEXT,
            text TEXT,
            created_at TEXT
        )
    """)

    # watch later
    db.execute("""
        CREATE TABLE IF NOT EXISTS watch_later (
            username TEXT,
            video_id TEXT,
            PRIMARY KEY (username, video_id)
        )
    """)

    # history
    db.execute("""
        CREATE TABLE IF NOT EXISTS history (
            username TEXT,
            video_id TEXT,
            watched_at TEXT,
            PRIMARY KEY (username, video_id)
        )
    """)

    # playlists
    db.execute("""
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            name TEXT,
            created_at TEXT
        )
    """)

    # playlist videos
    db.execute("""
        CREATE TABLE IF NOT EXISTS playlist_videos (
            playlist_id INTEGER,
            video_id TEXT,
            PRIMARY KEY (playlist_id, video_id)
        )
    """)

    db.commit()

    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT,
            created_at TEXT
        )
    """)
    db.commit()

    for username, password in SEEDED_USERS:
        db.execute("""
            INSERT OR IGNORE INTO users (username, password_hash, created_at)
            VALUES (?,?,?)
        """, (
            username,
            generate_password_hash(password),
            datetime.utcnow().isoformat()
        ))
    db.commit()

    db.execute("""
        DELETE FROM videos
        WHERE video_path IS NULL OR video_path = ''
    """)
    db.commit()

    # local FineVideo seed entries can be refreshed independently
    if os.path.exists(FINEVIDEO_DATA_PATH):
        with open(FINEVIDEO_DATA_PATH, "r", encoding="utf-8") as f:
            videos = json.load(f)
        for v in videos:
            insert_video_seed(db, v, replace=True)
        db.commit()



# ------------------------------------------------------------------------------
# Utils
# ------------------------------------------------------------------------------
def allowed_file(filename: str, extensions: set[str]) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in extensions


def static_asset_url(path: str | None) -> str:
    if not path:
        return ""
    if path.startswith(("http://", "https://", "/")):
        return path
    return url_for("static", filename=path)


app.jinja_env.filters["static_asset_url"] = static_asset_url


def parse_view_count(view_text: str | None) -> int:
    if not view_text:
        return 0

    match = re.match(
        r"^\s*(\d[\d,]*(?:\.\d+)?)\s*([KMB]?)\s*(?:views?)?\s*$",
        str(view_text),
        re.IGNORECASE,
    )
    if not match:
        return 0

    value = float(match.group(1).replace(",", ""))
    suffix = match.group(2).upper()
    multipliers = {
        "": 1,
        "K": 1_000,
        "M": 1_000_000,
        "B": 1_000_000_000,
    }
    return int(value * multipliers.get(suffix, 1))


def sort_videos_by_view_count(videos):
    return sorted(videos, key=lambda row: parse_view_count(row["views"]), reverse=True)


def get_like_counts(db, video_id):
    cur = db.execute("""
        SELECT value, COUNT(*) AS c
        FROM likes
        WHERE video_id = ?
        GROUP BY value
    """, (video_id,))
    likes = 0
    dislikes = 0
    for row in cur.fetchall():
        if row["value"] == 1:
            likes = row["c"]
        elif row["value"] == -1:
            dislikes = row["c"]
    return likes, dislikes


# ------------------------------------------------------------------------------
# Auth routes
# ------------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if not user:
            flash("User not registered. Please register first.", "error")
            return redirect(url_for("login"))

        
        if not check_password_hash(user["password_hash"], password):
            flash("Incorrect password.", "error")
            return redirect(url_for("login"))

       
        session.clear()
        session["username"] = username

        next_page = request.args.get("next")
        return redirect(next_page or url_for("home"))

    return render_template("login.html")



@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("home"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password required.", "warning")
            return redirect(url_for("register"))

        db = get_db()
        exists = db.execute(
            "SELECT username FROM users WHERE username = ?", (username,)
        ).fetchone()
        if exists:
            flash("User already exists.", "warning")
            return redirect(url_for("register"))

        db.execute("""
            INSERT INTO users (username, password_hash, created_at)
            VALUES (?,?,?)
        """, (username, generate_password_hash(password),
              datetime.utcnow().isoformat()))
        db.commit()
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# ------------------------------------------------------------------------------
# Home / search / explore
# ------------------------------------------------------------------------------
@app.route("/")
def home():
    db = get_db()

    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    duration = request.args.get("duration", "").strip()
    upload = request.args.get("upload", "").strip()
    sort = request.args.get("sort", "").strip()

    sql = "SELECT * FROM videos WHERE 1=1"
    params = []

    # search
    if q:
        sql += " AND (title LIKE ? OR description LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])

    # category
    if category:
        sql += " AND category = ?"
        params.append(category)

    # Stored durations are m:ss strings; compare their numeric length.
    duration_seconds = (
        "(CAST(substr(duration, 1, instr(duration, ':') - 1) AS INTEGER) * 60"
        " + CAST(substr(duration, instr(duration, ':') + 1) AS INTEGER))"
    )
    if duration == "short":
        sql += f" AND {duration_seconds} < 240"
    elif duration == "medium":
        sql += f" AND {duration_seconds} BETWEEN 240 AND 1200"
    elif duration == "long":
        sql += f" AND {duration_seconds} > 1200"

    # upload time filter
    if upload == "today":
        sql += " AND created_at >= datetime('now','-1 day')"
    elif upload == "week":
        sql += " AND created_at >= datetime('now','-7 day')"
    elif upload == "month":
        sql += " AND created_at >= datetime('now','-30 day')"

    # sort
    if sort != "views":
        sql += " ORDER BY created_at DESC"

    videos = db.execute(sql, params).fetchall()
    if sort == "views":
        videos = sort_videos_by_view_count(videos)

    return render_template(
        "index.html",
        videos=videos,
        q=q,
        category=category,
        duration=duration,
        upload=upload,
        sort=sort
    )



@app.route("/explore/<category>")
def explore(category):
    db = get_db()
    videos = db.execute("""
        SELECT * FROM videos
        WHERE category = ?
        ORDER BY created_at DESC
    """, (category,)).fetchall()
    return render_template("explore.html", videos=videos, category=category)


# ------------------------------------------------------------------------------
# Watch / comments / likes
# ------------------------------------------------------------------------------
@app.route("/watch/<video_id>", methods=["GET", "POST"])
def watch(video_id):
    db = get_db()
    video = db.execute(
        "SELECT * FROM videos WHERE id = ?", (video_id,)
    ).fetchone()
    if not video:
        return "Video not found", 404

    username = current_user()

    db.execute("""
        INSERT OR REPLACE INTO history (username, video_id, watched_at)
        VALUES (?,?,?)
    """, (username, video_id, datetime.utcnow().isoformat()))
    db.commit()

 
    if request.method == "POST":
        text = request.form.get("comment", "").strip()
        if text:
            db.execute("""
                INSERT INTO comments (video_id, username, text, created_at)
                VALUES (?,?,?,?)
            """, (video_id, username, text, datetime.utcnow().isoformat()))
            db.commit()
        return redirect(url_for("watch", video_id=video_id))

    comments = db.execute("""
        SELECT * FROM comments
        WHERE video_id = ?
        ORDER BY created_at DESC
    """, (video_id,)).fetchall()

    likes, dislikes = get_like_counts(db, video_id)

    upnext = db.execute("""
        SELECT * FROM videos
        WHERE id != ?
        ORDER BY created_at DESC
        LIMIT 10
    """, (video_id,)).fetchall()

    return render_template(
        "watch.html",
        video=video,
        comments=comments,
        likes=likes,
        dislikes=dislikes,
        upnext=upnext
    )


@app.route("/like/<video_id>")
@login_required
def like(video_id):
    db = get_db()
    username = current_user()
    db.execute("""
        INSERT OR REPLACE INTO likes (video_id, username, value)
        VALUES (?,?,1)
    """, (video_id, username))
    db.commit()
    return redirect(url_for("watch", video_id=video_id))


@app.route("/dislike/<video_id>")
@login_required
def dislike(video_id):
    db = get_db()
    username = current_user()
    db.execute("""
        INSERT OR REPLACE INTO likes (video_id, username, value)
        VALUES (?,?, -1)
    """, (video_id, username))
    db.commit()
    return redirect(url_for("watch", video_id=video_id))


# ------------------------------------------------------------------------------
# Watch later / history
# ------------------------------------------------------------------------------
@app.route("/watch-later/add/<video_id>")
@login_required
def watch_later_add(video_id):
    db = get_db()
    username = current_user()
    db.execute("""
        INSERT OR IGNORE INTO watch_later (username, video_id)
        VALUES (?,?)
    """, (username, video_id))
    db.commit()
    return redirect(request.referrer or url_for("home"))


@app.route("/watch-later/remove/<video_id>")
@login_required
def watch_later_remove(video_id):
    db = get_db()
    username = current_user()
    db.execute("""
        DELETE FROM watch_later
        WHERE username = ? AND video_id = ?
    """, (username, video_id))
    db.commit()
    return redirect(url_for("watch_later"))


@app.route("/library/watch-later")
@login_required
def watch_later():
    db = get_db()
    username = current_user()
    videos = db.execute("""
        SELECT v.* FROM videos v
        JOIN watch_later w ON v.id = w.video_id
        WHERE w.username = ?
        ORDER BY v.created_at DESC
    """, (username,)).fetchall()
    return render_template("watch_later.html", videos=videos)


@app.route("/library/history")
@login_required
def history():
    db = get_db()
    username = current_user()
    videos = db.execute("""
        SELECT v.*, h.watched_at
        FROM videos v
        JOIN history h ON v.id = h.video_id
        WHERE h.username = ?
        ORDER BY h.watched_at DESC
        LIMIT 50
    """, (username,)).fetchall()
    return render_template("history.html", videos=videos)


@app.route("/library/history/remove/<video_id>")
@login_required
def history_remove(video_id):
    db = get_db()
    username = current_user()
    db.execute("""
        DELETE FROM history
        WHERE username = ? AND video_id = ?
    """, (username, video_id))
    db.commit()
    return redirect(url_for("history"))


# ------------------------------------------------------------------------------
# Playlists
# ------------------------------------------------------------------------------
@app.route("/playlists", methods=["GET", "POST"])
@login_required
def playlists():
    db = get_db()
    username = current_user()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            db.execute("""
                INSERT INTO playlists (username, name, created_at)
                VALUES (?,?,?)
            """, (username, name, datetime.utcnow().isoformat()))
            db.commit()
        return redirect(url_for("playlists"))

    pls = db.execute("""
        SELECT * FROM playlists
        WHERE username = ?
        ORDER BY created_at DESC
    """, (username,)).fetchall()
    return render_template("playlist.html", playlists=pls)


@app.route("/playlists/<int:pid>")
@login_required
def playlist_detail(pid):
    db = get_db()
    username = current_user()

    playlist = db.execute("""
        SELECT * FROM playlists
        WHERE id = ? AND username = ?
    """, (pid, username)).fetchone()
    if not playlist:
        return "Playlist not found", 404

    videos = db.execute("""
        SELECT v.*
        FROM playlist_videos pv
        JOIN videos v ON v.id = pv.video_id
        WHERE pv.playlist_id = ?
    """, (pid,)).fetchall()

    all_videos = db.execute("""
        SELECT * FROM videos
        WHERE id NOT IN (
            SELECT video_id FROM playlist_videos
            WHERE playlist_id = ?
        )
        ORDER BY created_at DESC
        LIMIT 60
    """, (pid,)).fetchall()

    return render_template(
        "playlist_dedail.html",
        playlist=playlist,
        videos=videos,
        all_videos=all_videos
    )


@app.route("/playlists/<int:pid>/add/<video_id>")
@login_required
def playlist_add(pid, video_id):
    db = get_db()
    username = current_user()

    pl = db.execute("""
        SELECT * FROM playlists
        WHERE id = ? AND username = ?
    """, (pid, username)).fetchone()
    if not pl:
        return "Playlist not found", 404

    video = db.execute("""
        SELECT id FROM videos
        WHERE id = ?
    """, (video_id,)).fetchone()
    if not video:
        return "Video not found", 404

    db.execute("""
        INSERT OR IGNORE INTO playlist_videos (playlist_id, video_id)
        VALUES (?,?)
    """, (pid, video_id))
    db.commit()
    return redirect(url_for("playlist_detail", pid=pid))


@app.route("/playlists/<int:pid>/remove/<video_id>")
@login_required
def playlist_remove(pid, video_id):
    db = get_db()
    username = current_user()

    pl = db.execute("""
        SELECT id FROM playlists
        WHERE id = ? AND username = ?
    """, (pid, username)).fetchone()
    if not pl:
        return "Playlist not found", 404

    db.execute("""
        DELETE FROM playlist_videos
        WHERE playlist_id = ? AND video_id = ?
    """, (pid, video_id))
    db.commit()
    return redirect(url_for("playlist_detail", pid=pid))


# ------------------------------------------------------------------------------
# Upload (local MP4)
# ------------------------------------------------------------------------------
@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "Other").strip()
        description = request.form.get("description", "").strip()
        channel = current_user() or "Channel"
        video_file = request.files.get("video_file")
        thumbnail_file = request.files.get("thumbnail_file")

        thumb = None

        if not video_file or not video_file.filename:
            flash("Upload a local MP4 file.", "danger")
            return redirect(url_for("upload"))
        if not thumbnail_file or not thumbnail_file.filename:
            flash("Upload a local thumbnail image.", "danger")
            return redirect(url_for("upload"))
        if not allowed_file(video_file.filename, VIDEO_EXTENSIONS):
            flash("Local videos must be MP4 files.", "danger")
            return redirect(url_for("upload"))
        if not allowed_file(thumbnail_file.filename, THUMBNAIL_EXTENSIONS):
            flash("Thumbnails must be jpg, jpeg, png, or webp files.", "danger")
            return redirect(url_for("upload"))

        os.makedirs(VIDEO_UPLOAD_DIR, exist_ok=True)
        os.makedirs(THUMBNAIL_UPLOAD_DIR, exist_ok=True)

        stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        video_name = secure_filename(video_file.filename)
        video_name = f"{stamp}_{video_name}"
        video_file.save(os.path.join(VIDEO_UPLOAD_DIR, video_name))
        video_path = f"videos/{video_name}"

        thumb_name = secure_filename(thumbnail_file.filename)
        thumb_name = f"{stamp}_{thumb_name}"
        thumbnail_file.save(os.path.join(THUMBNAIL_UPLOAD_DIR, thumb_name))
        thumb = f"/static/thumbnails/{thumb_name}"

        if not title:
            title = os.path.splitext(secure_filename(video_file.filename))[0] or "Local video"

        vid_id = f"local_{stamp}"

        db = get_db()
        db.execute("""
            INSERT OR REPLACE INTO videos
            (id, title, channel, views, duration, category,
             video_path, thumbnail, description, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            vid_id,
            title,
            channel,
            "0 views",
            "0:00",
            category,
            video_path,
            thumb,
            description,
            datetime.utcnow().isoformat()
        ))
        db.commit()
        flash("Video added!", "success")
        return redirect(url_for("watch", video_id=vid_id))

    return render_template("upload.html")


# ------------------------------------------------------------------------------
# Status
# ------------------------------------------------------------------------------
@app.route("/status")
def status():
    return render_template("status.html")


# ------------------------------------------------------------------------------
# Read-only evaluation API
# ------------------------------------------------------------------------------
# Exposes backend state as JSON so the WebArena-Pro evaluator can grade tasks
# deterministically. Strictly read-only and gated by a secret token
# (WP_EVAL_TOKEN) the agent under test never sees, so it cannot be used to read
# answers. Disabled (403) when WP_EVAL_TOKEN is unset. No password hashes.

EVAL_STATE_QUERIES = {
    "videos": "SELECT id, title, channel, views, duration, category, description, created_at FROM videos",
    "likes": "SELECT video_id, username, value FROM likes",
    "comments": "SELECT id, video_id, username, text, created_at FROM comments",
    "watch_later": "SELECT username, video_id FROM watch_later",
    "history": "SELECT username, video_id, watched_at FROM history",
    "playlists": "SELECT id, username, name, created_at FROM playlists",
    "playlist_videos": "SELECT playlist_id, video_id FROM playlist_videos",
    "users": "SELECT username, created_at FROM users",
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
    for name, query in EVAL_STATE_QUERIES.items():
        try:
            out[name] = [dict(row) for row in db.execute(query).fetchall()]
        except sqlite3.Error:
            out[name] = []
    return jsonify(out)


# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------
if __name__ == "__main__":
   with app.app_context():
        init_db()
   app.run(host="0.0.0.0", port=7860, debug=False)

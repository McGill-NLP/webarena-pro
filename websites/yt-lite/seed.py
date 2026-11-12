import os, sqlite3, json, pathlib, random
from common.seed_utils import init_db, load_json


ROOT = pathlib.Path(__file__).parent
DB_PATH = ROOT / "db" / "yt.sqlite3"
SCHEMA = ROOT / "schema.sql"
SEED_JSON = ROOT / "data" / "videos_seed.json"
SEED = int(os.environ.get("APP_SEED", 42))
random.seed(SEED)


init_db(DB_PATH, SCHEMA)


videos = load_json(SEED_JSON)
with sqlite3.connect(DB_PATH) as con:
    for v in videos:
        con.execute(
    "INSERT INTO videos(id,title,channel,views,duration,description,tags) VALUES(?,?,?,?,?,?,?)",
    (v["id"], v["title"], v["channel"], v["views"], v["duration"], v["description"], ",".join(v["tags"]))
    )
    # Create one default playlist deterministically
    con.execute("INSERT INTO playlists(id,name,owner) VALUES(?,?,?)", ("p1", "AI Talks", "seed_user"))
    con.commit()
print("YT-Lite seeded.")
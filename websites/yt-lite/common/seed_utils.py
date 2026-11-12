import json
import pathlib
import sqlite3


def init_db(db_path: pathlib.Path, schema_path: pathlib.Path) -> None:
    db_path = pathlib.Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema = pathlib.Path(schema_path).read_text()
    with sqlite3.connect(db_path) as con:
        con.executescript(schema)
        con.commit()


def load_json(json_path: pathlib.Path):
    return json.loads(pathlib.Path(json_path).read_text())

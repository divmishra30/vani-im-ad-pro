"""Call history: outcomes, WhatsApp messages, callbacks, campaign edits. One SQLite file.

Every event for a seller feeds the History section of their seller.md, so the next call or
WhatsApp chat starts from where the last contact ended.
"""

import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("VANI_DB", Path(__file__).resolve().parent.parent / "data" / "vani.db"))


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS events ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, glid TEXT NOT NULL,"
        " type TEXT NOT NULL, data TEXT NOT NULL)"
    )
    return conn


def record(glid, type_, data):
    event = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "glid": glid, "type": type_, "data": data}
    with _conn() as conn:
        conn.execute("INSERT INTO events (at, glid, type, data) VALUES (?, ?, ?, ?)",
                     (event["at"], glid, type_, json.dumps(data, ensure_ascii=False)))
    return event


def _rows(sql, args=()):
    with _conn() as conn:
        return [{"at": r["at"], "glid": r["glid"], "type": r["type"], "data": json.loads(r["data"])}
                for r in conn.execute(sql, args)]


def history(glid, limit=50):
    """Events for one seller, newest first."""
    return _rows("SELECT * FROM events WHERE glid = ? ORDER BY id DESC LIMIT ?", (glid, limit))


def history_by_seller():
    out = defaultdict(list)
    for e in _rows("SELECT * FROM events ORDER BY id DESC"):
        out[e["glid"]].append(e)
    return out


def recent(limit=30):
    return _rows("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))

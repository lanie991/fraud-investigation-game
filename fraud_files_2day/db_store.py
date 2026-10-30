"""
Keeps the game's data safe overnight on Render's free plan.

The game itself runs on a small SQLite file, but Render's free web
service wipes its disk whenever it restarts or goes to sleep. When the
DATABASE_URL environment variable points at a Postgres database (Render's
free database, set up by render.yaml), this module:

  * restores the saved game file from Postgres when the server starts, and
  * copies the game file back to Postgres a moment after every change
    (and once more when the server shuts down).

Without DATABASE_URL (for example when playing on your own computer)
everything here does nothing and the local file is used as normal.
"""

import atexit
import os
import sqlite3
import ssl
import tempfile
import threading
import time
from urllib.parse import unquote, urlparse

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SAVE_DELAY_SECONDS = 1.5

_dirty = threading.Event()
_lock = threading.Lock()
_db_path = None
_started = False


def enabled():
    return bool(DATABASE_URL)


def _connect():
    import pg8000.dbapi

    url = urlparse(DATABASE_URL)
    # Render's internal address (no dots in the host) needs no SSL; the
    # external one does.
    use_ssl = "." in (url.hostname or "") and url.hostname not in ("localhost", "127.0.0.1")
    return pg8000.dbapi.connect(
        user=unquote(url.username or ""),
        password=unquote(url.password or ""),
        host=url.hostname,
        port=url.port or 5432,
        database=(url.path or "/").lstrip("/"),
        ssl_context=ssl.create_default_context() if use_ssl else None,
        timeout=15,
    )


def _ensure_table(connection):
    cursor = connection.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS game_snapshot ("
        " id INTEGER PRIMARY KEY,"
        " data BYTEA NOT NULL,"
        " saved_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
    )
    connection.commit()


def restore(db_path):
    """Write the saved game (if there is one) to db_path."""
    if not enabled():
        return False
    connection = _connect()
    try:
        _ensure_table(connection)
        cursor = connection.cursor()
        cursor.execute("SELECT data FROM game_snapshot WHERE id = 1")
        row = cursor.fetchone()
    finally:
        connection.close()
    if not row:
        return False
    with open(db_path, "wb") as handle:
        handle.write(bytes(row[0]))
    return True


def _snapshot_bytes(db_path):
    """A consistent copy of the SQLite file, even while it is in use."""
    fd, temp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        source = sqlite3.connect(db_path)
        target = sqlite3.connect(temp_path)
        with target:
            source.backup(target)
        source.close()
        target.close()
        with open(temp_path, "rb") as handle:
            return handle.read()
    finally:
        os.remove(temp_path)


def save_now():
    if not enabled() or not _db_path or not os.path.exists(_db_path):
        return
    with _lock:
        _dirty.clear()
        data = _snapshot_bytes(_db_path)
        connection = _connect()
        try:
            _ensure_table(connection)
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO game_snapshot (id, data, saved_at) VALUES (1, %s, NOW()) "
                "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, saved_at = NOW()",
                (data,),
            )
            connection.commit()
        finally:
            connection.close()


def mark_changed():
    if enabled():
        _dirty.set()


def _saver():
    while True:
        _dirty.wait()
        time.sleep(SAVE_DELAY_SECONDS)   # group quick changes into one save
        try:
            save_now()
        except Exception as error:      # keep trying; never crash the game
            print(f"[db_store] save failed, will retry: {error}", flush=True)
            _dirty.set()
            time.sleep(5)


def start(db_path):
    """Restore the saved game, then keep saving changes in the background."""
    global _db_path, _started
    _db_path = db_path
    if not enabled() or _started:
        return
    _started = True
    for attempt in range(5):
        try:
            if restore(db_path):
                print("[db_store] restored saved game from the database", flush=True)
            else:
                print("[db_store] no saved game yet; starting fresh", flush=True)
            break
        except Exception as error:
            print(f"[db_store] restore failed (attempt {attempt + 1}): {error}", flush=True)
            time.sleep(3)
    else:
        raise RuntimeError("Could not reach the game database (DATABASE_URL).")
    threading.Thread(target=_saver, daemon=True).start()
    atexit.register(_save_on_exit)


def _save_on_exit():
    if _dirty.is_set():
        try:
            save_now()
        except Exception as error:
            print(f"[db_store] final save failed: {error}", flush=True)


class SavingConnection(sqlite3.Connection):
    """A SQLite connection that schedules a save after every commit."""

    def commit(self):
        super().commit()
        mark_changed()

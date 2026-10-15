import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), snapshot TEXT, last_attempt TEXT, last_error TEXT, failures INTEGER NOT NULL DEFAULT 0)")
            db.execute("INSERT OR IGNORE INTO state(id) VALUES(1)")
            db.execute("CREATE TABLE IF NOT EXISTS history (version TEXT PRIMARY KEY, collected_at TEXT NOT NULL, snapshot TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def read(self):
        with self.connect() as db:
            row = dict(db.execute("SELECT * FROM state WHERE id=1").fetchone())
        row["snapshot"] = json.loads(row["snapshot"]) if row["snapshot"] else None
        return row

    def attempt(self):
        with self.connect() as db:
            db.execute("UPDATE state SET last_attempt=? WHERE id=1", (now_iso(),))

    def fail(self, error):
        with self.connect() as db:
            db.execute("UPDATE state SET last_error=?, failures=failures+1 WHERE id=1", (str(error)[:1000],))

    def publish(self, rows, source, is_demo=False, observed_at=None, keep=24):
        stamp = now_iso()
        snapshot = {"version": uuid.uuid4().hex, "collected_at": stamp,
                    "observed_at": observed_at or stamp, "source": source,
                    "is_demo": is_demo, "coverage": "provider_unverified" if source in ("eastmoney", "sina") else "sample" if is_demo else "file_unverified",
                    "count": len(rows), "quotes": rows}
        payload = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        with self.connect() as db:
            db.execute("UPDATE state SET snapshot=?,last_error=NULL,failures=0 WHERE id=1", (payload,))
            db.execute("INSERT INTO history VALUES(?,?,?)", (snapshot["version"], stamp, payload))
            db.execute("DELETE FROM history WHERE version NOT IN (SELECT version FROM history ORDER BY collected_at DESC LIMIT ?)", (keep,))
        return snapshot


@contextmanager
def collector_lock(path):
    """OS lock: exclusive per DB, automatically released after a crash."""
    lock_path = Path(str(Path(path).resolve()) + ".collector.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    stream = lock_path.open("a+b")
    locked = False
    try:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if __import__("os").name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise RuntimeError("another collector owns this database") from exc
        yield
    finally:
        if locked:
            stream.seek(0)
            if __import__("os").name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()

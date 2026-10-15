import csv
import json
import os
import tempfile
from pathlib import Path
from .formats import DataError


def export_snapshot(snapshot, path):
    path = Path(path)
    if path.suffix.lower() not in (".json", ".csv"):
        raise DataError("export extension must be .json or .csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8-sig" if path.suffix.lower() == ".csv" else "utf-8",
                                         newline="", dir=path.parent, delete=False) as stream:
            temp = Path(stream.name)
            if path.suffix.lower() == ".json":
                json.dump(snapshot, stream, ensure_ascii=False, allow_nan=False)
            else:
                writer = csv.DictWriter(stream, fieldnames=list(snapshot["quotes"][0]))
                writer.writeheader()
                writer.writerows(snapshot["quotes"])
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp and temp.exists():
            temp.unlink()

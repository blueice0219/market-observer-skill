"""Strict, bounded input parsing; all output numeric values are finite or None."""
import csv
import io
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 32 * 1024 * 1024
MAX_ROWS = 20000
ALIASES = {
    "code": ("code", "代码", "股票代码", "symbol"),
    "name": ("name", "名称", "股票名称"),
    "price": ("price", "最新价", "trade"),
    "change_pct": ("change_pct", "涨跌幅", "changepercent"),
    "change": ("change", "涨跌额", "pricechange"),
    "open": ("open", "今开", "开盘"),
    "high": ("high", "最高"),
    "low": ("low", "最低"),
    "prev_close": ("prev_close", "昨收", "settlement"),
    "volume": ("volume", "成交量"),
    "amount": ("amount", "成交额"),
    "turnover_pct": ("turnover_pct", "换手率"),
    "quote_time": ("quote_time", "时间戳"),
}


class DataError(ValueError):
    pass


def code_info(value):
    if isinstance(value, bool) or value is None:
        raise DataError("invalid stock code")
    raw = str(value).strip().lower()
    explicit = None
    match = re.fullmatch(r"(sh|sz|bj)(\d{6})", raw)
    suffix = re.fullmatch(r"(\d{6})\.(sh|sz|bj)", raw)
    if match:
        explicit, raw = match.groups()
    elif suffix:
        raw, explicit = suffix.groups()
    else:
        if re.fullmatch(r"\d{1,6}\.0", raw):
            raw = raw[:-2]
        if not re.fullmatch(r"\d{1,6}", raw):
            raise DataError("stock code must be 6 digits, sh600000 or 600000.SH")
        raw = raw.zfill(6)
    exchange = ("sh" if raw.startswith(("60", "68")) else
                "sz" if raw.startswith(("00", "30")) else
                "bj" if raw.startswith(("43", "83", "87", "88", "92")) else None)
    if exchange is None or (explicit and explicit != exchange):
        raise DataError(f"unsupported A-share code or exchange: {value}")
    return raw, exchange


def numeric(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise DataError("boolean is not a numeric quote")
    if isinstance(value, str):
        value = value.strip().replace(",", "")
        if value.lower() in ("", "-", "--", "null", "none", "nan", "n/a", "inf", "infinity", "-inf"):
            return None
        value = value.removesuffix("%")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DataError(f"invalid numeric value: {str(value)[:50]}") from exc
    return number if math.isfinite(number) else None


def records_from_json(obj):
    if isinstance(obj, list):
        return obj
    if not isinstance(obj, dict):
        raise DataError("JSON root must be an array or supported object")
    if isinstance(obj.get("columns"), list) and isinstance(obj.get("data"), list):
        columns = obj["columns"]
        if len(columns) != len(set(columns)):
            raise DataError("duplicate columns")
        if any(not isinstance(row, list) or len(row) != len(columns) for row in obj["data"]):
            raise DataError("split JSON row width mismatch")
        return [dict(zip(columns, row)) for row in obj["data"]]
    for key in ("quotes", "records", "data"):
        if isinstance(obj.get(key), list):
            return obj[key]
    if obj and all(isinstance(v, dict) for v in obj.values()):
        code_names = set(ALIASES["code"])
        if code_names.intersection(obj):  # pandas orient=columns
            indices = list(next(iter(obj.values())))
            if any(set(v) != set(indices) for v in obj.values()):
                raise DataError("column JSON has mismatched indices")
            return [{key: col[index] for key, col in obj.items()} for index in indices]
        if all(code_names.intersection(v) for v in obj.values()):  # orient=index
            return list(obj.values())
    raise DataError("unsupported JSON layout; use records, split, columns, index or data/quotes envelope")


def normalize(records, volume_unit="shares"):
    if volume_unit not in ("shares", "lots"):
        raise DataError("volume unit must be shares or lots")
    if not records or len(records) > MAX_ROWS:
        raise DataError(f"record count must be 1..{MAX_ROWS}")
    result, seen = [], set()
    for index, original in enumerate(records):
        if not isinstance(original, dict):
            raise DataError(f"row {index + 1} is not an object")
        row = {str(k).strip(): v for k, v in original.items()}
        values = {key: next((row[a] for a in names if a in row), None) for key, names in ALIASES.items()}
        try:
            code, exchange = code_info(values["code"])
            if code in seen:
                raise DataError(f"duplicate code {code}")
            seen.add(code)
            name = values["name"]
            if not isinstance(name, str) or not name.strip():
                raise DataError("missing stock name")
            if not any(a in row for a in ALIASES["price"]):
                raise DataError("missing price column")
            output = {"code": code, "exchange": exchange, "symbol": exchange + code, "name": name.strip()}
            for field in ALIASES:
                if field not in ("code", "name", "quote_time"):
                    output[field] = numeric(values[field])
            for field in ("price", "open", "high", "low", "prev_close", "volume", "amount"):
                if output[field] is not None and output[field] < 0:
                    raise DataError(f"negative {field}")
            if output["volume"] is not None and volume_unit == "lots":
                output["volume"] *= 100
                if not math.isfinite(output["volume"]):
                    raise DataError("volume overflow")
            quote_time = values["quote_time"]
            output["quote_time"] = str(quote_time).strip() if quote_time is not None and str(quote_time).strip() else None
            result.append(output)
        except DataError as exc:
            raise DataError(f"row {index + 1}: {exc}") from exc
    return sorted(result, key=lambda r: r["code"])


def load_file(path: Path, volume_unit="shares"):
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
        stat = __import__("os").fstat(stream.fileno())
    if len(raw) > MAX_BYTES:
        raise DataError("input exceeds 32 MiB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gb18030")
        except UnicodeDecodeError as exc:
            raise DataError("input is not UTF-8 or GB18030") from exc
    try:
        suffix = path.suffix.lower()
        if suffix in (".csv", ".tsv"):
            reader = csv.DictReader(io.StringIO(text), delimiter="\t" if suffix == ".tsv" else ",")
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise DataError("missing or duplicate CSV headers")
            rows = list(reader)
            if any(None in row or any(v is None for v in row.values()) for row in rows):
                raise DataError("CSV row width mismatch")
        elif suffix in (".jsonl", ".ndjson"):
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        elif suffix == ".json":
            rows = records_from_json(json.loads(text))
        else:
            raise DataError("supported files: .json .jsonl .ndjson .csv .tsv")
        return normalize(rows, volume_unit), datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
    except (json.JSONDecodeError, csv.Error, TypeError) as exc:
        raise DataError(f"invalid file format: {exc}") from exc

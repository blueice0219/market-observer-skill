import concurrent.futures
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from a_share_monitor.api import create_app
from a_share_monitor.collector import collect_once
from a_share_monitor.config import Settings
from a_share_monitor.exporter import export_snapshot
from a_share_monitor.formats import DataError, code_info, load_file, normalize, numeric, records_from_json
from a_share_monitor.providers import demo_rows, fetch_live
from a_share_monitor.store import Store, collector_lock


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "market.sqlite3")


@pytest.fixture
def client(store):
    collect_once(store, "demo")
    with TestClient(create_app(Settings(store.path, cors_origins=("http://localhost:3000",)))) as client:
        yield client


@pytest.mark.parametrize("raw,expected", [(1, "000001"), ("000001", "000001"), ("sh600000", "600000"),
                                         ("600000.SH", "600000"), ("920001", "920001"), (1.0, "000001")])
def test_codes(raw, expected):
    assert code_info(raw)[0] == expected


@pytest.mark.parametrize("raw", [True, None, "../x", "sz600000", "510300", "900001", "1234567"])
def test_bad_codes(raw):
    with pytest.raises(DataError):
        code_info(raw)


@pytest.mark.parametrize("raw,expected", [("1,234.5", 1234.5), ("2.5%", 2.5), ("--", None),
                                         (float("nan"), None), (float("inf"), None), ("", None)])
def test_numeric(raw, expected):
    assert numeric(raw) == expected


def test_normalization_units_and_duplicate():
    row = {"代码": "000001", "名称": "股票", "最新价": "-", "成交量": 12}
    assert normalize([row], "lots")[0]["volume"] == 1200
    assert normalize([row])[0]["price"] is None
    with pytest.raises(DataError, match="duplicate"):
        normalize([row, row])
    with pytest.raises(DataError):
        normalize([{**row, "成交量": "未知"}])
    with pytest.raises(DataError):
        normalize([{**row, "最新价": -1}])


@pytest.mark.parametrize("layout", ["records", "envelope", "split", "columns", "index", "table"])
def test_json_layout(tmp_path, layout):
    row = {"code": "000001", "name": "中文", "price": 1}
    values = {"records": [row], "envelope": {"quotes": [row]},
              "split": {"columns": list(row), "data": [list(row.values())]},
              "columns": {k: {"0": v} for k, v in row.items()}, "index": {"0": row},
              "table": {"schema": {}, "data": [row]}}
    path = tmp_path / "input.json"
    path.write_text(json.dumps(values[layout], ensure_ascii=False), encoding="utf-8-sig")
    assert load_file(path)[0][0]["code"] == "000001"


@pytest.mark.parametrize("encoding", ["utf-8-sig", "gb18030"])
def test_csv_encodings(tmp_path, encoding):
    path = tmp_path / "quotes.csv"
    path.write_text('代码,名称,最新价,成交额\n000001,中文,10,"1,000"\n', encoding=encoding)
    assert load_file(path)[0][0]["amount"] == 1000


def test_bad_files_and_jsonl(tmp_path):
    path = tmp_path / "quotes.jsonl"
    path.write_text('{"code":"000001","name":"one","price":1}\n\n', encoding="utf-8")
    assert len(load_file(path)[0]) == 1
    path.write_text('{broken', encoding="utf-8")
    with pytest.raises(DataError):
        load_file(path)
    with pytest.raises(DataError):
        records_from_json({"columns": ["a", "b"], "data": [[1]]})
    path = tmp_path / "bad.csv"
    path.write_text("code,name,price\n000001,x,1,extra", encoding="utf-8")
    with pytest.raises(DataError):
        load_file(path)


def test_api_queries(client):
    result = client.get("/api/v1/quotes?limit=10000").json()
    assert result["total"] == 6
    assert result["meta"]["is_demo"] is True
    assert result["meta"]["exchange_timestamp_verified"] is False
    assert client.get("/api/v1/quotes?exchange=sh").json()["total"] == 2
    assert client.get("/api/v1/quotes?q=平安").json()["total"] == 1
    assert client.get("/api/v1/quotes?offset=100").json()["data"] == []
    assert client.get("/api/v1/stocks/sh600000").json()["data"]["code"] == "600000"
    assert client.get("/api/v1/stocks/600000.SH").status_code == 200
    assert client.get("/api/v1/stocks/600001").status_code == 404
    assert client.get("/api/v1/stocks/invalid").status_code == 422
    assert client.get("/api/v1/quotes?expected_version=old").status_code == 409
    assert client.get("/api/v1/quotes?expected_version=" + result["meta"]["version"]).status_code == 200


def test_rankings_and_null_order(client):
    ranks = client.get("/api/v1/rankings?limit=2").json()
    assert ranks["data"][0]["code"] == "300750"
    assert ranks["total"] == 5
    assert client.get("/api/v1/rankings?order=asc").json()["data"][0]["code"] == "600000"
    for order in ("asc", "desc"):
        rows = client.get(f"/api/v1/quotes?sort_by=price&order={order}").json()["data"]
        assert rows[-1]["price"] is None


@pytest.mark.parametrize("url", ["/api/v1/quotes?limit=0", "/api/v1/quotes?limit=10001", "/api/v1/quotes?offset=-1",
                                 "/api/v1/quotes?exchange=xx", "/api/v1/rankings?metric=bad", "/api/v1/rankings?limit=501"])
def test_validation(client, url):
    response = client.get(url)
    assert response.status_code == 422
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_empty_and_stale(store):
    with TestClient(create_app(Settings(store.path, stale_seconds=1))) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 503
        assert client.get("/api/v1/status").json()["status"] == "no_data"
        assert client.get("/api/v1/quotes").status_code == 503
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        store.publish(demo_rows(), "file", observed_at=past)
        assert client.get("/api/v1/quotes").json()["meta"]["stale"] is True
        assert client.get("/api/v1/quotes?require_fresh=true").status_code == 503
        assert client.get("/api/v1/status").json()["status"] == "stale"


def test_cors_and_error_cors(client):
    origin = {"Origin": "http://localhost:3000"}
    response = client.options("/api/v1/quotes", headers={**origin, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "X-API-Key"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin["Origin"]
    assert "access-control-allow-credentials" not in response.headers
    assert client.get("/bad", headers=origin).headers["access-control-allow-origin"] == origin["Origin"]
    assert "access-control-allow-origin" not in client.get("/api/v1/quotes", headers={"Origin": "https://bad.example"}).headers


def test_auth_and_internal_error(store):
    app = create_app(Settings(store.path, api_key="secret", cors_origins=("*",)))
    @app.get("/test-error")
    def fail():
        raise RuntimeError("private traceback")
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/api/v1/status").status_code == 401
        assert client.get("/api/v1/status", headers={"X-API-Key": "secret"}).status_code == 200
        assert client.get("/healthz").status_code == 200
        response = client.get("/test-error", headers={"Origin": "http://example.com"})
        assert response.status_code == 500
        assert "private traceback" not in response.text
        assert response.headers["access-control-allow-origin"] == "*"


def test_failed_collection_retains_snapshot(store, tmp_path):
    first = collect_once(store, "demo")
    bad = tmp_path / "bad.json"
    bad.write_text("{broken", encoding="utf-8")
    with pytest.raises(DataError):
        collect_once(store, "file", file=bad)
    state = store.read()
    assert state["snapshot"]["version"] == first["version"]
    assert state["failures"] == 1
    assert state["last_error"]
    collect_once(store, "demo")
    assert store.read()["last_error"] is None


def test_fallback_and_coverage(store):
    calls = []
    def fake(source, timeout):
        calls.append(source)
        if source == "eastmoney":
            raise DataError("network down")
        return demo_rows()
    result = collect_once(store, "auto", min_rows=1, fetcher=fake)
    assert calls == ["eastmoney", "sina"]
    assert result["source"] == "sina"
    assert result["is_demo"] is False  # fake dependency only exists in test
    with pytest.raises(DataError):
        collect_once(store, "sina", min_rows=4000, fetcher=fake)
    with pytest.raises(DataError):
        collect_once(store, "sina", min_rows=1, fetcher=lambda *_: demo_rows()[:2])
    assert store.read()["snapshot"]["version"] == result["version"]


def test_timeout(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("worker", 1)
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(DataError, match="exceeded"):
        fetch_live("sina", 1)


def test_export_roundtrip_and_retention(store, tmp_path):
    for _ in range(5):
        snapshot = store.publish(demo_rows(), "demo", True, keep=2)
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM history").fetchone()[0] == 2
    for suffix in (".csv", ".json"):
        path = tmp_path / ("out" + suffix)
        export_snapshot(snapshot, path)
        assert load_file(path)[0] == snapshot["quotes"]


def test_atomic_concurrent_reads_writes(store):
    store.publish(demo_rows(), "demo", True)
    def writer():
        for i in range(30):
            store.publish(demo_rows()[:(i % 6) + 1], "demo", True)
    def reader():
        for _ in range(60):
            snapshot = store.read()["snapshot"]
            assert len(snapshot["quotes"]) == snapshot["count"]
            assert len({r["code"] for r in snapshot["quotes"]}) == snapshot["count"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(writer)] + [executor.submit(reader) for _ in range(4)]
        for future in futures:
            future.result()


def test_process_lock(store):
    code = "from a_share_monitor.store import collector_lock; import sys\nwith collector_lock(sys.argv[1]): print('acquired')"
    with collector_lock(store.path):
        result = subprocess.run([sys.executable, "-c", code, str(store.path)], capture_output=True, text=True)
        assert result.returncode != 0
        assert "another collector" in result.stderr
    result = subprocess.run([sys.executable, "-c", code, str(store.path)], capture_output=True, text=True)
    assert result.returncode == 0


def test_file_age_not_refreshed(store, tmp_path):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(demo_rows()), encoding="utf-8")
    old = (datetime.now(timezone.utc) - timedelta(days=2)).timestamp()
    os.utime(path, (old, old))
    result = collect_once(store, "file", file=path)
    assert datetime.fromisoformat(result["observed_at"]).timestamp() == pytest.approx(old)


def test_cli_smoke(tmp_path):
    env = {**os.environ, "MONITOR_DB": str(tmp_path / "cli.sqlite3")}
    result = subprocess.run([sys.executable, "-m", "a_share_monitor", "collect", "--source", "demo", "--once"], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert Store(tmp_path / "cli.sqlite3").read()["snapshot"]["count"] == 6

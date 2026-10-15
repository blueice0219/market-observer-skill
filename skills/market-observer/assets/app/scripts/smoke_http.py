"""Real TCP smoke test with two API processes and an independent collector.
Run from the project root: python scripts/smoke_http.py
Uses a temporary database and loopback ports. Does not fetch live market data.
"""
import concurrent.futures
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def get(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as response:
        return json.load(response)


def main():
    processes = []
    with tempfile.TemporaryDirectory(prefix="a-share-smoke-") as temp:
        env = {**os.environ, "MONITOR_DB": str(Path(temp) / "market.sqlite3"),
               "MONITOR_API_KEY": "", "MONITOR_STALE_SECONDS": "900", "PYTHONUTF8": "1"}
        bases = []
        with (Path(temp) / "server.log").open("w", encoding="utf-8") as log:
            try:
                for _ in range(2):
                    port = free_port()
                    process = subprocess.Popen([sys.executable, "-m", "a_share_monitor", "serve", "--port", str(port)],
                                               cwd=ROOT, env=env, stdout=log, stderr=log,
                                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                    processes.append(process)
                    base = f"http://127.0.0.1:{port}"
                    bases.append(base)
                    deadline = time.monotonic() + 20
                    while True:
                        try:
                            assert get(base, "/healthz")["status"] == "ok"
                            break
                        except Exception:
                            if process.poll() is not None or time.monotonic() > deadline:
                                raise RuntimeError("server did not start")
                            time.sleep(0.1)
                subprocess.run([sys.executable, "-m", "a_share_monitor", "collect", "--source", "demo", "--once"],
                               cwd=ROOT, env=env, check=True, stdout=log, stderr=log)
                paths = ["/api/v1/quotes?limit=10000", "/api/v1/stocks/000001", "/api/v1/rankings", "/api/v1/status", "/readyz", "/openapi.json"]
                for base in bases:
                    for path in paths:
                        assert get(base, path)
                old = get(bases[0], "/api/v1/quotes")["meta"]["version"]
                def reader(i):
                    result = get(bases[i % 2], "/api/v1/quotes?limit=10000")
                    assert result["total"] == len(result["data"]) == 6
                    assert result["meta"]["is_demo"]
                def writer():
                    subprocess.run([sys.executable, "-m", "a_share_monitor", "collect", "--source", "demo", "--once"],
                                   cwd=ROOT, env=env, check=True, stdout=log, stderr=log)
                with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
                    futures = [pool.submit(reader, i) for i in range(100)] + [pool.submit(writer)]
                    for future in futures:
                        future.result()
                versions = [get(base, "/api/v1/quotes")["meta"]["version"] for base in bases]
                assert versions[0] == versions[1] and versions[0] != old
                print(json.dumps({"passed": True, "api_processes": 2, "concurrent_requests": 100,
                                  "endpoints_per_process": len(paths), "cross_process_refresh": True}))
            finally:
                for process in processes:
                    process.terminate()
                for process in processes:
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__ == "__main__":
    main()

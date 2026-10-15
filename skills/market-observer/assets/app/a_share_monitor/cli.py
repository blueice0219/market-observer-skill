import argparse
import json
import logging
import signal
import sys
import threading
from pathlib import Path
from .config import Settings
from .collector import run
from .formats import DataError
from .providers import fetch_live
from .store import Store


def main():
    parser = argparse.ArgumentParser(description="A 股采集与 HTTP API")
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect", help="持续采集；--once 只采集一轮")
    collect.add_argument("--source", choices=["auto", "eastmoney", "sina", "file", "demo"], default="auto")
    collect.add_argument("--file", type=Path)
    collect.add_argument("--volume-unit", choices=["shares", "lots"], default="shares")
    collect.add_argument("--interval", type=float, default=300)
    collect.add_argument("--timeout", type=float, default=180)
    collect.add_argument("--min-rows", type=int, default=4000)
    collect.add_argument("--keep", type=int, default=24)
    collect.add_argument("--once", action="store_true")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--workers", type=int, default=1)
    export = sub.add_parser("export", help="原子导出当前快照 JSON 或 CSV")
    export.add_argument("path", type=Path)
    doctor = sub.add_parser("doctor", help="一次实时连通性诊断，不写入数据库")
    doctor.add_argument("--source", choices=["eastmoney", "sina"], default="eastmoney")
    doctor.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        settings = Settings.from_env()
        if args.command == "serve":
            if not 1 <= args.port <= 65535 or args.workers < 1:
                parser.error("invalid port or workers")
            import uvicorn
            uvicorn.run("a_share_monitor.api:create_app", factory=True, host=args.host, port=args.port, workers=args.workers)
        elif args.command == "collect":
            if not 1 <= args.interval <= 3600 or not 1 <= args.timeout <= 1800 or not 1 <= args.min_rows <= 20000 or not 1 <= args.keep <= 1000:
                parser.error("interval 1..3600, timeout 1..1800, min-rows 1..20000, keep 1..1000 required")
            if args.source in ("auto", "eastmoney", "sina") and args.interval < 60:
                parser.error("live collection interval must be at least 60 seconds")
            if args.source == "file" and not args.file:
                parser.error("--source file requires --file")
            stop = threading.Event()
            signal.signal(signal.SIGINT, lambda *_: stop.set())
            signal.signal(signal.SIGTERM, lambda *_: stop.set())
            run(settings, source=args.source, interval=args.interval, once=args.once, stop=stop,
                file=args.file, volume_unit=args.volume_unit, timeout=args.timeout, min_rows=args.min_rows, keep=args.keep)
        elif args.command == "doctor":
            if not 1 <= args.timeout <= 1800:
                parser.error("timeout must be 1..1800")
            rows = fetch_live(args.source, args.timeout)
            print(json.dumps({"source": args.source, "count": len(rows), "sample": rows[:2]}, ensure_ascii=False, allow_nan=False))
        elif args.command == "export":
            from .exporter import export_snapshot
            snapshot = Store(settings.db).read()["snapshot"]
            if not snapshot:
                raise DataError("no snapshot to export")
            export_snapshot(snapshot, args.path)
            print(str(args.path.resolve()))
    except (DataError, RuntimeError, OSError, ValueError) as exc:
        logging.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()

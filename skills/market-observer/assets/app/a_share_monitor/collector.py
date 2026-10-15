import logging
import random
import threading
from .formats import DataError, load_file
from .providers import demo_rows, fetch_live
from .store import Store, collector_lock

log = logging.getLogger(__name__)


def collect_once(store, source="auto", file=None, volume_unit="shares", timeout=180,
                 min_rows=4000, keep=24, fetcher=fetch_live):
    store.attempt()
    sources = ("eastmoney", "sina") if source == "auto" else (source,)
    errors = []
    for provider in sources:
        try:
            observed = None
            if provider == "demo":
                rows = demo_rows()
            elif provider == "file":
                if file is None:
                    raise DataError("--file is required for file source")
                rows, observed = load_file(file, volume_unit)
            else:
                rows = fetcher(provider, timeout)
                if len(rows) < min_rows:
                    raise DataError(f"only {len(rows)} rows; minimum is {min_rows}")
                previous = store.read()["snapshot"]
                if previous and previous["source"] in ("eastmoney", "sina") and len(rows) < previous["count"] * 0.8:
                    raise DataError("coverage dropped more than 20%; preserving previous snapshot")
            snapshot = store.publish(rows, provider, provider == "demo", observed, keep)
            log.info("published source=%s count=%s version=%s", provider, len(rows), snapshot["version"])
            return snapshot
        except Exception as exc:
            log.warning("collection failed for %s: %s", provider, exc)
            errors.append(f"{provider}: {exc}")
    store.fail("; ".join(errors))
    raise DataError("; ".join(errors))


def run(settings, source="auto", interval=300, once=False, stop=None, **options):
    stop = stop or threading.Event()
    store = Store(settings.db)
    with collector_lock(settings.db):
        failures = 0
        while not stop.is_set():
            try:
                collect_once(store, source=source, **options)
                failures = 0
            except DataError:
                failures += 1
                if once:
                    raise
            if once:
                return
            delay = min(interval * 2 ** min(failures, 4), 3600)
            if failures:
                delay += random.uniform(0, min(30, interval / 10))
            log.info("next collection in %.1f seconds", delay)
            stop.wait(delay)

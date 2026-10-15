import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from .formats import DataError, load_file, normalize


def demo_rows():
    # Deliberately fictional values, never selected as a live-source fallback.
    return normalize([
        {"code": "000001", "name": "平安银行（示例）", "price": 10, "change_pct": 1.5, "volume": 1200000, "amount": 12000000},
        {"code": "600000", "name": "浦发银行（示例）", "price": 8, "change_pct": -2, "volume": 2000000, "amount": 16000000},
        {"code": "300750", "name": "宁德时代（示例）", "price": 200, "change_pct": 3, "volume": 100000, "amount": 20000000},
        {"code": "688001", "name": "华兴源创（示例）", "price": 20, "change_pct": 0, "volume": 20000, "amount": 400000},
        {"code": "920001", "name": "北交所示例", "price": 15, "change_pct": -1, "volume": 5000, "amount": 75000},
        {"code": "000002", "name": "停牌示例", "price": None, "change_pct": None, "volume": 0, "amount": 0},
    ])


def fetch_live(source, timeout=180):
    # Subprocess isolation provides a hard deadline even if upstream libraries hang.
    with tempfile.TemporaryDirectory(prefix="a-share-") as temp:
        output = Path(temp) / "quotes.json"
        try:
            result = subprocess.run([sys.executable, "-m", "a_share_monitor.worker", source, str(output)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                    timeout=timeout, check=False, encoding="utf-8", errors="replace",
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except subprocess.TimeoutExpired as exc:
            raise DataError(f"{source}: collection exceeded {timeout}s") from exc
        if result.returncode:
            logging.getLogger(__name__).warning("%s worker diagnostics: %s", source, result.stderr[-2000:])
            # Full traceback may contain upstream URLs. Keep it in collector logs, not API.
            raise DataError(f"{source}: worker failed (exit={result.returncode}); check installation/network or run doctor")
        rows, _ = load_file(output, "lots" if source == "eastmoney" else "shares")
        return rows

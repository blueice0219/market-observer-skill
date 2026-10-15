import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db: Path = Path("data/market.sqlite3")
    stale_seconds: float = 900
    cors_origins: tuple[str, ...] = ()
    api_key: str = ""

    @classmethod
    def from_env(cls):
        seconds = float(os.getenv("MONITOR_STALE_SECONDS", "900"))
        if not 1 <= seconds <= 604800:
            raise ValueError("MONITOR_STALE_SECONDS must be between 1 and 604800")
        origins = tuple(x.strip() for x in os.getenv("MONITOR_CORS_ORIGINS", "").split(",") if x.strip())
        return cls(Path(os.getenv("MONITOR_DB", "data/market.sqlite3")).resolve(),
                   seconds, origins, os.getenv("MONITOR_API_KEY", ""))

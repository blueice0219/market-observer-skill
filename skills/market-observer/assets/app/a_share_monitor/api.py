import hmac
import logging
import sqlite3
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from starlette.exceptions import HTTPException as StarletteHTTPException
from .config import Settings
from .formats import DataError, code_info
from .store import Store

SortField = Literal["code", "price", "change_pct", "change", "volume", "amount", "turnover_pct"]
Exchange = Literal["sh", "sz", "bj"]


def market_clock():
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    minute = now.hour * 60 + now.minute
    phase = ("weekend" if now.weekday() >= 5 else
             "auction_window" if 555 <= minute < 565 else
             "continuous_window" if 570 <= minute < 690 or 780 <= minute < 897 else
             "closing_auction_window" if 897 <= minute < 900 else "outside_session_window")
    return {"time": now.isoformat(), "phase_estimate": phase, "holiday_calendar_verified": False}


def metadata(snapshot, settings):
    age = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(snapshot["observed_at"])).total_seconds())
    return {key: value for key, value in snapshot.items() if key != "quotes"} | {
        "age_seconds": round(age, 2), "stale": age > settings.stale_seconds,
        "stale_after_seconds": settings.stale_seconds, "exchange_timestamp_verified": False,
        "units": {"price": "CNY", "amount": "CNY", "volume": "shares", "change_pct": "percent_points"}}


def create_app(settings=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(settings.db)
        yield

    app = FastAPI(title="A 股全市场行情 API", version="1.0.0", lifespan=lifespan,
                  description="读取采集快照；不会因 HTTP 请求触发外部抓取。离线示例始终标记 is_demo=true。")
    ui_dir = Path(__file__).parent / "ui"
    app.mount("/assets", StaticFiles(directory=ui_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(ui_dir / "index.html")

    def error_response(request, status, code, message, details=None):
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": message,
                            "details": details, "request_id": getattr(request.state, "request_id", None)}})

    @app.middleware("http")
    async def request_context(request, call_next):
        request.state.request_id = uuid.uuid4().hex
        try:
            response = await call_next(request)
        except Exception:
            logging.getLogger(__name__).exception("request failed id=%s", request.state.request_id)
            response = error_response(request, 500, "INTERNAL_ERROR", "服务内部错误，请按 request_id 检查日志")
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "HTTP_ERROR", "message": str(exc.detail)}
        return error_response(request, exc.status_code, detail["code"], detail["message"])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        details = [{"location": list(e["loc"]), "message": e["msg"]} for e in exc.errors()]
        return error_response(request, 422, "INVALID_PARAMETER", "参数格式或范围不正确", details)

    @app.exception_handler(sqlite3.Error)
    async def database_error(request, exc):
        logging.getLogger(__name__).exception("database error", exc_info=exc)
        return error_response(request, 503, "STORAGE_UNAVAILABLE", "行情存储暂时不可用")

    key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    def authorized(provided_key: str | None = Depends(key_header)):
        if settings.api_key and not hmac.compare_digest((provided_key or "").encode(), settings.api_key.encode()):
            raise HTTPException(401, {"code": "UNAUTHORIZED", "message": "需要有效的 X-API-Key"})

    def snapshot(request: Request, require_fresh: bool = False, expected_version: str | None = None):
        state = request.app.state.store.read()
        data = state["snapshot"]
        if data is None:
            raise HTTPException(503, {"code": "NO_DATA", "message": "暂无有效快照，请先运行采集器并查看 /api/v1/status"})
        meta = metadata(data, settings)
        meta["collector_error"] = state["last_error"] is not None
        if expected_version and expected_version != data["version"]:
            raise HTTPException(409, {"code": "SNAPSHOT_CHANGED", "message": "快照已更新，请重新从第一页查询"})
        if require_fresh and meta["stale"]:
            raise HTTPException(503, {"code": "STALE_DATA", "message": "快照已过期"})
        return data, meta

    @app.get("/healthz", tags=["health"])
    def health():
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"], dependencies=[Depends(authorized)])
    def ready(request: Request):
        data, meta = snapshot(request, require_fresh=True)
        return {"status": "ready", "meta": meta}

    @app.get("/api/v1/status", tags=["market"], dependencies=[Depends(authorized)])
    def status(request: Request):
        state = request.app.state.store.read()
        data = state["snapshot"]
        meta = metadata(data, settings) if data else None
        status_value = "no_data" if data is None else "stale" if meta["stale"] else "degraded" if state["last_error"] else "ok"
        return {"status": status_value, "meta": meta, "last_attempt": state["last_attempt"],
                "last_error": state["last_error"], "consecutive_failures": state["failures"],
                "market_clock": market_clock()}

    @app.get("/api/v1/quotes", tags=["market"], dependencies=[Depends(authorized)])
    def quotes(request: Request, limit: int = Query(100, ge=1, le=10000), offset: int = Query(0, ge=0, le=100000),
               exchange: Exchange | None = None, q: str = Query("", max_length=64),
               sort_by: SortField = "code", order: Literal["asc", "desc"] = "asc",
               require_fresh: bool = False, expected_version: str | None = None):
        data, meta = snapshot(request, require_fresh, expected_version)
        rows = [r for r in data["quotes"] if (exchange is None or r["exchange"] == exchange)
                and (not q or q.lower() in (r["symbol"] + r["name"]).lower())]
        valid = [r for r in rows if r[sort_by] is not None]
        missing = [r for r in rows if r[sort_by] is None]
        valid.sort(key=lambda r: r["code"])
        valid.sort(key=lambda r: r[sort_by], reverse=order == "desc")
        rows = valid + sorted(missing, key=lambda r: r["code"])
        return {"meta": meta, "total": len(rows), "offset": offset, "limit": limit, "data": rows[offset:offset + limit]}

    @app.get("/api/v1/stocks/{code}", tags=["market"], dependencies=[Depends(authorized)])
    def stock(code: str, request: Request, require_fresh: bool = False):
        try:
            canonical, _ = code_info(code)
        except DataError as exc:
            raise HTTPException(422, {"code": "INVALID_CODE", "message": str(exc)}) from exc
        data, meta = snapshot(request, require_fresh)
        row = next((r for r in data["quotes"] if r["code"] == canonical), None)
        if row is None:
            raise HTTPException(404, {"code": "STOCK_NOT_FOUND", "message": "当前快照中不存在该股票"})
        return {"meta": meta, "data": row}

    @app.get("/api/v1/rankings", tags=["market"], dependencies=[Depends(authorized)])
    def rankings(request: Request, metric: Literal["change_pct", "change", "price", "volume", "amount", "turnover_pct"] = "change_pct",
                 order: Literal["asc", "desc"] = "desc", limit: int = Query(20, ge=1, le=500),
                 exchange: Exchange | None = None, require_fresh: bool = False):
        data, meta = snapshot(request, require_fresh)
        rows = [r for r in data["quotes"] if r[metric] is not None and (exchange is None or r["exchange"] == exchange)]
        rows.sort(key=lambda r: r["code"])
        rows.sort(key=lambda r: r[metric], reverse=order == "desc")
        return {"meta": meta, "metric": metric, "order": order, "total": len(rows),
                "data": [{"rank": i + 1, **row} for i, row in enumerate(rows[:limit])]}

    # Added last to wrap error responses as well; credentials deliberately disabled.
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_credentials=False, allow_methods=["GET", "OPTIONS"],
                       allow_headers=["X-API-Key", "Content-Type"], expose_headers=["X-Request-ID"])
    return app

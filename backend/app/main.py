"""Read-only A-share market data API backed by AkShare.

This service intentionally does not expose order, account, payment, or funding
endpoints. It is suitable for a demo market-data backend and should be paired
with an authorized market-data provider before production use.
"""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import akshare as ak
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware


CACHE_TTL_SECONDS = int(os.getenv("QUOTE_CACHE_TTL_SECONDS", "30"))
MAX_PAGE_SIZE = 100


class MarketCache:
    def __init__(self) -> None:
        self.stocks: list[dict[str, Any]] = []
        self.indices: list[dict[str, Any]] = []
        self.updated_at: float = 0
        self.lock = asyncio.Lock()

    def fresh(self) -> bool:
        return bool(self.stocks) and time.time() - self.updated_at < CACHE_TTL_SECONDS

    async def refresh(self) -> None:
        if self.fresh():
            return
        async with self.lock:
            if self.fresh():
                return
            stocks, indices = await asyncio.gather(
                asyncio.to_thread(ak.stock_zh_a_spot_em),
                asyncio.to_thread(ak.stock_zh_index_spot_em),
            )
            self.stocks = normalize_stocks(stocks)
            self.indices = normalize_indices(indices)
            self.updated_at = time.time()


cache = MarketCache()


def _value(row: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if name in row.index:
            value = row[name]
            if value != value:  # NaN
                return default
            return value
    return default


def normalize_stocks(frame: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        code = str(_value(row, "代码", "股票代码", default="")).zfill(6)
        if not code.isdigit():
            continue
        rows.append(
            {
                "code": code,
                "name": str(_value(row, "名称", "股票名称", default="")),
                "price": _number(_value(row, "最新价", "现价")),
                "change": _number(_value(row, "涨跌额")),
                "change_percent": _number(_value(row, "涨跌幅")),
                "open": _number(_value(row, "今开")),
                "high": _number(_value(row, "最高")),
                "low": _number(_value(row, "最低")),
                "volume": _number(_value(row, "成交量")),
                "amount": _number(_value(row, "成交额")),
            }
        )
    return rows


def normalize_indices(frame: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        code = str(_value(row, "代码", "指数代码", default=""))
        if not code:
            continue
        rows.append(
            {
                "code": code,
                "name": str(_value(row, "名称", "指数名称", default="")),
                "price": _number(_value(row, "最新价", "现价")),
                "change": _number(_value(row, "涨跌额")),
                "change_percent": _number(_value(row, "涨跌幅")),
            }
        )
    return rows


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def metadata() -> dict[str, Any]:
    return {
        "source": "AkShare",
        "updated_at": datetime.fromtimestamp(cache.updated_at, tz=timezone.utc).isoformat()
        if cache.updated_at
        else None,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "delayed_or_unavailable": False,
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title="VMS Market Data API", version="1.0.0", lifespan=lifespan)
allowed_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "service": "vms-market-data", **metadata()}


@app.get("/api/stocks")
async def stocks(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    search: str = Query("", max_length=30),
) -> dict[str, Any]:
    try:
        await cache.refresh()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"行情源暂时不可用: {exc}") from exc
    keyword = search.strip().lower()
    filtered = [item for item in cache.stocks if not keyword or keyword in item["code"].lower() or keyword in item["name"].lower()]
    start = (page - 1) * page_size
    end = start + page_size
    return {"items": filtered[start:end], "page": page, "page_size": page_size, "total": len(filtered), **metadata()}


@app.get("/api/stocks/{code}")
async def stock(code: str) -> dict[str, Any]:
    code = code.strip()
    if len(code) != 6 or not code.isdigit():
        raise HTTPException(status_code=422, detail="股票代码必须是 6 位数字")
    await cache.refresh()
    for item in cache.stocks:
        if item["code"] == code:
            return {"item": item, **metadata()}
    raise HTTPException(status_code=404, detail="未找到该股票")


@app.get("/api/indices")
async def indices() -> dict[str, Any]:
    try:
        await cache.refresh()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"行情源暂时不可用: {exc}") from exc
    return {"items": cache.indices, **metadata()}

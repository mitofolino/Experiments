#!/usr/bin/env python3
"""
webhook_api.py

FastAPI webhook that returns derived metrics for any ticker by reusing
compute_metrics() from get_aapl_metrics.py. Designed for easy debugging and
includes a simple in-memory cache to avoid repeated external calls.

Run (from Experiments, with venv activated):
  uvicorn webhook_api:app --reload --host 127.0.0.1 --port 8000

Docs: http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json
import logging
import time
import os

# reuse compute_metrics from existing script
try:
    from get_aapl_metrics import compute_metrics
except Exception as e:
    # if import fails, provide a clear runtime error when endpoints are hit
    compute_metrics = None
    import traceback
    _import_error = traceback.format_exc()


class TickerRequest(BaseModel):
    ticker: str


app = FastAPI(title="Ticker Metrics API", version="0.2")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook_api")

# Simple in-memory cache: { ticker_upper: {"metrics": {...}, "ts": <epoch>} }
CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))  # seconds


def _get_cached(ticker: str) -> Optional[Dict[str, Any]]:
    key = ticker.upper()
    entry = CACHE.get(key)
    if not entry:
        return None
    if time.time() - entry.get("ts", 0) > CACHE_TTL:
        # expired
        CACHE.pop(key, None)
        return None
    return entry.get("metrics")


def _set_cache(ticker: str, metrics: Dict[str, Any]):
    key = ticker.upper()
    CACHE[key] = {"metrics": metrics, "ts": time.time()}


@app.get("/", tags=["health"])
async def root():
    return {"status": "ok", "message": "Ticker Metrics API. See /docs."}


@app.get("/metrics/{ticker}", tags=["metrics"])
async def get_metrics(ticker: str, save: Optional[bool] = False, use_cache: Optional[bool] = True,
                      background: Optional[bool] = True):
    """Get metrics for ticker (GET).

    Params:
    - use_cache: if true (default) return cached metrics when available.
    - save: write metrics to metrics_<ticker>.json (sync for GET).
    """
    if compute_metrics is None:
        logger.error("compute_metrics import failed:\n%s", _import_error)
        raise HTTPException(status_code=500, detail="compute_metrics not available. Check server logs.")

    # Try cache
    if use_cache:
        cached = _get_cached(ticker)
        if cached is not None:
            out = dict(cached)
            out["_cached"] = True
            out["_cached_at"] = time.time()
            logger.info("Cache hit for %s", ticker)
            return out

    # Not cached -> compute
    try:
        metrics = compute_metrics(ticker)
    except Exception as e:
        logger.exception("Error computing metrics for %s", ticker)
        raise HTTPException(status_code=500, detail=str(e))

    # cache the fresh result
    try:
        _set_cache(ticker, metrics)
    except Exception:
        logger.exception("Failed to set cache for %s", ticker)

    # optional save
    if save:
        fname = f"metrics_{ticker}.json"
        try:
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=2, ensure_ascii=False)
            logger.info("Saved metrics to %s", fname)
        except Exception:
            logger.exception("Failed to save metrics file %s", fname)

    return metrics


@app.post("/metrics", tags=["metrics"])
async def post_metrics(req: TickerRequest, save: Optional[bool] = False,
                       use_cache: Optional[bool] = True, background_tasks: BackgroundTasks = None):
    """Post with body {"ticker":"AAPL"}. Set save=true to write a JSON file in background.

    By default use_cache=True: if cached value exists it will be returned. To force refresh set use_cache=false.
    """
    ticker = req.ticker
    if compute_metrics is None:
        logger.error("compute_metrics import failed:\n%s", _import_error)
        raise HTTPException(status_code=500, detail="compute_metrics not available. Check server logs.")

    if use_cache:
        cached = _get_cached(ticker)
        if cached is not None:
            out = dict(cached)
            out["_cached"] = True
            out["_cached_at"] = time.time()
            logger.info("Cache hit for %s (POST)", ticker)
            return out

    try:
        metrics = compute_metrics(ticker)
    except Exception as e:
        logger.exception("Error computing metrics for %s", ticker)
        raise HTTPException(status_code=500, detail=str(e))

    # update cache with fresh result
    try:
        _set_cache(ticker, metrics)
    except Exception:
        logger.exception("Failed to set cache for %s", ticker)

    if save and background_tasks is not None:
        def _save(m: Dict[str, Any], t: str):
            fname = f"metrics_{t}.json"
            try:
                with open(fname, "w", encoding="utf-8") as f:
                    json.dump(m, f, indent=2, ensure_ascii=False)
                logger.info("Saved metrics to %s", fname)
            except Exception:
                logger.exception("Failed to save metrics file %s", fname)

        background_tasks.add_task(_save, metrics, ticker)

    return metrics


@app.get("/cache", tags=["cache"])
async def view_cache():
    """View current cache keys and age (for debugging)."""
    now = time.time()
    out = {k: {"age_seconds": now - v["ts"]} for k, v in CACHE.items()}
    return out


@app.post("/cache/clear", tags=["cache"])
async def clear_cache(ticker: Optional[str] = Query(None)):
    """Clear cache. If `ticker` is provided, clears only that key; otherwise clears all."""
    if ticker:
        removed = CACHE.pop(ticker.upper(), None)
        return {"cleared": bool(removed), "ticker": ticker.upper()}
    else:
        CACHE.clear()
        return {"cleared": True, "all": True}


# Helpful debug endpoint to show import status (useful if compute_metrics import fails)
@app.get("/debug/import", tags=["debug"])
async def debug_import():
    if compute_metrics is None:
        return {"ok": False, "error": _import_error}
    return {"ok": True, "msg": "compute_metrics available"}

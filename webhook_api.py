#!/usr/bin/env python3
"""
webhook_api.py

FastAPI webhook that returns derived metrics for any ticker by reusing
compute_metrics() from get_aapl_metrics.py. Designed for easy debugging:
- run with --reload
- logs exceptions and returns structured JSON
- supports POST /metrics with JSON body {"ticker":"AAPL"}
- supports GET /metrics/{ticker}
- optional save parameter to write metrics_<ticker>.json in working dir

Run (from Experiments, with venv activated):
  uvicorn webhook_api:app --reload --host 127.0.0.1 --port 8000

Docs: http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json
import logging

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


app = FastAPI(title="Ticker Metrics API", version="0.1")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook_api")


@app.get("/", tags=["health"])
async def root():
    return {"status": "ok", "message": "Ticker Metrics API. See /docs."}


@app.get("/metrics/{ticker}", tags=["metrics"])
async def get_metrics(ticker: str, save: Optional[bool] = False, background: Optional[bool] = True):
    """Get metrics for ticker (GET)."""
    if compute_metrics is None:
        logger.error("compute_metrics import failed:\n%s", _import_error)
        raise HTTPException(status_code=500, detail="compute_metrics not available. Check server logs.")
    try:
        metrics = compute_metrics(ticker)
    except Exception as e:
        logger.exception("Error computing metrics for %s", ticker)
        raise HTTPException(status_code=500, detail=str(e))

    if save and background:
        # schedule a background save to avoid blocking
        # FastAPI's BackgroundTasks isn't available in GET handler signature easily; write sync
        fname = f"metrics_{ticker}.json"
        try:
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=2, ensure_ascii=False)
            logger.info("Saved metrics to %s", fname)
        except Exception:
            logger.exception("Failed to save metrics file %s", fname)

    return metrics


@app.post("/metrics", tags=["metrics"])
async def post_metrics(req: TickerRequest, save: Optional[bool] = False, background_tasks: BackgroundTasks = None):
    """Post with body {"ticker":"AAPL"}. Set save=true to write a JSON file in background."""
    ticker = req.ticker
    if compute_metrics is None:
        logger.error("compute_metrics import failed:\n%s", _import_error)
        raise HTTPException(status_code=500, detail="compute_metrics not available. Check server logs.")
    try:
        metrics = compute_metrics(ticker)
    except Exception as e:
        logger.exception("Error computing metrics for %s", ticker)
        raise HTTPException(status_code=500, detail=str(e))

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


# Helpful debug endpoint to show import status (useful if compute_metrics import fails)
@app.get("/debug/import", tags=["debug"])
async def debug_import():
    if compute_metrics is None:
        return {"ok": False, "error": _import_error}
    return {"ok": True, "msg": "compute_metrics available"}

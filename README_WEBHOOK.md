Webhook (FastAPI) — README

This provides a small FastAPI service that exposes derived metrics for any ticker.

Files:
- webhook_api.py — FastAPI app. Endpoints:
  - GET /metrics/{ticker}  -> returns metrics JSON
  - POST /metrics with JSON {"ticker":"AAPL"} -> returns metrics JSON
  - Optional query/body param: save=true to write metrics_<ticker>.json
  - /docs for interactive API docs

Run (from Experiments, with venv activated):
  source .venv/bin/activate
  uvicorn webhook_api:app --reload --host 127.0.0.1 --port 8000

Debugging tips:
- Use --reload to get auto-restarts on code changes.
- Check /debug/import to confirm compute_metrics imported correctly.
- Add logging or attach debugger in your IDE to webhook_api.py; compute_metrics is synchronous so it's easy to step into.

Sample curl calls:
  curl -X GET 'http://127.0.0.1:8000/metrics/AAPL'
  curl -X POST -H 'Content-Type: application/json' -d '{"ticker":"AAPL"}' 'http://127.0.0.1:8000/metrics'
  curl -X POST -H 'Content-Type: application/json' -d '{"ticker":"AAPL"}' 'http://127.0.0.1:8000/metrics?save=true'

Notes:
- The service imports compute_metrics() from get_aapl_metrics.py so keep that file in the same folder.
- JSON files created by save are written to the Experiments working directory.
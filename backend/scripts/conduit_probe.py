#!/usr/bin/env python
"""Discovery probe for the Conduit@Empathy API - run once the key arrives and paste the output.

    cd backend && python scripts/conduit_probe.py [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--days 1]

Prints: HTTP status, top-level JSON type / keys, row count, the first 2 rows and the set of column
names.  Bypasses the cache.  Never prints the API key or e-mail.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.providers.weather.conduit_api import DEFAULT_URL, ConduitApiClient, ConduitError  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="fromdate", type=date.fromisoformat)
    ap.add_argument("--to", dest="todate", type=date.fromisoformat)
    ap.add_argument("--days", type=int, default=1)
    args = ap.parse_args()
    s = get_settings()
    if not s.conduit_api_key or not s.conduit_email:
        print("CONDUIT_API_KEY / CONDUIT_EMAIL not set in backend/.env", file=sys.stderr)
        return 2
    todate = args.todate or date.today()
    fromdate = args.fromdate or todate - timedelta(days=args.days - 1)
    client = ConduitApiClient(s.conduit_api_key, s.conduit_email, s.conduit_api_url or DEFAULT_URL, retries=1)
    print(f"POST {client.url}  fromdate={fromdate} todate={todate}  (key/email: set, not shown)")
    try:
        resp = client.request_raw(fromdate, todate)
    except ConduitError as exc:
        print(f"transport failure: {exc}")
        return 1
    print(f"HTTP {resp.status_code}  content-type={resp.headers.get('content-type')}  bytes={len(resp.content)}")
    try:
        payload = resp.json()
    except ValueError:
        print("NOT JSON. First 300 chars of body:")
        print(resp.text[:300])
        return 1
    print(f"top-level type: {type(payload).__name__}")
    if isinstance(payload, dict):
        print(f"top-level keys: {list(payload.keys())[:30]}")
        for k, v in payload.items():
            if not isinstance(v, (list, dict)):
                print(f"  {k} = {str(v)[:120]}")
    rows = ConduitApiClient.extract_rows(payload)
    print(f"rows: {len(rows)}")
    cols: set[str] = set()
    for r in rows:
        cols.update(r.keys())
    print(f"columns ({len(cols)}): {sorted(cols)}")
    for i, r in enumerate(rows[:2]):
        print(f"row[{i}]: {json.dumps(r, ensure_ascii=False)[:1200]}")
    if rows:
        from app.ingest import geocsv, resample

        recs = geocsv.normalise_rows(rows)
        mapped = geocsv.build_column_map(rows[0].keys())
        print(f"mapped columns: {mapped}")
        print(f"normalised records: {len(recs)}; first: {recs[0] if recs else None}")
        days = resample.daily(recs, min_records=1)
        print(f"daily rows: {len(days)}; first: {days[0] if days else None}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""Pull Conduit@Empathy history in <=7-day chunks into backend/data/cache and rebuild data/conduit_daily.csv.

    cd backend && python scripts/conduit_backfill.py --from 2026-06-01 --to 2026-09-03 [--no-cache] [--min-records 12]

Existing daily rows outside the pulled range are kept; overlapping dates are replaced.  If a raw GeoCSV export
(data/conduit_raw.csv) exists it is merged too, so file and API data end up in one daily table.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.ingest import geocsv, resample  # noqa: E402
from app.providers.weather import backend_path  # noqa: E402
from app.providers.weather.conduit_api import DEFAULT_URL, ConduitApiClient, ConduitError  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="fromdate", type=date.fromisoformat, required=True)
    ap.add_argument("--to", dest="todate", type=date.fromisoformat, default=date.today())
    ap.add_argument("--no-cache", action="store_true", help="ignore cached windows and re-download")
    ap.add_argument("--min-records", type=int, default=12, help="drop days with fewer station records than this")
    ap.add_argument("--out", type=Path, default=None, help="daily CSV path (default: CONDUIT_DAILY_CSV)")
    args = ap.parse_args()
    s = get_settings()
    if not s.conduit_api_key or not s.conduit_email:
        print("CONDUIT_API_KEY / CONDUIT_EMAIL not set in backend/.env", file=sys.stderr)
        return 2
    out = args.out or backend_path(s.conduit_daily_csv)
    client = ConduitApiClient(s.conduit_api_key, s.conduit_email, s.conduit_api_url or DEFAULT_URL, cache_dir=backend_path(s.conduit_cache_dir), cache_ttl_min=s.conduit_cache_ttl_min)
    print(f"pulling {args.fromdate} .. {args.todate} in {client.chunk_days}-day chunks -> cache {client.cache_dir}")
    try:
        rows = client.fetch_range(args.fromdate, args.todate, use_cache=not args.no_cache)
    except ConduitError as exc:
        print(f"FAILED: {exc} (HTTP {exc.status}) body: {exc.body_snippet}", file=sys.stderr)
        return 1
    print(f"api rows: {len(rows)} ({client.requests_made} HTTP requests, rest from cache)")
    recs = geocsv.normalise_rows(rows)
    raw_csv = backend_path(s.conduit_raw_csv)
    if raw_csv.exists():
        recs = geocsv.normalise_rows([*rows, *[]])  # keep API rows as-is
        file_recs = geocsv.parse_geocsv(raw_csv)
        seen = {r["time"] for r in recs}
        recs = sorted([*recs, *[r for r in file_recs if r["time"] not in seen]], key=lambda r: r["time"])
        print(f"merged {len(file_recs)} records from {raw_csv.name}")
    new_days = resample.daily(recs, min_records=args.min_records)
    existing = {r["date"]: r for r in resample.read_daily_csv(out)}
    for d in new_days:
        existing[d["date"]] = d
    merged = [existing[k] for k in sorted(existing)]
    resample.write_daily_csv(merged, out)
    if merged:
        real = [d for d in merged if d.get("temp_max_c") is not None]
        print(f"wrote {out} : {len(merged)} daily rows, {merged[0]['date']} .. {merged[-1]['date']} ({len(new_days)} new/updated)")
        rain = sum(d.get("rainfall_mm") or 0 for d in real[-30:])
        print(f"last 30 days: rain {rain:.1f} mm, Tmax peak {max(d['temp_max_c'] for d in real[-30:]):.1f} C")
    else:
        print("no daily rows produced - check the probe output / min-records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

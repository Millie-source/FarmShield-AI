"""Freeze the OpenAPI spec to docs/openapi.json (the contract the frontend builds against).

    python -m app.export_openapi
"""
from __future__ import annotations

import json
from pathlib import Path

from app.main import app

OUT = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"


def main() -> None:
    spec = app.openapi()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(spec['paths'])} paths, {len(spec['components']['schemas'])} schemas)")


if __name__ == "__main__":
    main()

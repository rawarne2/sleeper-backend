#!/usr/bin/env python
"""Export the FastAPI OpenAPI schema to openapi.json (deterministic; CI checks freshness)."""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("TEST_DATABASE_URI", "sqlite:///:memory:")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402


def main() -> int:
    out = ROOT / "openapi.json"
    out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

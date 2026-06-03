"""Step 1 — run this first on the target machine.

Confirms the Nina API is reachable, prints the response shape, and prints one
sample release so we can verify our metadata-extraction assumptions before
spending hours on enumeration.

    python probe.py
"""
from __future__ import annotations

import json
import sys

import config
from nina_api import NinaSession, _extract_list


def main() -> int:
    s = NinaSession()
    url = f"{config.API_BASE}/releases"
    print(f"GET {url}?limit=2&offset=0")
    try:
        payload = s.get_json(url, params={"limit": 2, "offset": 0})
    except Exception as exc:
        print(f"FAILED: {exc}")
        print("\nIf this is a 403/connection reset, try:")
        print("  - export NINA_USER_AGENT='Mozilla/5.0 ...'")
        print("  - check that api.ninaprotocol.com is reachable: curl -v https://api.ninaprotocol.com/v1/releases?limit=1")
        return 1

    print("\n--- top-level keys ---")
    if isinstance(payload, dict):
        for k, v in payload.items():
            kind = type(v).__name__
            extra = f" (len={len(v)})" if hasattr(v, "__len__") else ""
            print(f"  {k}: {kind}{extra}")
    else:
        print(f"  (response is a {type(payload).__name__})")

    items = _extract_list(payload)
    if not items:
        print("\nNO RELEASES FOUND in response. Adjust API_BASE or _extract_list().")
        return 2

    sample = items[0]
    print(f"\n--- sample release keys ---")
    if isinstance(sample, dict):
        for k in sample.keys():
            print(f"  {k}")
        print("\n--- sample release (truncated JSON) ---")
        dump = json.dumps(sample, indent=2, default=str)
        print(dump if len(dump) < 4000 else dump[:4000] + "\n... [truncated] ...")

    total = payload.get("total") if isinstance(payload, dict) else None
    if total is not None:
        print(f"\nReported total releases: {total}")
    print("\nIf the sample looks right, run:  python enumerate.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

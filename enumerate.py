"""Step 2 — walk the API and save every release to index.json.

Resumable: writes a sidecar `.partial` file as it goes, atomically renames at
the end. If you interrupt it, just re-run; it restarts from offset 0 but Nina's
API is fast for the metadata pass (no audio downloaded here).

    python enumerate.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from tqdm import tqdm

import config
from nina_api import NinaSession, iter_releases
from extract import normalize_release


def main() -> int:
    s = NinaSession()
    out_path: Path = config.INDEX_PATH
    partial = out_path.with_suffix(out_path.suffix + ".partial")

    print(f"Enumerating releases from {config.API_BASE}/releases ...")
    print(f"Writing to: {out_path}")

    seen_ids: set[str] = set()
    normalized: list[dict] = []
    raw_kept: list[dict] = []

    bar = tqdm(unit=" releases", desc="enumerate")
    try:
        for raw in iter_releases(s):
            n = normalize_release(raw)
            rid = n.get("id")
            if not rid or rid in seen_ids:
                continue
            seen_ids.add(rid)
            normalized.append(n)
            raw_kept.append(raw)
            bar.update(1)

            # checkpoint every 500 so a crash doesn't lose hours of work
            if len(normalized) % 500 == 0:
                _write(partial, normalized, raw_kept)
    finally:
        bar.close()

    if not normalized:
        print("Got zero releases. Check probe.py output and adjust nina_api.py / extract.py.")
        return 1

    _write(partial, normalized, raw_kept)
    partial.replace(out_path)
    print(f"Wrote {len(normalized)} releases to {out_path}")
    print("Next:  python download.py")
    return 0


def _write(path: Path, normalized: list[dict], raw: list[dict]) -> None:
    payload = {
        "version": 1,
        "count": len(normalized),
        "releases": normalized,
        "_raw": raw,  # kept so we never lose a field we forgot to extract
    }
    path.write_text(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    sys.exit(main())

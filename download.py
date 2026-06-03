"""Step 4 — download audio + art + metadata for every release in index.json.

Safe to interrupt and re-run: progress.json tracks per-release completion.
Failures are logged to failures.log; retry by re-running.

    python download.py             # download everything
    python download.py --limit 10  # just the first 10 (smoke test)
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

import config
from extract import pick_preferred_audio
from nina_api import NinaSession, arweave_url, guess_extension


_progress_lock = threading.Lock()
_failures_lock = threading.Lock()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="only download first N releases (smoke test)")
    ap.add_argument("--retry-failed", action="store_true", help="re-attempt releases logged in failures.log")
    args = ap.parse_args()

    if not config.INDEX_PATH.exists():
        print(f"No {config.INDEX_PATH}. Run probe.py and enumerate.py first.")
        return 1

    index = json.loads(config.INDEX_PATH.read_text())
    releases = index["releases"]
    if args.limit:
        releases = releases[: args.limit]

    progress = _load_progress()
    if args.retry_failed:
        # drop failed entries from progress so they're retried
        for rid in _failed_ids():
            progress.pop(rid, None)

    config.RELEASES_DIR.mkdir(parents=True, exist_ok=True)

    todo = [r for r in releases if progress.get(r["id"], {}).get("status") != "done"]
    print(f"{len(todo)} of {len(releases)} releases left to download (parallel={config.PARALLEL_DOWNLOADS})")

    session = NinaSession()  # one shared connection pool for HTTP keepalive

    bar = tqdm(total=len(todo), unit=" releases", desc="download")
    with ThreadPoolExecutor(max_workers=config.PARALLEL_DOWNLOADS) as pool:
        futures = {pool.submit(_download_one, session, r): r for r in todo}
        for fut in as_completed(futures):
            r = futures[fut]
            try:
                result = fut.result()
                _record_progress(r["id"], result)
            except Exception as exc:
                _record_progress(r["id"], {"status": "failed", "error": str(exc)})
                _log_failure(r["id"], str(exc))
            bar.update(1)
    bar.close()

    done = sum(1 for v in progress.values() if v.get("status") == "done")
    failed = sum(1 for v in progress.values() if v.get("status") == "failed")
    print(f"\nDone: {done}   Failed: {failed}   See {config.FAILURES_PATH} for failure details.")
    print("Re-run anytime to resume.  Use --retry-failed to retry failures.")
    return 0


def _download_one(session: NinaSession, release: dict) -> dict:
    rid = release["id"]
    rdir = config.RELEASES_DIR / _safe_dirname(rid)
    rdir.mkdir(parents=True, exist_ok=True)

    # 1. metadata.json (always)
    (rdir / "metadata.json").write_text(json.dumps(release, indent=2, default=str))

    # 2. cover art (best-effort; non-fatal if missing)
    art_uri = release.get("image_uri")
    cover_path = None
    if art_uri:
        ext = guess_extension(art_uri)
        cover_path = rdir / f"cover.{ext}"
        if not cover_path.exists() or cover_path.stat().st_size == 0:
            _stream_with_gateway_fallback(session, art_uri, cover_path)

    # 3. audio (preferred format; required)
    audio = pick_preferred_audio(release.get("audio_files") or [])
    if not audio:
        return {"status": "failed", "error": "no audio file in metadata"}

    audio_uri = audio["uri"]
    ext = guess_extension(audio_uri, mime=audio.get("type"))
    audio_path = rdir / f"audio.{ext}"
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        bytes_written = _stream_with_gateway_fallback(session, audio_uri, audio_path)
    else:
        bytes_written = audio_path.stat().st_size

    return {
        "status": "done",
        "audio_path": str(audio_path.relative_to(config.ROOT)),
        "audio_format": ext,
        "audio_bytes": bytes_written,
        "cover_path": str(cover_path.relative_to(config.ROOT)) if cover_path else None,
    }


def _stream_with_gateway_fallback(session: NinaSession, uri: str, dest: Path) -> int:
    """Try each Arweave gateway in turn until one works.
    Streams to a .part file and renames atomically so a kill mid-write doesn't
    leave us with a half-file that looks complete."""
    last_exc: Exception | None = None
    tmp = dest.with_suffix(dest.suffix + ".part")
    for i in range(len(config.ARWEAVE_GATEWAYS)):
        url = arweave_url(uri, gateway_index=i)
        try:
            with open(tmp, "wb") as fh:
                written = session.stream_to_file(url, fh)
            tmp.replace(dest)
            return written
        except Exception as exc:
            last_exc = exc
            if tmp.exists():
                tmp.unlink()
    raise RuntimeError(f"all gateways failed for {uri}: {last_exc}")


def _safe_dirname(rid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(rid))[:128]


def _load_progress() -> dict:
    if config.PROGRESS_PATH.exists():
        return json.loads(config.PROGRESS_PATH.read_text())
    return {}


def _record_progress(rid: str, result: dict) -> None:
    with _progress_lock:
        progress = _load_progress()
        progress[rid] = result
        tmp = config.PROGRESS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(progress, indent=2, default=str))
        tmp.replace(config.PROGRESS_PATH)


def _log_failure(rid: str, error: str) -> None:
    with _failures_lock:
        with open(config.FAILURES_PATH, "a") as fh:
            fh.write(f"{rid}\t{error}\n")


def _failed_ids() -> set[str]:
    if not config.FAILURES_PATH.exists():
        return set()
    out = set()
    for line in config.FAILURES_PATH.read_text().splitlines():
        if line.strip():
            out.add(line.split("\t", 1)[0])
    return out


if __name__ == "__main__":
    sys.exit(main())

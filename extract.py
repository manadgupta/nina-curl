"""Pull the bits we care about (audio uri, art uri, title, artist, etc.) out
of a raw Nina release object. Tolerates several known shapes of the response.

Returns a normalized dict; missing fields are None / [].
"""
from __future__ import annotations

from typing import Any

import config


def normalize_release(raw: dict) -> dict:
    """Return a small, predictable shape regardless of which API version this came from."""
    md = raw.get("metadata") or raw.get("metadataJson") or {}
    if isinstance(md, str):  # some endpoints return JSON-as-string
        import json
        try:
            md = json.loads(md)
        except Exception:
            md = {}

    release_id = (
        raw.get("publicKey")
        or raw.get("releasePublicKey")
        or raw.get("id")
        or md.get("symbol")
        or md.get("name")
    )

    title = md.get("name") or raw.get("title")
    artist = (
        md.get("properties", {}).get("artist")
        if isinstance(md.get("properties"), dict) else None
    ) or raw.get("artist") or _maybe_artist_from_publisher(raw)

    description = md.get("description")
    image_uri = md.get("image") or raw.get("image") or raw.get("cover")

    audio_files = _extract_audio_files(md, raw)

    return {
        "id": release_id,
        "title": title,
        "artist": artist,
        "description": description,
        "image_uri": image_uri,
        "audio_files": audio_files,        # list of {"uri": str, "type": str|None, "track": str|None}
        "raw_metadata": md,                 # keep full metadata for the per-release file
    }


def _maybe_artist_from_publisher(raw: dict) -> str | None:
    pub = raw.get("publisherAccount") or raw.get("publisher") or {}
    if isinstance(pub, dict):
        return pub.get("displayName") or pub.get("handle")
    return None


def _extract_audio_files(metadata: dict, raw: dict) -> list[dict]:
    files: list[dict] = []
    props = metadata.get("properties") if isinstance(metadata, dict) else None
    if isinstance(props, dict):
        for f in props.get("files", []) or []:
            uri = f.get("uri") or f.get("url")
            if not uri:
                continue
            files.append({
                "uri": uri,
                "type": (f.get("type") or "").lower() or None,
                "track_number": f.get("track") if isinstance(f.get("track"), int) else None,
                "track_title": f.get("track_title") or f.get("trackTitle") or None,
            })
    # fallbacks seen in older payloads
    for key in ("audio", "trackUri"):
        v = raw.get(key)
        if isinstance(v, str) and v and not any(x["uri"] == v for x in files):
            files.append({"uri": v, "type": None, "track_number": None, "track_title": None})
    return files


def pick_preferred_audio_per_track(audio_files: list[dict]) -> list[dict]:
    """Group by track_number, pick the preferred-format file within each group.

    For releases without track numbers (legacy / single-track), each entry is
    its own group. Returns list ordered by track number.
    """
    if not audio_files:
        return []

    groups: dict = {}
    for i, f in enumerate(audio_files):
        key = f.get("track_number") if f.get("track_number") is not None else f"_solo_{i}"
        groups.setdefault(key, []).append(f)

    chosen: list[dict] = []
    for key, items in groups.items():
        chosen.append(sorted(items, key=_format_rank)[0])

    chosen.sort(key=lambda f: (f.get("track_number") is None, f.get("track_number") or 0))
    return chosen


def _format_rank(f: dict) -> int:
    ext = _ext_from_audio(f)
    try:
        return config.AUDIO_FORMAT_PREFERENCE.index(ext)
    except ValueError:
        return len(config.AUDIO_FORMAT_PREFERENCE) + 1


def _ext_from_audio(f: dict) -> str:
    t = (f.get("type") or "").lower()
    if "mpeg" in t or "mp3" in t:
        return "mp3"
    if "mp4" in t:
        return "mp4"
    if "wav" in t:
        return "wav"
    if "flac" in t:
        return "flac"
    if "aac" in t:
        return "aac"
    if "ogg" in t:
        return "ogg"
    uri = f.get("uri") or ""
    if "." in uri.rsplit("/", 1)[-1]:
        return uri.rsplit(".", 1)[-1].lower()
    return ""

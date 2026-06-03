"""Thin wrapper over Nina's public HTTP API + Arweave gateways.

Kept dumb on purpose: every function does one thing, no global state, easy to
swap out if the API shape we assumed turns out to be wrong.
"""
from __future__ import annotations

import time
from typing import Any, Iterator
from urllib.parse import urlparse

import requests

import config


class NinaSession:
    def __init__(self) -> None:
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": config.USER_AGENT, "Accept": "application/json"})

    def get_json(self, url: str, params: dict | None = None) -> Any:
        last_exc: Exception | None = None
        for attempt in range(config.MAX_RETRIES):
            try:
                r = self.s.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", "10"))
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()
            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
                time.sleep(2 ** attempt)
        raise RuntimeError(f"GET {url} failed after {config.MAX_RETRIES} retries: {last_exc}")

    def stream_to_file(self, url: str, dest, chunk_size: int = 1 << 16) -> int:
        """Stream a URL to an open binary file handle. Returns bytes written."""
        with self.s.get(url, stream=True, timeout=config.REQUEST_TIMEOUT) as r:
            r.raise_for_status()
            written = 0
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:
                    dest.write(chunk)
                    written += len(chunk)
            return written


def iter_releases(session: NinaSession) -> Iterator[dict]:
    """Yield every release from the Nina API, walking limit/offset pagination.

    The endpoint shape we assume (confirmed on the public site as of writing):
        GET {API_BASE}/releases?limit=N&offset=M
        -> {"releases": [...], "total": N}  OR  {"data": [...]}
    `probe.py` verifies this before a real run.
    """
    offset = 0
    seen = 0
    while True:
        payload = session.get_json(
            f"{config.API_BASE}/releases",
            params={"limit": config.PAGE_SIZE, "offset": offset},
        )
        batch = _extract_list(payload)
        if not batch:
            return
        for item in batch:
            yield item
            seen += 1
        if len(batch) < config.PAGE_SIZE:
            return
        offset += config.PAGE_SIZE


def _extract_list(payload: Any) -> list[dict]:
    """Nina's responses have varied between {releases:[...]} and {data:[...]}.
    Accept either; fall back to bare list."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("releases", "data", "items", "results"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def arweave_url(tx_or_uri: str, gateway_index: int = 0) -> str:
    """Normalize whatever the API gives us into a fetchable URL.

    Accepts: full https URLs, ar:// URIs, or bare 43-char Arweave tx IDs.
    """
    if not tx_or_uri:
        raise ValueError("empty arweave reference")
    gw = config.ARWEAVE_GATEWAYS[gateway_index % len(config.ARWEAVE_GATEWAYS)].rstrip("/")
    if tx_or_uri.startswith(("http://", "https://")):
        return tx_or_uri
    if tx_or_uri.startswith("ar://"):
        return f"{gw}/{tx_or_uri[5:]}"
    return f"{gw}/{tx_or_uri}"


def guess_extension(uri: str, mime: str | None = None) -> str:
    """Best-effort extension from URL path or MIME type. Lowercase, no dot."""
    if mime:
        mime = mime.lower()
        if "/" in mime:
            sub = mime.split("/", 1)[1]
            sub = sub.split(";")[0].strip()
            if sub == "mpeg":
                return "mp3"
            if sub == "mp4":
                return "mp4"
            if sub in ("x-wav", "wave"):
                return "wav"
            if sub == "x-flac":
                return "flac"
            return sub
    path = urlparse(uri).path
    if "." in path:
        return path.rsplit(".", 1)[1].lower()
    return "bin"

"""Shared config for the Nina archive scripts.

Override any of these with environment variables of the same name, e.g.:
    NINA_API_BASE=https://api.ninaprotocol.com/v1 python enumerate.py
"""
import os
from pathlib import Path

API_BASE = os.environ.get("NINA_API_BASE", "https://services.ninaprotocol.com/v1")

ARWEAVE_GATEWAYS = os.environ.get(
    "NINA_ARWEAVE_GATEWAYS",
    "https://arweave.net,https://gateway.irys.xyz,https://ar-io.net",
).split(",")

ROOT = Path(os.environ.get("NINA_ARCHIVE_ROOT", Path(__file__).parent)).resolve()
RELEASES_DIR = ROOT / "releases"
INDEX_PATH = ROOT / "index.json"
PROGRESS_PATH = ROOT / "progress.json"
FAILURES_PATH = ROOT / "failures.log"

PAGE_SIZE = int(os.environ.get("NINA_PAGE_SIZE", "100"))
PARALLEL_DOWNLOADS = int(os.environ.get("NINA_PARALLEL", "6"))
REQUEST_TIMEOUT = int(os.environ.get("NINA_TIMEOUT", "60"))
MAX_RETRIES = int(os.environ.get("NINA_RETRIES", "5"))

USER_AGENT = os.environ.get(
    "NINA_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
)

# Audio format preference: first match wins. Lowercase extensions, no dot.
AUDIO_FORMAT_PREFERENCE = ["mp3", "mp4", "m4a", "aac", "ogg", "opus", "wav", "flac", "aiff"]

# downina

Personal archive of the public Nina Protocol catalog (audio + art + metadata).
Code only — no downloaded data is committed (see `.gitignore`).

## What you'll end up with

```
<NINA_ARCHIVE_ROOT>/
  index.json              # master list of every release
  progress.json           # resumable per-release state
  failures.log            # release IDs that didn't download
  releases/
    <release-id>/
      audio.mp3           # preferred: mp3/mp4; falls back to wav/flac
      cover.jpg
      metadata.json
```

## Setup (on the machine that will do the downloads)

```bash
cd downina
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Requires: Python 3.9+, ~400 GB free disk (estimate; depends on catalog size and
how many releases are lossless-only).

## Run, in order

```bash
# 1. Verify the API works and the response shape matches our assumptions.
python probe.py

# 2. Walk every release, save the master manifest. Cheap, ~1-2 hours.
python enumerate.py

# 3. Smoke-test the downloader on 10 releases first.
python download.py --limit 10

# 4. Real run. Resumable; safe to interrupt and re-run.
python download.py
```

## Tuning

All knobs are env vars (see `config.py`):

| var                   | default                            | what                                          |
|-----------------------|------------------------------------|-----------------------------------------------|
| `NINA_ARCHIVE_ROOT`   | this directory                     | where `releases/` lives — point at ext drive  |
| `NINA_API_BASE`       | `https://api.ninaprotocol.com/v1`  | API host                                      |
| `NINA_ARWEAVE_GATEWAYS` | `arweave.net,gateway.irys.xyz,ar-io.net` | tried in order on failure              |
| `NINA_PARALLEL`       | `6`                                | concurrent downloads                          |
| `NINA_PAGE_SIZE`      | `100`                              | API pagination size                           |
| `NINA_RETRIES`        | `5`                                | per-request retries                           |

Example to put data on an external drive:

```bash
NINA_ARCHIVE_ROOT=/Volumes/MyDrive/nina-archive python download.py
```

## When something breaks

- **probe.py prints a 403 / connection-reset** — Nina is rate-limiting or fronting
  with Vercel's bot check. Set a real browser User-Agent:
  `export NINA_USER_AGENT="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ..."`
- **probe.py prints "NO RELEASES FOUND"** — the response shape changed. Print
  `payload` in `_extract_list()` and adjust the keys it looks for.
- **Many failures in failures.log** — usually Arweave gateway flakes. Re-run
  `python download.py --retry-failed`.
- **Disk filled up** — move `releases/` to an external drive and set
  `NINA_ARCHIVE_ROOT` to its parent.

## Not included

- Account-specific data (purchases, follows, hubs you own) — out of scope.
- Local frontend / browseable site — that's "Part 2", not in this directory.

# downina

Personal archive of the public Nina Protocol catalog — every release's audio
tracks + cover art + metadata, saved to a local folder. Nina is winding down;
this is a one-shot mirror so you keep the music after the site goes away.

Code only — no downloaded data is committed (see `.gitignore`).

## TL;DR

```bash
./run.sh setup                                                 # one-time
NINA_ARCHIVE_ROOT=/Volumes/MyDrive/nina ./run.sh smoke         # 10 releases
NINA_ARCHIVE_ROOT=/Volumes/MyDrive/nina ./run.sh download      # everything
```

The full catalog is ~38,800 releases and roughly **2 TB** on disk. Plan to
point `NINA_ARCHIVE_ROOT` at an external drive.

## What you'll end up with

```
<NINA_ARCHIVE_ROOT>/
  index.json                   # master list of every release
  progress.json                # resumable per-release state
  failures.log                 # release IDs that didn't download
  releases/
    <release-id>/
      audio.mp3                # single-track release
      cover.jpg                # full-resolution
      metadata.json
    <release-id>/
      track_01_<title>.mp3     # multi-track album
      track_02_<title>.mp3
      ...
      cover.jpg
      metadata.json
```

Audio format preference: `mp3 > mp4 > m4a > aac > ogg > opus > wav > flac`.
WAV is only used when no MP3 exists for that track.

## Prerequisites

- **Python 3.9+** (`python3 --version` to check). If missing:
  - macOS: `brew install python@3.11`  *(or download the installer from [python.org](https://www.python.org/downloads/))*
  - Ubuntu/Debian: `sudo apt install python3 python3-venv`
  - Fedora/RHEL: `sudo dnf install python3`
  - Windows: download the installer from [python.org](https://www.python.org/downloads/) and check "Add Python to PATH"
- **`bash`** (any modern Mac/Linux shell — on Windows use Git Bash or WSL)
- **~2 TB free disk** (point `NINA_ARCHIVE_ROOT` at an external drive)

## Setup (one-time, on the machine doing the downloads)

```bash
cd downina
./run.sh setup
```

`./run.sh setup` checks Python is installed, then creates a venv, installs
deps, and downloads a Chromium for the fallback browser enumerator (~150 MB).

## Run

```bash
./run.sh probe        # 1. confirm API is reachable + see a sample release
./run.sh enumerate    # 2. walk the API, write index.json (~38,800 releases)
./run.sh smoke        # 3. download 10 releases as a sanity check
./run.sh download     # 4. full run — resumable, safe to Ctrl-C
./run.sh status       # progress so far
./run.sh retry        # re-attempt anything in failures.log
```

The full download takes 1-3 days depending on network. It's resumable: if you
interrupt it, just run `./run.sh download` again — it picks up via
`progress.json`.

## If the API is blocked on your network

The script defaults to `services.ninaprotocol.com` (the live API). Some
networks (corp VPN, certain ISPs) block specific Nina hosts. If `./run.sh
probe` times out or returns 403/429:

```bash
./run.sh enumerate-browser           # uses headless Chromium + stealth patches
./run.sh enumerate-browser --headful # watch the browser work
```

The browser path drives a real Chromium against `ninaprotocol.com/explore` and
sniffs the rendered network traffic. Slower than the API path, but works
anywhere the website itself loads. Same `index.json` output — `download.py`
runs identically afterwards.

The downloads themselves go to `nina-file-service.s3.us-east-2.amazonaws.com`
(separate host from the API), so even if the API is blocked, the audio fetches
typically work fine.

## Tuning (env vars)

| var                     | default                                              | what                                                        |
|-------------------------|------------------------------------------------------|-------------------------------------------------------------|
| `NINA_ARCHIVE_ROOT`     | this directory                                       | where `releases/` lives — point at an external drive        |
| `NINA_API_BASE`         | `https://services.ninaprotocol.com/v1`               | API host                                                    |
| `NINA_ARWEAVE_GATEWAYS` | `arweave.net,gateway.irys.xyz,ar-io.net`             | gateway fallback list for any `ar://` references            |
| `NINA_PARALLEL`         | `6`                                                  | concurrent release downloads                                |
| `NINA_PAGE_SIZE`        | `100`                                                | API pagination size                                         |
| `NINA_RETRIES`          | `5`                                                  | per-request retries                                         |
| `NINA_TIMEOUT`          | `60`                                                 | per-request timeout (seconds)                               |
| `NINA_USER_AGENT`       | a real Chrome UA                                     | override if you hit 403                                     |

Example using an external drive and more parallelism:

```bash
NINA_ARCHIVE_ROOT=/Volumes/MyDrive/nina NINA_PARALLEL=12 ./run.sh download
```

## When something breaks

- **`probe` times out or resets** — network blocks the API host. Use
  `./run.sh enumerate-browser` instead.
- **`probe` returns 403/429** — rate-limited. Wait 10-15 min, or use the
  browser enumerator.
- **`enumerate` reports "NO RELEASES FOUND"** — Nina changed the response
  shape. Print `payload` in `_extract_list()` (`nina_api.py`) and adjust keys.
- **`enumerate-browser` captures 0 releases and shows "Vercel Security
  Checkpoint"** — stealth patches got stale. Try `--headful` to watch; you
  may need to update `playwright-stealth`.
- **Many entries in `failures.log`** — usually transient S3/Arweave flakes.
  Run `./run.sh retry`.
- **Disk fills up mid-run** — move the partial `releases/` to a bigger drive,
  set `NINA_ARCHIVE_ROOT` to its parent, re-run `./run.sh download` to resume.

## What's not in here

- Account-specific data (your purchases, follows, hubs you own) — out of
  scope; the public catalog is.
- A local browseable frontend — code is downloader-only. Building a local UI
  on top of the archive would be a separate project.

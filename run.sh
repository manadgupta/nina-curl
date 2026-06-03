#!/usr/bin/env bash
# One-shot driver for downina. Run from inside the downina/ directory:
#   ./run.sh setup       # create venv + install deps (run once)
#   ./run.sh probe       # step 1: verify API
#   ./run.sh enumerate   # step 2: build index.json
#   ./run.sh smoke       # step 3: download 10 releases
#   ./run.sh download    # step 4: full download (resumable)
#   ./run.sh retry       # re-attempt anything in failures.log
#   ./run.sh status      # show counts + disk usage
#   ./run.sh all         # setup -> probe -> enumerate -> smoke (pauses for ok before full)

set -euo pipefail

cd "$(dirname "$0")"

VENV=".venv"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

log()  { printf '\n=== %s ===\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

ensure_venv() {
    [ -x "$PY" ] || fail "venv missing — run: $0 setup"
}

confirm() {
    read -r -p "$1 [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]]
}

cmd_setup() {
    log "creating venv at $VENV"
    python3 -m venv "$VENV"
    log "installing requirements"
    "$PIP" install --upgrade pip >/dev/null
    "$PIP" install -r requirements.txt
    log "setup done"
}

cmd_probe() {
    ensure_venv
    log "probing Nina API"
    "$PY" probe.py
}

cmd_enumerate() {
    ensure_venv
    log "enumerating all releases (this takes 1-2 hours)"
    "$PY" enumerate.py
}

cmd_smoke() {
    ensure_venv
    [ -f index.json ] || fail "index.json not found — run: $0 enumerate"
    log "smoke test: downloading 10 releases"
    "$PY" download.py --limit 10
    log "check ./releases/ — play one audio file to confirm"
}

cmd_download() {
    ensure_venv
    [ -f index.json ] || fail "index.json not found — run: $0 enumerate"
    log "full download (resumable; safe to Ctrl-C and re-run)"
    "$PY" download.py
}

cmd_retry() {
    ensure_venv
    log "retrying failures"
    "$PY" download.py --retry-failed
}

cmd_status() {
    if [ -f index.json ]; then
        total=$("$PY" -c "import json; print(json.load(open('index.json'))['count'])" 2>/dev/null || echo "?")
        echo "index.json: $total releases"
    else
        echo "index.json: missing"
    fi
    if [ -f progress.json ]; then
        done_n=$("$PY" -c "import json; p=json.load(open('progress.json')); print(sum(1 for v in p.values() if v.get('status')=='done'))" 2>/dev/null || echo "?")
        fail_n=$("$PY" -c "import json; p=json.load(open('progress.json')); print(sum(1 for v in p.values() if v.get('status')=='failed'))" 2>/dev/null || echo "?")
        echo "progress.json: $done_n done, $fail_n failed"
    else
        echo "progress.json: missing"
    fi
    if [ -d releases ]; then
        echo "releases/: $(find releases -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ') folders, $(du -sh releases 2>/dev/null | cut -f1) on disk"
    fi
}

cmd_all() {
    [ -x "$PY" ] || cmd_setup
    cmd_probe
    if ! confirm "probe looks good — continue to enumerate?"; then exit 0; fi
    cmd_enumerate
    if ! confirm "enumerate done — run smoke test (10 releases)?"; then exit 0; fi
    cmd_smoke
    if ! confirm "smoke test done — start FULL download (could take days)?"; then exit 0; fi
    cmd_download
}

usage() {
    sed -n '2,12p' "$0"
    exit 1
}

case "${1:-}" in
    setup)     cmd_setup ;;
    probe)     cmd_probe ;;
    enumerate) cmd_enumerate ;;
    smoke)     cmd_smoke ;;
    download)  cmd_download ;;
    retry)     cmd_retry ;;
    status)    cmd_status ;;
    all)       cmd_all ;;
    *)         usage ;;
esac

"""Browser-driven enumeration via Playwright.

Used when api.ninaprotocol.com is blocked from your network but ninaprotocol.com
itself is reachable. A real Chromium loads /explore, scrolls to the bottom, and
captures every API response in the network log. Same output shape as
enumerate.py, so download.py works unchanged.

    python enumerate_browser.py
    python enumerate_browser.py --limit 30      # stop after capturing N releases (smoke test)
    python enumerate_browser.py --headful       # show the browser window (debugging)
    python enumerate_browser.py --start-url https://www.ninaprotocol.com/explore
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import config
from extract import normalize_release


EXPLORE_URL = "https://www.ninaprotocol.com/explore"

# Any response whose URL contains one of these substrings is treated as
# potentially containing release data. We then sniff the JSON body for a
# releases-shaped payload before keeping it.
API_URL_HINTS = ("ninaprotocol.com/v1/", "/releases", "/hubs", "/accounts")

# Stop scrolling when this many consecutive scroll attempts produce no new
# releases. Higher = more thorough, slower.
NO_PROGRESS_BUDGET = 8

# How long to wait after each scroll for the network to settle (seconds).
SCROLL_SETTLE_SECS = 2.5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="stop after capturing N releases")
    ap.add_argument("--headful", action="store_true", help="show browser window")
    ap.add_argument("--start-url", default=EXPLORE_URL)
    ap.add_argument("--max-scroll-minutes", type=int, default=120,
                    help="hard cap on total scroll time")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed. Run:")
        print("  pip install playwright")
        print("  playwright install chromium")
        return 1

    seen: dict[str, dict] = {}   # release id -> normalized
    seen_raw: dict[str, dict] = {}

    def maybe_capture(payload, source_url: str) -> int:
        """Try to extract releases from a JSON payload. Returns count of new releases added."""
        added = 0
        for raw in _iter_release_objects(payload):
            n = normalize_release(raw)
            rid = n.get("id")
            if not rid or rid in seen:
                continue
            seen[rid] = n
            seen_raw[rid] = raw
            added += 1
        return added

    try:
        from playwright_stealth import Stealth
        stealth_factory = Stealth()
    except ImportError:
        stealth_factory = None

    # A real Mac Chrome UA helps; matches the Chromium build Playwright ships.
    real_chrome_ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    )
    ua = config.USER_AGENT if "Mozilla" in config.USER_AGENT else real_chrome_ua

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=not args.headful,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent=ua,
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        page = ctx.new_page()
        if stealth_factory:
            stealth_factory.apply_stealth_sync(page)
        else:
            print("(playwright-stealth not installed — proceeding without stealth patches)")

        seen_url_log: list[str] = []

        def on_response(response):
            url = response.url
            ctype = (response.headers.get("content-type") or "").lower()
            if "json" in ctype or any(h in url for h in API_URL_HINTS):
                seen_url_log.append(f"{response.status} {ctype.split(';')[0]:30} {url}")
            if not any(h in url for h in API_URL_HINTS):
                return
            try:
                body = response.json()
            except Exception:
                return
            new_count = maybe_capture(body, url)
            if new_count:
                print(f"  +{new_count:>3} (total {len(seen)}) <- {url[:100]}")

        page.on("response", on_response)

        print(f"Opening {args.start_url} ...")
        resp = page.goto(args.start_url, wait_until="domcontentloaded", timeout=60_000)
        if resp:
            print(f"  HTTP {resp.status}  ({len(resp.body() or b'')} bytes body)")
        title = page.title()
        print(f"  page title: {title!r}")
        body_text = page.evaluate("document.body ? document.body.innerText.slice(0, 200) : ''")
        print(f"  body preview: {body_text!r}")

        # Try to grab anything embedded in the initial HTML (e.g. SSR'd __NEXT_DATA__).
        try:
            initial = page.evaluate("""() => {
                const el = document.getElementById('__NEXT_DATA__');
                return el ? el.textContent : null;
            }""")
            if initial:
                try:
                    blob = json.loads(initial)
                    new = maybe_capture(blob, "__NEXT_DATA__")
                    if new:
                        print(f"  +{new} from __NEXT_DATA__ (total {len(seen)})")
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

        print("Scrolling to load all releases. Ctrl-C to stop early.")
        deadline = time.monotonic() + args.max_scroll_minutes * 60
        no_progress = 0
        last_count = len(seen)

        try:
            while True:
                if args.limit and len(seen) >= args.limit:
                    print(f"Reached --limit {args.limit}, stopping.")
                    break
                if time.monotonic() > deadline:
                    print("Hit --max-scroll-minutes, stopping.")
                    break

                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(int(SCROLL_SETTLE_SECS * 1000))

                if len(seen) == last_count:
                    no_progress += 1
                    if no_progress >= NO_PROGRESS_BUDGET:
                        print(f"No new releases after {NO_PROGRESS_BUDGET} scrolls — done.")
                        break
                else:
                    no_progress = 0
                    last_count = len(seen)
        except KeyboardInterrupt:
            print("\nStopped by user. Saving what we have...")
        finally:
            browser.close()

    if not seen:
        print("Captured zero releases. Did the page load? Try --headful to watch.")
        print("\n--- last 40 JSON-ish responses observed ---")
        for line in seen_url_log[-40:]:
            print(line)
        if not seen_url_log:
            print("(no JSON or hint-matching responses at all — page likely blocked or didn't load)")
        return 2

    payload = {
        "version": 1,
        "count": len(seen),
        "releases": list(seen.values()),
        "_raw": list(seen_raw.values()),
        "_source": "playwright_browser",
    }
    config.INDEX_PATH.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nWrote {len(seen)} releases to {config.INDEX_PATH}")
    print("Next:  python download.py --limit 10   (smoke test)")
    return 0


def _iter_release_objects(payload):
    """Yield anything that looks like a single release dict, anywhere in the payload tree."""
    if isinstance(payload, dict):
        if _looks_like_release(payload):
            yield payload
            return
        for v in payload.values():
            yield from _iter_release_objects(v)
    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_release_objects(item)


def _looks_like_release(obj: dict) -> bool:
    """Heuristic: must have an ID-shaped field AND either metadata or audio refs."""
    if not isinstance(obj, dict):
        return False
    has_id = any(k in obj for k in ("publicKey", "releasePublicKey", "id"))
    if not has_id:
        return False
    has_release_signal = (
        "metadata" in obj
        or "metadataJson" in obj
        or "publisherAccount" in obj
        or "hubReleases" in obj
    )
    return has_release_signal


if __name__ == "__main__":
    sys.exit(main())

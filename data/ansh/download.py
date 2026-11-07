#!/usr/bin/env python3
"""
Download every CityBus board packet listed in packets.csv.

Run this on your own machine (the sandbox can't reach in.gov):

    python3 fetch_packets.py              # regular monthly packets only
    python3 fetch_packets.py --all        # include special meetings
    python3 fetch_packets.py --only 2024  # just one year

Already-downloaded files are skipped, so it is safe to re-run after a failure.
PDFs land in ./pdfs/ named <meeting_no>_<meeting_date>.pdf
"""

import argparse
import csv
import os
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "packets.csv")
OUTDIR = os.path.join(HERE, "pdfs")

# Generic client name. Do not put a personal email here.
UA = "citybus-capstone-research/1.0"
TIMEOUT = 60
RETRIES = 3
PAUSE = 1.0          # seconds between downloads, to be polite to the host
MIN_BYTES = 50_000   # a real packet is hundreds of KB; anything smaller is an error page


CURL = shutil.which("curl")


def ssl_context():
    """
    A verifying context that works on macOS, where a python.org build does not
    read the system keychain. certifi ships the CA bundle that fixes it.
    Verification stays on either way.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


CTX = ssl_context()


def check(body):
    """Is this actually a board packet? Returns (ok, message)."""
    if not body.startswith(b"%PDF"):
        return False, f"not a PDF (got {len(body)} bytes, starts {body[:16]!r})"
    if len(body) < MIN_BYTES:
        return False, f"suspiciously small ({len(body)} bytes)"
    return True, f"{len(body) / 1_000_000:.1f} MB"


def write_out(body, dest):
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(body)
    os.replace(tmp, dest)


def fetch_curl(url, dest):
    """
    Fall back to the system curl, which uses the OS trust store and so works
    where a freshly installed Python does not. Verification stays on.
    """
    if not CURL:
        return False, "curl not found"
    tmp = dest + ".part"
    r = subprocess.run(
        [CURL, "-sSL", "--fail", "--max-time", str(TIMEOUT),
         "-A", UA, "-o", tmp, url],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        return False, f"curl exit {r.returncode}: {r.stderr.strip()[:120]}"
    with open(tmp, "rb") as f:
        body = f.read()
    ok, msg = check(body)
    if not ok:
        os.remove(tmp)
        return False, msg
    os.replace(tmp, dest)
    return True, msg + " (via curl)"


def fetch(url, dest):
    """Download one PDF. Returns (ok, message)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last = ""
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as r:
                body = r.read()
        except ssl.SSLCertVerificationError as e:
            # Python can't verify the chain. The OS almost certainly can.
            ok, msg = fetch_curl(url, dest)
            if ok:
                return True, msg
            return False, f"SSL verify failed and curl fallback failed ({msg}); {e}"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            if isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
                ok, msg = fetch_curl(url, dest)
                if ok:
                    return True, msg
                return False, f"SSL verify failed and curl fallback failed ({msg})"
            last = f"{type(e).__name__}: {e}"
            if attempt < RETRIES:
                time.sleep(2 * attempt)
            continue

        ok, msg = check(body)
        if not ok:
            return False, msg
        write_out(body, dest)
        return True, msg

    return False, last or "unknown error"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="include special meetings and unclassified packets")
    ap.add_argument("--only", metavar="YEAR",
                    help="restrict to one meeting year, e.g. 2024")
    args = ap.parse_args()

    if not os.path.exists(MANIFEST):
        sys.exit(f"packets.csv not found next to this script ({MANIFEST})")
    os.makedirs(OUTDIR, exist_ok=True)

    with open(MANIFEST, newline="") as f:
        rows = list(csv.DictReader(f))

    if not args.all:
        rows = [r for r in rows if r["kind"] == "regular"]
    if args.only:
        rows = [r for r in rows if r["meeting_date"].startswith(args.only)]

    print(f"{len(rows)} packets to consider -> {OUTDIR}\n")
    got = skipped = 0
    failures = []

    for i, r in enumerate(rows, 1):
        dest = os.path.join(OUTDIR, r["local_file"])
        tag = f"[{i:>2}/{len(rows)}] No.{r['meeting_no']} {r['meeting_date']} (reports {r['reported_month'] or '?'})"

        if os.path.exists(dest) and os.path.getsize(dest) >= MIN_BYTES:
            print(f"{tag}  skip, already here")
            skipped += 1
            continue

        ok, msg = fetch(r["url"], dest)
        print(f"{tag}  {'ok  ' + msg if ok else 'FAIL  ' + msg}")
        if ok:
            got += 1
        else:
            failures.append((r["meeting_no"], r["meeting_date"], r["url"], msg))
        time.sleep(PAUSE)

    print(f"\ndownloaded {got}, already had {skipped}, failed {len(failures)}")

    if failures:
        path = os.path.join(HERE, "fetch_failures.csv")
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["meeting_no", "meeting_date", "url", "error"])
            w.writerows(failures)
        print(f"\nFailures written to {path}")
        print("The board page can move or rename a file. Open the page and check the")
        print("link for any packet listed there, then fix its url in packets.csv and re-run:")
        print("  https://www.in.gov/citybuslafayette/about/board-of-directors/")


if __name__ == "__main__":
    main()
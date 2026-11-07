#!/usr/bin/env python3
"""
Survey every downloaded board packet before writing a parser for them.

Answers three questions across all packets at once:
  1. Does each PDF have a real text layer, or is it a scan that needs OCR?
  2. Which of the tables we need are present, and under which heading?
  3. How many distinct layout families are there?

Tries three extractors in order and records which one worked, so a broken
pdftotext shows up as a tooling problem rather than as "everything is scanned":
  pdftotext -layout  (poppler)   brew install poppler
  pdfplumber                     pip3 install pdfplumber
  pypdf                          pip3 install pypdf

Run next to packets.csv, PDFs in ./pdfs/ :

    python3 survey_packets.py
    python3 survey_packets.py --refresh     # ignore the text/ cache
    python3 survey_packets.py --only 717    # one packet, verbose

Writes survey.csv, survey_samples.txt, and text/<name>.txt
"""

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
PDFDIR = os.path.join(HERE, "pdfs")
TXTDIR = os.path.join(HERE, "text")
MANIFEST = os.path.join(HERE, "packets.csv")

ANCHORS = {
    "pnl":        [r"TOTAL OPERATING EXPENSES", r"TOTAL EXPENSES"],
    "revenue":    [r"CASH FARES", r"SEMESTER PASS"],
    "budget":     [r"REMAINING\s+BUDGET", r"BUDGET VS", r"EXPENDITURES TO DATE"],
    "ridership":  [r"P/\s?Hrs", r"P/\s?Mi", r"PASSENGERS PER HOUR"],
    "operations": [r"OVERTIME IN HOURS", r"PAID HOURS"],
    "roadcalls":  [r"ROAD\s?CALL"],
    "fuel":       [r"CNG", r"DIESEL"],
    "payroll":    [r"GROSS (WAGES|PAY)", r"PAYROLL"],
}

MEETING_NO = re.compile(r"BOARD MEETING NO\.?\s*(\d{3})", re.I)
CENTS = re.compile(r"\d,\d{3}\.\d{2}\b")


# ---------------------------------------------------------------- extractors

def try_pdftotext(pdf):
    exe = shutil.which("pdftotext")
    if not exe:
        return "", "pdftotext not on PATH"
    try:
        r = subprocess.run([exe, "-layout", pdf, "-"],
                           capture_output=True, text=True,
                           errors="replace", timeout=180)
    except subprocess.TimeoutExpired:
        return "", "pdftotext timed out"
    except Exception as e:
        return "", f"pdftotext failed to launch: {e}"
    if r.returncode != 0:
        return "", f"pdftotext exit {r.returncode}: {(r.stderr or '').strip()[:200]}"
    if not r.stdout.strip():
        return "", f"pdftotext produced no output; stderr: {(r.stderr or '').strip()[:200]}"
    return r.stdout, ""


def try_pdfplumber(pdf):
    try:
        import pdfplumber
    except ImportError:
        return "", "pdfplumber not installed (pip3 install pdfplumber)"
    try:
        out = []
        with pdfplumber.open(pdf) as doc:
            for page in doc.pages:
                out.append(page.extract_text(layout=True) or "")
        text = "\n".join(out)
        return (text, "") if text.strip() else ("", "pdfplumber found no text")
    except Exception as e:
        return "", f"pdfplumber error: {type(e).__name__}: {e}"[:200]


def try_pypdf(pdf):
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", "pypdf not installed (pip3 install pypdf)"
    try:
        reader = PdfReader(pdf)
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception:
                return "", "PDF is encrypted"
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        return (text, "") if text.strip() else ("", "pypdf found no text")
    except Exception as e:
        return "", f"pypdf error: {type(e).__name__}: {e}"[:200]


ENGINES = [("pdftotext", try_pdftotext),
           ("pdfplumber", try_pdfplumber),
           ("pypdf", try_pypdf)]


def extract(pdf, cache, refresh, verbose):
    """Returns (text, engine, note). Caches whatever worked."""
    meta = cache + ".engine"
    if not refresh and os.path.exists(cache) and os.path.getsize(cache) > 0:
        eng = open(meta).read().strip() if os.path.exists(meta) else "cache"
        return open(cache, encoding="utf-8", errors="replace").read(), eng, ""

    notes = []
    for name, fn in ENGINES:
        text, err = fn(pdf)
        if verbose:
            print(f"    {name}: {'ok, %d chars' % len(text) if text else err}")
        if text:
            with open(cache, "w", encoding="utf-8") as f:
                f.write(text)
            with open(meta, "w") as f:
                f.write(name)
            return text, name, "; ".join(notes)
        notes.append(f"{name}: {err}")
    return "", "none", "; ".join(notes)


# ---------------------------------------------------------------- inspection

def find_line(text, patterns):
    for pat in patterns:
        rx = re.compile(pat, re.I)
        for line in text.splitlines():
            if rx.search(line):
                return line.strip()[:160], pat
    return "", ""


def ridership_header(text):
    for line in text.splitlines():
        if re.search(r"P/\s?Hrs", line, re.I):
            return re.sub(r"\s{2,}", " | ", line.strip())[:160]
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="ignore the text/ cache")
    ap.add_argument("--only", metavar="SUBSTR", help="one packet, with per-engine detail")
    args = ap.parse_args()

    if not os.path.isdir(PDFDIR):
        sys.exit(f"no pdfs/ directory at {PDFDIR}")
    os.makedirs(TXTDIR, exist_ok=True)

    exe = shutil.which("pdftotext")
    print(f"pdftotext : {exe or 'NOT FOUND (brew install poppler)'}")
    if exe:
        v = subprocess.run([exe, "-v"], capture_output=True, text=True)
        print(f"            {((v.stderr or v.stdout).splitlines() or [''])[0].strip()}")
    for mod in ("pdfplumber", "pypdf"):
        try:
            __import__(mod)
            print(f"{mod:<10}: available")
        except ImportError:
            print(f"{mod:<10}: not installed")
    print()

    wanted = {}
    if os.path.exists(MANIFEST):
        with open(MANIFEST, newline="") as f:
            wanted = {r["local_file"]: r for r in csv.DictReader(f)}

    pdfs = sorted(f for f in os.listdir(PDFDIR) if f.lower().endswith(".pdf"))
    if args.only:
        pdfs = [p for p in pdfs if args.only in p]
    if not pdfs:
        sys.exit(f"no matching PDFs in {PDFDIR}")

    rows, samples = [], []
    for name in pdfs:
        path = os.path.join(PDFDIR, name)
        size = os.path.getsize(path)
        if args.only:
            print(f"{name}  ({size:,} bytes on disk)")
        text, engine, note = extract(
            path, os.path.join(TXTDIR, name[:-4] + ".txt"), args.refresh, bool(args.only))
        alnum = sum(c.isalnum() for c in text)
        meta = wanted.get(name, {})
        m = MEETING_NO.search(text)

        row = {
            "file": name,
            "meeting_no": m.group(1) if m else meta.get("meeting_no", ""),
            "reported_month": meta.get("reported_month", ""),
            "pdf_bytes": size,
            "chars": alnum,
            "engine": engine,
            "scanned": "YES" if (engine != "none" and alnum < 5000) else "",
            "error": "" if engine != "none" else note[:300],
            "pnl_cents": "yes" if CENTS.search(text) else "no",
        }
        sample = [f"=== {name}  (reports {row['reported_month'] or '?'}, "
                  f"{size:,} bytes, {alnum:,} chars via {engine})"]
        if engine == "none":
            sample.append(f"  NO TEXT EXTRACTED -- {note}")

        for key, pats in ANCHORS.items():
            line, pat = find_line(text, pats)
            row[key] = "y" if line else "-"
            sample.append(f"  {key:<11} [{pat}]  {line}" if line
                          else f"  {key:<11} NOT FOUND")

        rh = ridership_header(text)
        row["ridership_header"] = rh
        if rh:
            sample.append(f"  ridership header:  {rh}")
        rows.append(row)
        samples.append("\n".join(sample))

        flag = "NO TEXT " if engine == "none" else ("SCANNED " if row["scanned"] else "")
        print(f"{name:<26} {alnum:>8,} chars  {engine:<11}{flag}"
              f"{''.join(row[k] for k in ANCHORS)}")

    cols = (["file", "meeting_no", "reported_month", "pdf_bytes", "chars",
             "engine", "scanned", "error", "pnl_cents"]
            + list(ANCHORS) + ["ridership_header"])
    with open(os.path.join(HERE, "survey.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(HERE, "survey_samples.txt"), "w", encoding="utf-8") as f:
        f.write("\n\n".join(samples))

    notext = [r for r in rows if r["engine"] == "none"]
    scanned = [r["file"] for r in rows if r["scanned"]]
    fams = Counter((r["pnl_cents"], r["ridership_header"][:80])
                   for r in rows if r["engine"] != "none")

    print(f"\n{len(rows)} packets surveyed")
    print(f"engines used            : "
          f"{dict(Counter(r['engine'] for r in rows))}")
    print(f"no text extracted at all: {len(notext)}")
    if notext:
        print(f"   first error: {notext[0]['error']}")
        print("   Every extractor failing on every file means a tooling problem,")
        print("   not 57 scanned packets. Try:  python3 survey_packets.py --only 717")
    print(f"scanned / thin text     : {len(scanned)}"
          + (f"  -> {', '.join(scanned)}" if scanned else ""))
    print(f"distinct layout families: {len(fams)}")
    for (cents, hdr), n in fams.most_common():
        print(f"   {n:>3} packets  cents={cents}  {hdr or '(no ridership header)'}")
    print("\nWrote survey.csv and survey_samples.txt")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Extract the ridership-by-route table from every downloaded packet and write one
tidy route x month table, with verification.

    python3 run_ridership.py                 # every packet in packets.csv
    python3 run_ridership.py --only 2026     # one year
    python3 run_ridership.py --strict        # drop packets that fail checks

Writes:
    ridership_route_month.csv   one row per route per month
    ridership_verify.log        every check, pass or fail, per packet
    ridership_failures.csv      packets that could not be parsed

Verification per packet, before anything is written:
  1. numbered-route passengers, miles and hours each re-sum to the printed
     subtotal (display rounding of a unit or two is tolerated and logged)
  2. every printed P/Hrs and P/Mi is reproduced from its own printed
     components
A packet failing (1) is reported and, under --strict, excluded.
"""

import argparse
import csv
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdfplumber                                           # noqa: E402
import colgrid as cg                                        # noqa: E402
import ridership                                            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PDFDIR = os.path.join(HERE, "pdfs")
MANIFEST = os.path.join(HERE, "packets.csv")

OUT = os.path.join(HERE, "ridership_route_month.csv")
LOG = os.path.join(HERE, "ridership_verify.log")
FAIL = os.path.join(HERE, "ridership_failures.csv")

TOTAL_KEYS = {"SUBTOTAL_REGULAR", "SUBTOTAL_EXPRESS", "MB_TOTAL", "DR_TOTAL",
              "VP_TOTAL", "GRAND_TOTAL"}
HOURS_SWING = 0.40      # month-over-month change that earns a review flag


def num(s):
    """Printed cell -> float, or None. Blank and '-' stay missing, never zero."""
    try:
        return cg.number(s)
    except ValueError:
        return None


def check_packet(rows, log):
    """Round 1: internal consistency. Returns (ok, n_checks, n_hard_fails)."""
    by = {k: v for k, _, v in rows}
    checks = fails = 0

    groups = {}
    for k, _, v in rows:
        g = v.get("group", "")
        if not g:
            continue
        if k.startswith("SUBTOTAL"):
            groups.setdefault(g, {})["total"] = (k, v)
        elif k not in TOTAL_KEYS and k not in ("DR", "VP", "ACCESS"):
            groups.setdefault(g, {}).setdefault("rows", []).append(v)

    if not groups:
        log.append("      FAIL      no route groups found")
        fails += 1
    for g in sorted(groups):
        blk = groups[g]
        if "total" not in blk or "rows" not in blk:
            continue
        name, sub = blk["total"]
        for field, tol in (("passengers", 1.0), ("total_miles", 0.05),
                           ("total_hours", 0.05)):
            parts = [num(r.get(field)) for r in blk["rows"]]
            parts = [p for p in parts if p is not None]
            printed = num(sub.get(field))
            if printed is None or not parts:
                continue
            checks += 1
            diff = sum(parts) - printed
            if abs(diff) > tol:
                if abs(diff) <= max(tol * 40, 2.0):
                    log.append(f"      rounding  {name} {field}: components "
                               f"{sum(parts):,.2f} vs printed {printed:,.2f} ({diff:+.2f})")
                else:
                    fails += 1
                    log.append(f"      FAIL      {name} {field}: components "
                               f"{sum(parts):,.2f} vs printed {printed:,.2f} ({diff:+.2f})")
    for key, _, v in rows:
        pax, hrs, mi = num(v.get("passengers")), num(v.get("total_hours")), num(v.get("total_miles"))
        for printed_f, denom, label in (("pax_per_hour", hrs, "P/Hrs"),
                                        ("pax_per_mile", mi, "P/Mi")):
            printed = num(v.get(printed_f))
            if printed is None or pax is None or not denom:
                continue
            checks += 1
            want = pax / denom
            if abs(want - printed) > max(0.05, abs(printed) * 0.01):
                fails += 1
                log.append(f"      FAIL      {key} {label}: printed {printed} "
                           f"vs {pax:,.0f}/{denom:,.2f} = {want:.2f}")
    return fails == 0, checks, fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", metavar="YEAR")
    ap.add_argument("--strict", action="store_true",
                    help="exclude packets that fail a consistency check")
    args = ap.parse_args()

    with open(MANIFEST, newline="") as f:
        packets = [r for r in csv.DictReader(f)
                   if r["kind"] == "regular" and r["reported_month"]]
    if args.only:
        packets = [p for p in packets if p["meeting_date"].startswith(args.only)]
    packets.sort(key=lambda p: p["reported_month"])

    out_rows, log, failures = [], [], []
    for p in packets:
        path = os.path.join(PDFDIR, p["local_file"])
        tag = f"{p['reported_month']}  (No.{p['meeting_no']})"
        if not os.path.exists(path):
            failures.append((p["meeting_no"], p["reported_month"], "PDF not downloaded"))
            continue
        try:
            with pdfplumber.open(path) as d:
                page = d.pages[cg.find_page(d, "P/Hrs")]
                rows = ridership.parse(page)
        except Exception as e:
            failures.append((p["meeting_no"], p["reported_month"],
                             f"{type(e).__name__}: {e}"))
            print(f"{tag}  PARSE FAILED  {type(e).__name__}: {e}")
            log.append(f"{tag}\n      PARSE FAILED\n{traceback.format_exc()}")
            continue

        log.append(f"{tag}  {len(rows)} rows")
        ok, checks, fails = check_packet(rows, log)
        if ok:
            log.append(f"      {checks} checks, all pass")
        if not ok and args.strict:
            failures.append((p["meeting_no"], p["reported_month"],
                             f"{fails} consistency failures"))
            print(f"{tag}  {len(rows):>3} rows  {checks:>3} checks  "
                  f"{fails} FAILED - excluded")
            continue
        print(f"{tag}  {len(rows):>3} rows  {checks:>3} checks"
              + (f"  {fails} FAILED" if fails else "  ok"))

        for key, name, v in rows:
            out_rows.append({
                "month": p["reported_month"],
                "meeting_no": p["meeting_no"],
                "route_key": key,
                "route_name": name,
                "is_total": "y" if key in TOTAL_KEYS else "",
                "passengers": v.get("passengers", ""),
                "total_miles": v.get("total_miles", ""),
                "total_hours": v.get("total_hours", ""),
                "pax_per_mile": v.get("pax_per_mile", ""),
                "pax_per_hour": v.get("pax_per_hour", ""),
                "pax_per_mile_pct_diff": v.get("pax_per_mile_pct_diff", ""),
                "pax_per_hour_pct_diff": v.get("pax_per_hour_pct_diff", ""),
                "group": v.get("group", ""),
                "consistency": "pass" if ok else "review",
                "hours_swing_flag": "",
            })

    # month-over-month hours swing, the fault seen on routes 42/43 in Sep 2026
    prev = {}
    for r in out_rows:
        if r["is_total"]:
            continue
        h = num(r["total_hours"])
        last = prev.get(r["route_key"])
        if h and last and abs(h - last) / last > HOURS_SWING:
            r["hours_swing_flag"] = f"{(h - last) / last:+.0%}"
            log.append(f"{r['month']}  hours swing  route {r['route_key']}: "
                       f"{last:,.2f} -> {h:,.2f} ({(h - last) / last:+.0%})")
        if h:
            prev[r["route_key"]] = h

    if out_rows:
        with open(OUT, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0]))
            w.writeheader()
            w.writerows(out_rows)
    with open(LOG, "w") as f:
        f.write("\n".join(log))
    if failures:
        with open(FAIL, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["meeting_no", "reported_month", "error"])
            w.writerows(failures)

    months = sorted({r["month"] for r in out_rows})
    service = [r for r in out_rows if not r["is_total"]]
    flagged = [r for r in service if r["hours_swing_flag"]]
    review = sorted({r["month"] for r in out_rows if r["consistency"] == "review"})

    print(f"\npackets parsed   : {len(months)} of {len(packets)}")
    if months:
        print(f"months covered   : {months[0]} .. {months[-1]}")
    print(f"rows written     : {len(out_rows)}  ({len(service)} route rows)")
    print(f"packets to review: {len(review)}" + (f"  {review}" if review else ""))
    print(f"hours-swing flags: {len(flagged)}")
    for r in flagged[:10]:
        print(f"   {r['month']}  route {r['route_key']:<5} {r['hours_swing_flag']}")
    if failures:
        print(f"\nfailed packets   : {len(failures)}  -> {FAIL}")
    print(f"\n{OUT}\n{LOG}")


if __name__ == "__main__":
    main()

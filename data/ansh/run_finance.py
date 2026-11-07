#!/usr/bin/env python3
"""
Build finance_month.csv from every downloaded packet, then fit Model C.

    python3 run_finance.py

Writes:
    finance_month.csv      one row per month: expense lines + revenue hours
    pnl_line_month.csv     one row per P&L line per month (the audit trail)
    finance_verify.log

Model C regresses the expense that actually moves with service - operator and
maintenance wages, their fringe, fuel, vehicle parts, tyres, oil - on revenue
hours. Total expense is roughly 38% fixed, so regressing it on hours yields a
slope dominated by whatever else was trending, and on our two sample months
even comes out negative.
"""

import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdfplumber                                            # noqa: E402
import colgrid as cg                                         # noqa: E402
import pnl as pnl_mod                                        # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PDFDIR = os.path.join(HERE, "pdfs")

# Expense lines that scale with how much service is operated.
DIRECT = [r"OPERATOR WAGES", r"MAINTENANCE WAGES", r"DIESEL", r"NATURAL GAS FUEL",
          r"HYDROGEN", r"GASOLINE", r"OIL & ANTIFREEZE", r"REPAIR PARTS.*REVENUE",
          r"TIRES"]
# Fringe rides with payroll; apportioned by the service share of total wages.
FRINGE = [r"^FICA", r"^PERF", r"LIFE & HEALTH", r"UNEMPLOYMENT", r"WORK COMP",
          r"UNFORMS|UNIFORMS", r"TOOL ALLOWANCE"]
ADMIN_WAGE = r"ADMINISTRATIVE WAGES"
TOTAL_EXP = r"^TOTAL EXPENSES$"


def pick(lines, patterns):
    hits = {}
    for label, v in lines.items():
        for p in patterns:
            if re.search(p, label):
                hits[label] = v
                break
    return hits


def total(d):
    s = [v for v in d.values() if v is not None]
    return sum(s) if s else None


def main():
    with open(os.path.join(HERE, "packets.csv"), newline="") as f:
        packets = [r for r in csv.DictReader(f)
                   if r["kind"] == "regular" and r["reported_month"]]
    packets.sort(key=lambda p: p["reported_month"])

    # revenue hours come free from the ridership extraction
    hours = {}
    rp = os.path.join(HERE, "ridership_route_month.csv")
    if os.path.exists(rp):
        for r in csv.DictReader(open(rp, newline="")):
            if r["route_key"] == "GRAND_TOTAL":
                hours[r["month"]] = cg.number(r["total_hours"])
    else:
        print("note: ridership_route_month.csv not found - run run_ridership.py "
              "first, or Model C has no revenue hours to regress against.\n")

    out, detail, log = [], [], []
    for p in packets:
        path = os.path.join(PDFDIR, p["local_file"])
        month = p["reported_month"]
        if not os.path.exists(path):
            continue
        try:
            with pdfplumber.open(path) as d:
                rows, fields = pnl_mod.parse(d.pages[pnl_mod.find(d)])
        except Exception as e:
            log.append(f"{month}  PARSE FAILED  {type(e).__name__}: {e}")
            print(f"{month}  PARSE FAILED  {type(e).__name__}: {e}")
            continue

        lines = {}
        for order, section, item, v in rows:
            key = item.upper()
            try:
                val = cg.number(v.get("month_cur"))
            except ValueError:
                val = None
            lines.setdefault(key, val)
            detail.append({"month": month, "order": order, "section": section,
                           "line_item": item,
                           **{f: v.get(f, "") for f in fields}})

        direct = pick(lines, DIRECT)
        fringe = pick(lines, FRINGE)
        svc_wage = sum(v for k, v in lines.items()
                       if re.search(r"OPERATOR WAGES|MAINTENANCE WAGES", k) and v)
        adm_wage = sum(v for k, v in lines.items()
                       if re.search(ADMIN_WAGE, k) and v)
        share = svc_wage / (svc_wage + adm_wage) if (svc_wage + adm_wage) else None
        f_tot = total(fringe)
        d_tot = total(direct)
        variable = (d_tot or 0) + ((f_tot or 0) * share if share else 0)
        tot_exp = next((v for k, v in lines.items() if re.fullmatch(TOTAL_EXP, k)), None)

        out.append({
            "month": month,
            "meeting_no": p["meeting_no"],
            "revenue_hours": f"{hours[month]:.2f}" if hours.get(month) else "",
            "total_operating_expense": f"{tot_exp:.2f}" if tot_exp else "",
            "variable_expense": f"{variable:.2f}" if variable else "",
            "direct_service_expense": f"{d_tot:.2f}" if d_tot else "",
            "fringe_pool": f"{f_tot:.2f}" if f_tot else "",
            "service_wage_share": f"{share:.4f}" if share else "",
            "operator_wages": lines.get("OPERATOR WAGES") or "",
            "maintenance_wages": lines.get("MAINTENANCE WAGES") or "",
            "administrative_wages": adm_wage or "",
            "n_direct_lines": len(direct),
            "n_fringe_lines": len(fringe),
        })
        print(f"{month}  total {tot_exp or 0:>12,.0f}   variable {variable:>12,.0f}"
              f"   hours {hours.get(month) or 0:>9,.2f}   "
              f"({len(direct)} direct, {len(fringe)} fringe lines)")

    for name, data in (("finance_month.csv", out), ("pnl_line_month.csv", detail)):
        if data:
            with open(os.path.join(HERE, name), "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(data[0]))
                w.writeheader()
                w.writerows(data)
    with open(os.path.join(HERE, "finance_verify.log"), "w") as f:
        f.write("\n".join(log))

    fit = [(cg.number(r["revenue_hours"]), cg.number(r["variable_expense"]))
           for r in out if r["revenue_hours"] and r["variable_expense"]]
    print(f"\nmonths written : {len(out)}")
    print(f"usable for fit : {len(fit)}")
    if len(fit) >= 3:
        n = len(fit)
        mx = sum(x for x, _ in fit) / n
        my = sum(y for _, y in fit) / n
        sxx = sum((x - mx) ** 2 for x, _ in fit)
        sxy = sum((x - mx) * (y - my) for x, y in fit)
        b = sxy / sxx
        a = my - b * mx
        ss_t = sum((y - my) ** 2 for _, y in fit)
        ss_r = sum((y - (a + b * x)) ** 2 for x, y in fit)
        print(f"\nModel C  variable_expense = {a:,.0f} + {b:,.2f} x revenue_hours")
        print(f"         marginal cost per revenue hour : ${b:,.2f}")
        print(f"         intercept (should be near zero): ${a:,.0f}")
        print(f"         R^2 : {1 - ss_r / ss_t:.3f}   n = {n}")
        print(f"\n  sanity check: slope x 12 x mean monthly hours = "
              f"${b * 12 * mx:,.0f} a year")
        print("  compare against $10,515,589, the FY2026 budget's variable lines.")
    else:
        print("\nNot enough months yet to fit Model C.")


if __name__ == "__main__":
    main()

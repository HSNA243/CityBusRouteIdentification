#!/usr/bin/env python3
"""
Model C: does monthly operating cost scale with monthly service hours?

Fits variable_expense ~ revenue_hours by ordinary least squares over several
month subsets, so the effect of excluding the known-bad packets is visible
rather than assumed. Then computes the accounting alternative.

    python3 model_c.py

Reads finance_month.csv, written by run_finance.py.
"""

import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Packets whose extraction failed verification; see ridership_verify.log.
#   2022-11, 2022-12  GRAND_TOTAL hours read from the wrong column
#   2024-01           whole table shifted one column
#   2026-04           only 2 rows parsed
EXCLUDE = {"2022-11", "2022-12", "2024-01", "2026-04"}

# FY2026 budget, from 07_budget_vs_actual. The variable figure is the lines
# that move with service: operator and maintenance wages, their share of
# fringe, fuel, vehicle parts, tyres, oil.
BUDGET_VARIABLE = 10_515_589
BUDGET_TOTAL = 16_996_092

FREED_HOURS_PER_MONTH = 903.76     # routes 35 + 36, deleted 2026-08-24
BOARD_ESTIMATE = 530_000


def num(s):
    s = (s or "").replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def ols(pairs):
    """(slope, intercept, r2, n) for y ~ x."""
    n = len(pairs)
    mx = sum(x for x, _ in pairs) / n
    my = sum(y for _, y in pairs) / n
    sxx = sum((x - mx) ** 2 for x, _ in pairs)
    sxy = sum((x - mx) * (y - my) for x, y in pairs)
    b = sxy / sxx
    a = my - b * mx
    sst = sum((y - my) ** 2 for _, y in pairs)
    ssr = sum((y - (a + b * x)) ** 2 for x, y in pairs)
    return b, a, (1 - ssr / sst if sst else float("nan")), n


def main():
    path = os.path.join(HERE, "finance_month.csv")
    if not os.path.exists(path):
        sys.exit("finance_month.csv not found - run run_finance.py first")
    rows = list(csv.DictReader(open(path, newline="")))

    def subset(keep):
        out = []
        for r in rows:
            h, v = num(r["revenue_hours"]), num(r["variable_expense"])
            if h and v and keep(r["month"]):
                out.append((h, v))
        return out

    print("Model C - variable_expense ~ revenue_hours, ordinary least squares\n")
    print(f"{'subset':<44}{'n':>4}{'slope':>11}{'intercept':>14}{'R2':>8}")
    for label, keep in (
        ("all months", lambda m: True),
        ("minus packets that failed verification",
         lambda m: m not in EXCLUDE),
        ("2023-03 onward, minus those",
         lambda m: m >= "2023-03" and m not in EXCLUDE),
        ("post-redesign only (2025-08 onward)",
         lambda m: m >= "2025-08" and m not in EXCLUDE),
    ):
        pairs = subset(keep)
        if len(pairs) < 3:
            print(f"{label:<44}{len(pairs):>4}   too few months")
            continue
        b, a, r2, n = ols(pairs)
        print(f"{label:<44}{n:>4}{b:>11,.2f}{a:>14,.0f}{r2:>8.3f}")

    main_set = subset(lambda m: m >= "2023-03" and m not in EXCLUDE)
    main_set.sort()
    print(f"\nlowest and highest service months in the main subset:")
    for h, v in main_set[:3] + main_set[-3:]:
        print(f"   {h:>9,.0f} hours   {v:>11,.0f} variable expense")
    lo, hi = main_set[0], main_set[-1]
    print(f"   hours +{(hi[0] / lo[0] - 1) * 100:.0f}%, variable expense "
          f"{(hi[1] / lo[1] - 1) * 100:+.0f}%")

    # Accounting alternative: annualise recent hours, divide the budget by it.
    recent = sorted(r["month"] for r in rows
                    if num(r["revenue_hours"]) and r["month"] not in EXCLUDE)[-12:]
    hrs = [num(r["revenue_hours"]) for r in rows if r["month"] in recent]
    annual = sum(hrs) / len(hrs) * 12
    var_hr, tot_hr = BUDGET_VARIABLE / annual, BUDGET_TOTAL / annual

    print(f"\nAccounting estimate")
    print(f"   annualised revenue hours      : {annual:,.0f}"
          f"   ({len(hrs)} months, mean {sum(hrs) / len(hrs):,.0f}/mo)")
    print(f"   variable cost per revenue hour: ${var_hr:,.2f}")
    print(f"   fully allocated per hour      : ${tot_hr:,.2f}")

    print(f"\nRoutes 35 + 36 ({FREED_HOURS_PER_MONTH:,.2f} revenue hours a month)")
    print(f"   fully allocated : {FREED_HOURS_PER_MONTH * tot_hr * 12:>12,.0f} /yr")
    print(f"   variable only   : {FREED_HOURS_PER_MONTH * var_hr * 12:>12,.0f} /yr")
    print(f"   board estimate  : {BOARD_ESTIMATE:>12,.0f} /yr")


if __name__ == "__main__":
    main()

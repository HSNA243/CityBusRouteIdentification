#!/usr/bin/env python3
"""
Figures for the modeling report.

    python3 make_plots.py

Reads finance_month.csv and ridership_route_month.csv, writes PNGs at 200 dpi:

    fig1_model_c_null.png     Model C rejected - cost does not track service hours
    fig2_hours_vs_cost.png    the same point over time, both series indexed
    fig3_savings_methods.png  three estimates of the routes 35/36 saving
    fig4_productivity.png     passengers per revenue hour by route, July 2026
"""

import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                              # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

BLUE, ORANGE, CRITICAL = "#2a78d6", "#eb6834", "#d03b3b"
SURFACE, INK, INK_2 = "#fcfcfb", "#0b0b0b", "#52514e"
MUTED, GRID, BASELINE = "#898781", "#e1e0d9", "#c3c2b7"

EXCLUDE = {"2022-11", "2022-12", "2024-01", "2026-04"}
START = "2023-03"
BUDGET_VARIABLE, BUDGET_TOTAL = 10_515_589, 16_996_092
FREED_HOURS, BOARD = 903.76, 530_000

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "axes.edgecolor": BASELINE, "axes.labelcolor": INK_2,
    "text.color": INK, "xtick.color": INK_2, "ytick.color": INK_2,
    "font.size": 10, "axes.titlesize": 13, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
})


def titles(ax, title, sub):
    ax.set_title(title, loc="left", pad=28 if "\n" not in sub else 40, fontweight="600")
    ax.text(0.0, 1.015, sub, transform=ax.transAxes, ha="left", va="bottom",
            fontsize=9.5, color=INK_2)


def clean(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def num(s):
    s = (s or "").replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def ols(pairs):
    n = len(pairs)
    mx = sum(x for x, _ in pairs) / n
    my = sum(y for _, y in pairs) / n
    sxx = sum((x - mx) ** 2 for x, _ in pairs)
    b = sum((x - mx) * (y - my) for x, y in pairs) / sxx
    a = my - b * mx
    sst = sum((y - my) ** 2 for _, y in pairs)
    ssr = sum((y - (a + b * x)) ** 2 for x, y in pairs)
    return b, a, 1 - ssr / sst, n


def load(name):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        sys.exit(f"{name} not found - run the extraction scripts first")
    return list(csv.DictReader(open(p, newline="")))


def main():
    fin = load("finance_month.csv")
    rid = load("ridership_route_month.csv")

    months = [(r["month"], num(r["revenue_hours"]), num(r["variable_expense"]))
              for r in fin]
    main_set = [(m, h, v) for m, h, v in months
                if h and v and m >= START and m not in EXCLUDE]
    main_set.sort()

    # ---------------- fig 1: the null result -----------------------------
    pairs = [(h, v) for _, h, v in main_set]
    b, a, r2, n = ols(pairs)
    fig, ax = plt.subplots(figsize=(8, 5.2))
    ax.scatter([h for h, _ in pairs], [v / 1000 for _, v in pairs],
               s=46, color=BLUE, alpha=0.75, edgecolor="none", zorder=3,
               label="month")
    xs = [min(h for h, _ in pairs), max(h for h, _ in pairs)]
    ax.plot(xs, [(a + b * x) / 1000 for x in xs], color=ORANGE, lw=2,
            zorder=4, label=f"OLS fit  (slope ${b:,.0f}/hr)")
    ax.set_xlabel("revenue hours in the month")
    ax.set_ylabel("variable operating expense  ($000)")
    titles(ax, "Operating cost does not track service hours",
           f"CityBus board packets, {main_set[0][0]} to {main_set[-1][0]}  ·  "
           f"n = {n} months  ·  R² = {r2:.3f}")
    ax.legend(frameon=False, loc="lower right")
    ax.text(0.02, 0.04,
            "Service hours explain almost none of the\n"
            "month-to-month variation in operating cost.",
            transform=ax.transAxes, fontsize=9.5, color=INK_2, va="bottom")
    clean(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig1_model_c_null.png"), dpi=200)
    plt.close(fig)

    # ---------------- fig 2: the same point over time ---------------------
    fig, ax = plt.subplots(figsize=(10, 4.6))
    labels = [m for m, _, _ in main_set]
    h0 = main_set[0][1]
    v0 = main_set[0][2]
    ax.plot(labels, [h / h0 * 100 for _, h, _ in main_set], color=BLUE, lw=2,
            marker="o", ms=3.5, label="revenue hours")
    ax.plot(labels, [v / v0 * 100 for _, _, v in main_set], color=ORANGE, lw=2,
            marker="o", ms=3.5, label="variable expense")
    ax.axhline(100, color=BASELINE, lw=1)
    ax.set_ylabel(f"index, {main_set[0][0]} = 100")
    titles(ax, "Cost and service move independently",
           "Both series indexed to their first month. Service follows the academic\nyear; cost spikes are accrual timing - insurance renewals, bulk parts orders.")
    step = max(1, len(labels) // 14)
    ax.set_xticks(range(0, len(labels), step))
    ax.set_xticklabels(labels[::step], rotation=45, ha="right", fontsize=8.5)
    ax.legend(frameon=False, ncol=2, loc="upper left")
    clean(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig2_hours_vs_cost.png"), dpi=200)
    plt.close(fig)

    # ---------------- fig 3: three savings estimates ----------------------
    recent = sorted(m for m, h, _ in months if h and m not in EXCLUDE)[-12:]
    hrs = [h for m, h, _ in months if m in recent and h]
    annual = sum(hrs) / len(hrs) * 12
    est = [("Board estimate\n(minutes, July 2026)", BOARD, MUTED),
           ("Variable cost\n($%.2f/hr)" % (BUDGET_VARIABLE / annual),
            FREED_HOURS * (BUDGET_VARIABLE / annual) * 12, BLUE),
           ("Fully allocated\n($%.2f/hr)" % (BUDGET_TOTAL / annual),
            FREED_HOURS * (BUDGET_TOTAL / annual) * 12, CRITICAL)]
    fig, ax = plt.subplots(figsize=(7.4, 5))
    bars = ax.bar([e[0] for e in est], [e[1] / 1e6 for e in est],
                  color=[e[2] for e in est], width=0.56, zorder=3)
    for bar, e in zip(bars, est):
        ax.text(bar.get_x() + bar.get_width() / 2, e[1] / 1e6 + 0.03,
                f"${e[1]/1e6:.2f}M", ha="center", fontsize=11, fontweight="600")
    ax.set_ylabel("annual saving  ($M)")
    titles(ax, "Average-cost allocation overstates the saving 2.8×",
           f"Routes 35 and 36, deleted 2026-08-24  ·  "
           f"{FREED_HOURS:,.0f} revenue hours a month")
    ax.set_ylim(0, max(e[1] for e in est) / 1e6 * 1.18)
    clean(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig3_savings_methods.png"), dpi=200)
    plt.close(fig)

    # ---------------- fig 4: route productivity ---------------------------
    target = "2026-07"
    # fixed route only - paratransit and vanpool are separate products with
    # their own economics, so they do not belong on a productivity ranking
    rows = [r for r in rid if r["month"] == target and not r["is_total"]
            and r["route_key"] not in ("DR", "VP", "ACCESS")]
    pts = []
    for r in rows:
        p, h = num(r["passengers"]), num(r["total_hours"])
        if p and h:
            pts.append((r["route_key"], p / h))
    pts.sort(key=lambda t: t[1])
    if pts:
        fig, ax = plt.subplots(figsize=(8, 5.4))
        colors = [CRITICAL if k in ("35", "36") else BLUE for k, _ in pts]
        ax.barh([k for k, _ in pts], [v for _, v in pts], color=colors,
                height=0.68, zorder=3)
        for i, (k, v) in enumerate(pts):
            ax.text(v + 0.25, i, f"{v:.1f}", va="center", fontsize=9,
                    color=INK_2)
        ax.set_xlabel("passengers per revenue hour")
        titles(ax, "The two routes CityBus cut were its two least productive",
               f"{target}  ·  fixed route only  ·  routes 35 and 36 deleted 2026-08-24")
        ax.set_xlim(0, max(v for _, v in pts) * 1.14)
        ax.grid(axis="y", visible=False)
        clean(ax)
        fig.tight_layout()
        fig.savefig(os.path.join(HERE, "fig4_productivity.png"), dpi=200)
        plt.close(fig)

    print("wrote:")
    for f in ("fig1_model_c_null.png", "fig2_hours_vs_cost.png",
              "fig3_savings_methods.png", "fig4_productivity.png"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            print(f"   {p}")


if __name__ == "__main__":
    main()

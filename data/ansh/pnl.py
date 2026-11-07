"""
Profit & loss statement from any CityBus board packet layout.

Same measured-column approach as the ridership table. Rows are keyed by their
order down the page, not by label, because the P&L prints duplicate labels
(two FEDERAL PLANNING ASSISTANCE lines, for one).
"""

import re
import colgrid as cg

# March-style packets add BUDGETED and BALANCE after the six standard columns.
BASE = ["month_cur", "month_prior", "pct_diff_month",
        "ytd_cur", "ytd_prior", "pct_diff_ytd"]
EXTRA = ["budgeted", "balance"]

SECTIONS = ("OPERATING REVENUE", "OPERATING EXPENSE", "PERSONNEL", "COMMODITIES",
            "SERVICES", "SERVICES & CHARGES", "OTHER INCOME", "OTHER EXPENSE",
            "OTHER INCOME/EXPENSE")
MONEY = re.compile(r"[\d-]")   # a row of dashes is still a data row


def find(pdf):
    """Index of the P&L page."""
    for i, p in enumerate(pdf.pages):
        t = (p.extract_text() or "").upper()
        if "OPERATING REVENUE" in t and "TOTAL EXPENSES" in t:
            return i
    raise LookupError("no profit & loss page found")


HEADER = re.compile(r"^(%DIFF\S*|YTD\d{4}|BUDGETED|BALANCE|[A-Z][a-z]{2}-\d{2})$")

NAME_FOR = [
    (re.compile(r"^[A-Z][a-z]{2}-\d{2}$"), None),      # positional, see below
]


def _header_bands(page):
    """
    Column boundaries from the P&L header row. The header labels are short,
    well separated and present in every layout, so they beat whitespace
    detection here - the value columns themselves are crowded with $ signs
    and in some packets sit only a few points apart.
    """
    rows = {}
    for w in page.extract_words(x_tolerance=1.5):
        if HEADER.match(w["text"]):
            rows.setdefault(round(w["top"] / 3) * 3, []).append(w)
    if not rows:
        raise LookupError("no profit & loss header row found")
    y = max(rows, key=lambda k: (len(rows[k]), -k))
    hdr = sorted(rows[y], key=lambda w: w["x0"])

    order, seen = [], set()
    for w in hdr:
        t = w["text"]
        if re.match(r"^[A-Z][a-z]{2}-\d{2}$", t):
            nm = "month_cur" if "month_cur" not in seen else "month_prior"
        elif t.startswith("%DIFF"):
            nm = "pct_diff_month" if "pct_diff_month" not in seen else "pct_diff_ytd"
        elif t.startswith("YTD"):
            nm = "ytd_cur" if "ytd_cur" not in seen else "ytd_prior"
        elif t == "BUDGETED":
            nm = "budgeted"
        elif t == "BALANCE":
            nm = "balance"
        else:
            continue
        seen.add(nm)
        order.append((nm, w["x0"], w["x1"]))

    # The item column must stop short of the leftmost money character, or wide
    # cent-precision numbers spill into the label.
    left = min((c["x0"] for c in page.chars
                if c["top"] > y + 4 and c["text"] in "$(0123456789"
                and c["x0"] > 120), default=order[0][1] - 6)
    split = min(left - 2, order[0][1] - 6)
    bands = [("item", 0.0, split)]
    for i, (nm, x0, x1) in enumerate(order):
        lo = split if i == 0 else (order[i - 1][2] + x0) / 2
        hi = x1 + 40 if i == len(order) - 1 else (x1 + order[i + 1][1]) / 2
        bands.append((nm, lo, hi))
    return bands, [n for n, _, _ in order], y


def parse(page):
    """
    Returns ([(order, section, line_item, {column: printed_text})], fields).
    Values exactly as printed; blanks stay blank.
    """
    bands, fields, hdr_y = _header_bands(page)

    out, section, order = [], "", 0
    for y, cell in cg.rows_of(page, bands, top=hdr_y + 4, bottom=page.height):
        item = cg.tidy(cell.get("item", ""))
        vals = {f: cg.raw(cell.get(f, "")) for f in fields}
        if not item:
            continue
        up = item.upper()
        if "BOARD MEETING" in up or up.startswith("GLPTC"):
            continue                          # page footer
        if not any(MONEY.search(v or "") for v in vals.values()):
            if up in SECTIONS or up.rstrip(":") in SECTIONS:
                section = up.rstrip(":")
            continue                          # header or spacer, no numbers
        order += 1
        out.append((order, section, item, vals))
        if up.startswith("TOTAL "):
            nxt = up[6:].strip()
            if nxt in SECTIONS:
                section = ""
    return out, fields

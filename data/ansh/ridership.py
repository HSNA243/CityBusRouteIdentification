"""
Ridership-by-route table, extracted from any CityBus board packet layout.

Column boundaries are measured from each packet rather than hard-coded, so the
2022, 2023 and post-2023 layouts all parse without per-era tuning. The window
used for measuring runs from the first numbered-route row to the first
"Sub Total:" row - the block where every column is populated and nothing
bridges a boundary.
"""

import re
import colgrid as cg

FIELDS = ["passengers", "total_miles", "total_hours", "pax_per_mile",
          "pax_per_mile_pct_diff", "pax_per_hour", "pax_per_hour_pct_diff"]

ROUTE_ID = re.compile(r"^\d{1,2}[AB]?E?$")

TOTAL_KEYS = [
    ("demand response total", "DR_TOTAL"),
    ("vanpool total",         "VP_TOTAL"),
    ("grand total",           "GRAND_TOTAL"),
    ("mb total",              "MB_TOTAL"),
]


def _window(page, left=70.0):
    """
    (top, bottom) of the clean numbered-route block.

    `left` is how far right a route id may sit. Some packets indent the route
    column, so the caller widens this before giving up.
    """
    first = None
    for w in sorted(page.extract_words(x_tolerance=1.5), key=lambda w: w["top"]):
        if first is None and ROUTE_ID.fullmatch(w["text"]) and w["x0"] < left:
            first = w["top"] - 2
        elif first is not None and w["text"].startswith("Total:") and w["top"] > first:
            return first, w["top"] + 6
    return first, (first + 400 if first else 800)


def _subtotal_row(page, after):
    """(top, bottom) of the first 'Sub Total:' row below `after`."""
    for w in sorted(page.extract_words(x_tolerance=1.5), key=lambda w: w["top"]):
        if w["text"].startswith("Total:") and w["top"] > after:
            return w["top"] - 4, w["top"] + w["height"] + 4
    return None


def _bands(page, top, bottom, left=70.0):
    """
    Nine columns: route, name, then the seven value columns.

    Measured from the first subtotal row rather than from the whole table. That
    row carries every value column populated and holds only a short label, so
    nothing bridges a boundary - which is what defeats whole-table detection on
    the 2022 packets, where long route names run into the passengers column.
    """
    names = ["route", "name"] + FIELDS

    sub = _subtotal_row(page, top)
    if sub:
        cols = cg.detect_bands(page, sub[0], sub[1])
        # drop the label band; the rest should be the seven value columns
        value = [c for c in cols if c[1] > 60]
        if len(value) == len(FIELDS) + 1:
            value = value[1:]
        if len(value) == len(FIELDS):
            route_right = 0.0
            for w in page.extract_words(x_tolerance=1.5):
                if top <= w["top"] <= bottom and ROUTE_ID.fullmatch(w["text"]) \
                        and w["x0"] < left:
                    route_right = max(route_right, w["x1"])
            route_right = (route_right + 6) if route_right else 60.0
            out = [("route", 0.0, route_right),
                   ("name", route_right, value[0][1])]
            out += [(FIELDS[i], lo, hi) for i, (_, lo, hi) in enumerate(value)]
            return out

    # fall back to measuring the whole numbered-route block
    cols = cg.detect_bands(page, top, bottom)
    if len(cols) != 9:
        raise LookupError(
            f"expected 9 ridership columns, measured {len(cols)}: "
            + " ".join(f"{lo:.0f}-{hi:.0f}" for _, lo, hi in cols))
    return [(names[i], lo, hi) for i, lo, hi in cols]


def parse(page):
    """
    Returns [(route_key, route_name, {field: printed_text})] down the page.
    Values are returned exactly as printed; blanks stay blank, never zero.
    """
    for left in (70.0, 110.0, 150.0):
        top, bottom = _window(page, left)
        if top is not None:
            break
    if top is None:
        raise LookupError("no numbered-route rows found on the ridership page")

    bands = _bands(page, top, bottom, left)

    out, subtotals, group = [], 0, 1
    for _, cell in cg.rows_of(page, bands, top=top - 60, bottom=page.height):
        rid = cg.raw(cell.get("route", ""))
        label = cg.tidy(cell.get("name", ""))
        vals = {f: cg.raw(cell.get(f, "")) for f in FIELDS}
        if not rid and not label:
            continue
        if not any(vals.values()) and not ROUTE_ID.fullmatch(rid or ""):
            continue                                   # header / spacer row

        low = label.lower()
        key = None
        if "sub total" in low:
            # 2023-era packets carry three route groups, so numbering has to
            # keep going rather than stopping at regular/express.
            subtotals += 1
            key = {1: "SUBTOTAL_REGULAR", 2: "SUBTOTAL_EXPRESS"}.get(
                subtotals, f"SUBTOTAL_{subtotals}")
            vals["group"] = str(subtotals)
            out.append((key, label, vals))
            group += 1
            continue
        else:
            for frag, k in TOTAL_KEYS:
                if frag in low:
                    key = k
                    break
        if key is None:
            if ROUTE_ID.fullmatch(rid or "") or rid in ("DR", "VP", "ACCESS"):
                key = rid
            else:
                continue          # header, section label or stray text
        vals["group"] = str(group) if key not in (
            "MB_TOTAL", "DR_TOTAL", "VP_TOTAL", "GRAND_TOTAL") else ""
        out.append((key, label, vals))
    return out

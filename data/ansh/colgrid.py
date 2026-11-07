"""
Character-grid table extraction for CityBus board packets.

pdfplumber's extract_words() splits numbers mid-token ("1" + "9,700") because
the PDF content stream contains literal spaces inside them, and raising
x_tolerance does not fix it. Working at the character level does: assign every
character to a column by where it physically sits on the page, concatenate the
characters in each cell, then delete whitespace inside the cell. Two numbers in
different columns can never merge, and one number split across a space is
always rejoined.
"""

import re
from collections import defaultdict


def rows_of(page, bands, top=None, bottom=None, row_tol=3.0):
    """
    Slice a page into rows of cells.

    bands: list of (name, x_min, x_max) covering the table's columns.
    Returns [(row_top, {name: cell_text})], ordered down the page.
    """
    buckets = defaultdict(lambda: defaultdict(list))
    for ch in page.chars:
        y = ch["top"]
        if top is not None and y < top:
            continue
        if bottom is not None and y > bottom:
            continue
        mid = (ch["x0"] + ch["x1"]) / 2
        for name, lo, hi in bands:
            if lo <= mid < hi:
                buckets[round(y / row_tol) * row_tol][name].append(ch)
                break

    out = []
    for y in sorted(buckets):
        cells = {}
        for name, chars in buckets[y].items():
            chars.sort(key=lambda c: c["x0"])
            cells[name] = "".join(c["text"] for c in chars)
        out.append((y, cells))
    return out


def squash(cell):
    """Collapse a numeric cell's internal spaces: '1 9,700' -> '19,700'."""
    return re.sub(r"\s+", "", cell or "")


def tidy(cell):
    """Normalise a text cell's whitespace, keeping real word gaps."""
    return re.sub(r"\s+", " ", (cell or "")).strip()


NUMERIC = re.compile(r"^\(?-?\$?\s*[\d,]*\.?\d+\)?%?$")


def number(cell, *, allow_blank=True):
    """
    Parse one numeric cell exactly as printed.

      ''  or '-'   -> None   (missing; never zero)
      '(24,982)'   -> -24982.0
      '1 9,700'    -> 19700.0
      '-27.62%'    -> -27.62
      '#DIV/0!'    -> None, flagged by the caller via raw()

    Raises ValueError on anything it does not recognise, so an unexpected cell
    stops the packet instead of silently becoming a wrong number.
    """
    s = squash(cell)
    # Strip currency and separators before testing for a blank, so a cell that
    # prints as "$-$" (a dash flanked by the column's own dollar signs) is
    # recognised as missing rather than as an unparseable number.
    s = s.replace("$", "").replace(",", "").replace("\u2014", "-").strip()
    if s in ("", "-", "--", "N/A", "n/a", "()"):
        if allow_blank:
            return None
        raise ValueError(f"blank cell where a number was required: {cell!r}")
    if s.startswith("#"):          # #DIV/0! and friends
        return None
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    s = s.rstrip("%")
    if not NUMERIC.match(s or "x"):
        raise ValueError(f"unparseable numeric cell: {cell!r}")
    try:
        v = float(s)
    except ValueError:
        raise ValueError(f"unparseable numeric cell: {cell!r}")
    return -v if neg else v


def raw(cell):
    """The cell exactly as printed, spaces squashed. For the audit trail."""
    return squash(cell)


def find_page(pdf, anchor, start=0):
    """First page index at or after `start` whose text contains `anchor`."""
    for i in range(start, len(pdf.pages)):
        if anchor in (pdf.pages[i].extract_text() or ""):
            return i
    raise LookupError(f"anchor not found in any page: {anchor!r}")


def band_probe(page, top=None, bottom=None):
    """
    Diagnostic: print every word with its x-range, to derive column bands for
    a layout we have not seen before.
    """
    ws = page.extract_words(x_tolerance=1.5)
    rows = defaultdict(list)
    for w in ws:
        if top is not None and w["top"] < top:
            continue
        if bottom is not None and w["top"] > bottom:
            continue
        rows[round(w["top"] / 3) * 3].append(w)
    for y in sorted(rows):
        line = "  ".join(f"{w['text']}@{w['x0']:.0f}-{w['x1']:.0f}"
                         for w in sorted(rows[y], key=lambda w: w["x0"]))
        print(f"{y:>6} | {line}")


def detect_bands(page, top, bottom, min_gap=8.0, pad=1.0):
    """
    Work out a table's column boundaries from the page itself.

    Projects every character in the region onto the x-axis and looks for
    vertical corridors of whitespace at least `min_gap` wide. Characters of one
    number are adjacent (gap 0) while real columns are separated by 15pt or
    more, so the corridors fall exactly on the column boundaries. This adapts
    to each packet's layout instead of needing hand-measured bands per era.

    Returns [(index, x_min, x_max)] left to right.
    """
    spans = []
    for ch in page.chars:
        if top <= ch["top"] <= bottom and not ch["text"].isspace():
            spans.append((ch["x0"], ch["x1"]))
    if not spans:
        return []

    spans.sort()
    merged = [list(spans[0])]
    for a, b in spans[1:]:
        if a - merged[-1][1] < min_gap:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])

    bands = []
    for i, (a, b) in enumerate(merged):
        lo = a - pad if i == 0 else (merged[i - 1][1] + a) / 2
        hi = b + pad if i == len(merged) - 1 else (b + merged[i + 1][0]) / 2
        bands.append((i, lo, hi))
    return bands

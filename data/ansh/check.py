import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdfplumber, colgrid as cg, ridership

CSVMAP = {"passengers":"passengers","total_miles":"total_miles","total_hours":"total_hours",
          "pax_per_mile":"pax_per_mile","pax_per_mile_pct_diff":"pax_per_mile_pct_diff_vs_2025",
          "pax_per_hour":"pax_per_hour","pax_per_hour_pct_diff":"pax_per_hour_pct_diff_vs_2025"}

def norm(s):
    s=(s or '').strip().replace(',','').replace('$','').replace('%','')
    if s in ('','-'): return ''
    try: return f"{float(s):.6g}"
    except ValueError: return s

with pdfplumber.open(sys.argv[1]) as d:
    rows = ridership.parse(d.pages[cg.find_page(d,'P/Hrs')])
got = {k:v for k,_,v in rows}
truth = {r['route_id']:r for r in csv.DictReader(open(sys.argv[2], newline=''))}

checked=bad=0; miss=[]
for rid,want in truth.items():
    g = got.get(rid)
    if g is None: miss.append(rid); continue
    for f,col in CSVMAP.items():
        if col not in want: continue
        a,b = norm(want[col]), norm(g.get(f)); checked+=1
        if a!=b:
            bad+=1; print(f"  MISMATCH {rid:<18}{col:<34}csv={want[col]!r:>12} pdf={g.get(f)!r:>12}")
print(f"csv rows {len(truth)} | parsed rows {len(got)} | unmatched {miss or 'none'}")
print(f"cells {checked} | mismatches {bad}")
print("PASS" if bad==0 and not miss else "FAIL")

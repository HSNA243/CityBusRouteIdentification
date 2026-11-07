# Tonight's run order

All files go in the same folder, with the PDFs in `pdfs/` and `packets.csv` beside them.

```
pip3 install pdfplumber

python3 run_ridership.py      # ~20-40 min, writes ridership_route_month.csv
python3 run_finance.py        # needs the above; writes finance_month.csv + fits Model C
```

## What you get

| File | Grain | Feeds |
|---|---|---|
| `ridership_route_month.csv` | route x month | Model B target, Model A output |
| `finance_month.csv` | month | Model C |
| `pnl_line_month.csv` | P&L line x month | audit trail |
| `ridership_verify.log`, `finance_verify.log` | — | the checks, pass and fail |
| `ridership_failures.csv` | — | packets that would not parse |

`run_finance.py` prints the Model C fit at the end: slope (marginal cost per
revenue hour), intercept, R-squared and n.

## Reading the output

- `consistency` = `review` means a packet failed a subtotal or ratio check. Look it
  up in the log before using that month.
- `hours_swing_flag` marks a route whose hours moved more than 40% from the previous
  month. Routes 42 and 43 in 2026-09 are the known bad case.
- Blank is blank. A dash in the source means no service, never zero riders.

## Validate before you trust it

```
python3 check.py pdfs/717_2026-08-26.pdf <path to>/01_ridership_by_route_2026-07.csv
```

Must print PASS: 168 cells, zero mismatches against the hand-verified extraction.

## Known limits

- Only ridership and the P&L are parsed. No revenue detail, budget-vs-actual or
  operations table yet.
- Model C regresses variable expense (operator and maintenance wages, their fringe,
  fuel, parts, tyres, oil) on revenue hours. Not total expense: ~38% of the budget is
  fixed, and regressing the total gives a slope driven by whatever else was trending.
- Sanity check on the slope: slope x annual revenue hours should land near
  $10,515,589, the FY2026 budget's variable lines. Far off means something is wrong.
- The 2022 layout is untested. Failures land in `ridership_failures.csv` with the error.

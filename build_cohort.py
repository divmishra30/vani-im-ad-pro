"""Build the Sarvam campaign cohort CSV for VANI from the IndiaMART lead reports.

Reads   data/lead-report-pmcat.csv  (main: remapped MCAT + PMCAT per work order)
        data/lead-report.csv        (only for its 7D/28D columns, joined on Work Order)
        data/mcat-pmcat-mapping.csv (MCAT -> PMCAT, for upsell; optional demand column)
Writes  sarvam/cohort-all.csv, sarvam/cohort-demo.csv, sarvam/sellers/<glid>.md

Usage:  python build_cohort.py --phone +919876543210
        (no seller phone numbers in the report yet, so every row dials this number)
"""

import argparse
import csv

from vani.core import DEMO_SELLERS, OUT, PRIORITY, build_rows
from vani.store import history_by_seller


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phone", default="", help="number every row dials, e.g. +919876543210")
    args = ap.parse_args()

    rows = build_rows(args.phone, history_by_seller())
    (OUT / "sellers").mkdir(parents=True, exist_ok=True)
    write_csv(OUT / "cohort-all.csv", rows)
    write_csv(OUT / "cohort-demo.csv", [r for g in DEMO_SELLERS for r in rows if r["glid"] == g])
    for r in rows:
        (OUT / "sellers" / f"{r['glid']}.md").write_text(r["seller_md"], encoding="utf-8")

    counts = {k: sum(r["call_reason"] == k for r in rows) for k in PRIORITY}
    print(f"{len(rows)} sellers to call: {counts}")
    print(f"upsell sellers with a category to pitch: {sum(1 for r in rows if r['call_reason'] == 'upsell' and r['upsell_category'])}")
    print(f"wrote {OUT / 'cohort-all.csv'}, {OUT / 'cohort-demo.csv'} and {len(rows)} seller files")
    if not args.phone:
        print("note: phone_number is empty; rerun with --phone +91XXXXXXXXXX before uploading")


if __name__ == "__main__":
    main()

"""Batch-extract a folder of invoice PDFs into one Excel file.

Usage:
    python cli.py samples/invoices --engine offline --out invoices.xlsx
    python cli.py path/to/pdfs --engine claude --out march_invoices.xlsx
"""
import argparse
from collections import Counter
from pathlib import Path

from extractor.export import to_excel
from extractor.pipeline import ENGINES, load_folder, run_batch


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="Folder containing PDF invoices")
    ap.add_argument("--engine", default="claude", choices=list(ENGINES))
    ap.add_argument("--out", default="extracted_invoices.xlsx")
    args = ap.parse_args()

    files = load_folder(args.folder)
    if not files:
        raise SystemExit(f"No PDF files found in {args.folder}")
    results = run_batch(files, args.engine)
    Path(args.out).write_bytes(to_excel(results))

    counts = Counter(r.status for r in results)
    print(f"{len(results)} invoices -> {args.out}")
    for status in ("OK", "Check", "Needs review", "Failed"):
        if counts[status]:
            print(f"  {status}: {counts[status]}")
    for r in results:
        for i in r.issues:
            if i.severity == "error":
                print(f"  ! {r.source_file}: {i.message}")
        if r.error:
            print(f"  x {r.source_file}: {r.error}")


if __name__ == "__main__":
    main()

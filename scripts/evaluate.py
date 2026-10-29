"""Measure extraction accuracy against samples/ground_truth.json.

Usage:
    python scripts/evaluate.py --engine offline
    python scripts/evaluate.py --engine claude     # needs ANTHROPIC_API_KEY
    python scripts/evaluate.py --engine gemini     # needs GEMINI_API_KEY
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from extractor.pipeline import load_folder, run_batch  # noqa: E402

FIELDS = ["vendor_name", "vendor_gstin", "buyer_name", "buyer_gstin", "invoice_number", "invoice_date",
          "subtotal", "cgst", "sgst", "igst", "total"]
# planted problem -> the check that should flag it
EXPECTED_CHECK = {"total_mismatch": "total_mismatch", "line_item_mismatch": "line_item_mismatch",
                  "invalid_gstin": "invalid_gstin", "wrong_tax_type": "wrong_tax_type", "duplicate": "duplicate"}


def same(a, b) -> bool:
    if isinstance(b, (int, float)) and a is not None:
        try:
            return abs(float(a) - float(b)) < 0.01
        except (TypeError, ValueError):
            return False
    return (str(a).strip().lower() if a is not None else None) == (str(b).strip().lower() if b is not None else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="offline", choices=["offline", "claude", "gemini"])
    args = ap.parse_args()

    truth = {t["file"]: t for t in json.loads((ROOT / "samples" / "ground_truth.json").read_text())}
    results = run_batch(load_folder(ROOT / "samples" / "invoices"), args.engine)

    field_hits = field_total = line_hits = line_total = 0
    caught = planted = false_alarms = clean = 0
    misses = []
    for r in results:
        t = truth[r.source_file]
        for f in FIELDS:
            field_total += 1
            if same(getattr(r.data, f), t[f]):
                field_hits += 1
            else:
                misses.append(f"{r.source_file}: {f} = {getattr(r.data, f)!r}, expected {t[f]!r}")
        for i, tli in enumerate(t["line_items"]):
            line_total += 1
            li = r.data.line_items[i] if i < len(r.data.line_items) else None
            if li and all(same(getattr(li, k), tli[k]) for k in ("description", "quantity", "unit_price", "amount")):
                line_hits += 1
            else:
                misses.append(f"{r.source_file}: line {i + 1} not extracted correctly")
        codes = {i.code for i in r.issues if i.severity == "error"}
        if t["planted_problem"]:
            planted += 1
            caught += EXPECTED_CHECK[t["planted_problem"]] in codes
        else:
            clean += 1
            false_alarms += bool(codes)

    print(f"Engine: {args.engine}")
    print(f"Header fields correct: {field_hits}/{field_total} ({field_hits / field_total:.1%})")
    print(f"Line items correct:    {line_hits}/{line_total} ({line_hits / line_total:.1%})")
    print(f"Planted problems caught: {caught}/{planted}")
    print(f"Clean invoices wrongly flagged: {false_alarms}/{clean}")
    if misses:
        print("\nMisses:")
        print("\n".join("  " + m for m in misses))


if __name__ == "__main__":
    main()

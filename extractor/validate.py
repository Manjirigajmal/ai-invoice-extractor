"""Checks run on every extracted invoice before it reaches Excel.

The LLM is told to copy values exactly as printed. These checks then catch
both supplier mistakes (wrong totals, wrong tax type, invalid GSTIN) and
extraction mistakes (a misread number usually breaks the arithmetic).
"""
from collections import defaultdict
from datetime import date

from . import gstin as G
from .schema import InvoiceData, InvoiceResult, Issue

TOLERANCE = 1.00  # rupees, allows for rounding on the invoice
KNOWN_GST_RATES = {0, 0.25, 3, 5, 12, 18, 28, 40}
REQUIRED = {"vendor_name": "supplier name", "vendor_gstin": "supplier GSTIN",
            "invoice_number": "invoice number", "invoice_date": "invoice date", "total": "invoice total"}


def _money(x: float) -> str:
    return f"{x:,.2f}"


def check_invoice(d: InvoiceData, today: date | None = None) -> list[Issue]:
    issues: list[Issue] = []
    err = lambda code, msg: issues.append(Issue(severity="error", code=code, message=msg))  # noqa: E731
    warn = lambda code, msg: issues.append(Issue(severity="warning", code=code, message=msg))  # noqa: E731

    for field, label in REQUIRED.items():
        if getattr(d, field) in (None, ""):
            err("missing_field", f"Missing {label}")

    for who, value in (("Supplier", d.vendor_gstin), ("Buyer", d.buyer_gstin)):
        if value and not G.is_valid(value):
            err("invalid_gstin", f"{who} GSTIN {value} fails the format/checksum test")

    for n, li in enumerate(d.line_items, 1):
        if None not in (li.quantity, li.unit_price, li.amount):
            expected = li.quantity * li.unit_price
            if abs(expected - li.amount) > TOLERANCE:
                err("line_item_mismatch",
                    f"Line {n}: {li.quantity:g} x {_money(li.unit_price)} = {_money(expected)}, "
                    f"but invoice shows {_money(li.amount)}")

    if d.line_items and d.subtotal is not None and all(li.amount is not None for li in d.line_items):
        lines_sum = sum(li.amount for li in d.line_items)
        if abs(lines_sum - d.subtotal) > TOLERANCE:
            err("subtotal_mismatch", f"Line items add up to {_money(lines_sum)}, subtotal shows {_money(d.subtotal)}")

    cgst, sgst, igst = d.cgst or 0, d.sgst or 0, d.igst or 0
    v_state, b_state = G.state_code(d.vendor_gstin), G.state_code(d.buyer_gstin)
    if v_state and b_state and (cgst or sgst or igst):
        if v_state == b_state and igst:
            err("wrong_tax_type", f"Supplier and buyer are both in {G.STATES.get(v_state, v_state)}: "
                                  "expected CGST + SGST, invoice charges IGST")
        if v_state != b_state and (cgst or sgst):
            err("wrong_tax_type", f"Supplier is in {G.STATES.get(v_state, v_state)}, buyer in "
                                  f"{G.STATES.get(b_state, b_state)}: expected IGST, invoice charges CGST + SGST")
    if abs(cgst - sgst) > TOLERANCE:
        warn("cgst_sgst_unequal", f"CGST ({_money(cgst)}) and SGST ({_money(sgst)}) should be equal")

    if d.subtotal:
        rate = round((cgst + sgst + igst) / d.subtotal * 100, 2)
        if not any(abs(rate - r) < 0.05 for r in KNOWN_GST_RATES):
            warn("unusual_gst_rate", f"Effective GST rate is {rate}%, not a standard slab")

    if d.subtotal is not None and d.total is not None:
        expected_total = d.subtotal + cgst + sgst + igst
        if abs(expected_total - d.total) > TOLERANCE:
            err("total_mismatch", f"Subtotal + tax = {_money(expected_total)}, invoice total shows "
                                  f"{_money(d.total)} (difference {_money(d.total - expected_total)})")

    if d.invoice_date:
        try:
            when = date.fromisoformat(d.invoice_date)
            if when > (today or date.today()):
                warn("future_date", f"Invoice date {d.invoice_date} is in the future")
        except ValueError:
            warn("bad_date", f"Could not read invoice date '{d.invoice_date}'")
    return issues


def check_batch(results: list[InvoiceResult]) -> None:
    """Adds per-invoice issues plus duplicates across the whole batch (in place)."""
    seen = defaultdict(list)
    for r in results:
        if r.error:
            continue
        r.issues = check_invoice(r.data)
        key = ((r.data.vendor_gstin or "").upper(), (r.data.invoice_number or "").upper())
        if all(key):
            seen[key].append(r)
    for (_, number), group in seen.items():
        if len(group) > 1:
            files = ", ".join(g.source_file for g in group)
            for r in group[1:]:
                r.issues.append(Issue(severity="error", code="duplicate",
                                      message=f"Invoice {number} from this supplier appears more than once ({files})"))

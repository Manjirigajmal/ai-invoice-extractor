"""Generate fictional Indian GST invoices for the demo, plus ground truth.

Four fictional vendors, each with its own layout, date format and labels,
so the extractor has to cope with real-world variety. Five invoices carry
deliberate problems that the validation step should catch.

Run:  python samples/generate_invoices.py
"""
import json
import sys
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extractor.gstin import make  # noqa: E402

OUT = Path(__file__).resolve().parent / "invoices"
TRUTH = Path(__file__).resolve().parent / "ground_truth.json"

BUYER = {
    "name": "Meridian Analytics Pvt Ltd",
    "gstin": make("27", "AAHCM4821K"),
    "address": "402, Orbit Plaza, Andheri East, Mumbai 400069",
}

VENDORS = {
    "SGP": {"name": "Shree Ganesh Packaging Pvt Ltd", "gstin": make("27", "AAKCS7310P"),
            "address": "Plot 18, MIDC Bhosari, Pune 411026", "layout": "classic"},
    "NLS": {"name": "Nilgiri Lab Supplies LLP", "gstin": make("33", "AAQFN2264D"),
            "address": "14 Industrial Estate, Guindy, Chennai 600032", "layout": "modern"},
    "BW": {"name": "Bluewave IT Services", "gstin": make("29", "ABDFB9051R"),
           "address": "3rd Floor, Prestige Tower, Koramangala, Bengaluru 560034", "layout": "minimal"},
    "KOS": {"name": "Kavya Office Solutions", "gstin": make("27", "AFZPK6627L"),
            "address": "Shop 7, Gokhale Road, Thane West 400602", "layout": "boxed"},
}

# (vendor, invoice_no, date, gst_rate, items[(description, hsn, qty, rate)], problem)
INVOICES = [
    ("SGP", "SGP-2026-0142", date(2026, 9, 3), 18,
     [("Corrugated boxes 5-ply 18x12x12", "4819", 400, 42.50), ("Bubble wrap roll 1m x 100m", "3920", 12, 1150.00)], None),
    ("SGP", "SGP-2026-0148", date(2026, 9, 17), 18,
     [("Corrugated boxes 3-ply 12x10x8", "4819", 600, 21.00), ("BOPP tape 48mm x 65m", "3919", 144, 38.00)], "total_mismatch"),
    ("SGP", "SGP-2026-0161", date(2026, 10, 6), 18,
     [("Printed mailer boxes", "4819", 250, 64.00), ("Kraft paper roll 90 GSM", "4804", 8, 2350.00)], "line_item_mismatch"),
    ("NLS", "NLS/26-27/0087", date(2026, 9, 9), 18,
     [("Nitrile gloves (box of 100)", "4015", 40, 385.00), ("Petri dishes 90mm sterile (pack of 500)", "3926", 6, 2950.00),
      ("Disposable pipette tips 200ul (rack of 96)", "3926", 30, 210.00)], None),
    ("NLS", "NLS/26-27/0092", date(2026, 9, 24), 18,
     [("Culture media SCDA 500g", "3821", 10, 4200.00), ("Sterile swabs (pack of 100)", "3005", 15, 540.00)], "invalid_gstin"),
    ("NLS", "NLS/26-27/0101", date(2026, 10, 14), 18,
     [("Autoclave indicator tape", "3919", 20, 310.00), ("Glass media bottles 500ml", "7017", 24, 365.00)], None),
    ("BW", "BW-INV-3302", date(2026, 9, 1), 18,
     [("Managed IT support - September 2026", "998313", 1, 45000.00), ("Microsoft 365 licences (monthly)", "997331", 18, 620.00)], None),
    ("BW", "BW-INV-3317", date(2026, 10, 1), 18,
     [("Managed IT support - October 2026", "998313", 1, 45000.00), ("Laptop setup and imaging", "998713", 4, 1800.00)], "wrong_tax_type"),
    ("BW", "BW-INV-3329", date(2026, 10, 19), 18,
     [("Firewall configuration (one-time)", "998316", 1, 22000.00)], None),
    ("KOS", "KOS-0605", date(2026, 9, 12), 18,
     [("A4 copier paper 75 GSM (ream)", "4802", 60, 265.00), ("Printer toner cartridge 88A", "8443", 5, 2450.00)], None),
    ("KOS", "KOS-0611", date(2026, 9, 29), 18,
     [("Ergonomic office chair", "9401", 6, 7800.00), ("Whiteboard 4x3 ft", "9610", 2, 2150.00)], None),
    ("KOS", "KOS-0611", date(2026, 9, 29), 18,
     [("Ergonomic office chair", "9401", 6, 7800.00), ("Whiteboard 4x3 ft", "9610", 2, 2150.00)], "duplicate"),
]


def inr(x: float) -> str:
    """Indian digit grouping: 1,23,456.00"""
    neg = x < 0
    whole, frac = f"{abs(x):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if neg else "") + f"{whole}.{frac}"


def build_record(vendor_key, inv_no, inv_date, rate, items, problem):
    v = dict(VENDORS[vendor_key])
    if problem == "invalid_gstin":
        good = v["gstin"]
        bad_last = "A" if good[-1] != "A" else "B"
        v["gstin"] = good[:-1] + bad_last
    lines = []
    for desc, hsn, qty, unit in items:
        amount = round(qty * unit, 2)
        lines.append({"description": desc, "hsn_sac": hsn, "quantity": qty, "unit_price": unit, "amount": amount})
    subtotal = round(sum(li["amount"] for li in lines), 2)
    if problem == "line_item_mismatch":
        # the printed amount on line 2 doesn't equal qty x rate, but subtotal is the true sum
        lines[1]["amount"] = round(lines[1]["amount"] + 2350.00, 2)
    intra = VENDORS[vendor_key]["gstin"][:2] == BUYER["gstin"][:2]
    if problem == "wrong_tax_type":
        intra = True  # charges CGST+SGST although supplier is in another state
    tax = round(subtotal * rate / 100, 2)
    cgst = sgst = igst = 0.0
    if intra:
        cgst = sgst = round(tax / 2, 2)
    else:
        igst = tax
    total = round(subtotal + cgst + sgst + igst, 2)
    if problem == "total_mismatch":
        total = round(total + 1000.00, 2)
    return {
        "file": f"{inv_no.replace('/', '-')}{'_copy' if problem == 'duplicate' else ''}.pdf",
        "vendor_name": v["name"], "vendor_gstin": v["gstin"],
        "buyer_name": BUYER["name"], "buyer_gstin": BUYER["gstin"],
        "invoice_number": inv_no, "invoice_date": inv_date.isoformat(),
        "line_items": lines, "subtotal": subtotal,
        "cgst": cgst, "sgst": sgst, "igst": igst, "total": total,
        "gst_rate": rate, "planted_problem": problem,
        "_layout": v["layout"], "_vendor_address": v["address"],
    }


S = {
    "title": ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=16, leading=20),
    "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=10, leading=13),
    "n": ParagraphStyle("n", fontName="Helvetica", fontSize=9, leading=12),
    "s": ParagraphStyle("s", fontName="Helvetica", fontSize=8, leading=10, textColor=colors.grey),
}


def P(text, style="n"):
    return Paragraph(text, S[style])


def items_table(r, header, cols, money):
    data = [header]
    for i, li in enumerate(r["line_items"], 1):
        row = {"sr": str(i), "desc": li["description"], "hsn": li["hsn_sac"], "qty": f"{li['quantity']:g}",
               "rate": money(li["unit_price"]), "amt": money(li["amount"])}
        data.append([row[c] for c in cols])
    return data


def tax_rows(r, money, labels):
    rows = [[labels["sub"], money(r["subtotal"])]]
    half = r["gst_rate"] / 2
    if r["cgst"] or r["sgst"]:
        rows += [[f"CGST @ {half:g}%", money(r["cgst"])], [f"SGST @ {half:g}%", money(r["sgst"])]]
    if r["igst"]:
        rows += [[f"IGST @ {r['gst_rate']:g}%", money(r["igst"])]]
    rows += [[labels["total"], money(r["total"])]]
    return rows


def grid(data, widths, header=True, box=True):
    t = Table(data, colWidths=widths)
    style = [("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("ALIGN", (-1, 0), (-1, -1), "RIGHT")]
    if header:
        style += [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee"))]
    if box:
        style += [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999"))]
    t.setStyle(TableStyle(style))
    return t


def layout_classic(r):
    money = lambda x: inr(x)  # noqa: E731
    d = r["invoice_date"].split("-")
    date_txt = f"{d[2]}-{d[1]}-{d[0]}"  # 03-09-2026
    story = [P(r["vendor_name"], "title"), P(r["_vendor_address"]), P(f"GSTIN: {r['vendor_gstin']}"), Spacer(1, 6 * mm),
             P("TAX INVOICE", "h"), Spacer(1, 2 * mm),
             grid([["Invoice No: " + r["invoice_number"], "Invoice Date: " + date_txt]], [90 * mm, 80 * mm], header=False),
             Spacer(1, 4 * mm), P("Bill To:", "h"), P(r["buyer_name"]), P(BUYER["address"]), P(f"GSTIN: {r['buyer_gstin']}"),
             Spacer(1, 5 * mm),
             grid(items_table(r, ["Sr", "Description", "HSN", "Qty", "Rate (Rs.)", "Amount (Rs.)"],
                              ["sr", "desc", "hsn", "qty", "rate", "amt"], money),
                  [10 * mm, 72 * mm, 18 * mm, 15 * mm, 25 * mm, 30 * mm]),
             Spacer(1, 4 * mm),
             grid(tax_rows(r, lambda x: "Rs. " + money(x), {"sub": "Taxable Value", "total": "Grand Total"}),
                  [60 * mm, 40 * mm], header=False),
             Spacer(1, 8 * mm), P("Payment due within 30 days. Bank: HDFC Bank, A/c 50200012345678, IFSC HDFC0000123", "s")]
    return story


def layout_modern(r):
    money = lambda x: "INR " + inr(x)  # noqa: E731
    dt = date.fromisoformat(r["invoice_date"]).strftime("%d %b %Y")  # 09 Sep 2026
    head = Table([[P(r["vendor_name"], "title"), P("<b>INVOICE</b>")],
                  [P(r["_vendor_address"]), P(f"Invoice # {r['invoice_number']}")],
                  [P(f"Supplier GSTIN {r['vendor_gstin']}"), P(f"Dated {dt}")]], colWidths=[110 * mm, 60 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story = [head, Spacer(1, 6 * mm),
             P("Billed to", "h"), P(f"{r['buyer_name']}, {BUYER['address']}"), P(f"Recipient GSTIN {r['buyer_gstin']}"),
             Spacer(1, 6 * mm),
             grid(items_table(r, ["Item", "HSN/SAC", "Qty", "Unit Price", "Line Total"],
                              ["desc", "hsn", "qty", "rate", "amt"], money),
                  [78 * mm, 20 * mm, 12 * mm, 30 * mm, 30 * mm], box=False),
             Spacer(1, 5 * mm),
             grid(tax_rows(r, money, {"sub": "Sub Total", "total": "Total Amount Payable"}), [70 * mm, 40 * mm],
                  header=False, box=False),
             Spacer(1, 10 * mm), P("Thank you for your business. Goods once sold will not be taken back.", "s")]
    return story


def layout_minimal(r):
    money = lambda x: inr(x)  # noqa: E731
    dt = r["invoice_date"]  # ISO 2026-09-01
    story = [P(f"<b>{r['vendor_name']}</b> | GSTIN {r['vendor_gstin']}"), P(r["_vendor_address"], "s"), Spacer(1, 8 * mm),
             P("Tax Invoice", "title"), P(f"Invoice Number: {r['invoice_number']}"), P(f"Date of Issue: {dt}"),
             P(f"Customer: {r['buyer_name']} (GSTIN {r['buyer_gstin']})"), Spacer(1, 6 * mm),
             grid(items_table(r, ["Service", "SAC", "Qty", "Rate", "Amount"], ["desc", "hsn", "qty", "rate", "amt"], money),
                  [80 * mm, 20 * mm, 12 * mm, 28 * mm, 30 * mm]),
             Spacer(1, 4 * mm),
             grid(tax_rows(r, money, {"sub": "Taxable Amount", "total": "Invoice Total (INR)"}), [70 * mm, 40 * mm],
                  header=False, box=False),
             Spacer(1, 10 * mm), P("Amounts in Indian Rupees. This is a computer-generated invoice.", "s")]
    return story


def layout_boxed(r):
    money = lambda x: inr(x)  # noqa: E731
    dt = date.fromisoformat(r["invoice_date"]).strftime("%d/%m/%Y")  # 12/09/2026
    top = grid([[P(f"<b>{r['vendor_name']}</b><br/>{r['_vendor_address']}<br/>GST No: {r['vendor_gstin']}"),
                 P(f"<b>TAX INVOICE</b><br/>Bill No: {r['invoice_number']}<br/>Bill Date: {dt}")]],
               [105 * mm, 65 * mm], header=False)
    to = grid([[P(f"<b>Buyer</b><br/>{r['buyer_name']}<br/>{BUYER['address']}<br/>GST No: {r['buyer_gstin']}")]],
              [170 * mm], header=False)
    story = [top, to, Spacer(1, 4 * mm),
             grid(items_table(r, ["S.No", "Particulars", "HSN", "Qty", "Rate", "Amount"],
                              ["sr", "desc", "hsn", "qty", "rate", "amt"], money),
                  [12 * mm, 75 * mm, 18 * mm, 13 * mm, 24 * mm, 28 * mm]),
             grid(tax_rows(r, money, {"sub": "Total Before Tax", "total": "Net Amount (Rs.)"}), [142 * mm, 28 * mm],
                  header=False),
             Spacer(1, 8 * mm), P("Subject to Thane jurisdiction. E. & O.E.", "s")]
    return story


LAYOUTS = {"classic": layout_classic, "modern": layout_modern, "minimal": layout_minimal, "boxed": layout_boxed}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.pdf"):
        old.unlink()
    truth = []
    for spec in INVOICES:
        r = build_record(*spec)
        doc = SimpleDocTemplate(str(OUT / r["file"]), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                                topMargin=16 * mm, bottomMargin=16 * mm, title=r["invoice_number"],
                                author=r["vendor_name"])
        doc.build(LAYOUTS[r["_layout"]](r))
        truth.append({k: v for k, v in r.items() if not k.startswith("_")})
    TRUTH.write_text(json.dumps(truth, indent=2))
    print(f"Wrote {len(truth)} invoices to {OUT} and ground truth to {TRUTH.name}")


if __name__ == "__main__":
    main()

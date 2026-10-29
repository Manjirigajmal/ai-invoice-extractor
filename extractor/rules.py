"""Offline demo engine: regular expressions, no AI.

It exists so anyone can try the app without an API key. The patterns were
written for the four sample invoice layouts, so it is brittle by design:
an unfamiliar layout will break it, which is exactly the problem the LLM
engines solve. Use Claude or Gemini for real documents.
"""
import re
from datetime import datetime

from .schema import InvoiceData, LineItem

GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b")
AMT = r"(?:Rs\.|INR)?\s*([\d,]+\.\d{2})"
DATE_FORMATS = ["%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d"]

LABELS = {
    "subtotal": r"(?:Taxable Value|Sub Total|Taxable Amount|Total Before Tax)",
    "cgst": r"CGST\s*@\s*[\d.]+%",
    "sgst": r"SGST\s*@\s*[\d.]+%",
    "igst": r"IGST\s*@\s*[\d.]+%",
    "total": r"(?:Grand Total|Total Amount Payable|Invoice Total \(INR\)|Net Amount \(Rs\.\))",
}
ITEM_RE = re.compile(
    r"^(?:\d+\s+)?(?P<desc>.+?)\s+(?P<hsn>\d{4,8})\s+(?P<qty>\d+(?:\.\d+)?)\s+"
    r"(?:INR\s+)?(?P<rate>[\d,]+\.\d{2})\s+(?:INR\s+)?(?P<amt>[\d,]+\.\d{2})$"
)


def _num(s: str | None) -> float | None:
    return float(s.replace(",", "")) if s else None


def _find(pattern: str, text: str, flags=re.MULTILINE) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _date(raw: str | None) -> str | None:
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _vendor_name(lines: list[str]) -> str | None:
    if not lines:
        return None
    first = lines[0].split("|")[0]
    return re.sub(r"\s+(TAX\s+)?INVOICE$", "", first.strip(), flags=re.I) or None


def _buyer_name(text: str) -> str | None:
    m = re.search(r"^(?:Bill To:|Buyer)\s*\n(.+)$", text, re.M)
    if m:
        return m.group(1).strip()
    m = re.search(r"^Billed to\s*\n([^,\n]+)", text, re.M)
    if m:
        return m.group(1).strip()
    return _find(r"^Customer:\s*(.+?)\s*\(GSTIN", text)


def extract_with_rules(text: str) -> InvoiceData:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    gstins = GSTIN_RE.findall(text)
    items = []
    for ln in lines:
        m = ITEM_RE.match(ln)
        if m:
            items.append(LineItem(description=m["desc"], hsn_sac=m["hsn"], quantity=float(m["qty"]),
                                  unit_price=_num(m["rate"]), amount=_num(m["amt"])))
    amounts = {k: _num(_find(rf"^{label}\s+{AMT}\s*$", text)) for k, label in LABELS.items()}
    for tax in ("cgst", "sgst", "igst"):
        amounts[tax] = amounts[tax] or 0.0
    return InvoiceData(
        vendor_name=_vendor_name(lines),
        vendor_gstin=gstins[0] if gstins else None,
        buyer_name=_buyer_name(text),
        buyer_gstin=gstins[-1] if len(gstins) > 1 else None,
        invoice_number=_find(r"(?:Invoice No|Invoice #|Invoice Number|Bill No)\s*[:#]?\s*([A-Z0-9][A-Z0-9/\-]+)", text),
        invoice_date=_date(_find(r"(?:Invoice Date|Dated|Date of Issue|Bill Date)\s*:?\s*"
                                 r"(\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{1,2} [A-Za-z]{3,9} \d{4}|\d{4}-\d{2}-\d{2})", text)),
        line_items=items,
        **amounts,
    )

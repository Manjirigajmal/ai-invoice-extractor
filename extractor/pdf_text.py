"""Read the text layer of a PDF. Scanned PDFs have little or no text,
in which case the LLM engines receive the PDF file itself instead."""
import io

import pdfplumber

MIN_TEXT_CHARS = 40


def extract_text(pdf_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n\n".join(pages).strip()


def has_text_layer(text: str) -> bool:
    return len(text) >= MIN_TEXT_CHARS

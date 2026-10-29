"""LLM extraction engines (Claude and Gemini).

Both engines get the same instructions and the same JSON schema, and both
return an InvoiceData object. If a PDF has a usable text layer we send the
text (cheaper, faster); if it is a scan we send the PDF itself so the model
can read the page image.
"""
import base64
import copy
import json
import os

from .schema import InvoiceData

INSTRUCTIONS = """You extract data from Indian GST invoices for an accounts team.

Rules:
- Copy values exactly as printed on the invoice. Do NOT correct, recalculate or
  "fix" anything, even if a total or tax looks wrong. A separate validation
  step checks the arithmetic, so wrong values must reach it unchanged.
- Amounts: plain numbers, no currency symbols, no thousands separators
  (1,23,456.50 -> 123456.50).
- Dates: ISO format YYYY-MM-DD. Indian invoices write dates day-first
  (03-09-2026 and 03/09/2026 mean 3 September 2026).
- GSTINs: 15 characters, uppercase, no spaces. The supplier's GSTIN is the
  seller's; the buyer's GSTIN is under Bill To / Buyer / Customer / Recipient.
- Taxes: fill cgst, sgst and igst with the amounts charged; use 0 for any tax
  that is not on the invoice.
- If a field is genuinely missing or unreadable, return null. Never guess.
"""


def _inline_refs(schema: dict) -> dict:
    """Replace $ref pointers with the referenced definitions (some APIs prefer a flat schema)."""
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


SCHEMA = _inline_refs(InvoiceData.model_json_schema())


def extract_with_claude(text: str | None, pdf_bytes: bytes, model: str | None = None) -> InvoiceData:
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    model = model or os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")
    if text:
        content = [{"type": "text", "text": f"Invoice text:\n\n{text}"}]
    else:
        content = [
            {"type": "document",
             "source": {"type": "base64", "media_type": "application/pdf",
                        "data": base64.standard_b64encode(pdf_bytes).decode()}},
            {"type": "text", "text": "Extract the invoice data from this document."},
        ]
    response = client.messages.create(
        model=model,
        max_tokens=4000,
        system=INSTRUCTIONS,
        tools=[{"name": "record_invoice", "description": "Record the extracted invoice fields.",
                "input_schema": SCHEMA}],
        tool_choice={"type": "tool", "name": "record_invoice"},
        messages=[{"role": "user", "content": content}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return InvoiceData.model_validate(block.input)
    raise RuntimeError("Claude did not return structured invoice data")


def extract_with_gemini(text: str | None, pdf_bytes: bytes, model: str | None = None) -> InvoiceData:
    from google import genai
    from google.genai import types

    client = genai.Client()  # reads GEMINI_API_KEY / GOOGLE_API_KEY
    model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    if text:
        contents = [f"Invoice text:\n\n{text}"]
    else:
        contents = [types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    "Extract the invoice data from this document."]
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=INSTRUCTIONS,
            response_mime_type="application/json",
            response_schema=InvoiceData,
            temperature=0,
        ),
    )
    if getattr(response, "parsed", None) is not None:
        return InvoiceData.model_validate(response.parsed)
    return InvoiceData.model_validate(json.loads(response.text))

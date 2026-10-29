"""Streamlit app: upload invoice PDFs, extract with an LLM, review issues, download Excel.

Run:  streamlit run app.py
"""
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from extractor.export import INVOICE_COLS, invoice_rows, to_excel
from extractor.pipeline import ENGINES, load_folder, run_batch

SAMPLES = Path(__file__).parent / "samples" / "invoices"
STATUS_COLOURS = {"OK": "#e6f4ea", "Check": "#fff4ce", "Needs review": "#fde2e1", "Failed": "#e0e0e0"}

st.set_page_config(page_title="AI Invoice Extractor", page_icon="🧾", layout="wide")

# ---------- sidebar ----------
with st.sidebar:
    st.header("Settings")
    engine = st.radio("Extraction engine", list(ENGINES), format_func=ENGINES.get,
                      index=0 if os.getenv("ANTHROPIC_API_KEY") else 2)
    if engine == "claude" and not os.getenv("ANTHROPIC_API_KEY"):
        key = st.text_input("Anthropic API key", type="password")
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key
    if engine == "gemini" and not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        key = st.text_input("Gemini API key", type="password")
        if key:
            os.environ["GEMINI_API_KEY"] = key
    if engine == "offline":
        st.info("Offline demo uses fixed rules written for the sample layouts. "
                "Choose Claude or Gemini for your own invoices.")
    st.caption("Keys are used only for this session and never stored.")

# ---------- header ----------
st.title("AI Invoice Extractor")
st.write("Upload GST invoice PDFs. The tool pulls out supplier, GSTIN, dates, line items and taxes, "
         "checks every number, and gives you one Excel file with anything suspicious flagged for review.")

col_upload, col_sample = st.columns([3, 1])
with col_upload:
    uploads = st.file_uploader("Invoice PDFs", type="pdf", accept_multiple_files=True, label_visibility="collapsed")
with col_sample:
    use_samples = st.button("Try 12 sample invoices", use_container_width=True)

files = [(u.name, u.getvalue()) for u in uploads] if uploads else []
if use_samples:
    files = load_folder(SAMPLES)

if files and (use_samples or st.button(f"Extract {len(files)} invoice(s)", type="primary")):
    with st.spinner(f"Reading {len(files)} invoice(s) with {ENGINES[engine]}..."):
        st.session_state.results = run_batch(files, engine)

results = st.session_state.get("results")
if not results:
    st.stop()

# ---------- summary ----------
counts = pd.Series([r.status for r in results]).value_counts()
total_value = sum(r.data.total or 0 for r in results if not r.error)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Invoices processed", len(results))
m2.metric("Clean", int(counts.get("OK", 0)))
m3.metric("Need review", int(counts.get("Needs review", 0) + counts.get("Failed", 0)))
m4.metric("Total value (INR)", f"{total_value:,.2f}")

st.download_button("Download Excel (Invoices, Line Items, Issues)", to_excel(results),
                   file_name="extracted_invoices.xlsx", type="primary",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---------- invoice table ----------
df = pd.DataFrame(invoice_rows(results), columns=[c for c, _ in INVOICE_COLS])
df = df[["Status", "Issues", "Supplier", "Invoice No", "Invoice Date", "Total", "Subtotal", "CGST", "SGST", "IGST",
         "Supplier GSTIN", "Lines", "Source File"]]
styled = df.style.map(lambda v: f"background-color: {STATUS_COLOURS.get(v, '')}", subset=["Status"]) \
    .format({c: "{:,.2f}" for c in ["Subtotal", "CGST", "SGST", "IGST", "Total"]}, na_rep="")
st.subheader("Extracted invoices")
st.dataframe(styled, hide_index=True, use_container_width=True,
             column_config={"Issues": st.column_config.TextColumn(width="large"),
                           "Supplier": st.column_config.TextColumn(width="medium")})

# ---------- review queue ----------
flagged = [r for r in results if r.status != "OK"]
if flagged:
    st.subheader(f"Review queue ({len(flagged)})")
    for r in flagged:
        with st.expander(f"{r.status}: {r.source_file} ({r.data.vendor_name or 'unknown supplier'})"):
            if r.error:
                st.error(r.error)
            for i in r.issues:
                (st.error if i.severity == "error" else st.warning)(i.message)
            if r.data.line_items:
                items = pd.DataFrame([li.model_dump() for li in r.data.line_items])
                items.columns = ["Description", "HSN/SAC", "Qty", "Unit Price", "Amount"]
                st.dataframe(items, hide_index=True,
                             use_container_width=True)

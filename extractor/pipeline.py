"""PDF in, validated InvoiceResult out."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .pdf_text import extract_text, has_text_layer
from .schema import InvoiceData, InvoiceResult
from .validate import check_batch

ENGINES = {
    "claude": "Claude (Anthropic API)",
    "gemini": "Gemini (Google API)",
    "offline": "Offline demo (rules, no AI)",
}


def extract_one(name: str, pdf_bytes: bytes, engine: str) -> InvoiceResult:
    try:
        text = extract_text(pdf_bytes)
        if engine == "offline":
            from .rules import extract_with_rules
            if not has_text_layer(text):
                raise ValueError("Scanned PDF: the offline demo engine needs a text layer, use Claude or Gemini")
            data = extract_with_rules(text)
        elif engine == "claude":
            from .llm import extract_with_claude
            data = extract_with_claude(text if has_text_layer(text) else None, pdf_bytes)
        elif engine == "gemini":
            from .llm import extract_with_gemini
            data = extract_with_gemini(text if has_text_layer(text) else None, pdf_bytes)
        else:
            raise ValueError(f"Unknown engine '{engine}'")
        return InvoiceResult(source_file=name, engine=engine, data=data)
    except Exception as exc:  # one bad file must not stop the batch
        return InvoiceResult(source_file=name, engine=engine, data=InvoiceData(), error=f"{type(exc).__name__}: {exc}")


def run_batch(files: list[tuple[str, bytes]], engine: str, workers: int = 4) -> list[InvoiceResult]:
    workers = 1 if engine == "offline" else workers
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda f: extract_one(f[0], f[1], engine), files))
    check_batch(results)
    return results


def load_folder(folder: str | Path) -> list[tuple[str, bytes]]:
    return [(p.name, p.read_bytes()) for p in sorted(Path(folder).glob("*.pdf"))]

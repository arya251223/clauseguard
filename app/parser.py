"""PDF text extraction and clause segmentation.

Extraction backend: PyMuPDF when installed (fast, layout-aware), otherwise pdfplumber.
Segmentation: numbered headings ("4.", "4.2", "ARTICLE V", "Section 7") become clause
boundaries, and every clause remembers the page it starts on. Documents with no
numbering fall back to paragraph splitting.
"""
import re
from typing import List, Tuple

from app.models import Clause

try:  # pragma: no cover - depends on the environment
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None


class PDFError(ValueError):
    """Raised for unreadable, encrypted, empty or oversized PDFs."""


def backend_name() -> str:
    return "pymupdf" if fitz else "pdfplumber"


def extract_pages(path: str, max_pages: int = 80) -> List[str]:
    try:
        if fitz:
            with fitz.open(path) as doc:
                if doc.needs_pass:
                    raise PDFError("PDF is password-protected.")
                if doc.page_count > max_pages:
                    raise PDFError(f"PDF has {doc.page_count} pages; the limit is {max_pages}.")
                pages = [p.get_text("text") for p in doc]
        else:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                if len(pdf.pages) > max_pages:
                    raise PDFError(f"PDF has {len(pdf.pages)} pages; the limit is {max_pages}.")
                pages = [(p.extract_text() or "") for p in pdf.pages]
    except PDFError:
        raise
    except Exception as exc:
        raise PDFError(f"Could not read PDF: {exc}") from exc
    if not "".join(pages).strip():
        raise PDFError("No extractable text found. Scanned PDFs need OCR first.")
    return pages


HEADING_RE = re.compile(
    r"^\s*(?:"
    r"(?:ARTICLE|Article|SECTION|Section)\s+(?:[IVXLC]+|\d{1,2})[.:)]?"
    r"|\d{1,3}(?:\.\d{1,2}){0,3}[.)]"
    r"|\d{1,3}(?:\.\d{1,2}){1,3}"
    r")\s+(?=[A-Z\"(])"
)


TITLE_RE = re.compile(r"^(?P<num>\S+)\s+(?P<title>[A-Z][\w ,&/'’-]{2,45})[.:]\s")


def _heading_label(line: str) -> str:
    line = line.strip()
    m = HEADING_RE.match(line)
    number = m.group(0).strip() if m else ""
    rest = line[len(m.group(0)):].strip() if m else line
    if len(rest) <= 70 and not rest.endswith((",", ";")):
        title = rest.rstrip(".:")
    else:
        t = TITLE_RE.match(line)
        title = t.group("title") if t else " ".join(rest.split()[:6]) + "…"
    return f"{number} {title}".strip()


def _clean(text: str) -> str:
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)   # de-hyphenate line wraps
    return re.sub(r"\s+", " ", text).strip()


def segment(pages: List[str]) -> List[Clause]:
    """Split page texts into clauses. Returns clauses in document order."""
    lines: List[Tuple[int, str]] = []
    for pno, text in enumerate(pages, start=1):
        for ln in text.splitlines():
            if ln.strip():
                lines.append((pno, ln))

    starts = [i for i, (_, ln) in enumerate(lines) if HEADING_RE.match(ln)]
    raw: List[Tuple[str, str, int]] = []   # heading, body, page

    if len(starts) >= 2:
        if starts[0] > 0:
            pre = _clean(" ".join(l for _, l in lines[: starts[0]]))
            if len(pre) > 80:
                raw.append(("Preamble", pre, lines[0][0]))
        for n, s in enumerate(starts):
            e = starts[n + 1] if n + 1 < len(starts) else len(lines)
            first = lines[s][1]
            body = _clean(" ".join(l for _, l in lines[s:e]))
            raw.append((_heading_label(first), body, lines[s][0]))
    else:  # no numbering: paragraph fallback
        for pno, text in enumerate(pages, start=1):
            for para in re.split(r"\n\s*\n", text):
                para = _clean(para)
                if len(para) >= 60:
                    raw.append((" ".join(para.split()[:6]) + "…", para, pno))

    out, prefix = [], ""
    for n, (h, t, p) in enumerate(raw):
        if len(t) < 40 and n + 1 < len(raw) and raw[n + 1][0].split(" ")[0].startswith(h.split(" ")[0].rstrip(".") + "."):
            prefix = h            # heading-only parent ("3. Fees"): label its children with it
            continue
        if prefix and h.split(" ")[0].startswith(prefix.split(" ")[0].rstrip(".") + "."):
            h = f"{prefix} › {h}"
        else:
            prefix = ""
        if len(t) >= 25:
            out.append(Clause(len(out), h, t, p))
    return out


def parse_pdf(path: str, max_pages: int = 80) -> Tuple[List[Clause], int]:
    pages = extract_pages(path, max_pages)
    clauses = segment(pages)
    if not clauses:
        raise PDFError("Text was found but no clauses could be identified.")
    return clauses, len(pages)

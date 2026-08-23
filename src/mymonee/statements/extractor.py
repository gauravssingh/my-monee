"""PDF extraction abstraction and sectionizer using PyMuPDF (fitz)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pymupdf


@dataclass
class TextBlock:
    page_num: int
    bbox: tuple[float, float, float, float]
    text: str
    lines: list[str] = field(default_factory=list)


@dataclass
class PDFDocumentStructure:
    page_count: int
    full_text: str
    pages_text: list[str]
    blocks_by_page: dict[int, list[TextBlock]]
    raw_doc: pymupdf.Document


def load_pdf_structure(pdf_path_or_bytes: str | bytes) -> PDFDocumentStructure:
    """Open a PDF document and extract page text, text blocks, and coordinates."""
    if isinstance(pdf_path_or_bytes, (str, bytes)) and not isinstance(pdf_path_or_bytes, bytes):
        doc = pymupdf.open(pdf_path_or_bytes)
    else:
        doc = pymupdf.open(stream=pdf_path_or_bytes, filetype="pdf")

    page_count = len(doc)
    pages_text: list[str] = []
    blocks_by_page: dict[int, list[TextBlock]] = {}
    full_text_parts: list[str] = []

    for pno in range(page_count):
        page = doc[pno]
        page_str = page.get_text("text")
        pages_text.append(page_str)
        full_text_parts.append(page_str)

        # Extract structured text blocks
        blocks = page.get_text("blocks")
        page_blocks: list[TextBlock] = []
        for b in blocks:
            # block tuple: (x0, y0, x1, y1, text, block_no, block_type)
            if len(b) >= 5 and b[4].strip():
                lines = [line.strip() for line in b[4].splitlines() if line.strip()]
                tb = TextBlock(
                    page_num=pno + 1,
                    bbox=(b[0], b[1], b[2], b[3]),
                    text=b[4].strip(),
                    lines=lines,
                )
                page_blocks.append(tb)
        blocks_by_page[pno + 1] = page_blocks

    return PDFDocumentStructure(
        page_count=page_count,
        full_text="\n--- PAGE ---\n".join(full_text_parts),
        pages_text=pages_text,
        blocks_by_page=blocks_by_page,
        raw_doc=doc,
    )


def extract_tables_from_page(page: pymupdf.Page) -> list[list[list[str]]]:
    """Extract tabular grid rows if structured tables exist using PyMuPDF table finder."""
    try:
        tabs = page.find_tables()
        tables_data = []
        for tab in tabs:
            extracted = tab.extract()
            if extracted:
                tables_data.append(extracted)
        return tables_data
    except Exception:
        return []


def clean_amount(val: Any) -> float | None:
    """Parse monetary amount string into float, stripping commas and currency symbols."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s == "-" or s == "--":
        return None
    # Remove currency symbols (₹, Rs, INR, $, etc.) and commas
    cleaned = re.sub(r"[₹\$\,\s]", "", s)
    is_negative = False
    if s.endswith("Dr") or "Dr" in s or s.startswith("-"):
        is_negative = True
    cleaned = re.sub(r"[A-Za-z\-]", "", cleaned)
    try:
        amt = float(cleaned)
        return -amt if is_negative else amt
    except (ValueError, TypeError):
        return None

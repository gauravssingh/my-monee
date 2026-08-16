"""PDF Vault: Immutable storage, SHA256 verification, and PDF unlock/validation engine."""

from __future__ import annotations

import hashlib
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

import pypdf

logger = logging.getLogger(__name__)


def compute_sha256(content: bytes) -> str:
    """Compute SHA256 hash of binary content."""
    return hashlib.sha256(content).hexdigest()


def resolve_statement_paths(
    data_dir: Path,
    account_id: str | None,
    statement_id: str,
    statement_date: datetime | None = None,
) -> tuple[Path, Path]:
    """Generate canonical filesystem paths for original and unlocked statement PDFs."""
    dt = statement_date or datetime.now(timezone.utc)
    year_str = f"{dt.year:04d}"
    month_str = f"{dt.month:02d}"
    account_folder = account_id or "unlinked"

    base_dir = data_dir / "statements" / account_folder / year_str / month_str
    orig_dir = base_dir / "original"
    unlocked_dir = base_dir / "unlocked"

    orig_dir.mkdir(parents=True, exist_ok=True)
    unlocked_dir.mkdir(parents=True, exist_ok=True)

    orig_path = orig_dir / f"{statement_id}.pdf"
    unlocked_path = unlocked_dir / f"{statement_id}.pdf"
    return orig_path, unlocked_path


def validate_pdf(source: bytes | Path | BinaryIO) -> tuple[bool, bool, int, str | None]:
    """Validate a PDF stream or file.

    Returns:
        (is_valid, is_encrypted, page_count, error_message)
    """
    try:
        if isinstance(source, bytes):
            stream = io.BytesIO(source)
        elif isinstance(source, Path):
            stream = open(source, "rb")  # noqa: SIM115
        else:
            stream = source

        reader = pypdf.PdfReader(stream)
        is_encrypted = bool(reader.is_encrypted)

        if not is_encrypted:
            page_count = len(reader.pages)
            if page_count == 0:
                return False, False, 0, "PDF contains 0 pages"
            # Verify first page access
            _ = reader.pages[0]
            return True, False, page_count, None
        else:
            return True, True, 0, None
    except Exception as exc:
        return False, False, 0, f"Corrupted or invalid PDF: {exc}"


def unlock_pdf(pdf_content: bytes, password: str) -> tuple[bool, bytes | None, str | None]:
    """Attempt to decrypt a PDF using the given password.

    Validates that the resulting unlocked PDF is readable and non-empty.
    Returns:
        (success, unlocked_bytes, error_message)
    """
    if not password:
        return False, None, "Password cannot be empty"

    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_content))
        if not reader.is_encrypted:
            # Already unlocked
            return True, pdf_content, None

        # pypdf decrypt returns PasswordType (0: failed, 1: user, 2: owner)
        decrypt_result = reader.decrypt(password)
        if decrypt_result == 0:
            return False, None, "Incorrect password"

        writer = pypdf.PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        out_stream = io.BytesIO()
        writer.write(out_stream)
        unlocked_bytes = out_stream.getvalue()

        # Strict validation: reopen and verify pages
        val_valid, val_enc, val_pages, val_err = validate_pdf(unlocked_bytes)
        if not val_valid or val_enc or val_pages == 0:
            return False, None, f"Decrypted PDF validation failed: {val_err or 'unreadable'}"

        return True, unlocked_bytes, None
    except Exception as exc:
        logger.warning(f"Error during PDF decryption: {exc}")
        return False, None, f"Decryption error: {exc}"


def save_original_statement(
    data_dir: Path,
    account_id: str | None,
    statement_id: str,
    content: bytes,
    statement_date: datetime | None = None,
) -> tuple[Path, str]:
    """Save original PDF immutably and return (absolute_path, sha256)."""
    orig_path, _ = resolve_statement_paths(data_dir, account_id, statement_id, statement_date)
    orig_path.write_bytes(content)
    sha256 = compute_sha256(content)
    return orig_path, sha256


def save_unlocked_statement(
    data_dir: Path,
    account_id: str | None,
    statement_id: str,
    content: bytes,
    statement_date: datetime | None = None,
) -> tuple[Path, str]:
    """Save unlocked PDF and return (absolute_path, sha256)."""
    _, unlocked_path = resolve_statement_paths(data_dir, account_id, statement_id, statement_date)
    unlocked_path.write_bytes(content)
    sha256 = compute_sha256(content)
    return unlocked_path, sha256

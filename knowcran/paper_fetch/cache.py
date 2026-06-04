"""PDF download cache - check for existing PDFs before downloading."""

from __future__ import annotations

from pathlib import Path

from knowcran.paper_fetch.pdf_utils import validate_pdf, compute_file_sha256


class PDFCache:
    """Local PDF cache backed by the filesystem."""

    def __init__(self, pdf_dir: str | Path):
        self.pdf_dir = Path(pdf_dir)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

    def find_by_doi(self, doi: str) -> Path | None:
        """Find a cached PDF by DOI filename."""
        safe = doi.replace("/", "_").replace(":", "_")
        for ext in [".pdf"]:
            path = self.pdf_dir / f"{safe}{ext}"
            if path.exists() and self._is_valid(path):
                return path
        return None

    def find_by_filename(self, filename: str) -> Path | None:
        """Find a cached PDF by exact filename."""
        path = self.pdf_dir / filename
        if path.exists() and self._is_valid(path):
            return path
        return None

    def find_by_arxiv_id(self, arxiv_id: str) -> Path | None:
        """Find a cached PDF by arXiv ID filename."""
        safe = arxiv_id.replace("/", "_")
        path = self.pdf_dir / f"{safe}.pdf"
        if path.exists() and self._is_valid(path):
            return path
        return None

    def store(self, data: bytes, filename: str) -> Path:
        """Store PDF data and return the path."""
        path = self.pdf_dir / filename
        path.write_bytes(data)
        return path

    def _is_valid(self, path: Path) -> bool:
        """Check if a cached PDF is valid."""
        try:
            data = path.read_bytes()
            valid, _ = validate_pdf(data)
            return valid
        except (OSError, IOError):
            return False

    def get_sha256(self, path: Path) -> str:
        """Get SHA-256 of a cached file."""
        return compute_file_sha256(path)

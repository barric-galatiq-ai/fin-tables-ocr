"""Abstract base class for bank-specific parsers."""

from abc import ABC, abstractmethod
from pathlib import Path

import pdfplumber

from ..models import BankStatement


class BankParser(ABC):
    """Base class for bank-specific PDF parsers."""

    bank_name: str = "Unknown"

    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self.pdf: pdfplumber.PDF | None = None

    def __enter__(self):
        self.pdf = pdfplumber.open(self.pdf_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.pdf:
            self.pdf.close()

    @abstractmethod
    def parse(self) -> BankStatement:
        """Parse the PDF and return a BankStatement."""
        pass

    @classmethod
    @abstractmethod
    def can_parse(cls, pdf: pdfplumber.PDF) -> bool:
        """Check if this parser can handle the given PDF."""
        pass

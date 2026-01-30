"""Auto-detect bank from PDF content."""

from pathlib import Path
from typing import Type

import pdfplumber

from .base import BankParser
from .truist import TruistParser


# Registry of available bank parsers
BANK_PARSERS: list[Type[BankParser]] = [
    TruistParser,
]


def detect_bank(pdf_path: Path) -> Type[BankParser] | None:
    """Detect which bank parser to use for a PDF.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        The appropriate BankParser class, or None if no match found
    """
    with pdfplumber.open(pdf_path) as pdf:
        for parser_class in BANK_PARSERS:
            if parser_class.can_parse(pdf):
                return parser_class

    return None

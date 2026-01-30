"""Main extraction orchestrator."""

from pathlib import Path

from .banks import detect_bank
from .models import BankStatement


def extract_statement(pdf_path: Path) -> BankStatement:
    """Extract transactions from a bank statement PDF.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        BankStatement with all extracted transactions

    Raises:
        ValueError: If the bank cannot be detected or is unsupported
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # Detect which bank parser to use
    parser_class = detect_bank(pdf_path)

    if parser_class is None:
        raise ValueError(
            f"Could not detect bank from PDF: {pdf_path}. "
            "The bank may not be supported yet."
        )

    # Parse the PDF
    with parser_class(pdf_path) as parser:
        return parser.parse()

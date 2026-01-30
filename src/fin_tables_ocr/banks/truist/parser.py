"""Truist bank statement parser."""

import re
from datetime import date
from pathlib import Path

import pdfplumber

from ...models import BankStatement, Transaction
from ..base import BankParser
from .page_classifier import classify_pages
from .table_parsers import (
    extract_checks_from_page,
    extract_deposits_from_page,
    extract_withdrawals_from_page,
)


class TruistParser(BankParser):
    """Parser for Truist bank statements."""

    bank_name = "Truist"

    def __init__(self, pdf_path: Path):
        super().__init__(pdf_path)
        self._year: int | None = None
        self._account_number: str | None = None

    @classmethod
    def can_parse(cls, pdf: pdfplumber.PDF) -> bool:
        """Check if this PDF is a Truist statement.

        Looks for "Truist" or "TRUIST" in the first page.
        """
        if not pdf.pages:
            return False

        first_page_text = pdf.pages[0].extract_text() or ""
        return "truist" in first_page_text.lower()

    def _extract_metadata(self) -> None:
        """Extract statement year and account number from the first page."""
        if not self.pdf or not self.pdf.pages:
            return

        text = self.pdf.pages[0].extract_text() or ""

        # Extract year from statement date (e.g., "For 10/31/2025" or "10/31/25")
        # Handle both "For 10/31/2025" and "For10/31/2025" (no space)
        date_match = re.search(r"For\s*(\d{2}/\d{2}/(\d{4}|\d{2}))", text)
        if date_match:
            year_str = date_match.group(2)
            if len(year_str) == 2:
                self._year = 2000 + int(year_str)
            else:
                self._year = int(year_str)
        else:
            # Fallback: look for any 4-digit year in common date formats
            year_match = re.search(r"20\d{2}", text)
            if year_match:
                self._year = int(year_match.group())
            else:
                self._year = date.today().year

        # Extract account number (e.g., "CHECKING 1340006375358" or "CHECKING1340006375358")
        account_match = re.search(r"CHECKING\s*(\d+)", text)
        if account_match:
            self._account_number = account_match.group(1)

    def _extract_statement_period(self) -> tuple[date | None, date | None]:
        """Extract statement period start and end dates."""
        if not self.pdf or not self.pdf.pages or not self._year:
            return None, None

        text = self.pdf.pages[0].extract_text() or ""

        # Look for "as of MM/DD/YYYY" patterns (handle missing spaces)
        start_match = re.search(
            r"previous\s*balance\s*as\s*of\s*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE
        )
        end_match = re.search(
            r"new\s*balance\s*as\s*of\s*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE
        )

        start_date = None
        end_date = None

        if start_match:
            parts = start_match.group(1).split("/")
            start_date = date(int(parts[2]), int(parts[0]), int(parts[1]))

        if end_match:
            parts = end_match.group(1).split("/")
            end_date = date(int(parts[2]), int(parts[0]), int(parts[1]))

        return start_date, end_date

    def parse(self) -> BankStatement:
        """Parse the Truist PDF and return a BankStatement."""
        if not self.pdf:
            raise RuntimeError("PDF not opened. Use 'with' context manager.")

        # Extract metadata first
        self._extract_metadata()
        start_date, end_date = self._extract_statement_period()

        # Classify pages
        page_classifications = classify_pages(self.pdf)

        # Extract transactions from each transaction page
        all_transactions: list[Transaction] = []

        for page_num, is_transaction_page in page_classifications.items():
            if not is_transaction_page:
                continue

            page = self.pdf.pages[page_num]

            # Extract all transaction types from this page
            checks = extract_checks_from_page(page, self._year)
            withdrawals = extract_withdrawals_from_page(page, self._year)
            deposits = extract_deposits_from_page(page, self._year)

            all_transactions.extend(checks)
            all_transactions.extend(withdrawals)
            all_transactions.extend(deposits)

        # Sort transactions by date
        all_transactions.sort(key=lambda t: (t.date, t.transaction_type.value))

        return BankStatement(
            bank_name=self.bank_name,
            account_number=self._account_number,
            statement_period_start=start_date,
            statement_period_end=end_date,
            transactions=all_transactions,
        )

"""Table parsing logic for Truist bank statements."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

import pdfplumber

from ...models import Transaction, TransactionType


def parse_amount(amount_str: str) -> Decimal:
    """Parse an amount string into a Decimal."""
    cleaned = amount_str.replace(",", "").strip()
    return Decimal(cleaned)


def parse_date(date_str: str, year: int) -> date:
    """Parse a MM/DD date string into a date object."""
    month, day = date_str.split("/")
    return date(year, int(month), int(day))


def extract_checks_from_page(page: pdfplumber.page.Page, year: int) -> list[Transaction]:
    """Extract check transactions from a page."""
    transactions = []
    text = page.extract_text() or ""

    # Find the checks section header
    checks_match = re.search(r"Checks\s*\n", text, re.IGNORECASE)
    if not checks_match:
        return transactions

    checks_start = checks_match.end()
    # End at withdrawals section or total checks
    next_section = re.search(
        r"(Total\s*checks|\*\s*indicates|Other\s*withdraw|Otherwithdraw|DATE\s+DESCRIPTION\s+AMOUNT)",
        text[checks_start:],
        re.IGNORECASE,
    )
    checks_end = checks_start + next_section.start() if next_section else len(text)
    checks_text = text[checks_start:checks_end]

    # Pattern for check entries: MM/DD [*]#### amount
    check_pattern = r"(\d{2}/\d{2})\s+\*?(\d+)\s+([\d,]+\.\d{2})"

    for match in re.finditer(check_pattern, checks_text):
        date_str, check_num, amount_str = match.groups()
        try:
            transactions.append(
                Transaction(
                    date=parse_date(date_str, year),
                    description=f"Check #{check_num}",
                    amount=parse_amount(amount_str),
                    transaction_type=TransactionType.CHECK,
                    check_number=int(check_num),
                )
            )
        except (ValueError, InvalidOperation):
            continue

    return transactions


def _extract_transactions_from_text(
    text: str, year: int, transaction_type: TransactionType
) -> list[Transaction]:
    """Extract transactions from a text block."""
    transactions = []
    lines = text.split("\n")

    for line in lines:
        line_upper = line.upper()
        # Skip header/footer lines
        if "DESCRIPTION" in line_upper and "AMOUNT" in line_upper:
            continue
        if "DATE" in line_upper and "CHECK" in line_upper:
            continue
        if "CONTINUED" in line_upper:
            continue
        if "PAGE" in line_upper and "OF" in line_upper:
            continue

        # Pattern: MM/DD description amount
        match = re.match(r"^(\d{2}/\d{2})\s+(.+?)\s+([\d,]+\.\d{2})\s*$", line.strip())
        if match:
            date_str, description, amount_str = match.groups()
            description = description.strip()

            if not description or len(description) < 3:
                continue

            try:
                transactions.append(
                    Transaction(
                        date=parse_date(date_str, year),
                        description=description,
                        amount=parse_amount(amount_str),
                        transaction_type=transaction_type,
                    )
                )
            except (ValueError, InvalidOperation):
                continue

    return transactions


def _find_section_markers(text: str) -> dict:
    """Find all relevant section markers in the text.

    A section marker is the section header FOLLOWED BY a table header (DATE DESCRIPTION AMOUNT).
    Summary lines in the account summary don't have table headers after them.
    """
    markers = {}

    # Find "DATE DESCRIPTION AMOUNT" table headers
    table_headers = [m for m in re.finditer(r"DATE\s+DESCRIPTION\s+AMOUNT", text, re.IGNORECASE)]

    for th in table_headers:
        # Look backwards from this table header to find section headers
        prefix = text[max(0, th.start() - 100) : th.start()]

        # Check for withdrawals section header (must NOT be part of "Total")
        withdraw_match = re.search(
            r"(Other\s*withdrawals?,?\s*debits|Otherwithdrawals?,?debits)",
            prefix,
            re.IGNORECASE,
        )
        if withdraw_match and "withdraw_header" not in markers:
            # Verify this is not inside a "Total" line
            match_prefix = prefix[max(0, withdraw_match.start() - 10) : withdraw_match.start()]
            if "total" not in match_prefix.lower():
                markers["withdraw_header"] = th.start() - len(prefix) + withdraw_match.start()
                markers["withdraw_table"] = th.end()

        # Check for deposits section header (must NOT be part of "Total")
        deposit_match = re.search(
            r"(Deposits,?\s*credits\s*and\s*interest|Deposits,?creditsandinterest)",
            prefix,
            re.IGNORECASE,
        )
        if deposit_match and "deposit_header" not in markers:
            # Verify this is not inside a "Total" line
            match_prefix = prefix[max(0, deposit_match.start() - 10) : deposit_match.start()]
            if "total" not in match_prefix.lower():
                markers["deposit_header"] = th.start() - len(prefix) + deposit_match.start()
                markers["deposit_table"] = th.end()

    # Total withdrawals line (marks end of withdrawals section)
    total_withdraw = re.search(
        r"Total\s*other\s*withdrawals|Totalotherwithdrawals",
        text,
        re.IGNORECASE,
    )
    if total_withdraw:
        markers["total_withdraw"] = total_withdraw.start()

    # Total deposits line
    total_deposit = re.search(
        r"Total\s*deposits|Totaldeposits",
        text,
        re.IGNORECASE,
    )
    if total_deposit:
        markers["total_deposit"] = total_deposit.start()

    return markers


def extract_withdrawals_from_page(
    page: pdfplumber.page.Page, year: int
) -> list[Transaction]:
    """Extract withdrawal/debit transactions from a page."""
    text = page.extract_text() or ""
    markers = _find_section_markers(text)

    is_continuation = "(continued)" in text[:200].lower()

    start = None
    end = None

    if "withdraw_table" in markers:
        # Page has explicit withdrawals section with table header
        start = markers["withdraw_table"]

    elif is_continuation:
        # Continuation page - determine if it has withdrawals
        if "total_withdraw" in markers:
            # Withdrawals end on this page - extract from first table header to total
            table_header = re.search(r"DATE\s+DESCRIPTION\s+AMOUNT", text, re.IGNORECASE)
            if table_header:
                start = table_header.end()
                end = markers["total_withdraw"]
        elif "deposit_header" not in markers and "deposit_table" not in markers:
            # No deposit section - check if this is withdrawal content
            table_header = re.search(r"DATE\s+DESCRIPTION\s+AMOUNT", text, re.IGNORECASE)
            if table_header:
                # Verify by checking content for withdrawal indicators (not deposit indicators)
                content = text[table_header.end() : table_header.end() + 500]
                deposit_indicators = ["DEPOSIT", "EDI PYMNTS", "PAYABLES", "INCOMING WIRE"]
                withdrawal_indicators = ["DEBIT", "ACH CORP DEBIT", "WIRE REF#", "ZELLE"]

                # If deposit indicators dominate, skip this page for withdrawals
                has_deposits = any(kw in content.upper() for kw in deposit_indicators)
                has_withdrawals = any(kw in content.upper() for kw in withdrawal_indicators)

                if has_withdrawals and not has_deposits:
                    start = table_header.end()
                elif has_withdrawals and has_deposits:
                    # Mixed - likely still withdrawals (they have both debits and some deposits for fees)
                    start = table_header.end()

    if start is None:
        return []

    # Determine end if not set
    if end is None:
        if "deposit_header" in markers:
            end = markers["deposit_header"]
        elif "total_withdraw" in markers:
            end = markers["total_withdraw"]
        else:
            page_marker = re.search(r"continued\s*\n|§\s*PAGE", text[start:], re.IGNORECASE)
            if page_marker:
                end = start + page_marker.start()
            else:
                end = len(text)

    return _extract_transactions_from_text(text[start:end], year, TransactionType.WITHDRAWAL)


def extract_deposits_from_page(
    page: pdfplumber.page.Page, year: int
) -> list[Transaction]:
    """Extract deposit/credit transactions from a page."""
    text = page.extract_text() or ""
    markers = _find_section_markers(text)

    is_continuation = "(continued)" in text[:200].lower()

    start = None
    end = None

    if "deposit_table" in markers:
        # Page has explicit deposits section with table header
        start = markers["deposit_table"]

    elif is_continuation:
        # Continuation page - determine if it has deposits
        if "total_withdraw" in markers:
            # Withdrawals ended on this page, deposits may follow
            # Find table header after total_withdraw
            table_header = re.search(
                r"DATE\s+DESCRIPTION\s+AMOUNT",
                text[markers["total_withdraw"] :],
                re.IGNORECASE,
            )
            if table_header:
                start = markers["total_withdraw"] + table_header.end()

        elif "withdraw_header" not in markers and "withdraw_table" not in markers:
            # No withdrawal markers - check if this is a deposits continuation
            table_header = re.search(r"DATE\s+DESCRIPTION\s+AMOUNT", text, re.IGNORECASE)
            if table_header:
                # Verify by checking content for deposit indicators
                content = text[table_header.end() : table_header.end() + 500]
                if any(
                    kw in content.upper()
                    for kw in ["DEPOSIT", "EDI PYMNTS", "PAYABLES", "INCOMING WIRE"]
                ):
                    start = table_header.end()

    if start is None:
        return []

    # Determine end
    if "total_deposit" in markers:
        end = markers["total_deposit"]
    else:
        end_marker = re.search(r"Important:|§\s*PAGE", text[start:], re.IGNORECASE)
        if end_marker:
            end = start + end_marker.start()
        else:
            end = len(text)

    return _extract_transactions_from_text(text[start:end], year, TransactionType.DEPOSIT)

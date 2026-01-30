"""Page classification for Truist bank statements."""

import re

import pdfplumber


# Indicators that a page contains transaction data
TRANSACTION_INDICATORS = [
    r"Checks",
    r"Other\s*withdrawals",
    r"Deposits,?\s*credits",
    r"DATE\s+DESCRIPTION\s+AMOUNT",
    r"DATE\s+CHECK\s*#\s+AMOUNT",
]

# Indicators that a page is boilerplate (should be skipped)
BOILERPLATE_INDICATORS = [
    r"Questions,?\s*comments\s*or\s*errors\?",
    r"Electronic\s*fund\s*transfers",
    r"How\s*to\s*Reconcile\s*Your\s*Account",
    r"Billing\s*Rights\s*Summary",
    r"Mail-in\s*deposits",
]


def is_transaction_page(page: pdfplumber.page.Page) -> bool:
    """Determine if a page contains transaction data.

    Args:
        page: A pdfplumber page object

    Returns:
        True if the page contains transactions, False otherwise
    """
    text = page.extract_text() or ""

    # Check for boilerplate indicators first (they take precedence)
    for pattern in BOILERPLATE_INDICATORS:
        if re.search(pattern, text, re.IGNORECASE):
            return False

    # Check if page is mostly empty
    if len(text.strip()) < 100:
        return False

    # Check for transaction indicators
    for pattern in TRANSACTION_INDICATORS:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    # Check for date + amount patterns (MM/DD followed by dollar amounts)
    date_amount_pattern = r"\d{2}/\d{2}\s+.*\d+\.\d{2}"
    matches = re.findall(date_amount_pattern, text)
    if len(matches) >= 3:  # At least 3 transactions on the page
        return True

    return False


def classify_pages(pdf: pdfplumber.PDF) -> dict[int, bool]:
    """Classify all pages in a PDF.

    Args:
        pdf: An open pdfplumber PDF object

    Returns:
        Dict mapping page number (0-indexed) to whether it's a transaction page
    """
    return {i: is_transaction_page(page) for i, page in enumerate(pdf.pages)}

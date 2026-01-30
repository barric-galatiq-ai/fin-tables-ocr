"""Lender transaction tagging module."""

import json
import re
import string
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .models import BankStatement, Transaction, TransactionType


@dataclass
class LenderMatch:
    """A match between a transaction and a lender keyword."""

    lender_name: str
    matched_keyword: str


@dataclass
class TaggedTransaction:
    """A transaction with lender tagging information."""

    transaction: Transaction
    lender_matches: list[LenderMatch] = field(default_factory=list)
    is_transfer: bool = False  # True if matches transferKeywords


@dataclass
class LenderSummary:
    """Summary of lender activity for transfers or payments."""

    count: int = 0
    total: Decimal = Decimal("0")
    by_lender: dict[str, dict] = field(default_factory=dict)


@dataclass
class TaggedStatement:
    """A bank statement with tagged transactions and lender summary."""

    statement: BankStatement
    tagged_transactions: list[TaggedTransaction]
    transfer_summary: LenderSummary
    payment_summary: LenderSummary


def load_keywords(keywords_path: Path) -> dict:
    """Load keywords from a JSON file.

    Args:
        keywords_path: Path to the keywords.json file

    Returns:
        Dictionary containing businessCategoryKeywords and transferKeywords

    Raises:
        FileNotFoundError: If the keywords file doesn't exist
        ValueError: If the keywords file is invalid JSON
    """
    if not keywords_path.exists():
        raise FileNotFoundError(f"Keywords file not found: {keywords_path}")

    try:
        with open(keywords_path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in keywords file: {e}") from e


def _normalize_text(text: str) -> str:
    """Normalize text for matching by lowercasing and removing punctuation."""
    # Convert to lowercase
    text = text.lower()
    # Remove punctuation
    text = text.translate(str.maketrans("", "", string.punctuation))
    return text


def _matches_keyword(description: str, keyword: str) -> bool:
    """Check if a keyword appears anywhere in the description (case-insensitive, ignoring punctuation)."""
    normalized_desc = _normalize_text(description)
    normalized_keyword = _normalize_text(keyword)
    return normalized_keyword in normalized_desc


def tag_transaction(txn: Transaction, keywords: dict) -> TaggedTransaction:
    """Tag a single transaction with lender matches.

    Args:
        txn: The transaction to tag
        keywords: Dictionary containing businessCategoryKeywords and transferKeywords

    Returns:
        TaggedTransaction with lender matches and transfer flag
    """
    lender_matches: list[LenderMatch] = []
    is_transfer = False

    business_keywords = keywords.get("businessCategoryKeywords", {})
    transfer_keywords = keywords.get("transferKeywords", [])

    # Check for lender keyword matches
    for lender_name, lender_keywords in business_keywords.items():
        for keyword in lender_keywords:
            if keyword and _matches_keyword(txn.description, keyword):
                lender_matches.append(
                    LenderMatch(lender_name=lender_name, matched_keyword=keyword)
                )
                break  # Only need one match per lender

    # Check for transfer keyword matches
    for keyword in transfer_keywords:
        if keyword and _matches_keyword(txn.description, keyword):
            is_transfer = True
            break

    return TaggedTransaction(
        transaction=txn,
        lender_matches=lender_matches,
        is_transfer=is_transfer,
    )


def tag_statement(statement: BankStatement, keywords: dict) -> TaggedStatement:
    """Tag all transactions in a bank statement.

    Args:
        statement: The bank statement to tag
        keywords: Dictionary containing businessCategoryKeywords and transferKeywords

    Returns:
        TaggedStatement with all transactions tagged and summary computed
    """
    tagged_transactions = [
        tag_transaction(txn, keywords) for txn in statement.transactions
    ]

    # Compute summaries
    transfer_summary = LenderSummary()
    payment_summary = LenderSummary()

    for tagged in tagged_transactions:
        txn = tagged.transaction
        is_deposit = txn.transaction_type == TransactionType.DEPOSIT
        is_withdrawal = txn.transaction_type in (
            TransactionType.WITHDRAWAL,
            TransactionType.CHECK,
        )

        has_lender_match = len(tagged.lender_matches) > 0

        # Transfers: deposits matching transferKeywords OR any lender keyword
        if is_deposit and (tagged.is_transfer or has_lender_match):
            transfer_summary.count += 1
            transfer_summary.total += txn.amount

            # Track by lender
            for match in tagged.lender_matches:
                if match.lender_name not in transfer_summary.by_lender:
                    transfer_summary.by_lender[match.lender_name] = {
                        "count": 0,
                        "total": Decimal("0"),
                    }
                transfer_summary.by_lender[match.lender_name]["count"] += 1
                transfer_summary.by_lender[match.lender_name]["total"] += txn.amount

        # Payments: withdrawals/checks matching any lender keyword
        if is_withdrawal and has_lender_match:
            payment_summary.count += 1
            payment_summary.total += txn.amount

            # Track by lender
            for match in tagged.lender_matches:
                if match.lender_name not in payment_summary.by_lender:
                    payment_summary.by_lender[match.lender_name] = {
                        "count": 0,
                        "total": Decimal("0"),
                    }
                payment_summary.by_lender[match.lender_name]["count"] += 1
                payment_summary.by_lender[match.lender_name]["total"] += txn.amount

    return TaggedStatement(
        statement=statement,
        tagged_transactions=tagged_transactions,
        transfer_summary=transfer_summary,
        payment_summary=payment_summary,
    )

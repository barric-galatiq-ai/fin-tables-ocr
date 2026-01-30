"""Output writers for CSV and JSON formats."""

import csv
import json
from decimal import Decimal
from pathlib import Path

from .lender_tagger import TaggedStatement
from .models import BankStatement


def write_csv(
    statement: BankStatement,
    output_path: Path,
    tagged_statement: TaggedStatement | None = None,
) -> None:
    """Write transactions to a CSV file.

    Args:
        statement: The BankStatement to export
        output_path: Path for the output CSV file
        tagged_statement: Optional tagged statement with lender info
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build lookup for tagged transactions
    tagged_lookup = {}
    if tagged_statement:
        for tagged in tagged_statement.tagged_transactions:
            # Use transaction identity to match
            key = (
                tagged.transaction.date,
                tagged.transaction.description,
                tagged.transaction.amount,
            )
            tagged_lookup[key] = tagged

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Write header
        header = [
            "date",
            "description",
            "amount",
            "transaction_type",
            "check_number",
        ]
        if tagged_statement:
            header.extend(["lender_matches", "is_lender_transfer", "is_lender_payment"])
        writer.writerow(header)

        # Write transactions
        for txn in statement.transactions:
            row = [
                txn.date.isoformat(),
                txn.description,
                str(txn.amount),
                txn.transaction_type.value,
                txn.check_number if txn.check_number else "",
            ]

            if tagged_statement:
                key = (txn.date, txn.description, txn.amount)
                tagged = tagged_lookup.get(key)
                if tagged:
                    lender_names = [m.lender_name for m in tagged.lender_matches]
                    is_transfer = txn.is_lender_transfer
                    is_payment = txn.is_lender_payment
                    row.extend(
                        [
                            "|".join(lender_names) if lender_names else "",
                            str(is_transfer).lower(),
                            str(is_payment).lower(),
                        ]
                    )
                else:
                    row.extend(["", "false", "false"])

            writer.writerow(row)


def _format_lender_summary(summary) -> dict:
    """Format a LenderSummary for JSON output."""
    by_lender = {}
    for lender_name, data in summary.by_lender.items():
        by_lender[lender_name] = {
            "count": data["count"],
            "total": str(data["total"]),
        }

    return {
        "count": summary.count,
        "total": str(summary.total),
        "by_lender": by_lender,
    }


def write_json(
    statement: BankStatement,
    output_path: Path,
    tagged_statement: TaggedStatement | None = None,
) -> None:
    """Write the full statement to a JSON file.

    Args:
        statement: The BankStatement to export
        output_path: Path for the output JSON file
        tagged_statement: Optional tagged statement with lender info
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build lookup for tagged transactions
    tagged_lookup = {}
    if tagged_statement:
        for tagged in tagged_statement.tagged_transactions:
            key = (
                tagged.transaction.date,
                tagged.transaction.description,
                tagged.transaction.amount,
            )
            tagged_lookup[key] = tagged

    # Build the output structure
    output = {
        "bank_name": statement.bank_name,
        "account_number": statement.account_number,
        "statement_period": {
            "start": (
                statement.statement_period_start.isoformat()
                if statement.statement_period_start
                else None
            ),
            "end": (
                statement.statement_period_end.isoformat()
                if statement.statement_period_end
                else None
            ),
        },
        "summary": statement.summary(),
    }

    # Add lender summary if available
    if tagged_statement:
        output["lender_summary"] = {
            "transfers": _format_lender_summary(tagged_statement.transfer_summary),
            "payments": _format_lender_summary(tagged_statement.payment_summary),
        }

    # Build transactions list
    transactions = []
    for txn in statement.transactions:
        txn_data = {
            "date": txn.date.isoformat(),
            "description": txn.description,
            "amount": str(txn.amount),
            "transaction_type": txn.transaction_type.value,
            "check_number": txn.check_number,
        }

        if tagged_statement:
            key = (txn.date, txn.description, txn.amount)
            tagged = tagged_lookup.get(key)
            if tagged:
                txn_data["lender_matches"] = [
                    m.lender_name for m in tagged.lender_matches
                ]
                txn_data["is_lender_transfer"] = txn.is_lender_transfer
                txn_data["is_lender_payment"] = txn.is_lender_payment
            else:
                txn_data["lender_matches"] = []
                txn_data["is_lender_transfer"] = False
                txn_data["is_lender_payment"] = False

        transactions.append(txn_data)

    output["transactions"] = transactions

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

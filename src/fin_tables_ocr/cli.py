"""Command-line interface for fin-tables-ocr."""

from pathlib import Path

import typer

from .extractor import extract_statement
from .lender_tagger import load_keywords, tag_statement, TaggedStatement
from .models import TransactionType
from .outputs import write_csv, write_json

app = typer.Typer(
    name="fin-tables-ocr",
    help="Extract transaction data from bank statement PDFs.",
)


def _apply_lender_tags(statement, tagged_statement: TaggedStatement) -> None:
    """Apply lender tags from tagged_statement to statement transactions."""
    # Build lookup by transaction identity
    tagged_lookup = {}
    for tagged in tagged_statement.tagged_transactions:
        key = (
            tagged.transaction.date,
            tagged.transaction.description,
            tagged.transaction.amount,
        )
        tagged_lookup[key] = tagged

    for txn in statement.transactions:
        key = (txn.date, txn.description, txn.amount)
        tagged = tagged_lookup.get(key)
        if tagged:
            txn.lender_matches = [m.lender_name for m in tagged.lender_matches]
            is_deposit = txn.transaction_type == TransactionType.DEPOSIT
            is_withdrawal = txn.transaction_type in (
                TransactionType.WITHDRAWAL,
                TransactionType.CHECK,
            )
            has_lender_match = len(tagged.lender_matches) > 0

            # Transfers: deposits matching transferKeywords OR any lender keyword
            txn.is_lender_transfer = is_deposit and (
                tagged.is_transfer or has_lender_match
            )
            # Payments: withdrawals/checks matching any lender keyword
            txn.is_lender_payment = is_withdrawal and has_lender_match


@app.command()
def extract(
    pdf_path: Path = typer.Argument(
        ...,
        help="Path to the bank statement PDF file",
        exists=True,
        readable=True,
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output",
        "-o",
        help="Output directory for CSV and JSON files",
    ),
    keywords_path: Path = typer.Option(
        ...,
        "--keywords",
        "-k",
        help="Path to keywords.json file for lender tagging",
        exists=True,
        readable=True,
    ),
) -> None:
    """Extract transactions from a bank statement PDF.

    Outputs both CSV and JSON files to the specified directory.
    """
    typer.echo(f"Processing: {pdf_path}")

    try:
        # Load keywords
        keywords = load_keywords(keywords_path)
        typer.echo(f"Loaded keywords from: {keywords_path}")

        # Extract statement
        statement = extract_statement(pdf_path)

        # Tag transactions with lender info
        tagged_statement = tag_statement(statement, keywords)

        # Apply lender tags to the statement transactions
        _apply_lender_tags(statement, tagged_statement)

        # Generate output filenames
        stem = pdf_path.stem
        csv_path = output_dir / f"{stem}.csv"
        json_path = output_dir / f"{stem}.json"

        # Write outputs with lender info
        write_csv(statement, csv_path, tagged_statement)
        write_json(statement, json_path, tagged_statement)

        # Print summary
        typer.echo(f"\nBank: {statement.bank_name}")
        if statement.account_number:
            typer.echo(f"Account: ...{statement.account_number[-4:]}")
        if statement.statement_period_start and statement.statement_period_end:
            typer.echo(
                f"Period: {statement.statement_period_start} to {statement.statement_period_end}"
            )

        typer.echo(f"\nExtracted {len(statement.transactions)} transactions:")
        typer.echo(f"  - Checks: {len(statement.checks)}")
        typer.echo(f"  - Withdrawals: {len(statement.withdrawals)}")
        typer.echo(f"  - Deposits: {len(statement.deposits)}")

        # Print lender summary
        typer.echo("\nLender Summary:")
        ts = tagged_statement.transfer_summary
        ps = tagged_statement.payment_summary

        typer.echo(f"  Transfers (deposits): {ts.count} totaling ${ts.total:,.2f}")
        if ts.by_lender:
            for lender, data in sorted(ts.by_lender.items()):
                typer.echo(
                    f"    - {lender}: {data['count']} totaling ${data['total']:,.2f}"
                )

        typer.echo(f"  Payments (withdrawals): {ps.count} totaling ${ps.total:,.2f}")
        if ps.by_lender:
            for lender, data in sorted(ps.by_lender.items()):
                typer.echo(
                    f"    - {lender}: {data['count']} totaling ${data['total']:,.2f}"
                )

        typer.echo(f"\nOutput files:")
        typer.echo(f"  - {csv_path}")
        typer.echo(f"  - {json_path}")

    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def info(
    pdf_path: Path = typer.Argument(
        ...,
        help="Path to the bank statement PDF file",
        exists=True,
        readable=True,
    ),
) -> None:
    """Show information about a bank statement PDF without extracting."""
    from .banks import detect_bank

    typer.echo(f"File: {pdf_path}")

    parser_class = detect_bank(pdf_path)
    if parser_class:
        typer.echo(f"Detected bank: {parser_class.bank_name}")
    else:
        typer.echo("Could not detect bank - may not be supported")


if __name__ == "__main__":
    app()

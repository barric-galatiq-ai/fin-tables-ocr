"""Pydantic models for bank statement data."""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class TransactionType(str, Enum):
    CHECK = "check"
    WITHDRAWAL = "withdrawal"
    DEPOSIT = "deposit"


class Transaction(BaseModel):
    """A single bank transaction."""

    date: date
    description: str
    amount: Decimal = Field(ge=0)
    transaction_type: TransactionType
    check_number: int | None = None

    # Lender tagging fields (populated by lender_tagger)
    lender_matches: list[str] | None = None
    is_lender_transfer: bool = False
    is_lender_payment: bool = False

    model_config = {"json_encoders": {Decimal: str}}


class BankStatement(BaseModel):
    """A complete bank statement with all transactions."""

    bank_name: str
    account_number: str | None = None
    statement_period_start: date | None = None
    statement_period_end: date | None = None
    transactions: list[Transaction] = Field(default_factory=list)

    @property
    def checks(self) -> list[Transaction]:
        return [t for t in self.transactions if t.transaction_type == TransactionType.CHECK]

    @property
    def withdrawals(self) -> list[Transaction]:
        return [t for t in self.transactions if t.transaction_type == TransactionType.WITHDRAWAL]

    @property
    def deposits(self) -> list[Transaction]:
        return [t for t in self.transactions if t.transaction_type == TransactionType.DEPOSIT]

    def summary(self) -> dict:
        return {
            "bank_name": self.bank_name,
            "total_transactions": len(self.transactions),
            "checks": len(self.checks),
            "withdrawals": len(self.withdrawals),
            "deposits": len(self.deposits),
        }

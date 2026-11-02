"""Every boto3 DynamoDB call the loader makes lives here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Table:
    """A low-level `dynamodb` client bound to one table name."""

    client: Any
    name: str
    # Table create/delete/reset are allowed only on an emulator (floci, moto), never on AWS.
    on_emulator: bool

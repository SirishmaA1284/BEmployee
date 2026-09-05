"""Business-rule errors shared by services and their callers.

Services raise `BusinessRuleError` for any rejected operation (unknown
entity, insufficient stock, illegal state transition). Callers translate it:
the API layer converts it to an HTTP response, the tool registry converts it
to a structured tool error — neither maps service logic to `None` checks.
"""

from typing import Any


class BusinessRuleError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
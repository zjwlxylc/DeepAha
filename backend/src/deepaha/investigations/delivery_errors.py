"""Stable delivery errors shared with the explicit historical replay boundary."""

from typing import NoReturn


class DeliveryValidationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def fail(code: str) -> NoReturn:
    raise DeliveryValidationError(code)

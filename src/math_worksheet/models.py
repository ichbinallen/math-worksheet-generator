"""Core data types for math worksheet problems."""

from dataclasses import dataclass
from enum import Enum


class Operation(str, Enum):
    """A supported arithmetic operation."""

    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    DIV = "div"

    @property
    def symbol(self) -> str:
        return _SYMBOLS[self]

    @property
    def long_name(self) -> str:
        return _LONG_NAMES[self]

    @classmethod
    def from_name(cls, name: "str | Operation") -> "Operation":
        """Look up an operation by short (``"add"``) or long (``"addition"``) name."""
        if isinstance(name, Operation):
            return name
        key = name.strip().lower()
        for op in cls:
            if key in (op.value, op.long_name):
                return op
        names = ", ".join(op.long_name for op in cls)
        raise ValueError(f"unknown problem type: {name!r} (choose from {names})")


_LONG_NAMES = {
    Operation.ADD: "addition",
    Operation.SUB: "subtraction",
    Operation.MUL: "multiplication",
    Operation.DIV: "division",
}

_SYMBOLS = {
    Operation.ADD: "+",
    Operation.SUB: "-",
    Operation.MUL: "x",
    Operation.DIV: "/",
}


@dataclass(frozen=True)
class Problem:
    """A single arithmetic problem, e.g. ``14 / 2 = 7``."""

    left: int
    right: int
    op: Operation
    answer: int

    @property
    def question(self) -> str:
        return f"{_fmt(self.left)} {self.op.symbol} {_fmt(self.right)}"


def _fmt(n: int) -> str:
    """Wrap negative numbers in parentheses so ``5 - (-3)`` reads clearly."""
    return f"({n})" if n < 0 else str(n)

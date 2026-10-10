"""Random generation of arithmetic problems."""

import random
from collections.abc import Iterable, Mapping, Sequence

from .models import Operation, Problem

# Which problem types to include: either on/off switches keyed by name, e.g.
# {"addition": True, "subtraction": True, "multiplication": False, "division": False},
# or simply the operations to include, e.g. [Operation.ADD, Operation.SUB].
ProblemTypes = Mapping[str | Operation, bool] | Iterable[str | Operation]

DEFAULT_TYPES: dict[str, bool] = {
    "addition": True,
    "subtraction": False,
    "multiplication": False,
    "division": False,
}
DEFAULT_COUNT = 100
DEFAULT_MIN = 0
DEFAULT_MAX = 10

# How many times to re-roll a problem that was already generated before
# accepting a duplicate (small ranges may not have enough unique problems).
_MAX_UNIQUE_ATTEMPTS = 50


def select_operations(types: ProblemTypes | None = None) -> list[Operation]:
    """Resolve problem-type switches (or a list of types) to the enabled operations.

    ``None`` means :data:`DEFAULT_TYPES` (addition only). Names may be long
    (``"addition"``) or short (``"add"``); types missing from a mapping are off.
    """
    if types is None:
        types = DEFAULT_TYPES
    if isinstance(types, Mapping):
        names = [name for name, enabled in types.items() if enabled]
    elif isinstance(types, str):  # a single type, e.g. "addition" (Operation is a str too)
        names = [types]
    else:
        names = list(types)
    ops = list(dict.fromkeys(Operation.from_name(name) for name in names))
    if not ops:
        raise ValueError("at least one problem type must be enabled")
    return ops


def generate_problem_list(
    types: ProblemTypes | None = None,
    count: int = DEFAULT_COUNT,
    min_value: int = DEFAULT_MIN,
    max_value: int = DEFAULT_MAX,
    allow_negatives: bool = False,
    seed: int | None = None,
) -> list[Problem]:
    """Generate ``count`` random problems of the enabled ``types``.

    ``types`` is a mapping of on/off switches such as
    ``{"addition": True, "subtraction": True, "multiplication": False, "division": False}``,
    or a list of types; it defaults to addition only. When several types are
    enabled, each problem's type is picked at random.

    Operands are drawn from ``[min_value, max_value]``. For division, the
    divisor and the quotient are drawn from that range and the dividend is
    their product, so every division problem has a zero remainder.

    When ``allow_negatives`` is False, ``min_value`` must be >= 0 and
    subtraction operands are ordered so the answer is never negative.
    """
    ops = select_operations(types)
    _validate(ops, count, min_value, max_value, allow_negatives)

    rng = random.Random(seed)
    problems: list[Problem] = []
    seen: set[Problem] = set()

    for _ in range(count):
        for _ in range(_MAX_UNIQUE_ATTEMPTS):
            problem = _make_problem(rng, rng.choice(ops), min_value, max_value, allow_negatives)
            if problem not in seen:
                break
        seen.add(problem)
        problems.append(problem)

    return problems


def generate_worksheets(
    worksheets: int,
    types: ProblemTypes | None = None,
    count: int = DEFAULT_COUNT,
    min_value: int = DEFAULT_MIN,
    max_value: int = DEFAULT_MAX,
    allow_negatives: bool = False,
    seed: int | None = None,
) -> list[list[Problem]]:
    """Generate ``worksheets`` independent lists of ``count`` problems each.

    With a ``seed``, worksheet *i* (from 0) uses ``seed + i``, so a batch is
    reproducible and its first worksheet matches a single worksheet with the
    same seed.
    """
    if worksheets < 1:
        raise ValueError("worksheets must be at least 1")
    return [
        generate_problem_list(
            types, count, min_value, max_value, allow_negatives, None if seed is None else seed + i
        )
        for i in range(worksheets)
    ]


def generate_problems(
    types: ProblemTypes | None = None,
    count: int = DEFAULT_COUNT,
    min_value: int = DEFAULT_MIN,
    max_value: int = DEFAULT_MAX,
    allow_negatives: bool = False,
    seed: int | None = None,
) -> dict[int, tuple[str, int]]:
    """Generate problems as ``{number: (question, answer)}``, numbered from 1."""
    problems = generate_problem_list(types, count, min_value, max_value, allow_negatives, seed)
    return to_dict(problems)


def to_dict(problems: Sequence[Problem]) -> dict[int, tuple[str, int]]:
    return {i: (p.question, p.answer) for i, p in enumerate(problems, start=1)}


def _validate(
    ops: Sequence[Operation],
    count: int,
    min_value: int,
    max_value: int,
    allow_negatives: bool,
) -> None:
    if count < 1:
        raise ValueError("count must be at least 1")
    if min_value > max_value:
        raise ValueError(f"min ({min_value}) must be <= max ({max_value})")
    if not allow_negatives and min_value < 0:
        raise ValueError("min must be >= 0 unless negatives are allowed")
    if Operation.DIV in ops and min_value == max_value == 0:
        raise ValueError("division needs a nonzero divisor in the range")


def _make_problem(
    rng: random.Random,
    op: Operation,
    lo: int,
    hi: int,
    allow_negatives: bool,
) -> Problem:
    if op is Operation.DIV:
        divisor = 0
        while divisor == 0:
            divisor = rng.randint(lo, hi)
        quotient = rng.randint(lo, hi)
        return Problem(divisor * quotient, divisor, op, quotient)

    a, b = rng.randint(lo, hi), rng.randint(lo, hi)
    if op is Operation.ADD:
        return Problem(a, b, op, a + b)
    if op is Operation.SUB:
        if not allow_negatives and a < b:
            a, b = b, a
        return Problem(a, b, op, a - b)
    return Problem(a, b, op, a * b)

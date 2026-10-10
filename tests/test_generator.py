import pytest

from math_worksheet import (
    DEFAULT_TYPES,
    Operation,
    Problem,
    generate_problem_list,
    generate_problems,
    generate_worksheets,
    select_operations,
)

ALL_OPS = list(Operation)


def _check_answer(p: Problem) -> None:
    if p.op is Operation.ADD:
        assert p.answer == p.left + p.right
    elif p.op is Operation.SUB:
        assert p.answer == p.left - p.right
    elif p.op is Operation.MUL:
        assert p.answer == p.left * p.right
    else:
        assert p.right != 0
        assert p.left % p.right == 0
        assert p.answer == p.left // p.right


@pytest.mark.parametrize("seed", range(20))
@pytest.mark.parametrize("op", ALL_OPS)
def test_answers_correct_and_operands_in_range(op, seed):
    problems = generate_problem_list([op], count=200, min_value=2, max_value=12, seed=seed)
    for p in problems:
        _check_answer(p)
        if op is Operation.DIV:
            # divisor and quotient come from the range; dividend is their product
            assert 2 <= p.right <= 12
            assert 2 <= p.answer <= 12
        elif op is Operation.SUB:
            assert {p.left, p.right} <= set(range(2, 13))
        else:
            assert 2 <= p.left <= 12 and 2 <= p.right <= 12


@pytest.mark.parametrize("seed", range(20))
def test_no_negatives_by_default(seed):
    for p in generate_problem_list(ALL_OPS, count=200, min_value=0, max_value=20, seed=seed):
        assert p.left >= 0 and p.right >= 0 and p.answer >= 0


def test_negatives_allowed():
    problems = generate_problem_list(ALL_OPS, count=500, min_value=-10, max_value=10, allow_negatives=True, seed=1)
    for p in problems:
        _check_answer(p)
    assert any(p.answer < 0 for p in problems)


def test_subtraction_can_go_negative_when_allowed():
    problems = generate_problem_list([Operation.SUB], count=200, min_value=0, max_value=10, allow_negatives=True, seed=3)
    assert any(p.answer < 0 for p in problems)


def test_select_operations():
    assert select_operations() == [Operation.ADD]
    assert select_operations(DEFAULT_TYPES) == [Operation.ADD]
    switches = {"addition": True, "subtraction": True, "multiplication": False, "division": False}
    assert select_operations(switches) == [Operation.ADD, Operation.SUB]
    assert select_operations({"mul": True, Operation.DIV: True}) == [Operation.MUL, Operation.DIV]
    assert select_operations("division") == [Operation.DIV]
    assert select_operations(["Addition", "add", Operation.ADD]) == [Operation.ADD]


def test_type_switches_drive_generation():
    switches = {"addition": True, "subtraction": True, "multiplication": False, "division": False}
    problems = generate_problem_list(switches, count=200, seed=0)
    assert {p.op for p in problems} == {Operation.ADD, Operation.SUB}
    assert {p.op for p in generate_problem_list(count=50, seed=0)} == {Operation.ADD}


def test_default_count_is_100():
    assert len(generate_problem_list([Operation.ADD])) == 100


def test_dict_output_format():
    result = generate_problems([Operation.ADD], count=5, seed=0)
    assert list(result) == [1, 2, 3, 4, 5]
    for question, answer in result.values():
        left, symbol, right = question.split()
        assert symbol == "+"
        assert int(left) + int(right) == answer


def test_seed_is_reproducible():
    assert generate_problems(ALL_OPS, seed=42) == generate_problems(ALL_OPS, seed=42)
    assert generate_problems(ALL_OPS, seed=42) != generate_problems(ALL_OPS, seed=43)


def test_avoids_duplicates_when_possible():
    # 0..10 addition has 121 unique problems, so 100 should all be distinct
    problems = generate_problem_list([Operation.ADD], count=100, min_value=0, max_value=10, seed=5)
    assert len(set(problems)) == 100


def test_tiny_range_allows_repeats():
    problems = generate_problem_list([Operation.ADD], count=100, min_value=0, max_value=1, seed=0)
    assert len(problems) == 100
    assert len(set(problems)) <= 4


def test_division_excludes_zero_divisor():
    problems = generate_problem_list([Operation.DIV], count=200, min_value=0, max_value=3, seed=0)
    assert all(p.right != 0 for p in problems)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"types": []},
        {"types": {"addition": False, "subtraction": False}},
        {"types": ["exponents"]},
        {"types": [Operation.ADD], "count": 0},
        {"types": [Operation.ADD], "min_value": 10, "max_value": 5},
        {"types": [Operation.ADD], "min_value": -5},
        {"types": [Operation.DIV], "min_value": 0, "max_value": 0},
    ],
)
def test_invalid_args(kwargs):
    with pytest.raises(ValueError):
        generate_problem_list(**kwargs)


def test_worksheets_are_reproducible_and_start_with_the_single_seed():
    sheets = generate_worksheets(3, count=20, seed=42)
    assert len(sheets) == 3 and all(len(sheet) == 20 for sheet in sheets)
    assert sheets[0] == generate_problem_list(count=20, seed=42)
    assert sheets == generate_worksheets(3, count=20, seed=42)
    assert sheets[0] != sheets[1] != sheets[2]


def test_worksheets_must_be_positive():
    with pytest.raises(ValueError, match="worksheets"):
        generate_worksheets(0)

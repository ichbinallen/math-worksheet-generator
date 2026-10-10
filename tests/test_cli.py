import csv
import io
import json

import pytest

from math_worksheet.cli import main


def test_text_output(capsys):
    assert main(["--addition", "-n", "5", "--seed", "1"]) == 0
    out = capsys.readouterr().out
    assert "Worksheet" in out and "Answer Key" in out
    assert out.count("= ____") == 5


def test_no_answers(capsys):
    main(["--addition", "-n", "5", "--no-answers"])
    assert "Answer Key" not in capsys.readouterr().out


def test_json_output(capsys):
    main(["--division", "--min", "1", "--max", "12", "-n", "20", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert list(data) == [str(i) for i in range(1, 21)]
    for entry in data.values():
        dividend, _, divisor = entry["question"].split()
        assert int(dividend) % int(divisor) == 0
        assert int(dividend) // int(divisor) == entry["answer"]


def test_csv_output(capsys):
    main(["--subtraction", "--max", "20", "-n", "50", "--format", "csv"])
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert len(rows) == 50
    assert all(int(r["answer"]) >= 0 for r in rows)


def _symbols(argv, capsys) -> set[str]:
    main([*argv, "-n", "200", "--min", "1", "--seed", "0", "-f", "csv"])
    questions = [r["question"] for r in csv.DictReader(io.StringIO(capsys.readouterr().out))]
    return {q.split()[1] for q in questions}


def test_default_is_addition_only(capsys):
    assert _symbols([], capsys) == {"+"}


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--addition", "--subtraction"], {"+", "-"}),
        (["--add", "--sub"], {"+", "-"}),
        (["--multiplication"], {"x"}),
        (["--mul", "--div"], {"x", "/"}),
        (["--addition", "--subtraction", "--multiplication", "--division"], {"+", "-", "x", "/"}),
    ],
)
def test_type_switches(argv, expected, capsys):
    assert _symbols(argv, capsys) == expected


def test_output_file(tmp_path):
    target = tmp_path / "sheet.txt"
    main(["--addition", "-n", "3", "-o", str(target)])
    assert target.read_text().count("= ____") == 3


@pytest.mark.parametrize(
    "argv",
    [
        ["--subtraction", "--min", "-5", "--max", "5"],
        ["--addition", "--min", "10", "--max", "1"],
        ["--addition", "-n", "0"],
        ["--exponents"],
        ["-t", "add"],  # replaced by --addition etc.
    ],
)
def test_invalid_args_exit_with_error(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2
    assert "error" in capsys.readouterr().err

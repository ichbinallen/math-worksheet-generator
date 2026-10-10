import builtins
import re
import sys

import pytest
from pypdf import PdfReader

from math_worksheet import Operation, generate_problem_list, generate_worksheets
from math_worksheet.cli import main
from math_worksheet.pdf import write_pdf, write_worksheets_pdf

ALL_OPS = list(Operation)


def _pages(path) -> list[str]:
    return [page.extract_text() for page in PdfReader(path).pages]


@pytest.mark.parametrize(("answers", "expected"), [(True, 10), (False, 5)])
def test_page_count(tmp_path, answers, expected):
    problems = generate_problem_list(ALL_OPS, count=100, min_value=1, seed=0)
    out = tmp_path / "w.pdf"
    assert write_pdf(problems, out, rows=5, cols=4, answers=answers) == expected
    assert len(_pages(out)) == expected


def test_partial_last_page(tmp_path):
    problems = generate_problem_list([Operation.ADD], count=23, seed=0)
    out = tmp_path / "w.pdf"
    assert write_pdf(problems, out, rows=5, cols=4, answers=False) == 2
    assert "23." in _pages(out)[1]


def test_inline_answers_only_on_answer_key(tmp_path):
    problems = generate_problem_list([Operation.MUL], count=6, min_value=11, max_value=99, seed=1)
    out = tmp_path / "w.pdf"
    write_pdf(problems, out, rows=3, cols=2, layout="inline")
    sheet, key = _pages(out)
    assert "Name:" in sheet and "Answer Key" in key
    for p in problems:
        assert p.question in sheet and p.question in key
        assert str(p.answer) in key
        assert str(p.answer) not in sheet  # products of 2-digit numbers have 3+ digits


@pytest.mark.parametrize("layout", ["vertical", "inline"])
@pytest.mark.parametrize("op", ALL_OPS)
def test_every_layout_and_operation_renders(tmp_path, layout, op):
    problems = generate_problem_list([op], count=30, min_value=-20, max_value=20, allow_negatives=True, seed=2)
    out = tmp_path / "w.pdf"
    write_pdf(problems, out, rows=6, cols=5, layout=layout, page_size="a4")
    key = _pages(out)[1]
    for p in problems:
        assert str(p.answer) in key


@pytest.mark.parametrize(
    "kwargs",
    [{"rows": 0}, {"cols": 0}, {"layout": "diagonal"}, {"page_size": "legal"}],
)
def test_invalid_options(tmp_path, kwargs):
    problems = generate_problem_list([Operation.ADD], count=1)
    with pytest.raises(ValueError):
        write_pdf(problems, tmp_path / "w.pdf", **kwargs)


def test_cli_infers_pdf_from_extension(tmp_path, capsys):
    out = tmp_path / "sheet.pdf"
    assert main(["--division", "--min", "1", "--max", "12", "-n", "20", "--rows", "4", "--cols", "5", "-o", str(out)]) == 0
    assert out.read_bytes().startswith(b"%PDF")
    assert len(_pages(out)) == 2
    assert "(2 pages)" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["--addition", "-f", "pdf"],  # no output file
        ["--addition", "--rows", "0", "-o", "x.pdf"],
        ["--addition", "--cols", "-1", "-o", "x.pdf"],
        ["--addition", "--layout", "diagonal", "-o", "x.pdf"],
    ],
)
def test_cli_pdf_errors(argv, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2


def test_cli_without_reportlab(tmp_path, monkeypatch, capsys):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("reportlab"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "math_worksheet.pdf", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(SystemExit) as exc:
        main(["--addition", "-o", str(tmp_path / "x.pdf")])
    assert exc.value.code == 2
    assert "math-worksheet[pdf]" in capsys.readouterr().err


def test_score_field_on_first_page_only(tmp_path):
    problems = generate_problem_list([Operation.ADD], count=30, seed=0)
    out = tmp_path / "w.pdf"
    write_pdf(problems, out, rows=5, cols=4)
    reader = PdfReader(out)
    assert set(reader.get_fields()) == {"score"}
    assert reader.get_fields()["score"]["/FT"] == "/Tx"
    pages = _pages(out)
    assert "Score:" in pages[0] and "/ 30" in pages[0]
    assert all("Score:" not in text for text in pages[1:])


@pytest.mark.parametrize("grid_lines", [True, False])
def test_grid_lines(tmp_path, grid_lines):
    problems = generate_problem_list([Operation.ADD], count=3, seed=0)
    out = tmp_path / "w.pdf"
    write_pdf(problems, out, rows=2, cols=2, answers=False, grid_lines=grid_lines)
    content = PdfReader(out).pages[0].get_contents().get_data()
    # one rectangle ("re") per occupied cell, none for the empty fourth cell
    assert content.count(b" re ") == (3 if grid_lines else 0)


def _cell_heights(path) -> set[float]:
    content = PdfReader(path).pages[0].get_contents().get_data().decode("latin-1")
    return {round(float(m.group(1)), 1) for m in re.finditer(r"\S+ \S+ \S+ (\S+) re ", content)}


def test_inline_rows_are_compact(tmp_path):
    problems = generate_problem_list([Operation.ADD], count=40, seed=0)
    inline, vertical = tmp_path / "inline.pdf", tmp_path / "vertical.pdf"
    write_pdf(problems, inline, rows=10, cols=4, layout="inline", answers=False)
    write_pdf(problems, vertical, rows=10, cols=4, layout="vertical", answers=False)
    (inline_h,), (vertical_h,) = _cell_heights(inline), _cell_heights(vertical)
    # vertical cells stretch to fill the page; inline cells hug a single line of text
    assert inline_h < 0.75 * vertical_h


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"rows": 10, "cols": 10, "layout": "inline"}, "too wide for 10 columns"),
        ({"rows": 80, "cols": 2, "layout": "vertical"}, "too tall for 80 rows"),
    ],
)
def test_problems_that_cannot_fit_are_rejected(tmp_path, kwargs, message):
    problems = generate_problem_list(
        [Operation.ADD, Operation.SUB], count=100, min_value=-1000, max_value=1000, allow_negatives=True, seed=1
    )
    out = tmp_path / "w.pdf"
    with pytest.raises(ValueError, match=message):
        write_pdf(problems, out, **kwargs)
    assert not out.exists()


def test_cli_reports_how_many_columns_fit(tmp_path, capsys):
    argv = ["--add", "--sub", "--min=-1000", "--max=1000", "--allow-negatives", "--layout", "inline"]
    with pytest.raises(SystemExit) as exc:
        main([*argv, "--rows", "10", "--cols", "10", "-o", str(tmp_path / "x.pdf")])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    fit = int(re.search(r"at most (\d+) fit", err).group(1))
    # the suggested column count really does fit
    assert main([*argv, "--rows", "10", "--cols", str(fit), "-o", str(tmp_path / "ok.pdf")]) == 0


def test_batch_puts_all_worksheets_before_all_answer_keys(tmp_path):
    sheets = generate_worksheets(3, [Operation.MUL], count=10, min_value=11, max_value=99, seed=0)
    out = tmp_path / "batch.pdf"
    assert write_worksheets_pdf(sheets, out, rows=5, cols=2, layout="inline") == 6
    pages = _pages(out)
    for n, problems in enumerate(sheets, start=1):
        sheet, key = pages[n - 1], pages[n + 2]
        assert f"Math Worksheet #{n}" in sheet and "Name:" in sheet and "Answer Key" not in sheet
        assert f"Math Worksheet #{n} — Answer Key" in key
        for p in problems:
            assert p.question in sheet and p.question in key
            assert str(p.answer) in key and str(p.answer) not in sheet
    assert set(PdfReader(out).get_fields()) == {"score_1", "score_2", "score_3"}


def test_batch_score_on_first_page_of_each_worksheet(tmp_path):
    sheets = generate_worksheets(2, [Operation.ADD], count=30, seed=0)
    out = tmp_path / "batch.pdf"
    assert write_worksheets_pdf(sheets, out, rows=5, cols=4) == 8
    pages = _pages(out)
    assert [i for i, text in enumerate(pages) if "Score:" in text] == [0, 2]
    assert [i for i, text in enumerate(pages) if "Answer Key" in text] == [4, 5, 6, 7]
    assert "Page 8 of 8" in pages[7]


def test_batch_without_answers(tmp_path):
    sheets = generate_worksheets(4, count=20, seed=0)
    out = tmp_path / "batch.pdf"
    assert write_worksheets_pdf(sheets, out, rows=5, cols=4, answers=False) == 4
    assert not any("Answer Key" in text for text in _pages(out))


@pytest.mark.parametrize("worksheets", [[], [generate_problem_list(count=3), []]])
def test_batch_rejects_empty_worksheets(tmp_path, worksheets):
    with pytest.raises(ValueError, match="no problems"):
        write_worksheets_pdf(worksheets, tmp_path / "w.pdf")


def test_single_worksheet_has_no_batch_number(tmp_path):
    out = tmp_path / "w.pdf"
    write_pdf(generate_problem_list(count=5, seed=0), out, rows=5, cols=4)
    assert all("#" not in text for text in _pages(out))


def test_cli_batch(tmp_path, capsys):
    out = tmp_path / "week.pdf"
    assert main(["--worksheets", "7", "--rows", "10", "--cols", "10", "--seed", "42", "-o", str(out)]) == 0
    assert len(_pages(out)) == 14
    err = capsys.readouterr().err
    assert "7 worksheets (700 problems, 14 pages)" in err
    assert "worksheets on pages 1-7, answer keys on pages 8-14" in err


def test_cli_batch_without_answers(tmp_path, capsys):
    out = tmp_path / "week.pdf"
    assert main(["--worksheets", "3", "-n", "20", "--no-answers", "-o", str(out)]) == 0
    assert len(_pages(out)) == 3
    assert "answer keys" not in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["--worksheets", "2", "-f", "json"],
        ["--worksheets", "2"],  # text to stdout
        ["--worksheets", "0", "-o", "x.pdf"],
    ],
)
def test_cli_batch_errors(argv, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2
    assert "worksheets" in capsys.readouterr().err

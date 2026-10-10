"""Render problems as a printable PDF worksheet laid out in a grid.

This is the only module that depends on ReportLab, which is an optional extra:
``pip install math-worksheet[pdf]``.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from math import ceil
from os import PathLike
from typing import BinaryIO

from reportlab.lib.colors import Color, black
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from .models import Operation, Problem

LAYOUTS = ("vertical", "inline")
PAGE_SIZES = {"letter": LETTER, "a4": A4}

FONT = "Helvetica"
MARGIN = 0.6 * inch
HEADER_HEIGHT = 0.9 * inch
FOOTER_HEIGHT = 0.3 * inch
MAX_FONT_SIZE = 28
MIN_FONT_SIZE = 6
LABEL_COLOR = Color(0.45, 0.45, 0.45)
GRID_COLOR = Color(0.7, 0.7, 0.7)

# Fraction of a cell that problem content may occupy, leaving whitespace for work.
_FILL_W = 0.8
_FILL_H = 0.75

# Line spacing for stacked layouts, in multiples of the font size.
_LINE = 1.25
# Inline layout, in multiples of the font size: space between "=" and the
# answer slot, extra slack on the answer slot, and the row height. Inline rows
# are sized to their content rather than stretched to fill the page.
_INLINE_GAP = 0.4
_INLINE_BLANK_PAD = 0.6
_INLINE_ROW = 2.2
_INLINE_LABEL_SCALE = 0.75


def write_pdf(
    problems: Sequence[Problem],
    path: str | PathLike[str] | BinaryIO,
    *,
    rows: int = 5,
    cols: int = 4,
    layout: str = "vertical",
    answers: bool = True,
    page_size: str = "letter",
    title: str = "Math Worksheet",
    grid_lines: bool = True,
) -> int:
    """Write ``problems`` to a PDF in a ``rows`` x ``cols`` grid per page.

    The first worksheet page has a fillable "Score: ___ / N" field. When
    ``answers`` is True, answer-key pages with the same grid follow the
    worksheet pages. Returns the total number of pages written.
    """
    return write_worksheets_pdf(
        [problems],
        path,
        rows=rows,
        cols=cols,
        layout=layout,
        answers=answers,
        page_size=page_size,
        title=title,
        grid_lines=grid_lines,
    )


def write_worksheets_pdf(
    worksheets: Sequence[Sequence[Problem]],
    path: str | PathLike[str] | BinaryIO,
    *,
    rows: int = 5,
    cols: int = 4,
    layout: str = "vertical",
    answers: bool = True,
    page_size: str = "letter",
    title: str = "Math Worksheet",
    grid_lines: bool = True,
) -> int:
    """Write several worksheets to one PDF, so a batch prints as a single job.

    All worksheet pages come first, then (when ``answers`` is True) all the
    answer keys in the same order, so the printed stack splits into student
    copies and keys. With more than one worksheet, each is titled
    ``"<title> #n"`` and gets its own Score field. Each worksheet is laid out
    exactly as :func:`write_pdf` would lay it out alone. Returns the total
    number of pages written.
    """
    if rows < 1 or cols < 1:
        raise ValueError("rows and cols must be at least 1")
    if layout not in LAYOUTS:
        raise ValueError(f"unknown layout: {layout!r} (choose from {', '.join(LAYOUTS)})")
    if page_size not in PAGE_SIZES:
        raise ValueError(f"unknown page size: {page_size!r} (choose from {', '.join(PAGE_SIZES)})")
    if not worksheets or not all(worksheets):
        raise ValueError("no problems to write")

    page_w, page_h = PAGE_SIZES[page_size]
    page_grid = _Grid(
        left=MARGIN,
        top=page_h - MARGIN - HEADER_HEIGHT,
        cell_w=(page_w - 2 * MARGIN) / cols,
        cell_h=(page_h - 2 * MARGIN - HEADER_HEIGHT - FOOTER_HEIGHT) / rows,
        rows=rows,
        cols=cols,
    )
    # Lay out every worksheet before creating the file, so one that cannot fit
    # raises without leaving a partial PDF behind.
    layouts = [_Layout.fit(problems, page_grid, layout) for problems in worksheets]

    per_page = rows * cols
    sheet_pages = sum(ceil(len(problems) / per_page) for problems in worksheets)
    total_pages = sheet_pages * (2 if answers else 1)

    canvas = Canvas(path if not isinstance(path, PathLike) else str(path), pagesize=(page_w, page_h))
    canvas.setTitle(title)
    canvas.setCreator("math-worksheet")

    batch = len(worksheets) > 1
    passes = [False, True] if answers else [False]
    page_no = 0
    for show_answers in passes:
        for n, (problems, sheet) in enumerate(zip(worksheets, layouts), start=1):
            grid, metrics, font_size = sheet.grid, sheet.metrics, sheet.font_size
            sheet_title = f"{title} #{n}" if batch else title
            score_field = f"score_{n}" if batch else "score"
            for start in range(0, len(problems), per_page):
                page_no += 1
                score_total = len(problems) if start == 0 else None
                _draw_header(canvas, page_w, page_h, sheet_title, show_answers, score_total, score_field)
                for i, problem in enumerate(problems[start : start + per_page]):
                    x, y = grid.cell_origin(i)
                    if grid_lines:
                        _draw_cell_border(canvas, x, y, grid)
                    _draw_cell(canvas, problem, start + i + 1, x, y, grid, font_size, metrics, layout, show_answers)
                _draw_footer(canvas, page_w, page_no, total_pages)
                canvas.showPage()

    canvas.save()
    return total_pages


@dataclass(frozen=True)
class _Layout:
    """How one worksheet's problems are sized and placed on its pages."""

    grid: "_Grid"
    metrics: "_Metrics"
    font_size: float

    @classmethod
    def fit(cls, problems: Sequence[Problem], grid: "_Grid", layout: str) -> "_Layout":
        metrics = _Metrics.measure(problems, layout)
        font_size = metrics.font_size(grid)
        if layout == "inline":
            grid = replace(grid, cell_h=min(grid.cell_h, font_size * _INLINE_ROW))
        return cls(grid, metrics, font_size)


@dataclass(frozen=True)
class _Grid:
    left: float
    top: float
    cell_w: float
    cell_h: float
    rows: int
    cols: int

    def cell_origin(self, index: int) -> tuple[float, float]:
        """Top-left corner of the ``index``-th cell on a page (row-major)."""
        row, col = divmod(index, self.cols)
        return self.left + col * self.cell_w, self.top - row * self.cell_h


@dataclass(frozen=True)
class _Metrics:
    """Widest content of each kind, measured at font size 1.

    Using sheet-wide widths keeps every problem in the grid the same size and
    aligned the same way, regardless of how many digits it has.
    """

    inline_label: float = 0.0  # "100." column, plus gap
    inline_text: float = 0.0  # "12 + 7 =" plus gap
    inline_blank: float = 0.0  # answer slot
    stack: float = 0.0  # vertical add/sub/mul block
    div_divisor: float = 0.0
    div_dividend: float = 0.0
    has_stack: bool = False
    has_div: bool = False

    @classmethod
    def measure(cls, problems: Sequence[Problem], layout: str) -> "_Metrics":
        if layout == "inline":
            return cls(
                inline_label=_w(f"{len(problems)}.") * _INLINE_LABEL_SCALE + _INLINE_GAP,
                inline_text=max(_w(f"{p.question} =") for p in problems) + _INLINE_GAP,
                inline_blank=max(max(_w(str(p.answer)) for p in problems), _w("00")) + _INLINE_BLANK_PAD,
            )
        stacks = [p for p in problems if p.op is not Operation.DIV]
        divs = [p for p in problems if p.op is Operation.DIV]
        return cls(
            stack=max((_stack_width(p) for p in stacks), default=0.0),
            div_divisor=max((_w(str(p.right)) for p in divs), default=0.0),
            div_dividend=max((_w(str(p.left)) for p in divs), default=0.0),
            has_stack=bool(stacks),
            has_div=bool(divs),
        )

    def font_size(self, grid: "_Grid") -> float:
        """Largest font size at which every problem fits inside a cell.

        Raises ValueError when the problems would not fit even at
        ``MIN_FONT_SIZE``, saying how many columns or rows would.
        """
        # Cell space needed per point of font size, including whitespace.
        if self.inline_text:
            # One line with the number label beside it; the row height follows the font.
            need_w = (self.inline_label + self.inline_text + self.inline_blank) / 0.9
            need_h = _INLINE_ROW
        else:
            # Stacked content plus the number label above it.
            boxes = []
            if self.has_stack:
                boxes.append((self.stack + _w("+ "), 3 * _LINE + 0.3))
            if self.has_div:
                boxes.append((_div_width(self.div_divisor, self.div_dividend), 2 * _LINE + 0.3))
            need_w = max(w for w, _ in boxes) / _FILL_W
            need_h = max(h + 0.6 for _, h in boxes) / _FILL_H

        width_size = grid.cell_w / need_w
        height_size = grid.cell_h / need_h
        if width_size < MIN_FONT_SIZE:
            fit = int(grid.cell_w * grid.cols / (need_w * MIN_FONT_SIZE))
            raise ValueError(
                f"these problems are too wide for {grid.cols} columns; "
                f"at most {fit} fit across the page (use fewer columns or smaller numbers)"
            )
        if height_size < MIN_FONT_SIZE:
            fit = int(grid.cell_h * grid.rows / (need_h * MIN_FONT_SIZE))
            raise ValueError(
                f"these problems are too tall for {grid.rows} rows; at most {fit} fit down the page"
            )
        return min(MAX_FONT_SIZE, width_size, height_size)


def _w(text: str, size: float = 1.0) -> float:
    return stringWidth(text, FONT, size)


def _stack_width(p: Problem) -> float:
    """Width of the right-aligned number column (operator excluded)."""
    return max(_w(str(p.left)), _w(str(p.right)), _w(str(p.answer)))


def _div_width(divisor_w: float, dividend_w: float) -> float:
    return divisor_w + 0.5 + dividend_w + 0.3


def _draw_header(
    canvas: Canvas,
    page_w: float,
    page_h: float,
    title: str,
    answer_key: bool,
    score_total: int | None,
    score_field: str = "score",
) -> None:
    top = page_h - MARGIN
    canvas.setFillColor(black)
    canvas.setFont(f"{FONT}-Bold", 18)
    canvas.drawString(MARGIN, top - 18, f"{title} — Answer Key" if answer_key else title)
    if score_total is not None and not answer_key:
        _draw_score_field(canvas, page_w - MARGIN, top - 18, score_total, score_field)
    if not answer_key:
        canvas.setFont(FONT, 11)
        y = top - 44
        canvas.drawString(MARGIN, y, "Name:")
        canvas.line(MARGIN + _w("Name: ", 11), y - 2, MARGIN + 3.2 * inch, y - 2)
        x = page_w - MARGIN - 2.4 * inch
        canvas.drawString(x, y, "Date:")
        canvas.line(x + _w("Date: ", 11), y - 2, page_w - MARGIN, y - 2)
    canvas.setStrokeColor(LABEL_COLOR)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, top - HEADER_HEIGHT + 8, page_w - MARGIN, top - HEADER_HEIGHT + 8)
    canvas.setStrokeColor(black)


def _draw_score_field(canvas: Canvas, right: float, baseline: float, total: int, name: str = "score") -> None:
    """Right-aligned ``Score: [    ] / total``; the box is a fillable form field.

    Fields with the same ``name`` share one value, so each worksheet in a
    batch needs its own.
    """
    fs = 13
    box_w, box_h = 0.75 * inch, 20
    suffix = f"/ {total}"
    suffix_x = right - _w(suffix, fs)
    box_x = suffix_x - 6 - box_w
    canvas.setFont(FONT, fs)
    canvas.drawString(suffix_x, baseline, suffix)
    canvas.drawRightString(box_x - 6, baseline, "Score:")
    canvas.acroForm.textfield(
        name=name,
        tooltip="Number of problems answered correctly",
        x=box_x,
        y=baseline - 5,
        width=box_w,
        height=box_h,
        fontName=FONT,
        fontSize=fs,
        borderColor=black,
        fillColor=None,
        borderWidth=1,
        maxlen=len(str(total)),
        fieldFlags="",
    )


def _draw_cell_border(canvas: Canvas, x: float, y: float, grid: _Grid) -> None:
    canvas.saveState()
    canvas.setStrokeColor(GRID_COLOR)
    canvas.setLineWidth(0.75)
    canvas.rect(x, y - grid.cell_h, grid.cell_w, grid.cell_h, stroke=1, fill=0)
    canvas.restoreState()


def _draw_footer(canvas: Canvas, page_w: float, page_no: int, total: int) -> None:
    canvas.setFont(FONT, 9)
    canvas.setFillColor(LABEL_COLOR)
    canvas.drawCentredString(page_w / 2, MARGIN / 2, f"Page {page_no} of {total}")
    canvas.setFillColor(black)


def _draw_cell(
    canvas: Canvas,
    problem: Problem,
    number: int,
    x: float,
    y: float,
    grid: _Grid,
    fs: float,
    m: _Metrics,
    layout: str,
    show_answer: bool,
) -> None:
    canvas.setLineWidth(max(0.75, fs / 18))
    if layout == "inline":
        _draw_inline(canvas, problem, number, x, y, grid, fs, m, show_answer)
        return

    label_fs = max(6.0, fs * 0.45)
    canvas.setFont(FONT, label_fs)
    canvas.setFillColor(LABEL_COLOR)
    canvas.drawString(x + 4, y - label_fs - 2, f"{number}.")
    canvas.setFillColor(black)
    canvas.setFont(FONT, fs)

    content_top = y - label_fs - 4
    if problem.op is Operation.DIV:
        _draw_long_division(canvas, problem, x, content_top, grid, fs, m, show_answer)
    else:
        _draw_stacked(canvas, problem, x, content_top, grid, fs, m, show_answer)


def _draw_inline(
    canvas: Canvas,
    p: Problem,
    number: int,
    x: float,
    top: float,
    grid: _Grid,
    fs: float,
    m: _Metrics,
    show_answer: bool,
) -> None:
    """``7.  12 + 7 = ____`` on one line, vertically centred in the cell.

    The number, question and blank each start in the same column on every row.
    """
    left = x + (grid.cell_w - (m.inline_label + m.inline_text + m.inline_blank) * fs) / 2
    baseline = top - grid.cell_h / 2 - 0.35 * fs  # 0.35em ~ half the digit height

    label_fs = fs * _INLINE_LABEL_SCALE
    canvas.setFont(FONT, label_fs)
    canvas.setFillColor(LABEL_COLOR)
    canvas.drawRightString(left + m.inline_label * fs - _INLINE_GAP * fs, baseline, f"{number}.")
    canvas.setFillColor(black)

    canvas.setFont(FONT, fs)
    left += m.inline_label * fs
    canvas.drawString(left, baseline, f"{p.question} =")
    blank_x = left + m.inline_text * fs
    if show_answer:
        canvas.drawString(blank_x, baseline, str(p.answer))
    else:
        canvas.line(blank_x, baseline - 2, blank_x + m.inline_blank * fs, baseline - 2)


def _draw_stacked(
    canvas: Canvas, p: Problem, x: float, top: float, grid: _Grid, fs: float, m: _Metrics, show_answer: bool
) -> None:
    """Column arithmetic::

          47
        + 85
        ----
         132
    """
    op_w = _w(f"{p.op.symbol} ", fs)
    block_w = op_w + m.stack * fs
    left = x + (grid.cell_w - block_w) / 2
    right = left + block_w

    y1 = top - fs
    y2 = y1 - _LINE * fs
    bar = y2 - 0.35 * fs
    canvas.drawRightString(right, y1, str(p.left))
    canvas.drawRightString(right, y2, str(p.right))
    canvas.drawString(left, y2, p.op.symbol)
    canvas.line(left - 0.1 * fs, bar, right + 0.1 * fs, bar)
    if show_answer:
        canvas.drawRightString(right, bar - _LINE * fs + 0.1 * fs, str(p.answer))


def _draw_long_division(
    canvas: Canvas, p: Problem, x: float, top: float, grid: _Grid, fs: float, m: _Metrics, show_answer: bool
) -> None:
    """Long-division bracket::

             7
           ----
        2 ) 14
    """
    block_w = _div_width(m.div_divisor, m.div_dividend) * fs
    left = x + (grid.cell_w - block_w) / 2
    bracket_x = left + (m.div_divisor + 0.25) * fs
    right = bracket_x + (0.25 + m.div_dividend + 0.3) * fs  # end of the bar
    dividend_right = right - 0.15 * fs

    quotient_y = top - fs
    bar = quotient_y - 0.4 * fs
    dividend_y = bar - 1.05 * fs

    canvas.drawRightString(bracket_x - 0.2 * fs, dividend_y, str(p.right))
    canvas.drawRightString(dividend_right, dividend_y, str(p.left))

    # ")"-shaped bracket from just below the dividend's baseline up to the bar.
    bottom = dividend_y - 0.25 * fs
    path = canvas.beginPath()
    path.moveTo(bracket_x, bottom)
    path.curveTo(bracket_x + 0.3 * fs, bottom + 0.3 * fs, bracket_x + 0.3 * fs, bar - 0.3 * fs, bracket_x, bar)
    path.lineTo(right, bar)
    canvas.drawPath(path, stroke=1, fill=0)

    if show_answer:
        canvas.drawRightString(dividend_right, quotient_y, str(p.answer))

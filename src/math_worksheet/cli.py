"""Command-line interface for generating math worksheets."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .formatters import FORMATS, render
from .generator import DEFAULT_COUNT, DEFAULT_MAX, DEFAULT_MIN, DEFAULT_TYPES, generate_worksheets
from .models import Operation, Problem

OUTPUT_FORMATS = (*FORMATS, "pdf")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="math-worksheet",
        description="Generate a set of random arithmetic problems with an answer key.",
        epilog=(
            "examples:\n"
            "  math-worksheet --max 10                      # addition (the default)\n"
            "  math-worksheet --subtraction --max 100 -n 20\n"
            "  math-worksheet --div --min 1 --max 12 --format json\n"
            "  math-worksheet --add --sub --min -10 --max 10 --allow-negatives -o sheet.pdf\n"
            "  math-worksheet --worksheets 7 --rows 10 --cols 10 -o week.pdf"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    types = parser.add_argument_group(
        "problem types",
        "Turn on each type to include; types not given are off.\n"
        "With none given, only addition is used. Several types are mixed at random.",
    )
    for op in Operation:
        types.add_argument(
            f"--{op.long_name}",
            f"--{op.value}",
            dest=op.long_name,
            action="store_true",
            help=f"include {op.long_name} problems",
        )
    parser.add_argument("--min", type=int, default=DEFAULT_MIN, help=f"smallest operand (default {DEFAULT_MIN})")
    parser.add_argument("--max", type=int, default=DEFAULT_MAX, help=f"largest operand (default {DEFAULT_MAX})")
    parser.add_argument(
        "-n", "--count", type=int, default=DEFAULT_COUNT, help=f"problems per worksheet (default {DEFAULT_COUNT})"
    )
    parser.add_argument(
        "--allow-negatives", action="store_true", help="allow negative operands and answers (default: off)"
    )
    parser.add_argument("--seed", type=int, help="random seed for a reproducible worksheet")
    parser.add_argument(
        "-f",
        "--format",
        choices=OUTPUT_FORMATS,
        help="output format (default text, or pdf when --output ends in .pdf)",
    )
    parser.add_argument("--no-answers", action="store_true", help="omit the answers")
    parser.add_argument("-o", "--output", type=Path, help="write to this file instead of stdout")

    pdf = parser.add_argument_group("PDF options")
    pdf.add_argument("--rows", type=_positive_int, default=5, help="grid rows per page (default 5)")
    pdf.add_argument("--cols", type=_positive_int, default=4, help="grid columns per page (default 4)")
    pdf.add_argument(
        "--layout",
        choices=("vertical", "inline"),
        default="vertical",
        help="vertical: stacked column / long-division form; inline: 7 + 5 = ___ (default vertical)",
    )
    pdf.add_argument("--page-size", choices=("letter", "a4"), default="letter", help="paper size (default letter)")
    pdf.add_argument("--title", default="Math Worksheet", help='page title (default "Math Worksheet")')
    pdf.add_argument("--no-grid", action="store_true", help="omit the lines separating problems")
    pdf.add_argument(
        "--worksheets",
        type=_positive_int,
        default=1,
        metavar="N",
        help="number of worksheets, each with its own problems and answer key, all in one PDF (default 1)",
    )
    return parser


def _positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {n}")
    return n


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.format is None:
        args.format = "pdf" if args.output and args.output.suffix.lower() == ".pdf" else "text"
    if args.format == "pdf" and not args.output:
        parser.error("PDF output requires --output FILE")
    if args.worksheets > 1 and args.format != "pdf":
        parser.error("--worksheets requires PDF output")

    types = {op.long_name: getattr(args, op.long_name) for op in Operation}
    if not any(types.values()):
        types = DEFAULT_TYPES
    try:
        worksheets = generate_worksheets(
            args.worksheets,
            types,
            count=args.count,
            min_value=args.min,
            max_value=args.max,
            allow_negatives=args.allow_negatives,
            seed=args.seed,
        )
    except ValueError as exc:
        parser.error(str(exc))

    if args.format == "pdf":
        return _write_pdf(parser, args, worksheets)

    (problems,) = worksheets
    output = render(problems, args.format, answers=not args.no_answers)
    if args.output:
        args.output.write_text(output)
        print(f"Wrote {len(problems)} problems to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output)
    return 0


def _write_pdf(parser: argparse.ArgumentParser, args: argparse.Namespace, worksheets: list[list[Problem]]) -> int:
    try:
        from .pdf import write_worksheets_pdf
    except ImportError:
        parser.error("PDF output requires ReportLab: pip install 'math-worksheet[pdf]'")

    try:
        pages = write_worksheets_pdf(
            worksheets,
            args.output,
            rows=args.rows,
            cols=args.cols,
            layout=args.layout,
            answers=not args.no_answers,
            page_size=args.page_size,
            title=args.title,
            grid_lines=not args.no_grid,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(_pdf_summary(worksheets, pages, args.output, answers=not args.no_answers), file=sys.stderr)
    return 0


def _pdf_summary(worksheets: list[list[Problem]], pages: int, output: Path, answers: bool) -> str:
    """Say what was written and, for a batch, which pages to print for students."""
    problems = sum(len(sheet) for sheet in worksheets)
    page_word = f"{pages} page{"s" if pages != 1 else ""}"
    if len(worksheets) == 1:
        return f"Wrote {problems} problems ({page_word}) to {output}"
    summary = f"Wrote {len(worksheets)} worksheets ({problems} problems, {page_word}) to {output}"
    if answers:
        sheet_pages = pages // 2
        summary += f": worksheets on pages 1-{sheet_pages}, answer keys on pages {sheet_pages + 1}-{pages}"
    return summary

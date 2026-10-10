"""Render a list of problems as text, JSON, or CSV."""

import csv
import io
import json
from collections.abc import Sequence

from .models import Problem

FORMATS = ("text", "json", "csv")


def render(problems: Sequence[Problem], fmt: str = "text", answers: bool = True) -> str:
    if fmt == "text":
        return to_text(problems, answers)
    if fmt == "json":
        return to_json(problems, answers)
    if fmt == "csv":
        return to_csv(problems, answers)
    raise ValueError(f"unknown format: {fmt!r} (choose from {', '.join(FORMATS)})")


def to_text(problems: Sequence[Problem], answers: bool = True) -> str:
    width = len(str(len(problems)))
    lines = ["Worksheet", "=========", ""]
    lines += [f"{i:>{width}}) {p.question} = ____" for i, p in enumerate(problems, start=1)]
    if answers:
        lines += ["", "Answer Key", "==========", ""]
        lines += [f"{i:>{width}}) {p.question} = {p.answer}" for i, p in enumerate(problems, start=1)]
    return "\n".join(lines) + "\n"


def to_json(problems: Sequence[Problem], answers: bool = True) -> str:
    data = {}
    for i, p in enumerate(problems, start=1):
        entry: dict[str, str | int] = {"question": p.question}
        if answers:
            entry["answer"] = p.answer
        data[str(i)] = entry
    return json.dumps(data, indent=2) + "\n"


def to_csv(problems: Sequence[Problem], answers: bool = True) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["number", "question", "answer"] if answers else ["number", "question"])
    for i, p in enumerate(problems, start=1):
        writer.writerow([i, p.question, p.answer] if answers else [i, p.question])
    return buf.getvalue()

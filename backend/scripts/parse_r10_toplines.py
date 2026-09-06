"""Parse the Afrobarometer Round 10 South Africa summary-of-results PDF into JSON.

R10 South Africa microdata (.sav) is not published yet; the summary of results is.
It reports every question as a percentage table with Urban / Rural / Men / Women /
Total columns, using the same variable codes as R9. That is enough to serve as the
ground truth for the R9 -> R10 backtest.

Usage:
    python backend/scripts/parse_r10_toplines.py [--pdf PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pypdf

_ROOT = Path(__file__).resolve().parents[1]
_PDF = _ROOT / "data" / "microdata" / "attitudes" / "afrobarometer_r10_sa_summary.pdf"
_OUT = _ROOT / "data" / "microdata" / "attitudes" / "afrobarometer_r10_sa_toplines.json"

# "Q4A." / "Q46I." / "Q37D1-SAF." / "Q80C_SAF." at the start of a line.
# The country-specific block uses hyphens and numeric suffixes; match both forms.
_QUESTION = re.compile(r"^(Q\d+[A-Z]*\d*(?:[-_]SAF)?)\.\s*(.*)$")
_HEADER = re.compile(r"^((?:Urban|Rural|Men|Women|Total)(?:\s+(?:Urban|Rural|Men|Women|Total))*)\s*$")
_CELL = re.compile(r"^(?:\d+,\d+|-)$")
_FOOTER = re.compile(r"^Copyright .*Afrobarometer \d{4}\s+\d+$")


def _clean(line: str) -> str:
    return line.replace("’", "'").replace("�", "'").strip()


def _num(tok: str) -> float | None:
    return None if tok == "-" else float(tok.replace(",", "."))


def _parse_table(tokens: list[str], ncols: int) -> dict[str, list[float | None]]:
    """Walk a flattened table body, emitting a row each time `ncols` cells close a label.

    Answer labels wrap across PDF lines and sometimes share a line with the
    previous row's numbers, so line-based parsing loses rows. Tokens do not.
    """
    rows: dict[str, list[float | None]] = {}
    label: list[str] = []
    run: list[str] = []
    for tok in tokens:
        if _CELL.match(tok):
            run.append(tok)
            if len(run) == ncols:
                name = " ".join(label).strip()
                if name:
                    rows[name] = [_num(t) for t in run]
                label, run = [], []
            continue
        # a non-cell token means the run was part of the label after all
        label.extend(run)
        run = []
        label.append(tok)
    return rows


def parse(pdf_path: Path) -> dict:
    reader = pypdf.PdfReader(str(pdf_path))
    lines: list[str] = []
    for page in reader.pages:
        for raw in (page.extract_text() or "").splitlines():
            line = _clean(raw)
            if line and not _FOOTER.match(line):
                lines.append(line)

    questions: dict[str, dict] = {}
    code: str | None = None
    text_parts: list[str] = []
    columns: list[str] = []
    body: list[str] = []

    def flush() -> None:
        if not code:
            return
        rows = _parse_table(body, len(columns)) if columns else {}
        if not rows:
            return
        i = columns.index("Total") if "Total" in columns else 0
        total = round(sum(v[i] or 0.0 for v in rows.values()), 1)
        questions[code] = {
            "text": " ".join(text_parts).strip(),
            "columns": list(columns),
            "rows": rows,
            "total_sum": total,
            # Multi-mention questions and stacked grids do not sum to 100. Flagged
            # rather than dropped, so item selection can steer clear of them.
            "suspect": not 97.0 <= total <= 103.0,
        }

    for line in lines:
        m = _QUESTION.match(line)
        if m:
            flush()
            code = m.group(1)
            text_parts = [m.group(2)] if m.group(2) else []
            columns, body = [], []
            continue
        if code is None:
            continue
        h = _HEADER.match(line)
        if h and not columns:
            columns = h.group(1).split()
            continue
        if columns:
            body.extend(line.split())
        else:
            text_parts.append(line)

    flush()
    return questions


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, default=_PDF)
    ap.add_argument("--out", type=Path, default=_OUT)
    args = ap.parse_args()

    questions = parse(args.pdf)
    payload = {
        "source": "Afrobarometer Round 10 South Africa summary of results (22 May 2026)",
        "fieldwork": "2025-06-28/2025-07-19",
        "sample_size": 1600,
        "margin_of_error_pp": 2.5,
        "note": "Percentages. Columns are demographic cuts as printed in the PDF.",
        "questions": questions,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    suspect = sorted(k for k, q in questions.items() if q["suspect"])
    print(f"{len(questions)} questions -> {args.out}")
    if suspect:
        print(f"{len(suspect)} flagged suspect (do not sum to 100): {', '.join(suspect)}")


if __name__ == "__main__":
    main()

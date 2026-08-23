"""Word-count the final report against the assignment's stated rules.

The brief excludes from the limits: the reference list, table and figure legends, and
chapter titles. It says nothing about excluding table *contents*, so this counts them —
the conservative reading. Code blocks and ASCII diagrams are excluded as figures.

Reported twice: a strict count (the number to check against the limits) and a raw count
(everything, as a naive word counter would report), so the margin between them is
visible rather than assumed.

Usage:  python scripts/word_count.py [path/to/FinalReport.md]
"""
from __future__ import annotations

import pathlib
import re
import sys

LIMITS = {
    "Chapter 1": 1000,
    "Chapter 2": 2500,
    "Chapter 3": 2000,
    "Chapter 4": 2500,
    "Chapter 5": 2500,
    "Chapter 6": 1000,
}
TOTAL_LIMIT = 10500

# A legend line: "*Table 2. …*" or "**Figure 4.** …"
_LEGEND = re.compile(r"^\s*\*{1,2}(Figure|Table)\s+\d+", re.IGNORECASE)


def count(text: str, strict: bool) -> int:
    """Words in `text`; `strict` applies the assignment's exclusions."""
    body = re.sub(r"```.*?```", "", text, flags=re.DOTALL)  # code blocks / diagrams
    if not strict:
        return len(body.split())
    lines = [ln for ln in body.splitlines() if not _LEGEND.match(ln)]
    lines = [ln for ln in lines if not ln.lstrip().startswith(("#", "|---", "| ---"))]
    return len(" ".join(lines).split())


def main(path: pathlib.Path) -> int:
    text = path.read_text(encoding="utf-8")
    # Drop everything from the reference list onward.
    marker = text.find("\n## References")
    body = text if marker == -1 else text[:marker]

    chapters = re.split(r"\n## ", body)[1:]
    rows, strict_total, raw_total = [], 0, 0
    for chapter in chapters:
        title = chapter.splitlines()[0]
        key = title.split(":")[0].strip()
        strict, raw = count(chapter, True), count(chapter, False)
        strict_total += strict
        raw_total += raw
        limit = LIMITS.get(key)
        status = "" if limit is None else ("OK" if strict <= limit else "OVER")
        rows.append((title, strict, raw, limit, status))

    width = max(len(r[0]) for r in rows) + 2
    print(f"{'Chapter':<{width}}{'strict':>8}{'raw':>8}{'limit':>8}  status")
    print("-" * (width + 34))
    for title, strict, raw, limit, status in rows:
        print(f"{title:<{width}}{strict:>8}{raw:>8}{str(limit or '-'):>8}  {status}")
    print("-" * (width + 34))
    over = strict_total > TOTAL_LIMIT
    print(
        f"{'TOTAL':<{width}}{strict_total:>8}{raw_total:>8}{TOTAL_LIMIT:>8}  "
        f"{'OVER' if over else 'OK'}"
    )
    print(f"\nmargin under the total limit: {TOTAL_LIMIT - strict_total} words")

    failures = [r for r in rows if r[4] == "OVER"]
    return 1 if failures or over else 0


if __name__ == "__main__":
    default = pathlib.Path(__file__).resolve().parents[2] / "FinalReport.md"
    sys.exit(main(pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else default))

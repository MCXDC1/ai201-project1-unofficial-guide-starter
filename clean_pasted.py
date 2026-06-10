"""Clean the manually-pasted source files (Reddit / RateMyProfessor / Quora).

Pasting from a live page drags in UI chrome: Reddit vote bars, usernames,
"2y ago", "Reply/Award/Share", embedded ads; RateMyProfessor's "QUALITY",
"would take again", "level of difficulty" labels. This script strips that and
rewrites each file as clean, blank-line-separated blocks (one comment / review
per block) so chunk_documents.py turns each into one chunk.

Routing is by filename: "reddit" -> Reddit cleaner, "ratemyprofessor" -> RMP
cleaner. Other files (Quora, USNews) only get whitespace/entity normalization
via chunk_documents.clean_text and are left as-is structurally.

Usage:
    python clean_pasted.py            # dry run: print cleaned output, write nothing
    python clean_pasted.py --write    # overwrite the files in place
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from chunk_documents import clean_text

# Reddit action-bar / chrome lines (exact, case-insensitive).
_REDDIT_CRUFT = {
    "upvote", "downvote", "reply", "award", "share", "go to comments",
    "op", "promoted", "learn more", "collapse video player", "show more",
}
# A line ends a comment (flush the current block) ...
_REDDIT_FLUSH = {"share", "go to comments"}
_TIME_AGO = re.compile(r"^\d+\s*[ymdwh]\s+ago$", re.IGNORECASE)
_VOTE_COUNT = re.compile(r"^\d+$")
_TIMESTAMP = re.compile(r"^\d+:\d+")


def _reddit_is_username(lines: list[str], i: int) -> bool:
    """A username line is one followed (past blanks/"OP") by the bullet '•'."""
    j = i + 1
    while j < len(lines) and (not lines[j].strip() or lines[j].strip().lower() == "op"):
        j += 1
    return j < len(lines) and lines[j].strip() == "•"


def clean_reddit(raw: str) -> str:
    """Strip Reddit UI chrome; return comments as blank-line-separated blocks."""
    lines = raw.split("\n")
    blocks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            blocks.append("\n".join(current).strip())
            current.clear()

    for i, line in enumerate(lines):
        s = line.strip()
        low = s.lower()

        if not s:
            continue
        # A new username marks the start of the next comment.
        if low.startswith("u/") or s.endswith(" avatar") or _reddit_is_username(lines, i):
            flush()
            continue
        if low in _REDDIT_CRUFT:
            if low in _REDDIT_FLUSH:
                flush()
            continue
        if s == "•" or _TIME_AGO.match(s) or _VOTE_COUNT.match(s) or _TIMESTAMP.match(s):
            continue
        # Embedded promoted-ad lines.
        if ("membership rewards" in low or "americanexpress" in low
                or "clickable image" in low):
            continue
        current.append(s)

    flush()
    # Drop any empties and de-noise each block's whitespace.
    return "\n\n".join(clean_text(b) for b in blocks if b.strip())


def clean_ratemyprofessor(raw: str) -> str:
    """Reformat RMP records into one readable line per professor."""
    # Each professor record begins at a "QUALITY" marker.
    records = re.split(r"(?im)^\s*quality\s*$", raw)
    out: list[str] = []

    for rec in records:
        toks = [t.strip() for t in rec.split("\n") if t.strip()]
        if not toks:
            continue

        # Locate fields by their labels so missing/extra blanks don't shift us.
        ratings = next((t for t in toks if re.search(r"\d+\s*ratings", t, re.I)), None)
        pct = next((t for t in toks if re.search(r"\d+%", t)), None)
        try:
            wta_idx = next(i for i, t in enumerate(toks)
                           if t.lower() == "would take again")
        except StopIteration:
            wta_idx = None

        score = toks[0] if re.match(r"^\d+(\.\d+)?$", toks[0]) else None
        # Name = the first token after the "N ratings" line that isn't a label.
        labels = {"engineering", "university of connecticut",
                  "would take again", "level of difficulty"}
        name = None
        if ratings in toks:
            for t in toks[toks.index(ratings) + 1:]:
                tl = t.lower()
                if tl in labels or "%" in t or re.match(r"^\d+(\.\d+)?$", t):
                    continue
                name = t
                break
        difficulty = (toks[wta_idx + 1] if wta_idx is not None
                      and wta_idx + 1 < len(toks) else None)

        if not name:
            continue
        parts = [f"{name} — Engineering, University of Connecticut."]
        if score:
            n = re.search(r"(\d+)", ratings).group(1) if ratings else "?"
            parts.append(f"Quality {score}/5 from {n} ratings.")
        if pct:
            parts.append(f"{re.search(r'\d+%', pct).group(0)} would take again.")
        if difficulty and re.match(r"^\d+(\.\d+)?$", difficulty):
            parts.append(f"Difficulty {difficulty}/5.")
        out.append(" ".join(parts))

    return "\n\n".join(out)


def clean_file(path: Path) -> str:
    name = path.name.lower()
    raw = path.read_text(encoding="utf-8", errors="replace")
    if "reddit" in name:
        return clean_reddit(raw)
    if "ratemyprofessor" in name:
        return clean_ratemyprofessor(raw)
    # Quora / USNews / anything else: just normalize.
    return clean_text(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("documents"))
    parser.add_argument("--write", action="store_true",
                        help="Overwrite files in place (default: dry-run print).")
    args = parser.parse_args(argv)

    targets = sorted(
        p for p in args.input_dir.glob("*")
        if p.suffix.lower() == ".txt"
        and any(k in p.name.lower() for k in ("reddit", "ratemyprofessor", "quora", "usnews"))
    )
    if not targets:
        print("No pasted source files found to clean.", file=sys.stderr)
        return 1

    for path in targets:
        cleaned = clean_file(path)
        blocks = [b for b in cleaned.split("\n\n") if b.strip()]
        print(f"\n{'='*70}\n{path.name}  ->  {len(blocks)} block(s), "
              f"{len(cleaned)} chars\n{'='*70}")
        print(cleaned)
        if args.write:
            path.write_text(cleaned + "\n", encoding="utf-8")

    print(f"\n{'WROTE' if args.write else 'DRY RUN (no files changed)'}: "
          f"{len(targets)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

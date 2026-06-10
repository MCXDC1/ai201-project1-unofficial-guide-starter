"""Load documents, clean them, and split them into chunks.

This is Milestone 3 of "The Unofficial Guide": ingestion + chunking.

The chunking strategy follows planning.md:
  - Review-style sources (Reddit / Quora / RateMyProfessor) are stored as JSON
    lists, where each comment / review becomes ONE chunk. These are short and
    self-contained, so no overlap is needed.
  - Prose sources (USNews, UCONN articles, catalog pages) are saved as .txt /
    .md / .html and split with a sliding character window that uses overlap so
    context isn't lost across chunk boundaries.

Usage:
    python chunk_documents.py                          # use defaults
    python chunk_documents.py --chunk-size 800 --overlap 150
    python chunk_documents.py --input-dir documents --output chunks.json

Output is a JSON file: a list of chunk records, each with the source file,
a chunk index, the cleaned text, and basic metadata. This feeds the embedding
step (Milestone 4).
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path

# Defaults for prose chunking (characters). Reviews/comments ignore these and
# become one chunk each. 800/150 fits medium-length article paragraphs while
# keeping enough overlap that a sentence split across a boundary still appears
# whole in at least one chunk.
DEFAULT_CHUNK_SIZE = 800
DEFAULT_OVERLAP = 150
DEFAULT_MIN_CHARS = 50  # drop trailing scraps shorter than this

PROSE_EXTENSIONS = {".txt", ".md", ".html", ".htm"}
REVIEW_EXTENSIONS = {".json", ".jsonl"}

# Tags whose contents are never readable body text. Only non-void tags belong
# here: void elements like <meta>/<link> have no end tag, so tracking skip
# depth on them would never unwind and would swallow the whole document.
_SKIP_TAGS = {"script", "style", "head", "noscript", "template", "svg"}


class _HTMLTextExtractor(HTMLParser):
    """Pull readable text out of HTML using only the standard library.

    Block-level tags become newlines so paragraphs stay separated; the
    contents of script/style/etc. are dropped.
    """

    _BLOCK_TAGS = {
        "p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
        "section", "article", "header", "footer", "blockquote", "ul", "ol",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def extract_main_content(raw: str) -> str:
    """Narrow raw HTML down to the primary content region before stripping.

    Site headers, nav bars, footers, and cookie modals live *outside* the
    page's <article>/<main> element. Returning just that region removes the
    bulk of the per-page boilerplate before we ever convert to text. Falls
    back to <body>, then the whole document, if no such region is found.
    """
    for tag in ("article", "main"):
        start = re.search(rf"<{tag}\b[^>]*>", raw, re.IGNORECASE)
        if not start:
            continue
        end = raw.lower().rfind(f"</{tag}>")
        if end > start.end():
            return raw[start.end():end]
    body = re.search(r"<body\b[^>]*>", raw, re.IGNORECASE)
    if body:
        end = raw.lower().rfind("</body>")
        if end > body.end():
            return raw[body.end():end]
    return raw


def strip_html(raw: str, main_only: bool = True) -> str:
    """Return readable text from an HTML string.

    With main_only=True (the default) the document is first narrowed to its
    <article>/<main> region so site chrome is dropped before text extraction.
    """
    if main_only:
        raw = extract_main_content(raw)
    parser = _HTMLTextExtractor()
    parser.feed(raw)
    parser.close()
    return parser.get_text()


# Lines that are pure site chrome (nav, footer, cookie/print controls). Matched
# case-insensitively against a whole stripped line, so substantive sentences are
# never affected. Extend this as you spot new boilerplate.
_BOILERPLATE_LINES = {
    "skip to content", "skip to navigation", "skip to main content",
    "skip to uconn search", "toggle menu", "back to top", "close this window",
    "menu", "search", "home", "archives", "contact us", "contact",
    "quick links", "find us on social media", "a to z index", "az index",
    "a-z index", "catalog home", "search catalog", "submit search",
    "search university of connecticut", "university of connecticut",
    "accessibility", "webmaster login", "disclaimers, privacy & copyright",
    "print options", "send page to printer", "print this page.",
    "download page (pdf)",
    "the pdf will include all information unique to this page.",
    "uconn", "today", "news", "series", "alumni", "athletics",
    "opt out", "what are cookies?", "authentication cookies",
    "analytics cookies", "uconn cookie information",
    # UConn Today category breadcrumbs that sit inside the <article> element.
    "school and college news", "arts & culture", "community impact",
    "entrepreneurship", "health & well-being", "research & discovery",
    "uconn health", "university life", "uconn voices", "university news",
}

# A whole injected cookie-policy block (identical on every UConn page). We drop
# everything from its heading down to the line that ends the block.
_COOKIE_START = re.compile(r"^\s*uconn cookie information\s*$", re.IGNORECASE)
_COOKIE_END = re.compile(
    r"certain features may not work as expected", re.IGNORECASE
)


def _drop_cookie_block(text: str) -> str:
    """Remove the multi-line UConn cookie-policy block if present."""
    lines = text.split("\n")
    out, skipping = [], False
    for line in lines:
        if not skipping and _COOKIE_START.match(line):
            skipping = True
            continue
        if skipping:
            if _COOKIE_END.search(line):
                skipping = False
            continue
        out.append(line)
    return "\n".join(out)


def clean_text(text: str) -> str:
    """Normalize whitespace, decode HTML entities, and strip boilerplate.

    Collapses runs of spaces/tabs, trims each line, squeezes blank-line runs,
    unescapes leftover HTML entities (&amp;, &nbsp;, ...), removes the injected
    cookie-policy block, and drops pure nav/footer chrome lines so only
    substantive content remains.
    """
    # Decode HTML entities (&amp; -> &, &nbsp; -> space, &#39; -> ', ...).
    text = html.unescape(text)
    # Normalize line endings and non-breaking spaces.
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    # Drop the cookie-policy block before line-level filtering.
    text = _drop_cookie_block(text)
    # Collapse horizontal whitespace, trim, and drop boilerplate chrome lines.
    cleaned_lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line.lower() in _BOILERPLATE_LINES:
            continue
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)
    # Squeeze 3+ newlines down to a paragraph break.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_with_overlap(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Sliding-window split on character count, snapping to word boundaries.

    Each window is `chunk_size` chars and advances by `chunk_size - overlap`.
    The cut point is nudged back to the nearest whitespace so words are never
    sliced in half.
    """
    if chunk_size <= overlap:
        raise ValueError(
            f"chunk_size ({chunk_size}) must be greater than overlap ({overlap})"
        )

    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []

    step = chunk_size - overlap
    chunks: list[str] = []
    start = 0
    n = len(text)

    while start < n:
        end = min(start + chunk_size, n)
        # Snap `end` back to a whitespace boundary unless we're at the very end.
        if end < n:
            boundary = text.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        # Advance by step, also snapping the next start to a word boundary.
        next_start = start + step
        if next_start < n and not text[next_start].isspace():
            boundary = text.find(" ", next_start)
            if 0 < boundary < end:
                next_start = boundary
        start = max(next_start, start + 1)

    return chunks


def _extract_review_text(item) -> str:
    """Pull the text out of one JSON review/comment record.

    Accepts a plain string, or a dict with a common text-bearing field.
    """
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("text", "body", "content", "comment", "review", "selftext"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value
        # Fall back to concatenating any string values.
        strings = [v for v in item.values() if isinstance(v, str) and v.strip()]
        return "\n".join(strings)
    return str(item)


@dataclass
class Chunk:
    id: str
    source: str
    chunk_index: int
    text: str
    n_chars: int
    strategy: str  # "review" (one-per-item) or "overlap" (sliding window)


def chunk_file(path: Path, chunk_size: int, overlap: int, min_chars: int) -> list[Chunk]:
    """Load, clean, and chunk a single document."""
    suffix = path.suffix.lower()
    chunks: list[Chunk] = []

    # Pasted reviews/comments: a "<name>.reviews.txt" file where each comment is
    # separated by a blank line. Each block -> one chunk ("one chunk per
    # comment" without hand-formatting JSON).
    if path.name.lower().endswith(".reviews.txt"):
        raw = clean_text(path.read_text(encoding="utf-8", errors="replace"))
        blocks = [b.strip() for b in re.split(r"\n\s*\n", raw)]
        idx = 0
        for block in blocks:
            if not block:
                continue
            chunks.append(Chunk(
                id=f"{path.stem}::{idx}",
                source=path.name,
                chunk_index=idx,
                text=block,
                n_chars=len(block),
                strategy="review",
            ))
            idx += 1
        return chunks

    if suffix in REVIEW_EXTENSIONS:
        # One chunk per comment / review.
        raw = path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".jsonl":
            items = [json.loads(line) for line in raw.splitlines() if line.strip()]
        else:
            data = json.loads(raw)
            items = data if isinstance(data, list) else [data]

        idx = 0
        for item in items:
            text = clean_text(_extract_review_text(item))
            # Keep every non-empty review/comment, even one-liners — a short
            # review is still a complete, meaningful unit. min_chars only
            # prunes trailing prose scraps below.
            if not text:
                continue
            chunks.append(Chunk(
                id=f"{path.stem}::{idx}",
                source=path.name,
                chunk_index=idx,
                text=text,
                n_chars=len(text),
                strategy="review",
            ))
            idx += 1
        return chunks

    # Prose: clean (strip HTML if needed) then sliding-window split.
    raw = path.read_text(encoding="utf-8", errors="replace")
    if suffix in {".html", ".htm"}:
        raw = strip_html(raw)
    text = clean_text(raw)

    pieces = _split_with_overlap(text, chunk_size, overlap)
    for idx, piece in enumerate(pieces):
        if len(piece) < min_chars and len(pieces) > 1:
            continue
        chunks.append(Chunk(
            id=f"{path.stem}::{idx}",
            source=path.name,
            chunk_index=idx,
            text=piece,
            n_chars=len(piece),
            strategy="overlap",
        ))
    return chunks


def load_and_chunk(
    input_dir: Path,
    chunk_size: int,
    overlap: int,
    min_chars: int,
) -> list[Chunk]:
    """Walk the input directory and chunk every supported document."""
    supported = PROSE_EXTENSIONS | REVIEW_EXTENSIONS
    files = sorted(
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in supported
    )

    if not files:
        print(
            f"No documents found in '{input_dir}/'.\n"
            f"  Supported types: {', '.join(sorted(supported))}\n"
            f"  Add your collected sources there, then re-run.",
            file=sys.stderr,
        )
        return []

    all_chunks: list[Chunk] = []
    for path in files:
        try:
            file_chunks = chunk_file(path, chunk_size, overlap, min_chars)
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"  ! Skipping {path.name}: {exc}", file=sys.stderr)
            continue
        all_chunks.extend(file_chunks)
        print(f"  {path.name}: {len(file_chunks)} chunk(s)")

    return all_chunks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load documents, clean them, and split into chunks.",
    )
    parser.add_argument(
        "--input-dir", type=Path, default=Path("documents"),
        help="Directory of source documents (default: documents).",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("chunks.json"),
        help="Where to write the chunk JSON (default: chunks.json).",
    )
    parser.add_argument(
        "--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
        help=f"Prose chunk size in characters (default: {DEFAULT_CHUNK_SIZE}).",
    )
    parser.add_argument(
        "--overlap", type=int, default=DEFAULT_OVERLAP,
        help=f"Prose overlap in characters (default: {DEFAULT_OVERLAP}).",
    )
    parser.add_argument(
        "--min-chars", type=int, default=DEFAULT_MIN_CHARS,
        help=f"Drop chunks shorter than this (default: {DEFAULT_MIN_CHARS}).",
    )
    args = parser.parse_args(argv)

    if not args.input_dir.is_dir():
        print(f"Input directory '{args.input_dir}' does not exist.", file=sys.stderr)
        return 1

    if args.chunk_size <= args.overlap:
        print(
            f"--chunk-size ({args.chunk_size}) must be greater than "
            f"--overlap ({args.overlap}).",
            file=sys.stderr,
        )
        return 1

    print(
        f"Chunking documents in '{args.input_dir}/' "
        f"(chunk_size={args.chunk_size}, overlap={args.overlap}):"
    )
    chunks = load_and_chunk(
        args.input_dir, args.chunk_size, args.overlap, args.min_chars
    )

    if not chunks:
        return 1

    args.output.write_text(
        json.dumps([asdict(c) for c in chunks], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    review_count = sum(1 for c in chunks if c.strategy == "review")
    prose_count = len(chunks) - review_count
    sources = len({c.source for c in chunks})
    print(
        f"\nWrote {len(chunks)} chunk(s) from {sources} source(s) to "
        f"'{args.output}'.\n"
        f"  {review_count} review/comment chunk(s), {prose_count} prose chunk(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

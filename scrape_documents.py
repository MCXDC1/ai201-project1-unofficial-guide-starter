
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

from chunk_documents import clean_text, strip_html

# A realistic browser UA. Many sites 403 the default urllib agent.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Sources that need a logged-in / JS-rendered browser; plain GET won't work.
_MANUAL_TYPES = {"quora", "rmp"}


def fetch(url: str, timeout: int = 30) -> bytes:
    """GET a URL with browser-like headers, following redirects."""
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _extract_reddit_comments(node, out: list[str]) -> None:
    """Walk a Reddit listing's comment tree, collecting comment bodies."""
    if isinstance(node, dict):
        data = node.get("data", {})
        body = data.get("body")
        if isinstance(body, str) and body.strip() not in ("", "[deleted]", "[removed]"):
            out.append(body.strip())
        # Recurse into replies and listing children.
        replies = data.get("replies")
        if isinstance(replies, dict):
            _extract_reddit_comments(replies, out)
        children = data.get("children")
        if isinstance(children, list):
            for child in children:
                _extract_reddit_comments(child, out)
    elif isinstance(node, list):
        for item in node:
            _extract_reddit_comments(item, out)


def scrape_reddit(url: str) -> list[str]:
    """Fetch a Reddit thread's post + comments as a list of text items."""
    json_url = url.rstrip("/") + ".json?limit=500"
    listings = json.loads(fetch(json_url).decode("utf-8", errors="replace"))

    items: list[str] = []
    # listings[0] = the post, listings[1] = the comment tree.
    if isinstance(listings, list) and listings:
        post = listings[0]["data"]["children"][0]["data"]
        title = post.get("title", "").strip()
        selftext = post.get("selftext", "").strip()
        header = "\n".join(p for p in (title, selftext) if p)
        if header:
            items.append(header)
        if len(listings) > 1:
            _extract_reddit_comments(listings[1], items)
    return items


def scrape_article(url: str) -> str:
    """Fetch an HTML page and return cleaned, readable text."""
    raw = fetch(url).decode("utf-8", errors="replace")
    return clean_text(strip_html(raw))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch sources.json URLs and save raw text into documents/.",
    )
    parser.add_argument("--sources", type=Path, default=Path("sources.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("documents"))
    args = parser.parse_args(argv)

    if not args.sources.is_file():
        print(f"Sources file '{args.sources}' not found.", file=sys.stderr)
        return 1

    sources = json.loads(args.sources.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)

    saved, skipped, failed = [], [], []

    for src in sources:
        sid, name, stype, url = src["id"], src["name"], src["type"], src["url"]
        stem = f"{sid}_{name}"

        if stype in _MANUAL_TYPES:
            skipped.append((stem, stype, url))
            print(f"  - {stem}: needs manual save ({stype}, JS/bot-protected)")
            continue

        try:
            if stype == "reddit":
                comments = scrape_reddit(url)
                if not comments:
                    raise ValueError("no comments returned")
                out = args.output_dir / f"{stem}.json"
                out.write_text(
                    json.dumps(comments, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                print(f"  ok {stem}.json ({len(comments)} comments)")
            else:  # article
                text = scrape_article(url)
                if len(text) < 100:
                    raise ValueError(f"only {len(text)} chars returned")
                out = args.output_dir / f"{stem}.txt"
                out.write_text(text, encoding="utf-8")
                print(f"  ok {stem}.txt ({len(text)} chars)")
            saved.append(stem)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            failed.append((stem, url, str(exc)))
            print(f"  ! {stem}: FAILED ({exc})", file=sys.stderr)

    print(f"\nSaved {len(saved)} file(s) to '{args.output_dir}/'.")

    if skipped or failed:
        print("\nMANUAL STEP NEEDED for these sources:")
        for stem, stype, url in skipped:
            print(f"  - {stem} ({stype}): {url}")
        for stem, url, _ in failed:
            print(f"  - {stem} (fetch failed): {url}")
        print(
            "\n  How to save manually (fast):\n"
            "    1. Open the URL in your browser.\n"
            "    2. Select the relevant text (reviews/comments/article body).\n"
            "    3. Paste into a file in documents/:\n"
            "         - articles  -> documents/<id>_<name>.txt\n"
            "         - reviews    -> documents/<id>_<name>.json  as a list:\n"
            '             ["first review text", "second review text", ...]\n'
            "       (.json files get one-chunk-per-review automatically.)"
        )

    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())

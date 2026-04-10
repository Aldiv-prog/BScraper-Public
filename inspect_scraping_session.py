"""Inspect scraping_session.json and summarize content_type behavior.

Usage:
    python inspect_scraping_session.py [--session-file output/scraping_session.json]

This helper is meant for debugging the content_type classifier. It prints:
- Overall content_type counts
- A simple "confusion-matrix" style table of content_type vs content length bucket
- Example post IDs per bucket so you can manually spot misclassifications

It does not re-fetch HTML; it only uses the saved ScrapingSession JSON.
"""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from textwrap import shorten

from scraper.models import ScrapingSession


def load_session(path: Path) -> ScrapingSession:
    session = ScrapingSession.load_from_file(str(path))
    if not session:
        raise SystemExit(f"No scraping session found at {path}")
    return session


def bucket_length(n: int) -> str:
    """Bucket content length into coarse ranges for inspection."""
    if n < 40:
        return "<40"
    if n < 80:
        return "40-79"
    if n < 160:
        return "80-159"
    return "160+"


def summarize_session(session: ScrapingSession) -> None:
    posts = session.posts_scraped or []
    if not posts:
        print("Session has no posts_scraped entries.")
        return

    # Overall content_type counts
    type_counts = Counter(p.get("content_type", "unknown") for p in posts)
    total = len(posts)

    print(f"Scraping session for blog '{session.blog_name}' (user '{session.username}')")
    print(f"Total posts in session: {total}\n")

    print("Content type counts:")
    for ctype, count in sorted(type_counts.items(), key=lambda kv: kv[0]):
        pct = 100.0 * count / total if total else 0.0
        print(f"  {ctype:15s}: {count:4d} ({pct:5.1f}%)")
    print()

    # Confusion-matrix style: content_type vs content length bucket
    matrix = defaultdict(lambda: Counter())
    examples = defaultdict(lambda: defaultdict(list))  # [ctype][bucket] -> [post_id]

    for p in posts:
        ctype = p.get("content_type", "unknown")
        content = p.get("content", "") or ""
        length = len(content.strip())
        bucket = bucket_length(length)
        matrix[ctype][bucket] += 1
        if len(examples[ctype][bucket]) < 5:
            examples[ctype][bucket].append((p.get("post_id", "?"), content))

    buckets = ["<40", "40-79", "80-159", "160+"]

    print("Content type vs content length (characters):")
    header = "".ljust(15) + " " + " ".join(f"{b:>8s}" for b in buckets)
    print(header)
    print("-" * len(header))
    for ctype in sorted(matrix.keys()):
        row_counts = [matrix[ctype].get(b, 0) for b in buckets]
        row = f"{ctype:15s} " + " ".join(f"{c:8d}" for c in row_counts)
        print(row)
    print()

    # Show a few concrete examples per (type, bucket)
    print("Example posts by content type and length bucket (post_id: first 80 chars of content):")
    for ctype in sorted(matrix.keys()):
        print(f"\n[{ctype}]")
        for bucket in buckets:
            ex_list = examples[ctype][bucket]
            if not ex_list:
                continue
            print(f"  Length {bucket}:")
            for post_id, content in ex_list:
                preview = shorten(content.replace("\n", " "), width=80, placeholder="...")
                print(f"    - {post_id}: {preview}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect scraping_session.json content_type behavior")
    parser.add_argument(
        "--session-file",
        type=Path,
        default=Path("output/scraping_session.json"),
        help="Path to scraping_session JSON file (default: output/scraping_session.json)",
    )
    args = parser.parse_args()

    session = load_session(args.session_file)
    summarize_session(session)


if __name__ == "__main__":  # pragma: no cover
    main()

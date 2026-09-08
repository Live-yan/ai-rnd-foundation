#!/usr/bin/env python3
"""Validate that Vite's built HTML uses the FastAPI root-path-aware public base."""
from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        wanted = {"script": "src", "link": "href", "img": "src"}.get(tag)
        if not wanted:
            return
        for key, value in attrs:
            if key == wanted and value:
                self.refs.append(value)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: verify_frontend_dist.py DIST_DIR PUBLIC_BASE", file=sys.stderr)
        return 2

    dist = Path(sys.argv[1]).resolve()
    public_base = sys.argv[2]
    if not public_base.startswith("/") or not public_base.endswith("/"):
        print(f"PUBLIC_BASE must start and end with '/': {public_base!r}", file=sys.stderr)
        return 2

    index = dist / "index.html"
    if not index.is_file():
        print(f"missing built index: {index}", file=sys.stderr)
        return 1

    parser = AssetParser()
    parser.feed(index.read_text(encoding="utf-8"))

    errors: list[str] = []
    local_refs: list[str] = []
    for ref in parser.refs:
        parsed = urlsplit(ref)
        if parsed.scheme or parsed.netloc or ref.startswith(("data:", "blob:")):
            continue
        path = parsed.path
        if not path.startswith("/"):
            errors.append(f"non-absolute built asset URL: {ref}")
            continue
        local_refs.append(path)
        if not path.startswith(public_base):
            errors.append(f"asset escapes public base {public_base}: {ref}")
            continue
        relative = path[len(public_base):]
        if relative and not (dist / relative).is_file():
            errors.append(f"referenced asset is missing from dist: {ref} -> {dist / relative}")

    if not any(ref.endswith(".js") or ".js?" in ref for ref in parser.refs):
        errors.append("index.html does not reference a built JavaScript entry")

    if errors:
        print("frontend public-path validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"frontend public-path OK: {len(local_refs)} local assets under {public_base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

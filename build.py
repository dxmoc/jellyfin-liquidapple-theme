#!/usr/bin/env python3
"""Concatenate src/*.css into dist/, readable and minified.

Standard library only. Run from anywhere:

    python build.py

Source files are concatenated in filename order, so the numeric prefixes are
the cascade order — 99-fallbacks.css must stay last.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
DIST = ROOT / "dist"
NAME = "liquidapple"
REPO = "https://github.com/dxmoc/jellyfin-liquidapple-theme"

# Whitespace may be collapsed away entirely next to these.
TIGHT = set("{};,")


def read_version() -> str:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        sys.exit(f"VERSION must be MAJOR.MINOR.PATCH, got {version!r}")
    return version


def tokenize(css: str) -> list[tuple[str, str]]:
    """Split into ('text' | 'string' | 'comment', chunk) so the minifier never
    touches the inside of a quoted value or a url()."""
    tokens: list[tuple[str, str]] = []
    i, n, start = 0, len(css), 0

    def flush(end: int) -> None:
        if end > start:
            tokens.append(("text", css[start:end]))

    while i < n:
        ch = css[i]
        if ch == "/" and css.startswith("/*", i):
            end = css.find("*/", i + 2)
            end = n if end == -1 else end + 2
            flush(i)
            tokens.append(("comment", css[i:end]))
            i = start = end
        elif ch in "\"'":
            end = i + 1
            while end < n:
                if css[end] == "\\":
                    end += 2
                    continue
                if css[end] == ch:
                    end += 1
                    break
                end += 1
            flush(i)
            tokens.append(("string", css[i:end]))
            i = start = end
        else:
            i += 1
    flush(n)
    return tokens


# `.foo :hover` (descendant of a hovered element) means something different from
# `.foo:hover`, and collapsing the space after a colon would silently turn one
# into the other. The source does not use that form; this guard makes sure a
# future edit fails the build instead of shipping a broken selector.
DESCENDANT_PSEUDO = re.compile(r"[\w)\]] +:[a-zA-Z-]")


def minify(css: str) -> str:
    """Deliberately conservative: comments, whitespace and trailing semicolons
    only. Nothing that requires understanding the grammar, so nothing that can
    silently corrupt a selector."""
    # Merge adjacent text so whitespace that met across a dropped comment gets
    # collapsed too, and keep strings intact so their contents are never touched.
    merged: list[tuple[str, str]] = []
    for kind, chunk in tokenize(css):
        if kind == "comment" and not chunk.startswith("/*!"):
            kind, chunk = "text", " "
        if kind == "text" and merged and merged[-1][0] == "text":
            merged[-1] = ("text", merged[-1][1] + chunk)
        else:
            merged.append((kind, chunk))

    out: list[str] = []
    for kind, chunk in merged:
        if kind != "text":
            out.append(chunk)
            continue
        if DESCENDANT_PSEUDO.search(chunk):
            hit = DESCENDANT_PSEUDO.search(chunk)
            sys.exit(
                "refusing to minify a descendant-pseudo selector: "
                f"...{chunk[max(0, hit.start() - 40):hit.end() + 10].strip()}..."
            )
        chunk = re.sub(r"\s+", " ", chunk)
        chunk = re.sub(r" ?([{};,]) ?", r"\1", chunk)
        chunk = chunk.replace(": ", ":").replace(";}", "}")
        out.append(chunk)

    return "".join(out).replace(";}", "}").strip()


def main() -> int:
    version = read_version()
    sources = sorted(SRC.glob("*.css"))
    if not sources:
        sys.exit(f"no source files in {SRC}")

    # ASCII only: this banner survives minification, and a client that guesses
    # the wrong charset would render mojibake in the one line everybody reads.
    banner = (
        f"/*! LiquidApple v{version} - Apple Liquid Glass for Jellyfin\n"
        f" * {REPO}\n"
        " * MIT licensed. Built by build.py - edit src/, not dist/.\n"
        " */\n"
    )

    parts = [banner]
    for path in sources:
        parts.append(f"\n/* ==== {path.name} ==== */\n")
        parts.append(path.read_text(encoding="utf-8").rstrip() + "\n")

    readable = "".join(parts).replace("__VERSION__", version)

    DIST.mkdir(exist_ok=True)
    full = DIST / f"{NAME}.css"
    small = DIST / f"{NAME}.min.css"
    full.write_text(readable, encoding="utf-8", newline="\n")
    small.write_text(minify(readable) + "\n", encoding="utf-8", newline="\n")

    for path in (full, small):
        size = path.stat().st_size
        print(f"{path.relative_to(ROOT).as_posix():<28} {size / 1024:6.1f} KB")
    print(f"\nv{version} from {len(sources)} source files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

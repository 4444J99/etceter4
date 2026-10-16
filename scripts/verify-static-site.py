#!/usr/bin/env python3
"""Check the historical site's local file references and first-party JS syntax."""

from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import posixpath
import subprocess
import sys
from urllib.parse import unquote, urlsplit


ENTRYPOINTS = ("index.html", "analog.html", "OGOD.html", "loophole.html", "sitemap.html")
JAVASCRIPT = (
    "js/analytics.js",
    "js/diary.js",
    "js/images.js",
    "js/legacy.js",
    "js/loophole.js",
    "js/main.js",
    "js/ogod.js",
    "js/page.js",
    "js/pageData.js",
    "js/sketch.js",
)


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = set()
        self.references = []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        for name, value in attrs:
            if name in {"src", "data-src", "poster"} or (
                name == "href" and tag in {"a", "link"}
            ):
                self.references.append((self.getpos()[0], value))


def local_reference(page, value):
    # Empty attributes and fragment-only links identify no separate local file.
    if not value:
        return None
    url = urlsplit(value)
    if url.scheme or url.netloc or not url.path:
        return None
    path = unquote(url.path)
    if "\\" in path or "\0" in path:
        raise ValueError(f"Unsupported local path: {value!r}")
    relative = posixpath.normpath(
        path.lstrip("/") if path.startswith("/") else posixpath.join(posixpath.dirname(page), path)
    )
    if relative == ".." or relative.startswith("../"):
        raise ValueError(f"Local reference escapes the site: {value!r}")
    return relative


def require_file(root, relative):
    current = root
    for part in PurePosixPath(relative).parts:
        if not current.is_dir() or part not in {p.name for p in current.iterdir()}:
            raise ValueError(f"Missing file or wrong filename case: {relative}")
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Local reference traverses a symlink: {relative}")
    if not current.is_file() or current.stat().st_size == 0:
        raise ValueError(f"Expected a nonempty regular file: {relative}")
    return current


def verify(root):
    resources = set()
    for page in ENTRYPOINTS:
        source = require_file(root, page)
        parser = References()
        parser.feed(source.read_text(encoding="utf-8"))
        parser.close()
        if not {"html", "head", "title", "body"}.issubset(parser.tags):
            raise ValueError(f"Missing document structure: {page}")
        for line, value in parser.references:
            try:
                relative = local_reference(page, value)
                if relative is not None:
                    require_file(root, relative)
                    resources.add(relative)
            except ValueError as error:
                raise ValueError(f"{page}:{line}: {error}") from error

    for relative in JAVASCRIPT:
        source = require_file(root, relative)
        result = subprocess.run(
            ["node", "--check", str(source)], capture_output=True, text=True, check=False
        )
        if result.returncode:
            raise ValueError(f"JavaScript syntax check failed: {relative}\n{result.stderr}")
    return len(resources)


if __name__ == "__main__":
    try:
        count = verify(Path(__file__).resolve().parents[1])
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Static source verification failed: {error}", file=sys.stderr)
        sys.exit(1)
    print(
        f"Verified {len(ENTRYPOINTS)} HTML entrypoints, {count} local file references, "
        f"and syntax of {len(JAVASCRIPT)} first-party JavaScript files."
    )

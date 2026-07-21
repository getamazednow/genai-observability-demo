#!/usr/bin/env python3
"""
check-links.py — fail the build if any internal link in the published site
points at a file that isn't there.

Scans every .html and .css file under the given root, extracts href/src/url()
targets, and resolves each one against the built tree. External (http/https),
mailto:, tel:, data: and pure-fragment (#...) links are reported but not
verified.

Usage:  python3 scripts/check-links.py _site
Exit:   0 = all internal links resolve, 1 = at least one is broken.
"""

import os
import re
import sys
from urllib.parse import unquote, urlparse

ATTR_RE = re.compile(r'(?:href|src)\s*=\s*["\']([^"\']+)["\']', re.I)
CSS_URL_RE = re.compile(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)', re.I)
EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "tel:", "data:", "//")


def collect_files(root):
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if name.lower().endswith((".html", ".css")):
                yield os.path.join(dirpath, name)


def targets(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        text = handle.read()
    found = set(ATTR_RE.findall(text))
    found |= set(CSS_URL_RE.findall(text))
    return found


def resolve(root, source, target):
    """Return the on-disk path a link should resolve to, or None if external."""
    if target.startswith(EXTERNAL_SCHEMES) or target.startswith("#"):
        return None

    parsed = urlparse(target)
    if parsed.scheme:
        return None

    path = unquote(parsed.path)
    if not path:
        return None

    if path.startswith("/"):
        candidate = os.path.join(root, path.lstrip("/"))
    else:
        candidate = os.path.join(os.path.dirname(source), path)

    return os.path.normpath(candidate)


def exists(candidate):
    if os.path.isfile(candidate):
        return True
    # Directory links (e.g. "demo/") are served by their index.html
    if os.path.isdir(candidate):
        return os.path.isfile(os.path.join(candidate, "index.html"))
    return False


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "_site")
    if not os.path.isdir(root):
        print(f"ERROR: {root} is not a directory. Run scripts/build-site.sh first.")
        return 1

    broken, internal, external = [], 0, 0

    for source in sorted(collect_files(root)):
        for target in sorted(targets(source)):
            candidate = resolve(root, source, target)
            if candidate is None:
                external += 1
                continue
            internal += 1
            if not exists(candidate):
                broken.append((os.path.relpath(source, root), target))

    print(f"Checked {internal} internal links ({external} external/anchor skipped).")

    if broken:
        print(f"\n{len(broken)} BROKEN LINK(S):")
        for source, target in broken:
            print(f"  {source} -> {target}")
        return 1

    print("All internal links resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

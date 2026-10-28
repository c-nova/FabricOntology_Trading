#!/usr/bin/env python3
"""Swap the demo environment's Fabric identifiers for placeholders, and back.

The repository is public, so workspace, capacity, item, job, SQL endpoint, Data Agent conversation
identifiers and the what-if app's host name are stored as placeholders such as
__WORKSPACE_ID__. The real values live in config/environment_ids.local.json
(git-ignored; format: config/environment_ids.example.json).

    python3 scripts/environment_ids.py redact    real value -> placeholder (before committing)
    python3 scripts/environment_ids.py restore   placeholder -> real value (before using Fabric)
    python3 scripts/environment_ids.py check     exit 1 if an environment-like identifier is left

Replacement also reaches inside base64 payloads (Fabric item definitions) and
.pptx XML parts. `check` needs no mapping: it flags any random (version 4) GUID,
SQL endpoint host or Fabric Apps host that is not a placeholder or on the allow-list below.
"""
import argparse
import base64
import binascii
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / "config/environment_ids.local.json"

# Saved Microsoft Learn page with sample payloads, and Office Open XML constants.
ALLOW_FILES = {"reports/ontology_api_reference.txt"}
ALLOW_GUIDS = {
    "c183d7f6-b498-43b3-948b-1728b52aa6e4", "bb962c8b-b14f-4d97-af65-f5344cb8ac3e",
    "5c22544a-7ee6-4342-b048-85bdc9fd1c3a", "e76ce94a-603c-4142-b9eb-6d1370010a27",
    "d31a062a-798a-4329-abdd-bba856620510",
    "4053a155-34a9-4b74-9bc2-e162f1b27fc7",  # sample dataset ID in the Rayfin scaffold README (whatif-app/README.md)
}
# Documentation of the placeholders themselves; `restore` must not rewrite them.
KEEP_PLACEHOLDERS = {"README.md", "AGENTS.md", "scripts/environment_ids.py", "config/environment_ids.example.json"}
SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".zip")
SQL_HOST_SUFFIX = ".datawarehouse.fabric.microsoft.com"
CAPACITY_HOST_SUFFIX = ".pbidedicated.windows.net"
APP_HOST_SUFFIX = ".webapp.fabricapps.net"

V4_GUID = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-"
                     r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}(?![0-9A-Fa-f])")
B64_RUN = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")
B64_FULL = re.compile(r"[A-Za-z0-9+/\s]{40,}={0,2}\s*")
MAX_DEPTH = 3


def load_mapping():
    if not LOCAL.exists():
        sys.exit(f"{LOCAL.relative_to(ROOT)} not found (see config/environment_ids.example.json)")
    mapping = json.loads(LOCAL.read_text(encoding="utf-8"))
    for placeholder, real in mapping.items():
        if not re.fullmatch(r"__[A-Za-z0-9_]+__", placeholder) or not isinstance(real, str) or not real.strip():
            sys.exit(f"invalid entry in {LOCAL.name}: {placeholder}")
    if len(set(mapping.values())) != len(mapping):
        sys.exit(f"duplicate values in {LOCAL.name}")
    return mapping


def decode_b64_text(candidate):
    """Return the UTF-8 text a base64 string encodes, or None if it is not base64 text."""
    if not B64_FULL.fullmatch(candidate):
        return None
    try:
        raw = base64.b64decode(re.sub(r"\s", "", candidate), validate=True)
        text = raw.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if not text or sum(ch.isprintable() or ch in "\r\n\t" for ch in text) / len(text) < 0.97:
        return None
    return text


def make_replacer(table):
    """table: {old: new}. Returns text -> text, applied also inside base64 runs."""
    pattern = re.compile("|".join(re.escape(old) for old in sorted(table, key=len, reverse=True)))

    def replace(text, depth=0):
        if any(old in text for old in table):
            text = pattern.sub(lambda m: table[m.group(0)], text)
        if depth < MAX_DEPTH:
            def run(m):
                decoded = decode_b64_text(m.group(0))
                if decoded is None:
                    return m.group(0)
                new = replace(decoded, depth + 1)
                return m.group(0) if new == decoded else base64.b64encode(new.encode("utf-8")).decode("ascii")
            text = B64_RUN.sub(run, text)
        return text
    return replace


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        skipped = {".git", "__pycache__", "qa"}
        return [p for p in ROOT.rglob("*") if p.is_file() and not skipped & set(p.relative_to(ROOT).parts)]
    return [ROOT / name for name in out.decode("utf-8").split("\0") if name]


def rel(path):
    return path.relative_to(ROOT).as_posix() if ROOT in path.parents else str(path)


def targets(paths, skip=()):
    files = [Path(p).resolve() for p in paths] if paths else tracked_files()
    return [p for p in files if p.is_file() and p != LOCAL and not p.name.endswith(SKIP_SUFFIXES)
            and rel(p) not in skip]


def rewrite_file(path, replace):
    """Rewrite one file in place; bytes are preserved apart from the replaced identifiers."""
    data = path.read_bytes()
    if path.suffix == ".pptx":
        source = zipfile.ZipFile(io.BytesIO(data))
        buffer, changed = io.BytesIO(), False
        with zipfile.ZipFile(buffer, "w") as target:
            for info in source.infolist():
                content = source.read(info.filename)
                if info.filename.endswith((".xml", ".rels")):
                    text = content.decode("utf-8")
                    new = replace(text)
                    if new != text:
                        content, changed = new.encode("utf-8"), True
                clone = zipfile.ZipInfo(info.filename, info.date_time)
                clone.compress_type, clone.external_attr, clone.create_system = (
                    info.compress_type, info.external_attr, info.create_system)
                target.writestr(clone, content)
        if changed:
            path.write_bytes(buffer.getvalue())
        return changed
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    new = replace(text)
    if new == text:
        return False
    path.write_bytes(new.encode("utf-8"))
    return True


def json_strings(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from json_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from json_strings(value)
    elif isinstance(node, str):
        yield node


def views(text, depth=0):
    """The text itself, JSON string values (unescaped) and everything base64-encoded inside."""
    yield text
    if depth >= MAX_DEPTH:
        return
    node = None
    if text.lstrip()[:1] in ("{", "["):
        try:
            node = json.loads(text)
        except ValueError:
            pass
    if node is None:
        candidates = (m.group(0) for m in B64_RUN.finditer(text))
    else:
        candidates = (s for s in json_strings(node) if len(s) >= 40)
    for candidate in candidates:
        if node is not None:
            yield candidate
        decoded = decode_b64_text(candidate)
        if decoded is not None:
            yield from views(decoded, depth + 1)
        elif node is not None:
            for run in B64_RUN.finditer(candidate):
                decoded = decode_b64_text(run.group(0))
                if decoded is not None:
                    yield from views(decoded, depth + 1)


def file_views(path):
    data = path.read_bytes()
    if path.suffix == ".pptx":
        archive = zipfile.ZipFile(io.BytesIO(data))
        for info in archive.infolist():
            if info.filename.endswith((".xml", ".rels")):
                xml = archive.read(info.filename).decode("utf-8")
                yield from views(xml)
                yield re.sub(r"<[^>]+>", "", xml)  # identifiers split over text runs
        return
    try:
        yield from views(data.decode("utf-8"))
    except UnicodeDecodeError:
        return


def host_labels(text, suffix):
    start = text.find(suffix)
    while start != -1:
        begin = start
        while begin > 0 and start - begin < 120 and (text[begin - 1].isalnum() or text[begin - 1] in "-_"):
            begin -= 1
        yield text[begin:start]
        start = text.find(suffix, start + len(suffix))


def check(paths):
    real_values = list(load_mapping().values()) if LOCAL.exists() else []
    problems = []
    for path in targets(paths):
        name = rel(path)
        found = set()
        for text in file_views(path):
            if name not in ALLOW_FILES:
                found.update(f"GUID {m.group(0)[:8]}…" for m in V4_GUID.finditer(text)
                             if m.group(0).lower() not in ALLOW_GUIDS)
                found.update(f"SQL host {label[:8]}…" for label in host_labels(text, SQL_HOST_SUFFIX)
                             if label and not re.fullmatch(r"__[A-Za-z0-9_]+__", label))
                found.update(f"capacity host {label[:8]}…" for label in host_labels(text, CAPACITY_HOST_SUFFIX)
                             if re.fullmatch(r"[0-9A-Fa-f]{32}", label))
                found.update(f"app host {label[:8]}…" for label in host_labels(text, APP_HOST_SUFFIX)
                             if label and not re.fullmatch(r"__[A-Za-z0-9_]+__", label))
            found.update(f"mapped value {real[:8]}…" for real in real_values if real in text)
        problems.extend(f"{name}: {item}" for item in sorted(found))
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("redact", "restore", "check"))
    parser.add_argument("paths", nargs="*", help="files to process (default: all tracked files)")
    args = parser.parse_args()

    if args.command == "check":
        problems = check(args.paths)
        print("\n".join(problems) if problems else "ok: no environment identifiers found")
        return 1 if problems else 0

    mapping = load_mapping()
    table = {real: placeholder for placeholder, real in mapping.items()}
    if args.command == "restore":
        table = {placeholder: real for real, placeholder in table.items()}
    replace = make_replacer(table)
    skip = KEEP_PLACEHOLDERS if args.command == "restore" else ()
    changed = [p for p in targets(args.paths, skip) if rewrite_file(p, replace)]
    for path in changed:
        print(f"{args.command}: {rel(path)}")
    print(f"{len(changed)} file(s) changed")
    if args.command == "redact":
        problems = check(args.paths)
        if problems:
            print("left over after redaction:\n" + "\n".join(problems))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

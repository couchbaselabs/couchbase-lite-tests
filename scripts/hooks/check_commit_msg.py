#!/usr/bin/env python3
"""Conventional Commits validator with interactive correction.

Wired in as the ``commit-msg`` hook (see ``.pre-commit-config.yaml``).

- If the first line already follows ``<type>[scope][!]: <description>`` it passes
  untouched.
- Otherwise, when a controlling terminal is available, it prompts for the type,
  optional scope, and breaking-change flag, rewrites the message, and lets the
  commit proceed.
- With no terminal (CI, GUI/IDE commit dialogs) it prints guidance and fails,
  exactly like a plain non-interactive check.

Standard library only, so it runs under any Python 3.10+ on PATH.
"""

from __future__ import annotations

import io
import os
import re
import sys
import tempfile

# (type, help text) — order drives the interactive menu numbering.
TYPES: list[tuple[str, str]] = [
    ("feat", "A new feature"),
    ("fix", "A bug fix"),
    ("docs", "Documentation only changes"),
    ("style", "Formatting / whitespace — no code behavior change"),
    ("refactor", "Code change that neither fixes a bug nor adds a feature"),
    ("perf", "Performance improvement"),
    ("test", "Add or fix tests"),
    ("build", "Build system or dependencies"),
    ("ci", "CI configuration"),
    ("chore", "Maintenance / tooling"),
    ("revert", "Revert a previous commit"),
]

_TYPE_NAMES = "|".join(name for name, _ in TYPES)
PATTERN = re.compile(rf"^({_TYPE_NAMES})(\([a-zA-Z0-9_./-]+\))?(!)?: .+")
SKIP_PATTERN = re.compile(r"^(Merge |Revert |fixup!|squash!)")
SCOPE_PATTERN = re.compile(r"^[a-zA-Z0-9_./-]+$")
# Leading "<word>(scope)?!?:" prefix we strip so a re-typed message isn't doubled.
BOGUS_PREFIX = re.compile(r"^[A-Za-z]+(\([^)]*\))?!?:\s*")


def guidance(message: str) -> None:
    """Print the non-interactive failure message (CI / no TTY)."""
    types = " ".join(name for name, _ in TYPES)
    lines = [
        "ERROR: Commit message does not follow Conventional Commits format.",
        "",
        "  Expected: <type>[optional scope]: <description>",
        "",
        f"  Types: {types}",
        "",
        "  Examples:",
        "    feat: add login page",
        "    fix(auth): resolve token expiry issue",
        "    docs: update README",
        "    feat!: breaking change to API",
        "",
        f"  Your message: {message}",
    ]
    print("\n".join(lines), file=sys.stderr)


def open_tty() -> tuple[io.TextIOBase, io.TextIOBase] | None:
    """Return ``(reader, writer)`` bound to the controlling terminal, or None.

    git and pre-commit pipe stdin, so ``input()`` would hit EOF; talking to the
    terminal device directly reaches the user even when stdin is redirected.
    """
    # Separate read/write handles: a TTY is not seekable, so a single "r+"
    # buffered stream raises UnsupportedOperation on open.
    read_dev, write_dev = (
        ("CONIN$", "CONOUT$") if os.name == "nt" else ("/dev/tty", "/dev/tty")
    )
    try:
        reader = open(read_dev, encoding="utf-8")
        writer = open(write_dev, "w", encoding="utf-8")
    except OSError:
        return None
    return reader, writer


def _ask(reader: io.TextIOBase, writer: io.TextIOBase, prompt: str) -> str | None:
    """Write a prompt to the terminal and read one line; None on EOF."""
    writer.write(prompt)
    writer.flush()
    line = reader.readline()
    if line == "":  # Ctrl-D / closed terminal
        return None
    return line.strip()


def correct(message: str, reader: io.TextIOBase, writer: io.TextIOBase) -> str | None:
    """Interactively build a valid first line; None if the user aborts."""
    writer.write("\nCommit message is not in Conventional Commits format:\n")
    writer.write(f"    {message}\n\n")
    writer.write("Pick a type:\n")
    for i, (name, desc) in enumerate(TYPES, start=1):
        writer.write(f"  {i:2d}) {name:<9} {desc}\n")
    writer.write("   q) abort commit\n\n")
    writer.flush()

    chosen = ""
    while not chosen:
        answer = _ask(reader, writer, f"Type number [1-{len(TYPES)}/q]: ")
        if answer is None or answer.lower() == "q":
            writer.write("Aborted.\n")
            writer.flush()
            return None
        if not answer.isdigit():
            writer.write("  Please enter a number from the list.\n")
            writer.flush()
            continue
        idx = int(answer)
        if 1 <= idx <= len(TYPES):
            chosen = TYPES[idx - 1][0]
        else:
            writer.write("  Out of range.\n")
            writer.flush()

    scope = ""
    while True:
        answer = _ask(reader, writer, "Optional scope (Enter to skip): ")
        scope = answer or ""
        if scope == "" or SCOPE_PATTERN.match(scope):
            break
        writer.write("  Scope may only contain letters, digits, and _ . / -\n")
        writer.flush()

    answer = _ask(reader, writer, "Breaking change? [y/N]: ")
    bang = "!" if (answer or "").lower() in {"y", "yes"} else ""

    description = BOGUS_PREFIX.sub("", message).strip()
    while not description:
        answer = _ask(reader, writer, "Description: ")
        if answer is None:
            writer.write("\nAborted.\n")
            writer.flush()
            return None
        description = answer

    scope_part = f"({scope})" if scope else ""
    return f"{chosen}{scope_part}{bang}: {description}"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: check_commit_msg.py <commit-msg-file>", file=sys.stderr)
        return 2

    path = args[0]
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    first = lines[0] if lines else ""

    if SKIP_PATTERN.match(first) or PATTERN.match(first):
        return 0

    tty = open_tty()
    if tty is None:
        guidance(first)
        return 1

    reader, writer = tty
    try:
        new_first = correct(first, reader, writer)
        if new_first is None:
            return 1
        if not PATTERN.match(new_first):
            writer.write("\n  Could not build a valid message from that input.\n")
            writer.flush()
            guidance(first)
            return 1

        body = lines[1:]
        fd, tmp = tempfile.mkstemp()
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(new_first + "\n")
            if body:
                out.write("\n".join(body) + "\n")
        os.replace(tmp, path)

        writer.write(f"\nRewrote commit message to:\n    {new_first}\n\n")
        writer.flush()
        return 0
    finally:
        reader.close()
        if writer is not reader:
            writer.close()


if __name__ == "__main__":
    raise SystemExit(main())

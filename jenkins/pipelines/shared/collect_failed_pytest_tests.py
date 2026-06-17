#!/usr/bin/env python3
"""Collect pytest node ids for failed tests from junit XML and/or console log."""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

FAILED_SUMMARY_RE = re.compile(r"^FAILED\s+(\S+::\S+::\S+)\s+-")
FAILED_PROGRESS_RE = re.compile(r"^(\S+::\S+::\S+)\s+FAILED\s")


def _nodeid_from_junit_case(case: ET.Element) -> str | None:
    classname = case.get("classname") or ""
    name = case.get("name") or ""
    if not classname or not name:
        return None

    parts = classname.split(".")
    module_file: str | None = None
    class_name: str | None = None
    for index, part in enumerate(parts):
        if not part.startswith("test_"):
            continue
        module_file = f"{part}.py"
        remaining = parts[index + 1 :]
        if remaining:
            class_name = remaining[-1]
        break

    if module_file is None:
        return None
    if class_name:
        return f"{module_file}::{class_name}::{name}"
    return f"{module_file}::{name}"


def from_junit(path: Path) -> list[str]:
    if not path.is_file():
        return []

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return []

    failed: list[str] = []
    for case in root.iter("testcase"):
        if case.find("failure") is None and case.find("error") is None:
            continue
        nodeid = _nodeid_from_junit_case(case)
        if nodeid:
            failed.append(nodeid)
    return failed


def from_log(path: Path) -> list[str]:
    if not path.is_file():
        return []

    failed: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        for pattern in (FAILED_SUMMARY_RE, FAILED_PROGRESS_RE):
            match = pattern.match(line.strip())
            if match:
                nodeid = match.group(1)
                if nodeid not in seen:
                    seen.add(nodeid)
                    failed.append(nodeid)
                break
    return failed


def from_lastfailed(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, dict):
        return []
    return [key for key in data if isinstance(key, str)]


def collect(
    *, junit: Path | None, log: Path | None, lastfailed: Path | None = None
) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for source in (
        from_junit(junit) if junit else [],
        from_log(log) if log else [],
        from_lastfailed(lastfailed) if lastfailed else [],
    ):
        for nodeid in source:
            if nodeid not in seen:
                seen.add(nodeid)
                ordered.append(nodeid)
    return ordered


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print pytest node ids for failed tests (one per line)."
    )
    parser.add_argument("--junit", type=Path, help="Path to junit XML output")
    parser.add_argument("--log", type=Path, help="Path to pytest console log")
    parser.add_argument(
        "--lastfailed",
        type=Path,
        help="Path to pytest .pytest_cache/v/cache/lastfailed",
    )
    args = parser.parse_args()

    nodeids = collect(junit=args.junit, log=args.log, lastfailed=args.lastfailed)
    for nodeid in nodeids:
        print(nodeid)


if __name__ == "__main__":
    main()

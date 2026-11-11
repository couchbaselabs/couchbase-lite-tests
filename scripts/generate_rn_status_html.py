#!/usr/bin/env python3
"""Generate single-platform React Native dev_e2e catalog HTML from JUnit output."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV_E2E = REPO_ROOT / "tests" / "dev_e2e"
RN_PKG = REPO_ROOT / "servers" / "reactnative" / "package.json"

sys.path.insert(0, str(REPO_ROOT / "tests"))
from dev_e2e.generate_reactnative_test_catalog_html import (
    DEFAULT_JUNIT_IOS,
    build_single_platform_html,
    collect_rn_tests,
    count_outcomes,
    parse_junit,
)


def read_cbl_version() -> str:
    if not RN_PKG.exists():
        return "1.1.1"
    data = json.loads(RN_PKG.read_text(encoding="utf-8"))
    dep = data.get("dependencies", {}).get("cbl-reactnative", "")
    match = re.search(r"@couchbase/couchbase-lite-react-native@([^\"']+)", dep)
    return match.group(1) if match else "1.1.1"


def main() -> int:
    default_downloads = Path.home() / "Downloads" / "dev-e2e-test-catalog.html"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, default=DEFAULT_JUNIT_IOS)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEV_E2E / "dev-e2e-test-catalog.html",
    )
    parser.add_argument(
        "--output-downloads",
        type=Path,
        default=default_downloads,
        help="Also write catalog to ~/Downloads/dev-e2e-test-catalog.html",
    )
    parser.add_argument("--config", type=Path, default=DEV_E2E / "config.json")
    parser.add_argument("--cbl-version", default=None)
    parser.add_argument(
        "--platform-tag",
        default="reactnative_ios",
        help="Label in JUnit summary line (reactnative_ios | reactnative_android)",
    )
    args = parser.parse_args()

    cbl_version = args.cbl_version or read_cbl_version()
    platform = parse_junit(args.junit)
    by_file = collect_rn_tests(args.config)
    passed, skipped, failed = count_outcomes(by_file, platform)
    run_summary = (
        f"JUnit: {passed} passed · {skipped} skipped · "
        f"platform {args.platform_tag}" + (f" · {failed} failed" if failed else "")
    )

    html_out = build_single_platform_html(
        by_file,
        platform,
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        cbl_version=cbl_version,
        config_label=str(args.config),
        run_summary=run_summary,
    )
    args.output.write_text(html_out, encoding="utf-8")
    print(f"Wrote {args.output}")
    if args.output_downloads:
        args.output_downloads.parent.mkdir(parents=True, exist_ok=True)
        args.output_downloads.write_text(html_out, encoding="utf-8")
        print(f"Wrote {args.output_downloads}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

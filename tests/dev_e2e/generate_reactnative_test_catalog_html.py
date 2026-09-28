"""Generate dev_e2e HTML test catalog for React Native runs (grouped like JS catalog)."""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_E2E = REPO_ROOT / "tests" / "dev_e2e"
DEFAULT_JUNIT_ANDROID = DEV_E2E / "junit_android.xml"
DEFAULT_JUNIT_IOS = DEV_E2E / "junit_ios.xml"
DEFAULT_OUT = DEV_E2E / "dev-e2e-test-catalog.html"
DEFAULT_OUT_ROOT = REPO_ROOT / "dev-e2e-test-catalog.html"
DEFAULT_RESULTS = DEV_E2E / "dev-e2e-test-results-rn.json"

CATALOG_TAIL_ORDER = (
    "test_encrypted_properties.py",
    "test_replication_upgrade.py",
    "test_replication_xdcr.py",
    "test_multipeer.py",
    "test_custom_conflict.py",
)
CATALOG_TAIL_COLLAPSED = frozenset(CATALOG_TAIL_ORDER)

RN_PYTEST_IGNORE = ("test_multipeer.py",)
RN_PYTEST_K = "not listener and not multipeer and not custom_conflict"

FILE_NOTES: dict[str, str] = {
    "test_encrypted_properties.py": (
        "Field encryption (`EncryptedValue`) is not implemented on the React Native test server; "
        "test skips unless platform is C."
    ),
    "test_replication_upgrade.py": (
        "SGW 4.x upgrade interop requires native CBL ≥ 4.0 and the v4.0 `upgrade` dataset; "
        "React Native 1.2.x skips with `CBL 1.0.0 not >= 4.0.0` until version reporting is aligned."
    ),
    "test_replication_xdcr.py": (
        "XDCR requires two Couchbase clusters, two Sync Gateways, and a load balancer; "
        "local RN docker uses a single cluster."
    ),
    "test_multipeer.py": (
        "Peer-to-peer replication is not in the RN dev_e2e selection (`--ignore=test_multipeer.py`)."
    ),
    "test_custom_conflict.py": (
        "Custom JS conflict resolvers are excluded from the RN filter (`not custom_conflict`)."
    ),
}

TestResult = dict[str, str]


def parse_junit(path: Path) -> dict[str, dict[str, TestResult]]:
    if not path.exists():
        return {}
    root = ET.parse(path).getroot()
    by_file: dict[str, dict[str, TestResult]] = defaultdict(dict)
    for case in root.iter("testcase"):
        class_name = case.get("classname", "")
        name = case.get("name", "")
        file_name = "unknown.py"
        for part in class_name.split("."):
            if part.startswith("test_"):
                file_name = f"{part}.py"
                break

        outcome = "PASSED"
        reason = ""
        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")
        if failure is not None:
            outcome = "FAILED"
            reason = (failure.get("message") or failure.text or "").strip()
        elif error is not None:
            outcome = "ERROR"
            reason = (error.get("message") or error.text or "").strip()
        elif skipped is not None:
            outcome = "SKIPPED"
            reason = (skipped.get("message") or skipped.text or "").strip()
            reason = re.sub(r"^/[^:]+:\d+:\s*", "", reason)

        by_file[file_name][name] = {"outcome": outcome, "reason": reason}
    return dict(by_file)


def collect_rn_tests(config: Path) -> dict[str, list[str]]:
    cmd = [
        "uv",
        "run",
        "pytest",
        ".",
        "--collect-only",
        "-q",
        f"--config={config}",
        f"--ignore={RN_PYTEST_IGNORE[0]}",
        "-k",
        RN_PYTEST_K,
    ]
    proc = subprocess.run(cmd, cwd=DEV_E2E, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        raise SystemExit(proc.returncode)

    by_file: dict[str, list[str]] = defaultdict(list)
    for line in proc.stdout.splitlines():
        line = line.strip()
        if "::" not in line or line.startswith("="):
            continue
        file_path, rest = line.split("::", 1)
        file_name = Path(file_path).name
        short_name = rest.split("::")[-1]
        by_file[file_name].append(short_name)
    return dict(sorted(by_file.items()))


def badge(outcome: str | None) -> str:
    if outcome is None:
        return '<span class="badge badge-pending">Not run</span>'
    mapping = {
        "PASSED": ("badge-pass", "Passed"),
        "FAILED": ("badge-fail", "Failed"),
        "SKIPPED": ("badge-skip", "Skipped"),
        "ERROR": ("badge-fail", "Error"),
    }
    css, label = mapping.get(outcome, ("badge-pending", outcome or "Not run"))
    return f'<span class="badge {css}">{label}</span>'


def applicable_badge(outcome: str | None, file_name: str) -> str:
    if file_name in {"test_multipeer.py", "test_custom_conflict.py"}:
        return '<span class="badge badge-app-no">No</span><span class="scope-tag">RN filter</span>'
    if outcome == "SKIPPED" and file_name in CATALOG_TAIL_COLLAPSED:
        return '<span class="badge badge-app-partial">Partial</span><span class="scope-tag">RN</span>'
    if outcome in ("PASSED", "SKIPPED", "FAILED", "ERROR"):
        return '<span class="badge badge-app-yes">Yes</span>'
    return '<span class="badge badge-app-partial">Partial</span>'


def reason_cell(*results: TestResult | None) -> str:
    for result in results:
        if result and result.get("reason"):
            text = html.escape(result["reason"])
            return f'<td class="reason"><div class="reason-line">{text}</div></td>'
    return '<td class="reason"><span class="reason-empty">—</span></td>'


def count_outcomes(
    by_file: dict[str, list[str]],
    results: dict[str, dict[str, TestResult]],
) -> tuple[int, int, int]:
    passed = skipped = failed = 0
    for file_name, tests in by_file.items():
        for test_name in tests:
            outcome = results.get(file_name, {}).get(test_name, {}).get("outcome")
            if outcome == "PASSED":
                passed += 1
            elif outcome == "SKIPPED":
                skipped += 1
            elif outcome in ("FAILED", "ERROR"):
                failed += 1
    return passed, skipped, failed


def file_sort_key(name: str) -> tuple[int, int, str]:
    if name in CATALOG_TAIL_ORDER:
        return (1, CATALOG_TAIL_ORDER.index(name), name)
    return (0, 0, name)


def build_html(
    by_file: dict[str, list[str]],
    android: dict[str, dict[str, TestResult]],
    ios: dict[str, dict[str, TestResult]],
    *,
    generated: str,
    cbl_version: str,
    config_label: str,
    run_summary: str,
) -> str:
    ordered_files = sorted(by_file.keys(), key=file_sort_key)
    total_tests = sum(len(tests) for tests in by_file.values())
    android_passed, _android_skipped, android_failed = count_outcomes(by_file, android)
    ios_passed, ios_skipped, ios_failed = count_outcomes(by_file, ios)

    toc_lines: list[str] = []
    sections: list[str] = []
    for file_name in ordered_files:
        tests = by_file[file_name]
        collapsed = file_name in CATALOG_TAIL_COLLAPSED
        tag = ' <span class="tag tag-na tag-inline">N/A</span>' if collapsed else ""
        toc_class = ' class="toc-tail"' if collapsed else ""
        toc_lines.append(
            f'        <li{toc_class}><a href="#{html.escape(file_name)}">'
            f"{html.escape(file_name)}</a>{tag} ({len(tests)})</li>"
        )

        rows: list[str] = []
        for test_name in tests:
            android_result = android.get(file_name, {}).get(test_name)
            ios_result = ios.get(file_name, {}).get(test_name)
            android_outcome = android_result.get("outcome") if android_result else None
            ios_outcome = ios_result.get("outcome") if ios_result else None
            applicable_outcome = (
                ios_outcome if ios_outcome is not None else android_outcome
            )
            rows.append(
                f"""        <tr>
          <td class="test-name">{html.escape(test_name)}</td>
          <td class="status">{badge(android_outcome)}</td>
          <td class="status">{badge(ios_outcome)}</td>
          <td class="applicable">{applicable_badge(applicable_outcome, file_name)}</td>
          {reason_cell(ios_result, android_result)}
        </tr>"""
            )

        note = FILE_NOTES.get(file_name, "")
        note_html = f'<p class="file-note">{html.escape(note)}</p>' if note else ""
        section_class = (
            "file-section file-section-collapsed" if collapsed else "file-section"
        )
        inner = f"""
  <h2>{html.escape(file_name)}</h2>
  <p class="file-meta">{len(tests)} tests</p>
  {note_html}
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Test</th>
          <th class="col-sg">Android</th>
          <th class="col-ios">iOS</th>
          <th class="col-app">Applicable</th>
          <th>Reason</th>
        </tr>
      </thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table>
  </div>"""

        if collapsed:
            sections.append(
                f"""<section class="{section_class}" id="{html.escape(file_name)}">
  <details class="file-details">
    <summary class="file-summary">
      <span class="file-summary-title">{html.escape(file_name)}<span class="tag tag-na">Tail</span></span>
      <span class="file-meta">{len(tests)} tests</span>
    </summary>
    <div class="file-details-body">
{inner}
    </div>
  </details>
</section>"""
            )
        else:
            sections.append(
                f"""<section class="{section_class}" id="{html.escape(file_name)}">
{inner}
</section>"""
            )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>dev_e2e Test Catalog · React Native</title>
  <style>
    :root {{
      --bg: #0b0f14;
      --surface: #151b24;
      --surface2: #1a2332;
      --border: #2d3a4d;
      --text: #e8edf4;
      --muted: #8fa3bc;
      --sg: #4da3ff;
      --es: #a78bfa;
      --app: #2dd4bf;
      --pending: #64748b;
      --pass: #34d399;
      --fail: #f87171;
      --skip: #fbbf24;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 1.5rem;
      line-height: 1.5;
    }}
    .wrap {{ max-width: 1200px; margin: 0 auto; }}
    header {{
      border-bottom: 1px solid var(--border);
      padding-bottom: 1.25rem;
      margin-bottom: 1.5rem;
    }}
    h1 {{ font-size: 1.5rem; margin: 0 0 0.35rem; }}
    .sub {{ color: var(--muted); font-size: 0.9rem; margin: 0.25rem 0; }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
      gap: 0.75rem;
      margin: 1rem 0 1.5rem;
    }}
    .summary-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.75rem 1rem;
    }}
    .summary-card strong {{ display: block; font-size: 1.25rem; }}
    .summary-card span {{ color: var(--muted); font-size: 0.8rem; }}
    nav.toc {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1rem 1.25rem;
      margin-bottom: 1.5rem;
    }}
    nav.toc ul {{
      columns: 2;
      column-gap: 2rem;
      margin: 0.5rem 0 0;
      padding-left: 1.25rem;
    }}
    @media (max-width: 700px) {{ nav.toc ul {{ columns: 1; }} }}
    nav.toc a {{ color: var(--sg); text-decoration: none; }}
    nav.toc a:hover {{ text-decoration: underline; }}
    nav.toc .toc-tail a {{ color: var(--muted); }}
    .toolbar {{ margin-bottom: 1.25rem; }}
    .toolbar input {{
      width: 100%;
      max-width: 420px;
      padding: 0.5rem 0.75rem;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--text);
    }}
    .file-section {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1rem 1.25rem 1.25rem;
      margin-bottom: 1.25rem;
    }}
    .file-section h2 {{ margin: 0 0 0.15rem; font-size: 1.1rem; color: var(--sg); }}
    .file-section-collapsed {{
      border-style: dashed;
      border-color: rgba(251,191,36,.35);
      background: rgba(251,191,36,.04);
    }}
    .file-details > summary {{ list-style: none; cursor: pointer; }}
    .file-details > summary::-webkit-details-marker {{ display: none; }}
    .file-summary {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.35rem 0.75rem;
    }}
    .file-summary-title {{ font-size: 1.1rem; font-weight: 600; color: var(--muted); }}
    .file-details-body {{ margin-top: 0.75rem; }}
    .tag {{
      display: inline-block;
      font-size: 0.62rem;
      font-weight: 700;
      padding: 0.15rem 0.55rem;
      border-radius: 999px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      vertical-align: middle;
      margin-left: 0.45rem;
    }}
    .tag-na {{
      background: linear-gradient(135deg, rgba(251,191,36,.22), rgba(248,113,113,.18));
      color: #fcd34d;
      border: 1px solid rgba(251,191,36,.45);
    }}
    .tag-inline {{ margin-left: 0.25rem; font-size: 0.55rem; padding: 0.08rem 0.4rem; }}
    .file-meta {{ color: var(--muted); font-size: 0.85rem; margin: 0 0 0.75rem; }}
    .file-summary .file-meta {{ margin: 0; }}
    .file-note {{
      color: var(--muted);
      font-size: 0.85rem;
      margin: -0.35rem 0 0.75rem;
      font-style: italic;
    }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
    th, td {{
      border: 1px solid var(--border);
      padding: 0.5rem 0.65rem;
      text-align: left;
      vertical-align: middle;
    }}
    th {{ background: var(--surface2); color: var(--muted); font-weight: 600; }}
    th.col-sg {{ border-top: 3px solid var(--app); }}
    th.col-ios {{ border-top: 3px solid var(--sg); }}
    th.col-app {{ border-top: 3px solid var(--es); }}
    .applicable {{ text-align: center; width: 170px; white-space: nowrap; }}
    .scope-tag {{
      display: inline-block;
      font-family: "SF Mono", Consolas, monospace;
      font-size: 0.7rem;
      padding: 0.12rem 0.45rem;
      border-radius: 6px;
      background: rgba(45,212,191,.12);
      color: var(--app);
      border: 1px solid rgba(45,212,191,.35);
      margin-left: 0.35rem;
    }}
    tr:nth-child(even) td {{ background: rgba(255,255,255,.02); }}
    .test-name {{ font-family: "SF Mono", Consolas, monospace; font-size: 0.82rem; }}
    .status {{ text-align: center; width: 110px; }}
    .reason {{ font-size: 0.8rem; color: var(--muted); min-width: 220px; max-width: 420px; }}
    .reason-empty {{ color: var(--pending); }}
    .reason-line {{ margin: 0.15rem 0; line-height: 1.35; }}
    .badge {{
      display: inline-block;
      font-size: 0.65rem;
      font-weight: 700;
      padding: 0.2rem 0.5rem;
      border-radius: 999px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }}
    .badge-pending {{ background: rgba(100,116,139,.2); color: var(--pending); }}
    .badge-pass {{ background: rgba(52,211,153,.15); color: var(--pass); }}
    .badge-fail {{ background: rgba(248,113,113,.15); color: var(--fail); }}
    .badge-skip {{ background: rgba(251,191,36,.15); color: var(--skip); }}
    .badge-app-yes {{ background: rgba(45,212,191,.15); color: var(--app); }}
    .badge-app-partial {{ background: rgba(167,139,250,.15); color: var(--es); }}
    .badge-app-no {{ background: rgba(100,116,139,.15); color: var(--muted); }}
    .hidden {{ display: none !important; }}
    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      font-size: 0.82rem;
      color: var(--muted);
      margin-top: 0.5rem;
    }}
    .legend-item {{ display: flex; align-items: center; gap: 0.35rem; }}
  </style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>dev_e2e Test Catalog · React Native</h1>
    <p class="sub">Couchbase Lite Test Harness · {html.escape(generated)}</p>
    <p class="sub">SDK: <code>@couchbase/couchbase-lite-react-native@{html.escape(cbl_version)}</code> · iOS Simulator · Sync Gateway (Docker)</p>
    <p class="sub">Config: <code>{html.escape(config_label)}</code></p>
    <div class="summary">
      <div class="summary-card"><strong>{len(by_file)}</strong><span>test files</span></div>
      <div class="summary-card"><strong>{total_tests}</strong><span>tests in RN selection</span></div>
      <div class="summary-card"><strong>{android_passed}</strong><span>Android passed</span></div>
      <div class="summary-card"><strong>{android_failed}</strong><span>Android failed</span></div>
      <div class="summary-card"><strong>{ios_passed}</strong><span>iOS passed</span></div>
      <div class="summary-card"><strong>{ios_failed}</strong><span>iOS failed</span></div>
      <div class="summary-card"><strong>{ios_skipped}</strong><span>iOS skipped</span></div>
    </div>
    <p class="sub">{html.escape(run_summary)}</p>
    <p class="sub">Selection: <code>--ignore=test_multipeer.py</code> · <code>-k &quot;{html.escape(RN_PYTEST_K)}&quot;</code></p>
    <div class="legend">
      <span class="legend-item"><span class="badge badge-pass">Passed</span></span>
      <span class="legend-item"><span class="badge badge-skip">Skipped</span></span>
      <span class="legend-item"><span class="badge badge-fail">Failed</span></span>
      <span class="legend-item"><span class="badge badge-pending">Not run</span></span>
    </div>
  </header>

  <nav class="toc">
    <strong>Test files</strong>
    <ul>
{chr(10).join(toc_lines)}
    </ul>
  </nav>

  <div class="toolbar">
    <input type="search" id="filter" placeholder="Filter by file or test name…" />
  </div>

{"".join(sections)}
</div>
<script>
document.getElementById('filter').addEventListener('input', function() {{
  const q = this.value.toLowerCase();
  document.querySelectorAll('.file-section').forEach(section => {{
    const text = section.textContent.toLowerCase();
    section.classList.toggle('hidden', q && !text.includes(q));
  }});
}});
</script>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit-android", type=Path, default=DEFAULT_JUNIT_ANDROID)
    parser.add_argument("--junit-ios", type=Path, default=DEFAULT_JUNIT_IOS)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUT_ROOT,
        help="Also write catalog HTML to repo root (dev-e2e-test-catalog.html)",
    )
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument(
        "--config",
        type=Path,
        default=REPO_ROOT / "environment" / "aws" / "config.json",
        help="Config used for pytest collect-only (paths only)",
    )
    parser.add_argument("--cbl-version", default="1.1.1-3")
    args = parser.parse_args()

    android = parse_junit(args.junit_android)
    ios = parse_junit(args.junit_ios)
    by_file = collect_rn_tests(args.config)

    store: dict[str, Any] = {
        "android": android,
        "ios": ios,
        "meta": {
            "generated": datetime.now(timezone.utc).isoformat(),
            "cbl_version": args.cbl_version,
            "junit_android": str(args.junit_android),
            "junit_ios": str(args.junit_ios),
        },
    }
    if args.results:
        args.results.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")

    a_pass, a_skip, _a_fail = count_outcomes(by_file, android)
    i_pass, i_skip, i_fail = count_outcomes(by_file, ios)
    run_summary = (
        f"Android JUnit ({args.junit_android.name}): {a_pass} passed · {a_skip} skipped · "
        f"iOS JUnit ({args.junit_ios.name}): {i_pass} passed · {i_skip} skipped · {i_fail} failed"
    )

    html_out = build_html(
        by_file,
        android,
        ios,
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        cbl_version=args.cbl_version,
        config_label=str(args.config),
        run_summary=run_summary,
    )
    args.output.write_text(html_out, encoding="utf-8")
    print(f"Wrote {args.output}")
    if args.output_root:
        args.output_root.write_text(html_out, encoding="utf-8")
        print(f"Wrote {args.output_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

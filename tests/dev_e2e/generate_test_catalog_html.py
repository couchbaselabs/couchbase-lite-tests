"""Generate an HTML catalog of all dev_e2e tests, optionally running pytest and recording results."""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_E2E = REPO_ROOT / "tests" / "dev_e2e"
DEFAULT_CONFIG = DEV_E2E / "config.docker-js.json"
DEFAULT_OUT = DEV_E2E / "dev-e2e-test-catalog.html"
DEFAULT_RESULTS = DEV_E2E / "dev-e2e-test-results.json"
JUNIT_PATH = DEV_E2E / ".catalog-junit.xml"

OUTCOME_LINE_RE = re.compile(
    r"^(?P<file>[\w/_.-]+\.py)::\S+::(?P<test>\S+(?:\[[^\]]+\])?)\s+(?P<outcome>PASSED|FAILED|SKIPPED|ERROR)"
)
SKIP_SUMMARY_RE = re.compile(
    r"^SKIPPED \[.*?\] (?P<file>[\w/_.-]+\.py)(?::\d+)?: (?P<reason>.+)$"
)

TestResult = dict[str, str]  # {"outcome": "...", "reason": "..."}

# Peer-to-peer tests — no SG or ES remote involved.
BOTH_NA_FILES = frozenset({"test_basic_multipeer.py"})

# Platform / topology limits for the JS docker catalog (see .cursor/js-e2e-test-matrix.md).
BOTH_NA_FILES_JS = frozenset(
    {
        "test_encrypted_properties.py",
        "test_replication_upgrade.py",
        "test_replication_xdcr.py",
    }
)
BOTH_NA_TEST_BASES = frozenset({"test_pull_non_blob_changes_with_delta_sync_and_compact"})

# ES-only smoke / JWT tests — not exercised as CBL → Sync Gateway.
SG_NA_FILES = frozenset(
    {
        "test_edge_server_cbl.py",
        "test_jwt_rotation.py",
        "test_jwt_simple.py",
    }
)

# Sync Gateway–only features — no Edge Server equivalent.
ES_NA_FILES = frozenset(
    {
        "test_fest.py",
        "test_replication_auto_purge.py",
    }
)
ES_NA_TEST_BASES = frozenset(
    {
        "test_pull_channels_filter",
        "test_replicate_public_channel",
        "test_reset_checkpoint_push",
        "test_reset_checkpoint_pull",
    }
)

FILE_NOTES: dict[str, str] = {
    "test_basic_multipeer.py": "Peer-to-peer (CBL ↔ CBL) — not a Sync Gateway or Edge Server test.",
}

SG_NA_FILE_REASONS: dict[str, str] = {
    "test_edge_server_cbl.py": "Edge Server smoke test; not CBL → Sync Gateway.",
    "test_jwt_rotation.py": "JWT / Edge Server replication test; not CBL → Sync Gateway.",
    "test_jwt_simple.py": "JWT / Edge Server replication test; not CBL → Sync Gateway.",
}

ES_NA_FILE_REASONS: dict[str, str] = {
    "test_fest.py": "Requires Sync Gateway roles, channels, and sync functions.",
    "test_replication_auto_purge.py": "Requires Sync Gateway channels, roles, and access revocation.",
}

ES_SKIP_REASON = "Requires Sync Gateway features (channels/roles/CBS); skipped for --cbl-remote=es"
ES_SKIP_FILES = frozenset(
    {
        "test_fest.py",
        "test_replication_auto_purge.py",
        "test_replication_upgrade.py",
        "test_replication_xdcr.py",
        "test_multipeer.py",
        "test_encrypted_properties.py",
        "test_edge_server_cbl.py",
        "test_custom_conflict.py",
    }
)

ES_NA_TEST_REASONS: dict[str, str] = {
    "test_pull_channels_filter": "Requires Sync Gateway sync channels; Edge Server has no channel ACL.",
    "test_replicate_public_channel": "Requires Sync Gateway public channel (`channel(\"!\")`).",
    "test_reset_checkpoint_push": "Requires Sync Gateway `_purge` API; not available on Edge Server.",
    "test_reset_checkpoint_pull": "Requires Sync Gateway `_purge` API; not available on Edge Server.",
}

BOTH_NA_FILE_REASONS: dict[str, str] = {
    "test_basic_multipeer.py": "Peer-to-peer (CBL ↔ CBL); no Sync Gateway or Edge Server remote.",
    "test_encrypted_properties.py": "Field encryption (`EncryptedValue`) is C-only; not supported on JS.",
    "test_replication_upgrade.py": "Requires native CBL ≥ 4.0 and dataset v4.0 restore; JS reports 1.1.0.",
    "test_replication_xdcr.py": "Requires native CBL ≥ 4.0, XDCR topology, and load balancer; JS reports 1.1.0.",
}

BOTH_NA_TEST_REASONS: dict[str, str] = {
    "test_pull_non_blob_changes_with_delta_sync_and_compact": (
        "Delta sync + compact path not supported on Couchbase Lite JavaScript (CBSE-14861)."
    ),
}


def test_base_name(test_name: str) -> str:
    return test_name.split("[")[0]


def remote_applicable(file_name: str, test_name: str, remote: str) -> bool:
    base = test_base_name(test_name)
    if file_name in BOTH_NA_FILES or file_name in BOTH_NA_FILES_JS or base in BOTH_NA_TEST_BASES:
        return False
    if remote == "sg":
        return file_name not in SG_NA_FILES
    if remote == "es":
        return file_name not in ES_NA_FILES and base not in ES_NA_TEST_BASES
    raise ValueError(f"unknown remote: {remote}")


def na_reason(file_name: str, test_name: str, remote: str) -> str | None:
    if remote_applicable(file_name, test_name, remote):
        return None
    base = test_base_name(test_name)
    if file_name in BOTH_NA_FILE_REASONS:
        return BOTH_NA_FILE_REASONS[file_name]
    if base in BOTH_NA_TEST_REASONS:
        return BOTH_NA_TEST_REASONS[base]
    if remote == "sg" and file_name in SG_NA_FILE_REASONS:
        return SG_NA_FILE_REASONS[file_name]
    if remote == "es":
        if file_name in ES_NA_FILE_REASONS:
            return ES_NA_FILE_REASONS[file_name]
        if base in ES_NA_TEST_REASONS:
            return ES_NA_TEST_REASONS[base]
    return "Not applicable to this remote."


def normalize_test_result(value: str | dict[str, str] | None) -> TestResult | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return {
            "outcome": value.get("outcome", "UNKNOWN"),
            "reason": value.get("reason", ""),
        }
    return {"outcome": value, "reason": ""}


def test_outcome(result: TestResult | None) -> str | None:
    if result is None:
        return None
    return result.get("outcome")


def status_badge(applicable: bool, outcome: str | None = None) -> str:
    if not applicable:
        return '<span class="badge badge-na" title="This test does not target this remote">N/A</span>'
    if outcome is None:
        return '<span class="badge badge-pending">Not run</span>'
    label = outcome.upper()
    if label == "PASSED":
        return '<span class="badge badge-pass">Passed</span>'
    if label in ("FAILED", "ERROR"):
        return '<span class="badge badge-fail">Failed</span>'
    if label == "SKIPPED":
        return '<span class="badge badge-skip">Skipped</span>'
    return f'<span class="badge badge-pending">{html.escape(label)}</span>'


def parse_pytest_log(log_text: str) -> dict[str, dict[str, TestResult]]:
    """Return {file_name: {test_name: {outcome, reason}}} from pytest output."""
    results: dict[str, dict[str, TestResult]] = defaultdict(dict)
    skip_reasons_by_file: dict[str, list[str]] = defaultdict(list)
    in_summary = False

    for line in log_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("= ") and "short test summary" in stripped:
            in_summary = True
            continue
        if in_summary and stripped.startswith("= ") and "short test summary" not in stripped:
            in_summary = False

        m = OUTCOME_LINE_RE.match(stripped)
        if m:
            file_name = Path(m.group("file")).name
            results[file_name][m.group("test")] = {
                "outcome": m.group("outcome"),
                "reason": "",
            }
            continue

        if in_summary:
            sm = SKIP_SUMMARY_RE.match(stripped)
            if sm:
                skip_reasons_by_file[Path(sm.group("file")).name].append(sm.group("reason"))

    for file_name, file_results in results.items():
        reasons = skip_reasons_by_file.get(file_name, [])
        skipped_tests = [name for name, res in file_results.items() if res["outcome"] == "SKIPPED"]
        if len(reasons) == len(skipped_tests):
            for test_name, reason in zip(skipped_tests, reasons, strict=True):
                file_results[test_name]["reason"] = reason
        elif len(reasons) == 1 and len(skipped_tests) == 1:
            file_results[skipped_tests[0]]["reason"] = reasons[0]
        elif reasons and skipped_tests:
            shared = reasons[0]
            for test_name in skipped_tests:
                if not file_results[test_name]["reason"]:
                    file_results[test_name]["reason"] = shared

    return dict(results)


def parse_junit(junit_path: Path) -> dict[str, dict[str, TestResult]]:
    if not junit_path.exists():
        return {}
    results: dict[str, dict[str, TestResult]] = defaultdict(dict)
    root = ET.parse(junit_path).getroot()
    for testcase in root.iter("testcase"):
        class_name = testcase.attrib.get("classname", "")
        test_name = testcase.attrib.get("name", "")
        if not test_name:
            continue
        module = class_name.rsplit(".", 1)[0] if class_name else ""
        file_name = module.rsplit(".", 1)[-1] + ".py" if module else ""
        if not file_name.endswith(".py"):
            continue

        outcome = "PASSED"
        reason = ""
        if testcase.find("failure") is not None:
            outcome = "FAILED"
            reason = (testcase.find("failure").attrib.get("message") or "").strip()
        elif testcase.find("error") is not None:
            outcome = "ERROR"
            reason = (testcase.find("error").attrib.get("message") or "").strip()
        elif testcase.find("skipped") is not None:
            outcome = "SKIPPED"
            skipped = testcase.find("skipped")
            reason = (skipped.attrib.get("message") or skipped.text or "").strip()
            if ": " in reason:
                reason = reason.split(": ", 1)[1]

        results[file_name][test_name] = {"outcome": outcome, "reason": reason}
    return dict(results)


def merge_parsed_results(
    log_parsed: dict[str, dict[str, TestResult]],
    junit_parsed: dict[str, dict[str, TestResult]],
) -> dict[str, dict[str, TestResult]]:
    merged: dict[str, dict[str, TestResult]] = defaultdict(dict)
    for source in (log_parsed, junit_parsed):
        for file_name, tests in source.items():
            for test_name, result in tests.items():
                existing = merged[file_name].get(test_name)
                if existing is None:
                    merged[file_name][test_name] = dict(result)
                else:
                    existing["outcome"] = result["outcome"]
                    if result.get("reason"):
                        existing["reason"] = result["reason"]
    return dict(merged)


def run_pytest(files: list[str], config: Path, remote: str) -> tuple[int, str]:
    if JUNIT_PATH.exists():
        JUNIT_PATH.unlink()
    cmd = [
        "uv",
        "run",
        "pytest",
        *[str(DEV_E2E / f) if not f.startswith("tests/") else f for f in files],
        "-v",
        "--tb=short",
        f"--config={config}",
        "-o",
        "console_output_style=classic",
        "-rs",
        f"--junitxml={JUNIT_PATH}",
    ]
    if remote == "es":
        cmd.append("--cbl-remote=es")
    print(f"Running {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    output = proc.stdout + proc.stderr
    if proc.returncode not in (0, 1):
        print(output, file=sys.stderr)
    return proc.returncode, output


def load_results(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"sg": {}, "es": {}, "meta": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("sg", {})
    data.setdefault("es", {})
    data.setdefault("meta", {})
    for remote in ("sg", "es"):
        normalized: dict[str, dict[str, TestResult]] = {}
        for file_name, tests in data[remote].items():
            normalized[file_name] = {
                test_name: normalize_test_result(result) for test_name, result in tests.items()
            }
        data[remote] = normalized
    return data


def save_results(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fill_missing_reasons(store: dict[str, Any]) -> None:
    for file_name, tests in store.get("es", {}).items():
        for test_name, result in tests.items():
            if result.get("outcome") != "SKIPPED" or result.get("reason"):
                continue
            if file_name in ES_SKIP_FILES or test_base_name(test_name) in ES_NA_TEST_BASES:
                result["reason"] = ES_SKIP_REASON


def merge_results(
    store: dict[str, Any],
    remote: str,
    parsed: dict[str, dict[str, TestResult]],
    run_at: str,
) -> None:
    for file_name, tests in parsed.items():
        store[remote].setdefault(file_name, {})
        for test_name, result in tests.items():
            store[remote][file_name][test_name] = dict(result)
        store["meta"].setdefault("runs", {})[f"{remote}:{file_name}"] = run_at


def reason_cell(
    file_name: str,
    test_name: str,
    sg_ok: bool,
    es_ok: bool,
    sg_result: TestResult | None,
    es_result: TestResult | None,
) -> str:
    lines: list[str] = []

    def add(remote_label: str, text: str) -> None:
        lines.append(f'<div class="reason-line"><span class="reason-remote">{remote_label}</span>{html.escape(text)}</div>')

    if not sg_ok:
        add("SG", na_reason(file_name, test_name, "sg") or "Not applicable.")
    elif (
        sg_result
        and sg_result.get("reason")
        and sg_result.get("outcome") in ("SKIPPED", "FAILED", "ERROR")
    ):
        add("SG", sg_result["reason"])

    if not es_ok:
        add("ES", na_reason(file_name, test_name, "es") or "Not applicable.")
    elif (
        es_result
        and es_result.get("reason")
        and es_result.get("outcome") in ("SKIPPED", "FAILED", "ERROR")
    ):
        add("ES", es_result["reason"])

    if not lines:
        return '<td class="reason"><span class="reason-empty">—</span></td>'
    return f'<td class="reason">{"".join(lines)}</td>'


def collect_tests(config: Path) -> dict[str, list[str]]:
    cmd = [
        "uv",
        "run",
        "pytest",
        str(DEV_E2E),
        "--collect-only",
        "-q",
        f"--config={config}",
    ]
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        raise SystemExit(proc.returncode)

    by_file: dict[str, list[str]] = defaultdict(list)
    for line in proc.stdout.splitlines():
        line = line.strip()
        if "::" not in line:
            continue
        file_path, rest = line.split("::", 1)
        file_name = Path(file_path).name
        short_name = rest.split("::")[-1]
        by_file[file_name].append(short_name)
    return dict(sorted(by_file.items()))


def effective_results(
    file_name: str,
    test_name: str,
    sg_results: dict[str, dict[str, TestResult]],
    es_results: dict[str, dict[str, TestResult]],
) -> tuple[bool, bool, TestResult | None, TestResult | None]:
    sg_ok = remote_applicable(file_name, test_name, "sg")
    es_ok = remote_applicable(file_name, test_name, "es")
    sg_result = normalize_test_result(sg_results.get(file_name, {}).get(test_name)) if sg_ok else None
    es_result = normalize_test_result(es_results.get(file_name, {}).get(test_name)) if es_ok else None

    # ES-only smoke/JWT tests run without --cbl-remote=es; store the outcome under sg.
    if es_ok and file_name in SG_NA_FILES:
        default_run = normalize_test_result(sg_results.get(file_name, {}).get(test_name))
        if default_run and default_run.get("outcome") not in (None, "SKIPPED"):
            es_result = default_run

    return sg_ok, es_ok, sg_result, es_result


def collect_summary_counts(
    by_file: dict[str, list[str]],
    sg_results: dict[str, dict[str, TestResult]],
    es_results: dict[str, dict[str, TestResult]],
) -> tuple[int, int, int, int, int, int]:
    sg_pass = sg_fail = sg_skip = es_pass = es_fail = es_skip = 0
    for file_name, tests in by_file.items():
        for test_name in tests:
            sg_ok, es_ok, sg_result, es_result = effective_results(
                file_name, test_name, sg_results, es_results
            )
            if sg_ok and sg_result:
                outcome = sg_result.get("outcome")
                if outcome == "PASSED":
                    sg_pass += 1
                elif outcome in ("FAILED", "ERROR"):
                    sg_fail += 1
                elif outcome == "SKIPPED":
                    sg_skip += 1
            if es_ok and es_result:
                outcome = es_result.get("outcome")
                if outcome == "PASSED":
                    es_pass += 1
                elif outcome in ("FAILED", "ERROR"):
                    es_fail += 1
                elif outcome == "SKIPPED":
                    es_skip += 1
    return sg_pass, sg_fail, sg_skip, es_pass, es_fail, es_skip


def build_html(
    by_file: dict[str, list[str]],
    config: Path,
    generated: str,
    results: dict[str, dict[str, dict[str, str]]],
) -> str:
    total_tests = sum(len(tests) for tests in by_file.values())
    sg_results = results.get("sg", {})
    es_results = results.get("es", {})

    sg_pass, sg_fail, sg_skip, es_pass, es_fail, es_skip = collect_summary_counts(
        by_file, sg_results, es_results
    )

    sg_summary = f"{sg_pass} passed" if sg_pass else "—"
    if sg_fail:
        sg_summary += f", {sg_fail} failed"
    if sg_skip:
        sg_summary += f", {sg_skip} skipped"
    es_summary = f"{es_pass} passed" if es_pass else "—"
    if es_fail:
        es_summary += f", {es_fail} failed"
    if es_skip:
        es_summary += f", {es_skip} skipped"

    sections: list[str] = []

    for file_name in sorted(by_file):
        tests = by_file[file_name]
        note = FILE_NOTES.get(file_name, "")
        note_html = f'\n  <p class="file-note">{html.escape(note)}</p>' if note else ""
        rows: list[str] = []
        for test_name in tests:
            sg_ok, es_ok, sg_result, es_result = effective_results(
                file_name, test_name, sg_results, es_results
            )
            rows.append(
                f"""        <tr>
          <td class="test-name">{html.escape(test_name)}</td>
          <td class="status">{status_badge(sg_ok, test_outcome(sg_result))}</td>
          <td class="status">{status_badge(es_ok, test_outcome(es_result))}</td>
          {reason_cell(file_name, test_name, sg_ok, es_ok, sg_result, es_result)}
        </tr>"""
            )
        sections.append(
            f"""
<section class="file-section" id="{html.escape(file_name, quote=True)}">
  <h2>{html.escape(file_name)}</h2>
  <p class="file-meta">{len(tests)} test{"s" if len(tests) != 1 else ""}</p>{note_html}
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Test</th>
          <th class="col-sg">Sync Gateway</th>
          <th class="col-es">Edge Server</th>
          <th>Reason</th>
        </tr>
      </thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table>
  </div>
</section>"""
        )

    toc_items = "".join(
        f'        <li><a href="#{html.escape(name, quote=True)}">{html.escape(name)}</a> ({len(by_file[name])})</li>\n'
        for name in sorted(by_file)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>dev_e2e Test Catalog</title>
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
    .summary-card strong {{
      display: block;
      font-size: 1.25rem;
    }}
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
    .file-section h2 {{
      margin: 0 0 0.15rem;
      font-size: 1.1rem;
      color: var(--sg);
    }}
    .file-meta {{ color: var(--muted); font-size: 0.85rem; margin: 0 0 0.75rem; }}
    .file-note {{
      color: var(--muted);
      font-size: 0.85rem;
      margin: -0.35rem 0 0.75rem;
      font-style: italic;
    }}
    .table-wrap {{ overflow-x: auto; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88rem;
    }}
    th, td {{
      border: 1px solid var(--border);
      padding: 0.5rem 0.65rem;
      text-align: left;
      vertical-align: middle;
    }}
    th {{ background: var(--surface2); color: var(--muted); font-weight: 600; }}
    th.col-sg {{ border-top: 3px solid var(--sg); }}
    th.col-es {{ border-top: 3px solid var(--es); }}
    tr:nth-child(even) td {{ background: rgba(255,255,255,.02); }}
    .test-name {{ font-family: "SF Mono", Consolas, monospace; font-size: 0.82rem; }}
    .status {{ text-align: center; width: 110px; }}
    .reason {{ font-size: 0.8rem; color: var(--muted); min-width: 220px; max-width: 420px; }}
    .reason-empty {{ color: var(--pending); }}
    .reason-line {{ margin: 0.15rem 0; line-height: 1.35; }}
    .reason-remote {{
      display: inline-block;
      font-size: 0.62rem;
      font-weight: 700;
      padding: 0.05rem 0.35rem;
      border-radius: 4px;
      margin-right: 0.35rem;
      text-transform: uppercase;
      background: rgba(100,116,139,.25);
      color: var(--text);
      vertical-align: baseline;
    }}
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
    .badge-na {{ background: rgba(100,116,139,.12); color: var(--muted); border: 1px dashed var(--border); }}
    .badge-pass {{ background: rgba(52,211,153,.15); color: var(--pass); }}
    .badge-fail {{ background: rgba(248,113,113,.15); color: var(--fail); }}
    .badge-skip {{ background: rgba(251,191,36,.15); color: var(--skip); }}
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
    <h1>dev_e2e Test Catalog</h1>
    <p class="sub">Couchbase Lite Test Harness · {html.escape(generated)}</p>
    <p class="sub">Config: <code>{html.escape(str(config.relative_to(REPO_ROOT)))}</code></p>
    <div class="summary">
      <div class="summary-card"><strong>{len(by_file)}</strong><span>test files</span></div>
      <div class="summary-card"><strong>{total_tests}</strong><span>tests collected</span></div>
      <div class="summary-card"><strong>{sg_pass or "—"}</strong><span>Sync Gateway passed</span></div>
      <div class="summary-card"><strong>{es_pass or "—"}</strong><span>Edge Server passed</span></div>
    </div>
    <p class="sub">Sync Gateway: {html.escape(sg_summary)} · Edge Server: {html.escape(es_summary)}</p>
    <div class="legend">
      <span class="legend-item"><span class="badge badge-pending">Not run</span> awaiting execution</span>
      <span class="legend-item"><span class="badge badge-na">N/A</span> not applicable to this remote</span>
      <span class="legend-item"><span class="badge badge-pass">Passed</span></span>
      <span class="legend-item"><span class="badge badge-fail">Failed</span></span>
      <span class="legend-item"><span class="badge badge-skip">Skipped</span></span>
    </div>
  </header>

  <nav class="toc">
    <strong>Test files</strong>
    <ul>
{toc_items}    </ul>
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
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument(
        "--run-files",
        nargs="+",
        metavar="FILE",
        help="Run pytest for these test files against SG and ES, merge into results",
    )
    parser.add_argument("--sg-log", type=Path, help="Import Sync Gateway results from a pytest log")
    parser.add_argument("--es-log", type=Path, help="Import Edge Server results from a pytest log")
    args = parser.parse_args()

    result_store = load_results(args.results)
    run_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    if args.run_files:
        for remote in ("sg", "es"):
            code, output = run_pytest(args.run_files, args.config, remote)
            parsed = merge_parsed_results(parse_pytest_log(output), parse_junit(JUNIT_PATH))
            merge_results(result_store, remote, parsed, run_at)
            print(f"{remote.upper()}: exit {code}, {sum(len(v) for v in parsed.values())} tests recorded")
        save_results(args.results, result_store)

    if args.sg_log:
        parsed = parse_pytest_log(args.sg_log.read_text(encoding="utf-8"))
        merge_results(result_store, "sg", parsed, run_at)
        save_results(args.results, result_store)
    if args.es_log:
        parsed = parse_pytest_log(args.es_log.read_text(encoding="utf-8"))
        merge_results(result_store, "es", parsed, run_at)
        save_results(args.results, result_store)

    fill_missing_reasons(result_store)
    save_results(args.results, result_store)

    by_file = collect_tests(args.config)
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out_html = build_html(by_file, args.config, generated, result_store)
    args.output.write_text(out_html, encoding="utf-8")
    total = sum(len(v) for v in by_file.values())
    print(f"Wrote {args.output} ({len(by_file)} files, {total} tests)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

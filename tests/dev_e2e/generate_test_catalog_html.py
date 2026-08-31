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

from es_remote import ES_NA_FILE_REASONS, ES_NA_TEST_REASONS

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_E2E = REPO_ROOT / "tests" / "dev_e2e"
DEFAULT_CONFIG = DEV_E2E / "config.docker-js.json"
DEFAULT_OUT = DEV_E2E / "dev-e2e-test-catalog.html"
DEFAULT_RESULTS = DEV_E2E / "dev-e2e-test-results.json"
JUNIT_PATH = DEV_E2E / ".catalog-junit.xml"

OUTCOME_LINE_RE = re.compile(
    r"^(?P<file>[\w/_.-]+\.py)::\S+::(?P<test>\S+(?:\[[^\]]+\])?)\s+(?P<outcome>PASSED|FAILED|SKIPPED|ERROR)"
)
SKIP_SUMMARY_RE = re.compile(r"^SKIPPED \[.*?\] (?P<file>[\w/_.-]+\.py)(?::\d+)?: (?P<reason>.+)$")

TestResult = dict[str, str]  # {"outcome": "...", "reason": "..."}

# Platform / JS-inapplicable tests — collapsed at end of catalog (multipeer always last).
CATALOG_TAIL_ORDER = (
    "test_encrypted_properties.py",
    "test_replication_upgrade.py",
    "test_replication_xdcr.py",
    "test_basic_multipeer.py",
)
CATALOG_TAIL_COLLAPSED_FILES = frozenset(CATALOG_TAIL_ORDER)
BOTH_NA_FILES = frozenset({"test_basic_multipeer.py"})

# Platform / topology limits for the JS docker catalog (see .cursor/js-e2e-test-matrix.md).
BOTH_NA_FILES_JS = frozenset(
    {
        "test_encrypted_properties.py",
        "test_replication_upgrade.py",
        "test_replication_xdcr.py",
    }
)
BOTH_NA_TEST_BASES = frozenset(
    {
        "test_pull_non_blob_changes_with_delta_sync_and_compact",
        "test_pull_resurrected_doc",
    }
)

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
        "test_blob_replication",
    }
)

FILE_NOTES: dict[str, str] = {
    "test_encrypted_properties.py": (
        "`EncryptedValue` field encryption is implemented on the C test server only; "
        "not wired in the JS TDK (test skips unless platform is C)."
    ),
    "test_replication_upgrade.py": (
        "SGW 4.x upgrade interop (pre-4.0 revision trees → HLV / version vectors) requires native CBL ≥ 4.0 "
        "and the v4.0 `upgrade` dataset; lite-js 1.1.x has rev-tree IDs only (no HLV) and skips with "
        "`CBL 1.1.0 not >= 4.0.0`."
    ),
    "test_replication_xdcr.py": (
        "Cross-datacenter replication (XDCR) requires two Couchbase clusters, two Sync Gateways, "
        "and a load balancer; the JS Docker config is single-cluster. Also requires native CBL ≥ 4.0 "
        "(lite-js reports 1.1.x)."
    ),
    "test_basic_multipeer.py": (
        "Peer-to-peer (CBL ↔ CBL) only — not Sync Gateway or Edge Server. "
        "Not supported on Couchbase Lite JavaScript (no multipeer API; requires 2 test servers)."
    ),
}

SG_NA_FILE_REASONS: dict[str, str] = {
    "test_edge_server_cbl.py": "Edge Server smoke test; not CBL → Sync Gateway.",
    "test_jwt_rotation.py": "JWT / Edge Server replication test; not CBL → Sync Gateway.",
    "test_jwt_simple.py": "JWT / Edge Server replication test; not CBL → Sync Gateway.",
}

ES_SKIP_REASON = "Requires Sync Gateway features (channels/roles/CBS); skipped for --cbl-remote=es"

# Short catalog notes (visible + HTML comment) for tests where ES pass/fail differs by design.
TEST_CATALOG_NOTES: dict[str, str] = {
    "test_reset_checkpoint_push": "Push: purge on remote → needs SG `_purge` (ES N/A).",
    "test_reset_checkpoint_pull": "Pull: purge on CBL only → remote still has doc (ES OK).",
    "test_blob_replication": ("Push + blob metadata OK on ES; step 7 checks SG `_attachments` stubs (ES N/A)."),
    "test_pull_non_blob_changes_with_delta_sync_and_compact": (
        "CBSE-14861 — delta sync + compact blob path; not supported on lite-js (both remotes N/A)."
    ),
    "test_pull_channels_filter": (
        "Pull filter by SG sync channels (`United Kingdom`, `France`); travel sync functions assign "
        "`channel(doc.channels)`. ES has collection ACL only (ES N/A)."
    ),
    "test_replicate_public_channel": (
        "SG public channel `!` with user2 (empty collection_access); ES run pulled 101 docs — no channel gate (ES N/A)."
    ),
}

BOTH_NA_FILE_REASONS: dict[str, str] = {
    "test_basic_multipeer.py": "Peer-to-peer (CBL ↔ CBL); no Sync Gateway or Edge Server remote.",
    "test_encrypted_properties.py": "`EncryptedValue` not implemented on JS test server (C TDK only).",
    "test_replication_upgrade.py": ("Requires native CBL ≥ 4.0 (HLV / upgrade interop); lite-js reports 1.1.0."),
    "test_replication_xdcr.py": "Requires native CBL ≥ 4.0, XDCR topology, and load balancer; JS reports 1.1.0.",
}

BOTH_NA_TEST_REASONS: dict[str, str] = {
    "test_pull_non_blob_changes_with_delta_sync_and_compact": (
        "Delta sync + compact path not supported on Couchbase Lite JavaScript (CBSE-14861)."
    ),
    "test_pull_resurrected_doc": (
        "CBL-7841 (pull resurrected doc over local tombstone) not in lite-js 1.x; native CBL ≥ 4.2.0."
    ),
}


# Why a test is not applicable, in the vocabulary used by the catalog audit:
#   CBL-JS — lite-js/JS TDK gap or wrong CBL version; neither remote can run it.
#   ES     — valid for CBL → Sync Gateway, but Edge Server cannot exercise it.
#   SGW    — targets Edge Server / JWT directly; never runs as CBL → Sync Gateway.
NA_SCOPE_CBL_JS = "CBL-JS"
NA_SCOPE_ES = "ES"
NA_SCOPE_SGW = "SGW"


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


def na_scopes(file_name: str, test_name: str) -> list[str]:
    """Scopes explaining why a test is N/A, ordered broadest first."""
    base = test_base_name(test_name)
    scopes: list[str] = []
    if file_name in BOTH_NA_FILES or file_name in BOTH_NA_FILES_JS or base in BOTH_NA_TEST_BASES:
        scopes.append(NA_SCOPE_CBL_JS)
    if file_name in SG_NA_FILES:
        scopes.append(NA_SCOPE_SGW)
    if file_name in ES_NA_FILES or base in ES_NA_TEST_BASES:
        scopes.append(NA_SCOPE_ES)
    return scopes


def applicability(file_name: str, test_name: str) -> tuple[str, str]:
    """Return (Yes | Partial (… only) | No, N/A scope) for the applicability column."""
    sg_ok = remote_applicable(file_name, test_name, "sg")
    es_ok = remote_applicable(file_name, test_name, "es")
    scope = "+".join(na_scopes(file_name, test_name))
    if sg_ok and es_ok:
        return "Yes", ""
    if sg_ok:
        return "Partial (SG only)", scope
    if es_ok:
        return "Partial (ES only)", scope
    return "No", scope


def applicability_cell(file_name: str, test_name: str) -> str:
    label, scope = applicability(file_name, test_name)
    css = {"Yes": "app-yes", "No": "app-no"}.get(label, "app-partial")
    parts = [f'<span class="badge badge-{css}">{html.escape(label)}</span>']
    if scope:
        parts.append(f'<span class="scope-tag">{html.escape(scope)}</span>')
    return f'<td class="applicable">{"".join(parts)}</td>'


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


def run_es_full_suite(config: Path) -> tuple[int, dict[str, dict[str, TestResult]]]:
    """Run all ES-applicable dev_e2e tests; JWT smoke runs without --cbl-remote=es."""
    es_junit = DEV_E2E / ".catalog-es-full-junit.xml"
    if es_junit.exists():
        es_junit.unlink()

    main_cmd = [
        "uv",
        "run",
        "pytest",
        str(DEV_E2E),
        "--ignore",
        str(DEV_E2E / "edge_server"),
        "-v",
        "--tb=short",
        f"--config={config}",
        "-o",
        "console_output_style=classic",
        "-rs",
        f"--junitxml={es_junit}",
        "--cbl-remote=es",
    ]
    print(f"Running {' '.join(main_cmd)}", flush=True)
    main_proc = subprocess.run(main_cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    main_output = main_proc.stdout + main_proc.stderr
    if main_proc.returncode not in (0, 1):
        print(main_output, file=sys.stderr)

    jwt_junit = DEV_E2E / ".catalog-es-full-jwt-junit.xml"
    if jwt_junit.exists():
        jwt_junit.unlink()
    jwt_cmd = [
        "uv",
        "run",
        "pytest",
        str(DEV_E2E / "edge_server"),
        "-v",
        "--tb=short",
        f"--config={config}",
        "-o",
        "console_output_style=classic",
        "-rs",
        f"--junitxml={jwt_junit}",
    ]
    print(f"Running {' '.join(jwt_cmd)}", flush=True)
    jwt_proc = subprocess.run(jwt_cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    jwt_output = jwt_proc.stdout + jwt_proc.stderr
    if jwt_proc.returncode not in (0, 1):
        print(jwt_output, file=sys.stderr)

    parsed = merge_parsed_results(parse_pytest_log(main_output), parse_junit(es_junit))
    jwt_parsed = merge_parsed_results(parse_pytest_log(jwt_output), parse_junit(jwt_junit))
    for file_name, tests in jwt_parsed.items():
        parsed.setdefault(file_name, {}).update(tests)

    exit_code = main_proc.returncode if main_proc.returncode != 0 else jwt_proc.returncode
    return exit_code, parsed


def load_results(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"sg": {}, "es": {}, "meta": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("sg", {})
    data.setdefault("es", {})
    data.setdefault("meta", {})
    data.pop("es2", None)
    for remote in ("sg", "es"):
        normalized: dict[str, dict[str, TestResult]] = {}
        for file_name, tests in data.get(remote, {}).items():
            normalized[file_name] = {test_name: normalize_test_result(result) for test_name, result in tests.items()}
        data[remote] = normalized
    return data


def save_results(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fill_missing_reasons(store: dict[str, Any], config_path: Path) -> None:
    from es_remote import load_es_remote_skips

    skip_files, skip_tests = load_es_remote_skips(config_path)
    for remote in ("es",):
        for file_name, tests in store.get(remote, {}).items():
            for test_name, result in tests.items():
                if result.get("outcome") != "SKIPPED" or result.get("reason"):
                    continue
                base = test_base_name(test_name)
                if file_name in skip_files:
                    result["reason"] = ES_NA_FILE_REASONS.get(file_name, ES_SKIP_REASON)
                elif base in skip_tests or base in ES_NA_TEST_BASES:
                    result["reason"] = ES_NA_TEST_REASONS.get(base, ES_SKIP_REASON)


def merge_results(
    store: dict[str, Any],
    remote: str,
    parsed: dict[str, dict[str, TestResult]],
    run_at: str,
) -> None:
    store.setdefault(remote, {})
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
        lines.append(
            f'<div class="reason-line"><span class="reason-remote">{remote_label}</span>{html.escape(text)}</div>'
        )

    if not sg_ok:
        add("SG", na_reason(file_name, test_name, "sg") or "Not applicable.")
    elif sg_result and sg_result.get("reason") and sg_result.get("outcome") in ("SKIPPED", "FAILED", "ERROR"):
        add("SG", sg_result["reason"])

    if not es_ok:
        add("ES", na_reason(file_name, test_name, "es") or "Not applicable.")
    elif es_result and es_result.get("reason") and es_result.get("outcome") in ("SKIPPED", "FAILED", "ERROR"):
        add("ES", es_result["reason"])

    base = test_base_name(test_name)
    if base in TEST_CATALOG_NOTES:
        lines.append(f'<div class="reason-note">{html.escape(TEST_CATALOG_NOTES[base])}</div>')

    if not lines:
        return '<td class="reason"><span class="reason-empty">—</span></td>'
    return f'<td class="reason">{"".join(lines)}</td>'


def test_row_comment(test_name: str) -> str:
    note = TEST_CATALOG_NOTES.get(test_base_name(test_name))
    if not note:
        return ""
    return f"<!-- {note} -->\n        "


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
            sg_ok, es_ok, sg_result, es_result = effective_results(file_name, test_name, sg_results, es_results)
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


def collect_applicability_counts(by_file: dict[str, list[str]]) -> tuple[int, int, int]:
    yes = partial = no = 0
    for file_name, tests in by_file.items():
        for test_name in tests:
            label, _ = applicability(file_name, test_name)
            if label == "Yes":
                yes += 1
            elif label == "No":
                no += 1
            else:
                partial += 1
    return yes, partial, no


def catalog_file_order(by_file: dict[str, list[str]]) -> list[str]:
    tail = [name for name in CATALOG_TAIL_ORDER if name in by_file]
    main = sorted(name for name in by_file if name not in CATALOG_TAIL_COLLAPSED_FILES)
    return main + tail


def render_file_section(
    file_name: str,
    tests: list[str],
    sg_results: dict[str, dict[str, TestResult]],
    es_results: dict[str, dict[str, TestResult]],
    *,
    collapsed: bool = False,
) -> str:
    note = FILE_NOTES.get(file_name, "")
    note_html = f'\n      <p class="file-note">{html.escape(note)}</p>' if note else ""
    rows: list[str] = []
    for test_name in tests:
        sg_ok, es_ok, sg_result, es_result = effective_results(file_name, test_name, sg_results, es_results)
        rows.append(
            f"""        {test_row_comment(test_name)}<tr>
          <td class="test-name">{html.escape(test_name)}</td>
          <td class="status">{status_badge(sg_ok, test_outcome(sg_result))}</td>
          <td class="status">{status_badge(es_ok, test_outcome(es_result))}</td>
          {applicability_cell(file_name, test_name)}
          {reason_cell(file_name, test_name, sg_ok, es_ok, sg_result, es_result)}
        </tr>"""
        )

    table_html = f"""    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Test</th>
            <th class="col-sg">Sync Gateway</th>
            <th class="col-es">Edge Server</th>
            <th class="col-app">Applicable</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
{chr(10).join(rows)}
        </tbody>
      </table>
    </div>"""

    title = html.escape(file_name)
    meta = f"{len(tests)} test{'s' if len(tests) != 1 else ''}"

    if collapsed:
        return f"""
<section class="file-section file-section-collapsed" id="{html.escape(file_name, quote=True)}">
  <details class="file-details">
    <summary class="file-summary">
      <span class="file-summary-title">{title}<span class="tag tag-na">Not applicable</span></span>
      <span class="file-meta">{meta}</span>
    </summary>
    <div class="file-details-body">{note_html}
{table_html}
    </div>
  </details>
</section>"""

    note_block = f'\n  <p class="file-note">{html.escape(note)}</p>' if note else ""
    return f"""
<section class="file-section" id="{html.escape(file_name, quote=True)}">
  <h2>{title}</h2>
  <p class="file-meta">{meta}</p>{note_block}
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Test</th>
          <th class="col-sg">Sync Gateway</th>
          <th class="col-es">Edge Server</th>
          <th class="col-app">Applicable</th>
          <th>Reason</th>
        </tr>
      </thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table>
  </div>
</section>"""


def build_html(
    by_file: dict[str, list[str]],
    config: Path,
    generated: str,
    results: dict[str, dict[str, dict[str, str]]],
) -> str:
    total_tests = sum(len(tests) for tests in by_file.values())
    sg_results = results.get("sg", {})
    es_results = results.get("es", {})

    sg_pass, sg_fail, sg_skip, es_pass, es_fail, es_skip = collect_summary_counts(by_file, sg_results, es_results)
    app_yes, app_partial, app_no = collect_applicability_counts(by_file)

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

    for file_name in catalog_file_order(by_file):
        sections.append(
            render_file_section(
                file_name,
                by_file[file_name],
                sg_results,
                es_results,
                collapsed=file_name in CATALOG_TAIL_COLLAPSED_FILES,
            )
        )

    toc_items = "".join(
        (
            f'        <li class="toc-tail"><a href="#{html.escape(name, quote=True)}">'
            f'{html.escape(name)} <span class="tag tag-na tag-inline">N/A</span></a> ({len(by_file[name])})</li>\n'
            if name in CATALOG_TAIL_COLLAPSED_FILES
            else f'        <li><a href="#{html.escape(name, quote=True)}">{html.escape(name)}</a> ({len(by_file[name])})</li>\n'
        )
        for name in catalog_file_order(by_file)
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
    .file-section-collapsed {{
      border-style: dashed;
      border-color: rgba(251,191,36,.35);
      background: rgba(251,191,36,.04);
    }}
    .file-details > summary {{
      list-style: none;
      cursor: pointer;
    }}
    .file-details > summary::-webkit-details-marker {{ display: none; }}
    .file-summary {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.35rem 0.75rem;
    }}
    .file-summary-title {{
      font-size: 1.1rem;
      font-weight: 600;
      color: var(--muted);
    }}
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
      box-shadow: 0 0 12px rgba(251,191,36,.12);
    }}
    .tag-inline {{ margin-left: 0.25rem; font-size: 0.55rem; padding: 0.08rem 0.4rem; }}
    nav.toc .toc-tail a {{ color: var(--muted); }}
    .file-meta {{ color: var(--muted); font-size: 0.85rem; margin: 0 0 0.75rem; }}
    .file-summary .file-meta {{ margin: 0; }}
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
    th.col-app {{ border-top: 3px solid var(--app); }}
    .applicable {{
      text-align: center;
      width: 170px;
      white-space: nowrap;
    }}
    .applicable .badge + .scope-tag {{ margin-left: 0.35rem; }}
    .scope-tag {{
      display: inline-block;
      font-family: "SF Mono", Consolas, monospace;
      font-size: 0.7rem;
      padding: 0.12rem 0.45rem;
      border-radius: 6px;
      background: rgba(251,191,36,.12);
      color: #fcd34d;
      border: 1px solid rgba(251,191,36,.35);
    }}
    tr:nth-child(even) td {{ background: rgba(255,255,255,.02); }}
    .test-name {{ font-family: "SF Mono", Consolas, monospace; font-size: 0.82rem; }}
    .status {{ text-align: center; width: 110px; }}
    .reason {{ font-size: 0.8rem; color: var(--muted); min-width: 220px; max-width: 420px; }}
    .reason-empty {{ color: var(--pending); }}
    .reason-line {{ margin: 0.15rem 0; line-height: 1.35; }}
    .reason-note {{
      margin-top: 0.35rem;
      font-size: 0.75rem;
      color: var(--muted);
      font-style: italic;
      line-height: 1.3;
    }}
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
    <h1>dev_e2e Test Catalog</h1>
    <p class="sub">Couchbase Lite Test Harness · {html.escape(generated)}</p>
    <p class="sub">Config: <code>{html.escape(str(config.relative_to(REPO_ROOT)))}</code></p>
    <div class="summary">
      <div class="summary-card"><strong>{len(by_file)}</strong><span>test files</span></div>
      <div class="summary-card"><strong>{total_tests}</strong><span>tests collected</span></div>
      <div class="summary-card"><strong>{sg_pass or "—"}</strong><span>Sync Gateway passed</span></div>
      <div class="summary-card"><strong>{es_pass or "—"}</strong><span>Edge Server passed</span></div>
      <div class="summary-card"><strong>{app_yes}</strong><span>applicable to both remotes</span></div>
      <div class="summary-card"><strong>{app_partial}</strong><span>applicable to one remote</span></div>
      <div class="summary-card"><strong>{app_no}</strong><span>not applicable</span></div>
    </div>
    <p class="sub">Sync Gateway: {html.escape(sg_summary)} · Edge Server: {html.escape(es_summary)}</p>
    <p class="sub">N/A scope — <strong>CBL-JS</strong>: lite-js / JS TDK gap or wrong CBL version (both remotes) ·
      <strong>ES</strong>: Sync Gateway–only semantics Edge Server cannot exercise ·
      <strong>SGW</strong>: targets Edge Server / JWT directly, never CBL → Sync Gateway</p>
    <div class="legend">
      <span class="legend-item"><span class="badge badge-pending">Not run</span> awaiting execution</span>
      <span class="legend-item"><span class="badge badge-na">N/A</span> not applicable to this remote</span>
      <span class="legend-item"><span class="badge badge-pass">Passed</span></span>
      <span class="legend-item"><span class="badge badge-fail">Failed</span></span>
      <span class="legend-item"><span class="badge badge-skip">Skipped</span></span>
      <span class="legend-item"><span class="badge badge-app-yes">Yes</span> applicable to both remotes</span>
      <span class="legend-item"><span class="badge badge-app-partial">Partial</span> applicable to one remote</span>
      <span class="legend-item"><span class="badge badge-app-no">No</span> applicable to neither</span>
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
    parser.add_argument(
        "--run-es-full",
        action="store_true",
        help="Run full dev_e2e suite against Edge Server and merge into ES results",
    )
    args = parser.parse_args()

    result_store = load_results(args.results)
    run_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    if args.run_es_full:
        code, parsed = run_es_full_suite(args.config)
        merge_results(result_store, "es", parsed, run_at)
        result_store["meta"].setdefault("runs", {})["es:full"] = run_at
        save_results(args.results, result_store)
        print(f"ES: exit {code}, {sum(len(v) for v in parsed.values())} tests recorded")

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

    fill_missing_reasons(result_store, args.config)
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

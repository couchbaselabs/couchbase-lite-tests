#!/usr/bin/env python3
"""Run JS dev_e2e tests against SG and ES, capture logs, emit side-by-side HTML."""

from __future__ import annotations

import argparse
import html
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEV_E2E = REPO_ROOT / "tests" / "dev_e2e"
CONFIG = DEV_E2E / "config.docker-js.json"
DEFAULT_OUT = Path(__file__).resolve().parent / "js-cbl-e2e-test-comparison.html"
LOG_DIR = Path(__file__).resolve().parent / "comparison-logs"

START_TEST_RE = re.compile(r"Starting test:\s*(\S+)")
NODEID_LINE_RE = re.compile(r"^(?P<nodeid>tests/dev_e2e/\S+::\S+(?:\[[^\]]+\])?)")
INLINE_OUTCOME_RE = re.compile(
    r"^(?P<outcome>PASSED|FAILED|SKIPPED|ERROR)\s+(?P<nodeid>tests/dev_e2e/\S+::\S+(?:\[[^\]]+\])?)"
    r"(?:\s+-\s+(?P<reason>.*))?$"
)
OUTCOME_ONLY = frozenset({"PASSED", "FAILED", "SKIPPED", "ERROR"})
SUMMARY_RE = re.compile(
    r"=+\s+(?P<failed>\d+) failed, (?P<passed>\d+) passed, (?P<skipped>\d+) skipped"
)
LOG_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s")


@dataclass
class TestRun:
    nodeid: str
    short_name: str
    outcome: str = "UNKNOWN"
    skip_reason: str = ""
    log_lines: list[str] = field(default_factory=list)

    @property
    def log_text(self) -> str:
        return "\n".join(self.log_lines).strip()


def run_pytest(remote: str, log_path: Path, investigate: bool) -> int:
    cmd = [
        "uv",
        "run",
        "pytest",
        str(DEV_E2E),
        "-v",
        "--tb=short",
        f"--config={CONFIG}",
        "--cbl-log-level=verbose",
        "-o",
        "console_output_style=classic",
        "--capture=no",
    ]
    if remote == "es":
        cmd.extend(["--cbl-remote=es"])
        if investigate:
            cmd.append("--investigate-es-hangs")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Running {' '.join(cmd)} -> {log_path}", flush=True)
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(f"# command: {' '.join(cmd)}\n")
        handle.write(f"# started: {datetime.now(UTC).isoformat()}\n\n")
        handle.flush()
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        handle.write(f"\n# exit_code: {proc.returncode}\n")
    return proc.returncode


def parse_summary(log_path: Path) -> dict[str, int] | None:
    text = log_path.read_text(encoding="utf-8", errors="replace")
    for line in reversed(text.splitlines()):
        m = SUMMARY_RE.search(line)
        if m:
            return {
                "passed": int(m.group("passed")),
                "failed": int(m.group("failed")),
                "skipped": int(m.group("skipped")),
            }
    return None


def _short_name(nodeid: str) -> str:
    return nodeid.split("::")[-1].split("[")[0]


def _build_short_to_nodeid(lines: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in lines:
        m = NODEID_LINE_RE.match(line.strip())
        if m:
            nodeid = m.group("nodeid")
            mapping[_short_name(nodeid)] = nodeid
        im = INLINE_OUTCOME_RE.match(line.strip())
        if im:
            nodeid = im.group("nodeid")
            mapping[_short_name(nodeid)] = nodeid
    return mapping


def _clean_skip_reason(reason: str) -> str:
    reason = reason.strip()
    if not reason or LOG_TIMESTAMP_RE.match(reason) or reason.startswith("[INFO]"):
        return ""
    return reason


def _record_run(
    runs: dict[str, TestRun],
    nodeid: str,
    outcome: str,
    skip_reason: str,
    block: list[str],
) -> None:
    short = _short_name(nodeid)
    prev = runs.get(nodeid)
    merged = (prev.log_lines + block) if prev else block
    runs[nodeid] = TestRun(
        nodeid=nodeid,
        short_name=short,
        outcome=outcome,
        skip_reason=skip_reason or (prev.skip_reason if prev else ""),
        log_lines=merged,
    )


def parse_log(log_path: Path) -> dict[str, TestRun]:
    if not log_path.exists():
        raise FileNotFoundError(log_path)

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    short_to_nodeid = _build_short_to_nodeid(lines)
    runs: dict[str, TestRun] = {}
    current_lines: list[str] = []
    active_short: str | None = None

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        im = INLINE_OUTCOME_RE.match(stripped)
        if im:
            nodeid = im.group("nodeid")
            _record_run(
                runs,
                nodeid,
                im.group("outcome"),
                _clean_skip_reason(im.group("reason") or ""),
                [line],
            )
            i += 1
            continue

        sm = START_TEST_RE.search(line)
        if sm:
            active_short = sm.group(1)
            current_lines = [line]
            i += 1
            continue

        if stripped in OUTCOME_ONLY:
            outcome = stripped
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            nodeid: str | None = None
            skip_reason = ""
            block_end = i + 1
            if j < len(lines):
                nm = NODEID_LINE_RE.match(lines[j].strip())
                if nm:
                    candidate = nm.group("nodeid")
                    if active_short and _short_name(candidate) == active_short:
                        nodeid = candidate
                    elif active_short and active_short in short_to_nodeid:
                        nodeid = short_to_nodeid[active_short]
                    else:
                        nodeid = candidate
                    skip_reason = _clean_skip_reason(lines[j][len(candidate) :])
                    block_end = j + 1
            if not nodeid and active_short and active_short in short_to_nodeid:
                nodeid = short_to_nodeid[active_short]
            if not nodeid:
                i += 1
                continue
            block = (current_lines if current_lines else []) + [line]
            if j < len(lines) and NODEID_LINE_RE.match(lines[j].strip()):
                block.append(lines[j])
            if outcome == "SKIPPED" and not skip_reason and block_end < len(lines):
                skip_reason = _clean_skip_reason(lines[block_end].strip())
            k = block_end
            while k < len(lines):
                nxt = lines[k].strip()
                if nxt in OUTCOME_ONLY or INLINE_OUTCOME_RE.match(nxt):
                    break
                if START_TEST_RE.search(lines[k]):
                    break
                if NODEID_LINE_RE.match(nxt) and k > block_end:
                    break
                block.append(lines[k])
                k += 1
            _record_run(runs, nodeid, outcome, skip_reason, block)
            current_lines = []
            active_short = None
            i = k
            continue

        if active_short is not None:
            current_lines.append(line)
        i += 1

    return runs


def outcome_badge(outcome: str) -> tuple[str, str]:
    o = outcome.upper()
    if o == "PASSED":
        return "pass", "PASSED"
    if o == "FAILED":
        return "fail", "FAILED"
    if o == "SKIPPED":
        return "skip", "SKIPPED"
    if o == "ERROR":
        return "fail", "ERROR"
    return "unknown", o


def filter_log_for_display(log: str, max_lines: int = 400) -> str:
    keep: list[str] = []
    for line in log.splitlines():
        if any(
            token in line
            for token in (
                "Starting test:",
                "Moving to step",
                "PASSED",
                "FAILED",
                "SKIPPED",
                "ERROR",
                "Timeout",
                "AssertionError",
                "CblTimeoutError",
                "getReplicatorStatus",
                "activity",
                "POST /reset",
                "POST /startReplicator",
                "returned -1",
                "ts_error",
            )
        ):
            keep.append(line)
    if not keep:
        keep = log.splitlines()
    if len(keep) > max_lines:
        keep = keep[: max_lines // 2] + ["... (log truncated) ..."] + keep[-max_lines // 2 :]
    return "\n".join(keep)


def build_html(
    sg: dict[str, TestRun],
    es: dict[str, TestRun],
    meta: dict[str, str],
    sg_summary: dict[str, int] | None = None,
    es_summary: dict[str, int] | None = None,
) -> str:
    all_nodeids = sorted(set(sg) | set(es), key=lambda n: (n.split("::")[0], n))

    def count(runs: dict[str, TestRun], outcome: str) -> int:
        return sum(1 for r in runs.values() if r.outcome == outcome)

    if sg_summary:
        sg_pass, sg_fail, sg_skip = sg_summary["passed"], sg_summary["failed"], sg_summary["skipped"]
    else:
        sg_pass = count(sg, "PASSED")
        sg_fail = count(sg, "FAILED") + count(sg, "ERROR")
        sg_skip = count(sg, "SKIPPED")

    if es_summary:
        es_pass, es_fail, es_skip = es_summary["passed"], es_summary["failed"], es_summary["skipped"]
    else:
        es_pass = count(es, "PASSED")
        es_fail = count(es, "FAILED") + count(es, "ERROR")
        es_skip = count(es, "SKIPPED")

    sections: list[str] = []
    for nodeid in all_nodeids:
        s = sg.get(nodeid)
        e = es.get(nodeid)
        short = nodeid.split("::")[-1]
        file_part = nodeid.split("::")[0].split("/")[-1]

        s_out = s.outcome if s else "NOT RUN"
        e_out = e.outcome if e else "NOT RUN"
        s_cls, s_label = outcome_badge(s_out)
        e_cls, e_label = outcome_badge(e_out)

        s_log = filter_log_for_display(s.log_text if s else "(no log — test not executed in SG run)")
        e_log = filter_log_for_display(e.log_text if e else "(no log — test not executed in ES run)")

        interop_gap = s_out == "PASSED" and e_out in ("FAILED", "ERROR")
        compare_note = ""
        if interop_gap:
            compare_note = (
                '<div class="compare-alert">Sync Gateway passes but Edge Server fails — interop gap for Edge Server team.</div>'
            )
        elif s_out in ("FAILED", "ERROR") and e_out == "PASSED":
            compare_note = (
                '<div class="compare-note">Edge Server passes but Sync Gateway failed — likely infra/noise in this run (check logs).</div>'
            )
        elif s_out == "PASSED" and e_out == "PASSED":
            compare_note = '<div class="compare-note compare-pass">Both remotes pass — reference behavior.</div>'
        elif s_out == "PASSED" and e_out == "SKIPPED":
            compare_note = '<div class="compare-note">Passes on SG; skipped on ES.</div>'
        elif s_out == "SKIPPED" and e_out == "SKIPPED":
            compare_note = '<div class="compare-note">Skipped on both (platform / topology).</div>'

        gap_attr = ' data-interop-gap="1"' if interop_gap else ""
        sections.append(
            f"""
<details class="test-case"{gap_attr} id="{html.escape(nodeid, quote=True)}">
  <summary>
    <span class="file-tag">{html.escape(file_part)}</span>
    <span class="test-name">{html.escape(short)}</span>
    <span class="badge badge-{s_cls}">SG {html.escape(s_label)}</span>
    <span class="badge badge-{e_cls}">ES {html.escape(e_label)}</span>
  </summary>
  <div class="test-body">
    <p class="nodeid"><code>{html.escape(nodeid)}</code></p>
    {compare_note}
    <div class="compare-grid">
      <div class="remote-col sg-col">
        <div class="remote-header">
          <span class="remote-icon sg-icon">SG</span>
          <strong>Sync Gateway</strong>
          <span class="badge badge-{s_cls}">{html.escape(s_label)}</span>
        </div>
        <div class="flow-mini">Client ──► SG :4984 ──► CBS</div>
        {f'<p class="skip-reason">{html.escape(s.skip_reason)}</p>' if s and s.skip_reason else ''}
        <pre class="log">{html.escape(s_log)}</pre>
      </div>
      <div class="remote-col es-col">
        <div class="remote-header">
          <span class="remote-icon es-icon">ES</span>
          <strong>Edge Server</strong>
          <span class="badge badge-{e_cls}">{html.escape(e_label)}</span>
        </div>
        <div class="flow-mini">Client ──► ES ws://:59840</div>
        {f'<p class="skip-reason">{html.escape(e.skip_reason)}</p>' if e and e.skip_reason else ''}
        <pre class="log">{html.escape(e_log)}</pre>
      </div>
    </div>
  </div>
</details>"""
        )

    generated = meta.get("generated", datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"))
    interop_count = sum(
        1
        for nodeid in all_nodeids
        if (sg.get(nodeid) and sg[nodeid].outcome == "PASSED")
        and (es.get(nodeid) and es[nodeid].outcome in ("FAILED", "ERROR"))
    )
    sg_errors = count(sg, "ERROR")
    callout = ""
    if sg_errors >= 10:
        callout = f"""<div class="callout-warn" style="background:rgba(251,191,36,.08);border-left:3px solid var(--skip);padding:.5rem .75rem;margin-bottom:1rem;font-size:.85rem;">
  SG run included {sg_errors} ERRORs (often WebSocket session drops) — treat unexpected SG failures as infra noise; focus on tests where <strong>SG passed and ES failed</strong> ({interop_count} in this report).
</div>"""
    elif interop_count:
        callout = f"""<div class="callout-warn" style="background:rgba(251,191,36,.08);border-left:3px solid var(--skip);padding:.5rem .75rem;margin-bottom:1rem;font-size:.85rem;">
  Focus on <strong>{interop_count} tests</strong> where Sync Gateway passes and Edge Server fails — primary interop gaps for the Edge Server team.
</div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>SG vs ES — Per-Test Log Comparison</title>
<style>
:root {{
  --bg:#0b0f14; --surface:#151b24; --border:#2d3a4d; --text:#e8edf4; --muted:#8fa3bc;
  --sg:#4da3ff; --es:#a78bfa; --pass:#34d399; --fail:#f87171; --skip:#fbbf24; --unk:#64748b;
}}
* {{ box-sizing:border-box; }}
body {{ font-family:system-ui,sans-serif; background:var(--bg); color:var(--text); margin:0; padding:1.5rem; line-height:1.5; }}
.wrap {{ max-width:1400px; margin:0 auto; }}
h1 {{ font-size:1.5rem; margin:0 0 .25rem; }}
.sub {{ color:var(--muted); margin-bottom:1.5rem; font-size:.9rem; }}
.summary-diagram {{
  display:grid; grid-template-columns:1fr auto 1fr; gap:1rem; align-items:center;
  background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:1.25rem; margin-bottom:1.5rem;
}}
.diagram-box {{ text-align:center; padding:1rem; border-radius:8px; border:2px solid; }}
.diagram-box.sg {{ border-color:var(--sg); background:rgba(77,163,255,.08); }}
.diagram-box.es {{ border-color:var(--es); background:rgba(167,139,250,.08); }}
.diagram-box h2 {{ margin:0 0 .5rem; font-size:1rem; }}
.stat {{ font-size:.85rem; color:var(--muted); }}
.stat span {{ display:inline-block; margin:.15rem .5rem; }}
.stat .p {{ color:var(--pass); }} .stat .f {{ color:var(--fail); }} .stat .s {{ color:var(--skip); }}
.vs {{ font-size:1.25rem; color:var(--muted); font-weight:bold; }}
.center-flow {{ text-align:center; font-family:monospace; font-size:.75rem; color:var(--muted); margin-top:.5rem; }}
.toolbar {{ margin-bottom:1rem; }}
.toolbar input {{ width:100%; max-width:400px; padding:.5rem .75rem; border-radius:8px; border:1px solid var(--border); background:var(--surface); color:var(--text); }}
details.test-case {{ background:var(--surface); border:1px solid var(--border); border-radius:8px; margin-bottom:.5rem; }}
details.test-case[open] {{ border-color:#4da3ff55; }}
summary {{ cursor:pointer; padding:.75rem 1rem; list-style:none; display:flex; flex-wrap:wrap; align-items:center; gap:.5rem; }}
summary::-webkit-details-marker {{ display:none; }}
.file-tag {{ font-size:.7rem; background:#243044; padding:.1rem .4rem; border-radius:4px; color:var(--muted); }}
.test-name {{ font-weight:600; flex:1; min-width:200px; }}
.badge {{ font-size:.65rem; font-weight:700; padding:.2rem .45rem; border-radius:999px; text-transform:uppercase; }}
.badge-pass {{ background:rgba(52,211,153,.15); color:var(--pass); }}
.badge-fail {{ background:rgba(248,113,113,.15); color:var(--fail); }}
.badge-skip {{ background:rgba(251,191,36,.15); color:var(--skip); }}
.badge-unknown {{ background:rgba(100,116,139,.2); color:var(--unk); }}
.test-body {{ padding:0 1rem 1rem; border-top:1px solid var(--border); }}
.nodeid {{ font-size:.8rem; color:var(--muted); }}
.compare-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:1rem; margin-top:.75rem; }}
@media (max-width:900px) {{ .compare-grid {{ grid-template-columns:1fr; }} .summary-diagram {{ grid-template-columns:1fr; }} .vs {{ display:none; }} }}
.remote-col {{ border:1px solid var(--border); border-radius:8px; overflow:hidden; }}
.sg-col {{ border-top:3px solid var(--sg); }}
.es-col {{ border-top:3px solid var(--es); }}
.remote-header {{ display:flex; align-items:center; gap:.5rem; padding:.5rem .75rem; background:#1a2332; border-bottom:1px solid var(--border); }}
.remote-icon {{ width:1.75rem; height:1.75rem; border-radius:6px; display:flex; align-items:center; justify-content:center; font-size:.65rem; font-weight:800; }}
.sg-icon {{ background:rgba(77,163,255,.2); color:var(--sg); }}
.es-icon {{ background:rgba(167,139,250,.2); color:var(--es); }}
.flow-mini {{ font-family:monospace; font-size:.7rem; color:var(--muted); padding:.35rem .75rem; background:#0d1117; }}
.skip-reason {{ font-size:.8rem; color:var(--skip); padding:.35rem .75rem; margin:0; }}
pre.log {{ margin:0; padding:.75rem; font-size:.68rem; line-height:1.4; max-height:420px; overflow:auto; background:#0d1117; white-space:pre-wrap; word-break:break-word; }}
.compare-alert {{ background:rgba(248,113,113,.1); border-left:3px solid var(--fail); padding:.5rem .75rem; margin:.5rem 0; font-size:.85rem; }}
.compare-note {{ background:rgba(77,163,255,.08); border-left:3px solid var(--sg); padding:.5rem .75rem; margin:.5rem 0; font-size:.85rem; }}
.compare-pass {{ border-left-color:var(--pass); background:rgba(52,211,153,.08); }}
.hidden {{ display:none !important; }}
</style>
</head>
<body>
<div class="wrap">
<h1>Sync Gateway vs Edge Server — Per-Test Log Comparison</h1>
<p class="sub">CBL-JavaScript dev_e2e · {html.escape(generated)} · {len(all_nodeids)} tests · Config: tests/dev_e2e/config.docker-js.json</p>
<p class="sub">Raw logs: <code>{html.escape(meta.get("sg_log", ""))}</code> · <code>{html.escape(meta.get("es_log", ""))}</code></p>
{callout}

<div class="summary-diagram">
  <div class="diagram-box sg">
    <h2>Sync Gateway 3.2.0</h2>
    <div class="stat">
      <span class="p">{sg_pass} passed</span>
      <span class="f">{sg_fail} failed</span>
      <span class="s">{sg_skip} skipped</span>
    </div>
    <div class="center-flow">JS CBL ──HTTP──► :4984 ──► CBS</div>
  </div>
  <div class="vs">⇔</div>
  <div class="diagram-box es">
    <h2>Edge Server 1.2.0-4</h2>
    <div class="stat">
      <span class="p">{es_pass} passed</span>
      <span class="f">{es_fail} failed</span>
      <span class="s">{es_skip} skipped</span>
    </div>
    <div class="center-flow">JS CBL ──ws://──► :59840</div>
  </div>
</div>

<div class="toolbar">
  <input type="search" id="filter" placeholder="Filter tests by name or file…" />
  <button type="button" id="interop-only" style="margin-left:.5rem;padding:.5rem .75rem;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text);cursor:pointer;">SG pass / ES fail only</button>
</div>

{"".join(sections)}
</div>
<script>
let interopOnly = false;
function applyFilters() {{
  const q = document.getElementById('filter').value.toLowerCase();
  document.querySelectorAll('details.test-case').forEach(el => {{
    const text = el.textContent.toLowerCase();
    const matchText = !q || text.includes(q);
    const matchInterop = !interopOnly || el.dataset.interopGap === '1';
    el.classList.toggle('hidden', !(matchText && matchInterop));
  }});
}}
document.getElementById('filter').addEventListener('input', applyFilters);
document.getElementById('interop-only').addEventListener('click', function() {{
  interopOnly = !interopOnly;
  this.style.background = interopOnly ? 'rgba(248,113,113,.15)' : 'var(--surface)';
  applyFilters();
}});
</script>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-tests", action="store_true", help="Execute pytest SG + ES before generating HTML")
    parser.add_argument("--run-sg-only", action="store_true", help="Run only Sync Gateway pytest")
    parser.add_argument("--run-es-only", action="store_true", help="Run only Edge Server pytest")
    parser.add_argument("--sg-log", type=Path, default=LOG_DIR / "sg-full.log")
    parser.add_argument("--es-log", type=Path, default=LOG_DIR / "es-full.log")
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if args.run_tests or args.run_sg_only:
        print("=== Sync Gateway run ===", flush=True)
        sg_code = run_pytest("sgw", args.sg_log, investigate=False)
        print(f"SG exit code: {sg_code}", flush=True)
    if args.run_tests or args.run_es_only:
        print("=== Edge Server run (--cbl-remote=es --investigate-es-hangs) ===", flush=True)
        es_code = run_pytest("es", args.es_log, investigate=True)
        print(f"ES exit code: {es_code}", flush=True)

    sg_runs = parse_log(args.sg_log)
    es_runs = parse_log(args.es_log)
    meta = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "sg_log": str(args.sg_log),
        "es_log": str(args.es_log),
    }
    out_html = build_html(
        sg_runs,
        es_runs,
        meta,
        sg_summary=parse_summary(args.sg_log),
        es_summary=parse_summary(args.es_log),
    )
    args.output.write_text(out_html, encoding="utf-8")
    print(f"Wrote {args.output} ({len(sg_runs)} SG tests, {len(es_runs)} ES tests parsed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Coverage test for check_topology_markers.py's usage-tracing.

check_topology_markers.py only ever flags *under*-declaration (a marker
that's missing or too low for detected usage) -- it intentionally never
flags over-declaration, since a test may legitimately want extra headroom.
This test looks the other way: for every `@pytest.mark.min_*` actually
declared across the real test suite, does the checker's own usage-tracing
independently find something that requires it?

A class-level marker is backed if *any* test method in that class has
detected usage for it -- markers are typically declared once on the class
and shared by every method for convenience, so most individual methods
won't independently need every marker the class declares. A method-level
marker (one added on top of what the class already declares) is held to
the stricter per-method bar, since a one-off override is presumably there
because that specific method needs something extra.

A marker declared with an explicit ``0`` (e.g. ``min_test_servers(0)``) is
excluded: that's self-documentation ("this test explicitly needs none"),
never something usage could "require" -- usage only ever implies a minimum
of 1 or more.

A marker showing up here means one of two things, and telling them apart is
manual: either check_topology_markers.py has a blind spot (a legitimate
usage pattern -- e.g. an autouse fixture, or an attribute access shape it
doesn't recognize) that should be fixed there, or the marker in the listed
class/test is unnecessary and could simply be removed. Use this test as the
starting point for that judgment call, not as a mandate to make it pass by
any means -- silencing a real blind spot instead of fixing it would defeat
the point.
"""

import ast
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_topology_markers.py"

_spec = importlib.util.spec_from_file_location("check_topology_markers", CHECKER_PATH)
assert _spec is not None and _spec.loader is not None
ctm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ctm)

TEST_DIRS = [REPO_ROOT / "tests" / "dev_e2e", REPO_ROOT / "tests" / "QE"]


def _iter_test_files():
    for directory in TEST_DIRS:
        yield from sorted(directory.rglob("test_*.py"))


def _unbacked_markers(path: Path) -> list[str]:
    """Declared markers in `path` with no usage the checker's tracing backs.

    Only class-level `ClassDef`s are visited: every test_* function in this
    suite lives inside one (verified separately -- there are no module-level
    test functions), so nested `visit_FunctionDef`/`visit_AsyncFunctionDef`
    isn't needed here the way it is in check_topology_markers.py's own
    _Checker, which must also handle that case.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    scope = ctm._build_scope(tree, path)
    violations: list[str] = []

    for class_node in ast.iter_child_nodes(tree):
        if not isinstance(class_node, ast.ClassDef):
            continue

        class_declared = {m: n for m, n in ctm._min_markers(class_node.decorator_list).items() if n}
        methods = {n.name: n for n in class_node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

        autouse_required, autouse_dynamic = ctm._class_autouse_usage(methods, scope)
        class_backed: set[str] = set(autouse_required) | autouse_dynamic
        method_results = []
        for method_node in methods.values():
            if not method_node.name.startswith("test_"):
                continue
            method_only_declared = {m: n for m, n in ctm._min_markers(method_node.decorator_list).items() if n}
            required, dynamic = ctm._scan_usage(method_node, methods, scope)
            backed = required.keys() | dynamic
            class_backed |= backed
            method_results.append((method_node, method_only_declared, backed))

        for marker in class_declared:
            if marker not in class_backed:
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}:{class_node.lineno}: class "
                    f"{class_node.name} declares @pytest.mark.{marker}(...) but "
                    "no test method in it has usage the checker can detect "
                    "requiring it"
                )

        for method_node, method_only_declared, backed in method_results:
            for marker in method_only_declared:
                if marker in class_declared or marker in backed:
                    continue
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}:{method_node.lineno}: "
                    f"{method_node.name} declares @pytest.mark.{marker}(...) "
                    "on top of the class markers, but no usage the checker "
                    "can detect requires it"
                )

    return violations


def test_declared_markers_are_backed_by_detected_usage() -> None:
    violations: list[str] = []
    for path in _iter_test_files():
        violations.extend(_unbacked_markers(path))

    assert not violations, (
        f"{len(violations)} declared marker(s) have no usage the checker "
        "can currently detect:\n" + "\n".join(violations)
    )

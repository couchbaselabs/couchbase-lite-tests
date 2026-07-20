#!/usr/bin/env python3
"""Pre-commit check: verify topology markers match server-list usage in test files.

Scans test functions for indexed or bare access to a topology list
(``sync_gateways``, ``couchbase_servers``, ``test_servers``, ``load_balancers``,
``edge_servers``) and flags cases where the accessed index exceeds the
declared ``@pytest.mark.min_*`` requirement, or where no such marker is
declared at all. This only catches under-declaration (which causes a real
IndexError/skip mismatch at runtime); over-declaring a minimum is never
flagged since a test may legitimately want extra headroom.
"""

import ast
import sys
from pathlib import Path

TOPOLOGY_ATTRS = {
    "test_servers": "min_test_servers",
    "sync_gateways": "min_sync_gateways",
    "couchbase_servers": "min_couchbase_servers",
    "load_balancers": "min_load_balancers",
    "edge_servers": "min_edge_servers",
}
TOPOLOGY_MARKERS = set(TOPOLOGY_ATTRS.values())


def _min_markers(decorator_list: list[ast.expr]) -> dict[str, int]:
    markers: dict[str, int] = {}
    for dec in decorator_list:
        if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
            continue
        marker_name = dec.func.attr
        if marker_name not in TOPOLOGY_MARKERS:
            continue
        mark_attr = dec.func.value
        if not (
            isinstance(mark_attr, ast.Attribute)
            and mark_attr.attr == "mark"
            and isinstance(mark_attr.value, ast.Name)
            and mark_attr.value.id == "pytest"
        ):
            continue

        value = None
        if (
            dec.args
            and isinstance(dec.args[0], ast.Constant)
            and isinstance(dec.args[0].value, int)
        ):
            value = dec.args[0].value
        else:
            for kw in dec.keywords:
                if isinstance(kw.value, ast.Constant) and isinstance(
                    kw.value.value, int
                ):
                    value = kw.value.value
                    break
        if value is not None:
            markers[marker_name] = value
    return markers


def _scan_usage(func: ast.AST) -> tuple[dict[str, int], set[str]]:
    """Return (marker -> min required by a constant index, markers accessed with no constant index)."""
    required: dict[str, int] = {}
    dynamic: set[str] = set()
    subscripted_attrs: set[int] = set()

    for node in ast.walk(func):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            attr = node.value.attr
            if attr not in TOPOLOGY_ATTRS:
                continue
            marker = TOPOLOGY_ATTRS[attr]
            subscripted_attrs.add(id(node.value))
            index = node.slice
            if isinstance(index, ast.Constant) and isinstance(index.value, int):
                needed = index.value + 1
                required[marker] = max(required.get(marker, 0), needed)
            else:
                dynamic.add(marker)

    for node in ast.walk(func):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in TOPOLOGY_ATTRS
            and id(node) not in subscripted_attrs
        ):
            dynamic.add(TOPOLOGY_ATTRS[node.attr])

    return required, dynamic


class _Checker(ast.NodeVisitor):
    def __init__(self, filename: str):
        self.filename = filename
        self.violations: list[str] = []
        self._class_markers: list[dict[str, int]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_markers.append(_min_markers(node.decorator_list))
        self.generic_visit(node)
        self._class_markers.pop()

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if not node.name.startswith("test_"):
            return

        declared: dict[str, int] = {}
        for markers in self._class_markers:
            declared.update(markers)
        declared.update(_min_markers(node.decorator_list))

        required, dynamic = _scan_usage(node)

        for marker, needed in required.items():
            have = declared.get(marker)
            if have is None:
                self.violations.append(
                    f"{self.filename}:{node.lineno}: {node.name} accesses an index requiring "
                    f"@pytest.mark.{marker}({needed}) but no such marker is declared"
                )
            elif have < needed:
                self.violations.append(
                    f"{self.filename}:{node.lineno}: {node.name} declares "
                    f"@pytest.mark.{marker}({have}) but accesses an index requiring at least {needed}"
                )

        for marker in dynamic - required.keys():
            if marker not in declared:
                self.violations.append(
                    f"{self.filename}:{node.lineno}: {node.name} uses the "
                    f"{marker.removeprefix('min_')} list but no @pytest.mark.{marker}(...) is declared"
                )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)


def check_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as e:
        return [f"{path}: syntax error: {e}"]
    checker = _Checker(str(path))
    checker.visit(tree)
    return checker.violations


def main(argv: list[str]) -> int:
    violations: list[str] = []
    for arg in argv:
        path = Path(arg)
        if path.suffix != ".py" or not path.name.startswith("test_"):
            continue
        violations.extend(check_file(path))

    for v in violations:
        print(v)

    if violations:
        print(f"\n{len(violations)} topology marker mismatch(es) found.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Pre-commit check: verify topology markers match server-list usage in test files.

Scans test functions for indexed or bare access to a topology list
(``sync_gateways``, ``couchbase_servers``, ``test_servers``, ``load_balancers``,
``edge_servers``) and flags cases where the accessed index exceeds the
declared ``@pytest.mark.min_*`` requirement, or where no such marker is
declared at all. This only catches under-declaration (which causes a real
IndexError/skip mismatch at runtime); over-declaring a minimum is never
flagged since a test may legitimately want extra headroom.

Usage is also traced one level of indirection deep: if a test function calls
a same-class helper method (``self._setup_foo()``) or a module-level helper
function, that helper's topology access is attributed back to the calling
test. Resolution is by name within the same file only (no cross-file or
inherited-method resolution), so calls into imported helpers or base-class
methods defined elsewhere are not followed.
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


def _constant_int_index(index: ast.expr) -> int | None:
    """Return the literal int value of a subscript index, or None if not a constant int.

    Handles negative literals, which parse as ``UnaryOp(USub, Constant(n))`` rather than
    a negative ``Constant``. Bools are excluded even though ``bool`` is an ``int`` subclass.
    """
    if (
        isinstance(index, ast.UnaryOp)
        and isinstance(index.op, ast.USub)
        and isinstance(index.operand, ast.Constant)
        and type(index.operand.value) is int
    ):
        return -index.operand.value
    if isinstance(index, ast.Constant) and type(index.value) is int:
        return index.value
    return None


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
            and type(dec.args[0].value) is int
        ):
            value = dec.args[0].value
        else:
            for kw in dec.keywords:
                if isinstance(kw.value, ast.Constant) and type(kw.value.value) is int:
                    value = kw.value.value
                    break
        if value is not None:
            markers[marker_name] = value
    return markers


def _local_usage(func: ast.AST) -> tuple[dict[str, int], set[str]]:
    """Return (marker -> min required by a constant index, markers accessed with no constant index).

    Only considers accesses written directly in ``func``'s own body, not calls it makes.
    """
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
            index_value = _constant_int_index(node.slice)
            if index_value is not None:
                needed = abs(index_value) if index_value < 0 else index_value + 1
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


def _resolve_call(
    node: ast.Call,
    class_methods: dict[str, ast.AST],
    module_funcs: dict[str, ast.AST],
) -> ast.AST | None:
    func = node.func
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in ("self", "cls")
    ):
        return class_methods.get(func.attr)
    if isinstance(func, ast.Name):
        return module_funcs.get(func.id) or class_methods.get(func.id)
    return None


def _scan_usage(
    func: ast.AST,
    class_methods: dict[str, ast.AST],
    module_funcs: dict[str, ast.AST],
    _visited: set[int] | None = None,
) -> tuple[dict[str, int], set[str]]:
    """Return usage in ``func``, plus usage in same-file helpers it calls (recursively)."""
    if _visited is None:
        _visited = set()
    if id(func) in _visited:
        return {}, set()
    _visited.add(id(func))

    required, dynamic = _local_usage(func)

    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        target = _resolve_call(node, class_methods, module_funcs)
        if target is None:
            continue
        sub_required, sub_dynamic = _scan_usage(
            target, class_methods, module_funcs, _visited
        )
        for marker, needed in sub_required.items():
            required[marker] = max(required.get(marker, 0), needed)
        dynamic |= sub_dynamic

    return required, dynamic


class _Checker(ast.NodeVisitor):
    def __init__(self, filename: str, module_funcs: dict[str, ast.AST]):
        self.filename = filename
        self.violations: list[str] = []
        self._class_markers: list[dict[str, int]] = []
        self._class_methods_stack: list[dict[str, ast.AST]] = []
        self._module_funcs = module_funcs

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_markers.append(_min_markers(node.decorator_list))
        methods = {
            n.name: n
            for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self._class_methods_stack.append(methods)
        self.generic_visit(node)
        self._class_methods_stack.pop()
        self._class_markers.pop()

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if not node.name.startswith("test_"):
            return

        declared: dict[str, int] = {}
        for markers in self._class_markers:
            declared.update(markers)
        declared.update(_min_markers(node.decorator_list))

        class_methods = (
            self._class_methods_stack[-1] if self._class_methods_stack else {}
        )
        required, dynamic = _scan_usage(node, class_methods, self._module_funcs)

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
    module_funcs = {
        n.name: n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    checker = _Checker(str(path), module_funcs)
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

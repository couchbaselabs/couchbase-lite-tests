#!/usr/bin/env python3
"""Pre-commit check: verify topology markers match server-list usage in test files.

Scans test functions for indexed or bare access to a topology list
(``sync_gateways``, ``couchbase_servers``, ``test_servers``, ``load_balancers``,
``edge_servers``) and flags cases where the accessed index exceeds the
declared ``@pytest.mark.min_*`` requirement, or where no such marker is
declared at all. This only catches under-declaration (which causes a real
IndexError/skip mismatch at runtime); over-declaring a minimum is never
flagged since a test may legitimately want extra headroom.

Usage is also traced through helper calls: same-class methods, same-file
functions, or imported functions (see ``_resolve_import_path``). Inherited
base-class methods aren't followed.

Calls on an arbitrary-typed receiver (e.g. ``cblpytest.simple_cloud()``)
aren't traced either — that would need type inference to know which class to
look the method up in. Those are hand-listed in ``INDIRECT_TOPOLOGY_CALLS``.
"""

import ast
import functools
import importlib.util
import sys
from pathlib import Path
from typing import NamedTuple

TOPOLOGY_ATTRS = {
    "test_servers": "min_test_servers",
    "sync_gateways": "min_sync_gateways",
    "couchbase_servers": "min_couchbase_servers",
    "load_balancers": "min_load_balancers",
    "edge_servers": "min_edge_servers",
}
TOPOLOGY_MARKERS = set(TOPOLOGY_ATTRS.values())


# CBLPyTest.simple_cloud() unconditionally requires sync_gateways (raises if
# empty) but only conditionally touches couchbase_servers (falls back to
# rosmar). Listing min_couchbase_servers here would get tests that pass fine
# on rosmar-only configs skipped, so only the always-true half is recorded.
INDIRECT_TOPOLOGY_CALLS = {
    "simple_cloud": "min_sync_gateways",
}


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

    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in INDIRECT_TOPOLOGY_CALLS
        ):
            marker = INDIRECT_TOPOLOGY_CALLS[node.func.attr]
            required[marker] = max(required.get(marker, 0), 1)

    return required, dynamic


class _FileScope(NamedTuple):
    module_funcs: dict[str, ast.AST]
    imports: dict[str, tuple[str, str]]  # local name -> (module, original name)
    dir: Path


def _build_scope(tree: ast.Module, path: Path) -> _FileScope:
    module_funcs = {
        n.name: n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    imports: dict[str, tuple[str, str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for alias in node.names:
                imports[alias.asname or alias.name] = (node.module, alias.name)
    return _FileScope(module_funcs, imports, path.parent)


def _load_scope(path: Path, cache: dict[str, _FileScope]) -> _FileScope:
    key = str(path.resolve())
    if key not in cache:
        cache[key] = _build_scope(ast.parse(path.read_text(), filename=str(path)), path)
    return cache[key]


@functools.cache
def _find_pyproject(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


def _resolve_import_path(module: str, importing_dir: Path) -> Path | None:
    """Locate the source file behind an absolute ``from <module> import ...``.

    Tries a real installed package first (e.g. ``cbltest`` submodules), then
    searches for a matching file starting at the importing file's own
    directory and walking up to the repo root — this is how pytest's
    rootless import mode and its ``pythonpath``-configured roots (e.g.
    ``tests/shared/...``) both resolve in practice, without needing to parse
    pytest's config to know which directories count as roots. Returns
    ``None`` if nothing matches — an ordinary outcome (most imports, e.g.
    third-party libraries, aren't meant to be traced), not an error.
    """
    # find_spec(module) would raise ModuleNotFoundError for a dotted name whose
    # parent package isn't installed (it has to import the parent to look up
    # the submodule). A single-component lookup never raises that way — it
    # just returns None — so check the top-level name first and only resolve
    # the full dotted path once we know its parent actually exists.
    spec = None
    if importlib.util.find_spec(module.partition(".")[0]) is not None:
        spec = importlib.util.find_spec(module)
    if spec is not None and spec.origin and spec.origin != "built-in":
        return Path(spec.origin)

    rel_path = Path(*module.split("."))
    pyproject = _find_pyproject(importing_dir)
    repo_root = pyproject.parent if pyproject is not None else importing_dir
    for directory in (importing_dir, *importing_dir.parents):
        candidate = directory / f"{rel_path}.py"
        if candidate.is_file():
            return candidate
        if directory == repo_root:
            break
    return None


def _resolve_call(
    node: ast.Call,
    class_methods: dict[str, ast.AST],
    scope: _FileScope,
    cache: dict[str, _FileScope],
) -> tuple[ast.AST, dict[str, ast.AST], _FileScope] | None:
    func = node.func
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in ("self", "cls")
    ):
        target = class_methods.get(func.attr)
        return (target, class_methods, scope) if target is not None else None

    if not isinstance(func, ast.Name):
        return None

    target = scope.module_funcs.get(func.id) or class_methods.get(func.id)
    if target is not None:
        return target, class_methods, scope

    imported = scope.imports.get(func.id)
    if imported is None:
        return None
    module, original_name = imported
    resolved_path = _resolve_import_path(module, scope.dir)
    if resolved_path is None:
        return None
    target_scope = _load_scope(resolved_path, cache)
    target = target_scope.module_funcs.get(original_name)
    return (target, {}, target_scope) if target is not None else None


def _scan_usage(
    func: ast.AST,
    class_methods: dict[str, ast.AST],
    scope: _FileScope,
    cache: dict[str, _FileScope],
    _visited: set[int] | None = None,
) -> tuple[dict[str, int], set[str]]:
    """Return usage in ``func``, plus usage in helpers it calls (recursively)."""
    if _visited is None:
        _visited = set()
    if id(func) in _visited:
        return {}, set()
    _visited.add(id(func))

    required, dynamic = _local_usage(func)

    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        resolved = _resolve_call(node, class_methods, scope, cache)
        if resolved is None:
            continue
        target, target_class_methods, target_scope = resolved
        sub_required, sub_dynamic = _scan_usage(
            target, target_class_methods, target_scope, cache, _visited
        )
        for marker, needed in sub_required.items():
            required[marker] = max(required.get(marker, 0), needed)
        dynamic |= sub_dynamic

    return required, dynamic


class _Checker(ast.NodeVisitor):
    def __init__(self, filename: str, scope: _FileScope, cache: dict[str, _FileScope]):
        self.filename = filename
        self.violations: list[str] = []
        self._class_markers: list[dict[str, int]] = []
        self._class_methods_stack: list[dict[str, ast.AST]] = []
        self._scope = scope
        self._cache = cache

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
        required, dynamic = _scan_usage(node, class_methods, self._scope, self._cache)

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
    tree = ast.parse(path.read_text(), filename=str(path))
    scope = _build_scope(tree, path)
    cache = {str(path.resolve()): scope}
    checker = _Checker(str(path), scope, cache)
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

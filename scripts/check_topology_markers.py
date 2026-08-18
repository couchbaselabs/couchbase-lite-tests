#!/usr/bin/env python3
"""Pre-commit check: verify @pytest.mark.min_*(n) markers match topology usage.

Flags a marker that's missing or too low for what a test actually uses --
a real IndexError/skip mismatch at runtime. Never flags an over-declared
minimum; a test may legitimately want extra headroom.

A topology attribute (e.g. ``sync_gateways``) is only recognized on a
receiver whose class actually owns it -- see ``TOPOLOGY_ATTRS``, keyed by
class then attribute. Matching by bare attribute name alone would
false-positive on an unrelated same-named attribute.

A receiver's class is inferred locally, function by function
(``_scan_usage``), from three sources layered in priority order:

- its own parameters (``_seed_type_env``) -- a well-known fixture name
  (``FIXTURE_TYPES``) binds by name alone; otherwise its own annotation
- its arguments at this call site (``_call_site_env``) -- lets an
  un-annotated helper parameter resolve when the caller passed something
  traceable
- simple local assignments in its own body (``_collect_assign_types``)

Usage is traced through helper calls -- same-class methods, same-file
functions, imported functions (``_resolve_import_path``) -- and through
autouse fixtures (``_class_autouse_usage``), but not through inherited
base-class methods or expressions ``_infer_type`` can't follow.
"""

import ast
import functools
import importlib.util
import sys
from pathlib import Path
from typing import NamedTuple

# Topology attributes this script tracks, keyed by owning class then
# attribute name -- so a receiver only matches attributes its own class
# actually has, not just any object with a matching attribute name.
TOPOLOGY_ATTRS: dict[str, dict[str, str]] = {
    "CBLPyTest": {
        "test_servers": "min_test_servers",
        "sync_gateways": "min_sync_gateways",
        "couchbase_servers": "min_couchbase_servers",
        "edge_servers": "min_edge_servers",
        "load_balancers": "min_load_balancers",
        "clusters": "min_clusters",
    },
    "CouchbaseCluster": {
        "sync_gateways": "min_sync_gateways",
        "couchbase_servers": "min_couchbase_servers",
    },
}
TOPOLOGY_MARKERS = {marker for attrs in TOPOLOGY_ATTRS.values() for marker in attrs.values()}

# A single cluster is the implicit default topology -- `clusters[0]` (or
# unindexed iteration) needs no marker. Only accessing a second cluster or
# higher requires declaring @pytest.mark.min_clusters(n >= 2).
_MIN_CLUSTERS_MARKER: str = "min_clusters"
_MIN_CLUSTERS_THRESHOLD = 2

# Pytest fixture names bound to their type regardless of annotation: pytest
# resolves fixtures by parameter name, so a "cblpytest" parameter is always
# a CBLPyTest instance.
FIXTURE_TYPES: dict[str, str] = {
    "cblpytest": "CBLPyTest",
}

# Every class this script can resolve a receiver to.
KNOWN_TYPES = frozenset(TOPOLOGY_ATTRS) | frozenset(FIXTURE_TYPES.values())


def _infer_type(expr: ast.expr, env: dict[str, str]) -> str | None:
    """Best-effort local type of a receiver expression, or None if unresolved.

    Recognizes:
    - a name already bound in ``env`` (see ``_seed_type_env``, ``_collect_assign_types``)
    - a subscript of a ``CBLPyTest.clusters`` access (e.g. ``cblpytest.clusters[0]``),
      which yields a ``CouchbaseCluster``

    Anything else returns None rather than guessing.
    """
    if isinstance(expr, ast.Name):
        return env.get(expr.id)
    if isinstance(expr, ast.Call):
        func = expr.func
        if isinstance(func, ast.Name) and func.id in KNOWN_TYPES:
            return func.id
    if isinstance(expr, ast.Subscript):
        value = expr.value
        if (
            isinstance(value, ast.Attribute)
            and value.attr == "clusters"
            and _infer_type(value.value, env) == "CBLPyTest"
        ):
            return "CouchbaseCluster"
    return None


def _member_marker(table: dict[str, dict[str, str]], receiver_type: str | None, name: str) -> str | None:
    """Marker for ``receiver_type.name`` per ``table`` (class -> member -> marker)."""
    if receiver_type is None:
        return None
    return table.get(receiver_type, {}).get(name)


def _seed_type_env(func: ast.AST) -> dict[str, str]:
    """Seed a type env from a function's own parameters.

    A well-known fixture name (``FIXTURE_TYPES``) binds by name alone, even
    without an annotation. Everything else falls back to its own type
    annotation, if any.
    """
    env: dict[str, str] = {}
    if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return env
    args = func.args
    for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs):
        if arg.arg in FIXTURE_TYPES:
            env[arg.arg] = FIXTURE_TYPES[arg.arg]
        elif isinstance(arg.annotation, ast.Name) and arg.annotation.id in KNOWN_TYPES:
            env[arg.arg] = arg.annotation.id
    return env


def _collect_assign_types(func: ast.AST, env: dict[str, str]) -> None:
    """Extend ``env`` in place from simple local assignments in ``func``.

    A two-hop chain (an alias of an alias) wouldn't resolve in this single
    pass, but no pattern in the test suite needs that.
    """
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if not isinstance(target, ast.Name):
            continue
        inferred = _infer_type(value, env)
        if inferred is not None:
            env[target.id] = inferred


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
    """Extract each ``@pytest.mark.min_*(n)`` decorator's declared minimum.

    Only the positional argument is read: the runtime consumer
    (``required_topology.py``) reads ``mark.args[0]`` exclusively, so a
    keyword-invoked marker (e.g. ``min_sync_gateways(count=3)``) would
    already fail at collection time before this check's opinion matters.
    """
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

        if dec.args and isinstance(dec.args[0], ast.Constant) and type(dec.args[0].value) is int:
            markers[marker_name] = dec.args[0].value
    return markers


def _is_autouse_fixture(decorator_list: list[ast.expr]) -> bool:
    """Whether a decorator list includes an autouse pytest fixture.

    Matches any ``@<name>.fixture(autouse=True)`` -- ``pytest`` or
    ``pytest_asyncio`` -- by the ``fixture`` attribute alone, so both
    modules match without hard-coding either name.
    """
    for dec in decorator_list:
        if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
            continue
        if dec.func.attr != "fixture":
            continue
        for kw in dec.keywords:
            if kw.arg == "autouse" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                return True
    return False


def _local_usage(func: ast.AST, env: dict[str, str]) -> tuple[dict[str, int], set[str]]:
    """Usage written directly in ``func``'s own body, not calls it makes.

    Returns (marker -> min required by a constant index, markers accessed
    with no constant index). ``env`` maps names to inferred classes; an
    attribute or call only counts if its receiver's class actually owns
    that member (``TOPOLOGY_ATTRS``).

    One walk suffices for ``subscripted_attrs``: ``ast.walk`` visits a
    ``Subscript`` before its own ``.value`` child, so it's already recorded
    by the time that same ``Attribute`` node is visited on its own.
    """
    required: dict[str, int] = {}
    dynamic: set[str] = set()
    subscripted_attrs: set[int] = set()

    for node in ast.walk(func):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            attr_node = node.value
            receiver_type = _infer_type(attr_node.value, env)
            marker = _member_marker(TOPOLOGY_ATTRS, receiver_type, attr_node.attr)
            if marker is None:
                continue
            subscripted_attrs.add(id(attr_node))
            index_value = _constant_int_index(node.slice)
            if index_value is not None:
                needed = abs(index_value) if index_value < 0 else index_value + 1
                required[marker] = max(required.get(marker, 0), needed)
            else:
                dynamic.add(marker)
        elif isinstance(node, ast.Attribute):
            if id(node) in subscripted_attrs:
                continue
            receiver_type = _infer_type(node.value, env)
            marker = _member_marker(TOPOLOGY_ATTRS, receiver_type, node.attr)
            if marker is not None:
                dynamic.add(marker)

    return required, dynamic


class _FileScope(NamedTuple):
    module_funcs: dict[str, ast.AST]
    imports: dict[str, tuple[str, str]]  # local name -> (module, original name)
    dir: Path


def _build_scope(tree: ast.Module, path: Path) -> _FileScope:
    module_funcs: dict[str, ast.AST] = {
        n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    imports: dict[str, tuple[str, str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for alias in node.names:
                imports[alias.asname or alias.name] = (node.module, alias.name)
    return _FileScope(module_funcs, imports, path.parent)


@functools.cache
def _load_scope(path: Path) -> _FileScope:
    return _build_scope(ast.parse(path.read_text(), filename=str(path)), path)


@functools.cache
def _find_pyproject(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


@functools.cache
def _resolve_import_path(module: str, importing_dir: Path) -> Path | None:
    """Locate the source file behind an absolute ``from <module> import ...``.

    Tries an installed package first, then searches from the importing
    file's own directory up to the repo root -- covers both real packages
    (e.g. ``cbltest``) and pytest's own import roots (e.g.
    ``tests/shared/...``). Returns None for anything that doesn't match
    (most imports, e.g. third-party libraries) -- that's normal, not an
    error.
    """
    # Check the top-level name first: find_spec on a dotted name raises
    # ModuleNotFoundError if its parent package isn't installed, but a
    # single-component lookup never does -- it just returns None.
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
) -> tuple[ast.AST, dict[str, ast.AST], _FileScope, bool] | None:
    """Resolve a call to its target function, plus whether it's a method call.

    The ``bool`` says whether to skip the target's leading ``self``/``cls``
    parameter when matching call-site arguments (``_call_site_env``) -- a
    ``self./cls.`` call never passes it explicitly.
    """
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in ("self", "cls"):
        target = class_methods.get(func.attr)
        return (target, class_methods, scope, True) if target is not None else None

    if not isinstance(func, ast.Name):
        return None

    target = scope.module_funcs.get(func.id) or class_methods.get(func.id)
    if target is not None:
        return target, class_methods, scope, False

    imported = scope.imports.get(func.id)
    if imported is None:
        return None
    module, original_name = imported
    resolved_path = _resolve_import_path(module, scope.dir)
    if resolved_path is None:
        return None
    target_scope = _load_scope(resolved_path)
    target = target_scope.module_funcs.get(original_name)
    return (target, {}, target_scope, False) if target is not None else None


def _call_site_env(
    node: ast.Call,
    target: ast.AST,
    env: dict[str, str],
    is_method_call: bool,
) -> dict[str, str]:
    """Infer ``target``'s own parameter types from this call's arguments.

    Matches ``node``'s positional/keyword arguments to ``target``'s
    parameters and infers each one's type using the *caller's* env -- e.g.
    ``self.setup(cloud, ...)`` binds ``target``'s ``cloud`` parameter even
    if it isn't itself annotated, as long as the caller's ``cloud`` is
    traceable. ``is_method_call`` skips ``target``'s leading ``self``/``cls``,
    which the call site never passes explicitly.
    """
    if not isinstance(target, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return {}

    params = [*target.args.posonlyargs, *target.args.args]
    if is_method_call and params:
        params = params[1:]

    seed: dict[str, str] = {}
    for param, arg_expr in zip(params, node.args):
        inferred = _infer_type(arg_expr, env)
        if inferred is not None:
            seed[param.arg] = inferred

    param_names = {p.arg for p in params} | {p.arg for p in target.args.kwonlyargs}
    for kw in node.keywords:
        if kw.arg is None or kw.arg not in param_names:
            continue
        inferred = _infer_type(kw.value, env)
        if inferred is not None:
            seed[kw.arg] = inferred

    return seed


def _scan_usage(
    func: ast.AST,
    class_methods: dict[str, ast.AST],
    scope: _FileScope,
    _visited: set[int] | None = None,
    _call_env: dict[str, str] | None = None,
) -> tuple[dict[str, int], set[str]]:
    """Return usage in ``func``, plus usage in helpers it calls (recursively).

    ``_call_env`` (see ``_call_site_env``) is layered on top of ``func``'s
    own parameter/fixture bindings and wins on conflicts, since it reflects
    what's actually passed at this call rather than a static declaration.
    """
    if _visited is None:
        _visited = set()
    if id(func) in _visited:
        return {}, set()
    _visited.add(id(func))

    env = _seed_type_env(func)
    if _call_env:
        env.update(_call_env)
    _collect_assign_types(func, env)
    required, dynamic = _local_usage(func, env)

    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        resolved = _resolve_call(node, class_methods, scope)
        if resolved is None:
            continue
        target, target_class_methods, target_scope, is_method_call = resolved
        call_env = _call_site_env(node, target, env, is_method_call)
        sub_required, sub_dynamic = _scan_usage(target, target_class_methods, target_scope, _visited, call_env)
        for marker, needed in sub_required.items():
            required[marker] = max(required.get(marker, 0), needed)
        dynamic |= sub_dynamic

    return required, dynamic


def _class_autouse_usage(methods: dict[str, ast.AST], scope: _FileScope) -> tuple[dict[str, int], set[str]]:
    """Usage from every autouse fixture among a class's own ``methods``.

    An autouse fixture runs for every test in its class automatically -- no
    test body calls it directly -- so its topology usage can't be found via
    the normal call-tracing path in ``_scan_usage``; it has to be attributed
    to every test method in the class separately, by the caller.
    """
    required: dict[str, int] = {}
    dynamic: set[str] = set()
    for member in methods.values():
        if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _is_autouse_fixture(member.decorator_list):
            continue
        req, dyn = _scan_usage(member, methods, scope)
        for marker, needed in req.items():
            required[marker] = max(required.get(marker, 0), needed)
        dynamic |= dyn
    return required, dynamic


class _Checker(ast.NodeVisitor):
    def __init__(self, filename: str, scope: _FileScope) -> None:
        self.filename = filename
        self.violations: list[str] = []
        self._class_markers: list[dict[str, int]] = []
        self._class_methods_stack: list[dict[str, ast.AST]] = []
        self._class_autouse_stack: list[tuple[dict[str, int], set[str]]] = []
        self._scope = scope

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_markers.append(_min_markers(node.decorator_list))
        methods: dict[str, ast.AST] = {
            n.name: n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self._class_methods_stack.append(methods)
        self._class_autouse_stack.append(_class_autouse_usage(methods, self._scope))

        self.generic_visit(node)
        self._class_autouse_stack.pop()
        self._class_methods_stack.pop()
        self._class_markers.pop()

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if not node.name.startswith("test_"):
            return

        declared: dict[str, int] = {}
        for markers in self._class_markers:
            declared.update(markers)
        declared.update(_min_markers(node.decorator_list))

        class_methods = self._class_methods_stack[-1] if self._class_methods_stack else {}
        required, dynamic = _scan_usage(node, class_methods, self._scope)
        if self._class_autouse_stack:
            autouse_required, autouse_dynamic = self._class_autouse_stack[-1]
            for marker, needed in autouse_required.items():
                required[marker] = max(required.get(marker, 0), needed)
            dynamic |= autouse_dynamic

        for marker, needed in required.items():
            if marker == _MIN_CLUSTERS_MARKER and needed < _MIN_CLUSTERS_THRESHOLD:
                continue
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
            if marker == _MIN_CLUSTERS_MARKER:
                continue
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
    checker = _Checker(str(path), scope)
    checker.visit(tree)
    return checker.violations


def main(argv: list[str]) -> int:
    violations: list[str] = []
    for arg in argv:
        violations.extend(check_file(Path(arg)))

    for v in violations:
        print(v)

    if violations:
        print(f"\n{len(violations)} topology marker mismatch(es) found.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Pre-commit check: verify topology markers match server-list usage in test files.

Scans test functions for indexed or bare access to a topology attribute
(``sync_gateways``, ``couchbase_servers``, ``test_servers``, ``load_balancers``,
``edge_servers``, or the singular ``couchbase_server`` property) and flags
cases where the accessed index exceeds the declared ``@pytest.mark.min_*``
requirement, or where no such marker is declared at all. This only catches
under-declaration (which causes a real IndexError/skip mismatch at runtime);
over-declaring a minimum is never flagged since a test may legitimately want
extra headroom.

Each attribute name is only recognized on a receiver expression that
resolves — via the lightweight local inference in ``_infer_type`` — to the
specific class that actually owns it: see ``TOPOLOGY_ATTRS``, keyed first by
class (``CBLPyTest``, ``CouchbaseCloud``) and then by the attribute that
class exposes. Matching by bare attribute name alone, regardless of
receiver, would be ambiguous: an unrelated object with a same-named
attribute would false-positive, and it would blur which class a violation
message is even about.

Usage is also traced through helper calls: same-class methods, same-file
functions, or imported functions (see ``_resolve_import_path``). Inherited
base-class methods aren't followed. Type inference resets at each function
boundary and is seeded only from that function's own parameter annotations
plus simple local assignments (``_seed_type_env``, ``_collect_assign_types``)
— it does not follow call-site argument types into a callee, since that
would require inlining the caller's env into every helper, and every helper
in this codebase already annotates the parameters it needs traced.

Calls on a receiver type the local inference can't resolve (e.g. a variable
returned from an un-annotated helper) aren't traced — that would need real
type inference. ``cblpytest.simple_cloud()`` is a special case: it returns a
``CouchbaseCloud`` but conditionally requires ``couchbase_servers``
(falls back to rosmar), so instead of inferring a return type for it,
its always-true half (``min_sync_gateways``) is hand-listed in
``INDIRECT_TOPOLOGY_CALLS``, scoped to a ``CBLPyTest`` receiver.
"""

import ast
import functools
import importlib.util
import sys
from pathlib import Path
from typing import NamedTuple

# Topology attributes this script tracks, keyed by the class that owns each
# one and then by the attribute name itself -- e.g. TOPOLOGY_ATTRS["CBLPyTest"]
# ["test_servers"] is "min_test_servers". Keying by owning class first means a
# receiver only ever matches the attributes its inferred class actually has.
TOPOLOGY_ATTRS: dict[str, dict[str, str]] = {
    "CBLPyTest": {
        "test_servers": "min_test_servers",
        "sync_gateways": "min_sync_gateways",
        "couchbase_servers": "min_couchbase_servers",
        "edge_servers": "min_edge_servers",
        "load_balancers": "min_load_balancers",
    },
    "CouchbaseCloud": {
        # Also exposes the SGW nodes it was constructed with.
        "sync_gateways": "min_sync_gateways",
        # Singular property; raises if no Couchbase Server was configured
        # (no rosmar fallback), unlike CBLPyTest.couchbase_servers above.
        "couchbase_server": "min_couchbase_servers",
    },
}
TOPOLOGY_MARKERS = {
    marker for attrs in TOPOLOGY_ATTRS.values() for marker in attrs.values()
}

# CBLPyTest.simple_cloud() unconditionally requires sync_gateways (raises if
# empty) but only conditionally touches couchbase_servers (falls back to
# rosmar). Listing min_couchbase_servers here would get tests that pass fine
# on rosmar-only configs skipped, so only the always-true half is recorded.
# Same shape as TOPOLOGY_ATTRS: class -> method name -> marker.
INDIRECT_TOPOLOGY_CALLS: dict[str, dict[str, str]] = {
    "CBLPyTest": {"simple_cloud": "min_sync_gateways"},
}

# The classes this script's local type inference resolves receivers to --
# every class named as a key above.
KNOWN_TYPES = frozenset(TOPOLOGY_ATTRS) | frozenset(INDIRECT_TOPOLOGY_CALLS)


def _infer_type(expr: ast.expr, env: dict[str, str]) -> str | None:
    """Best-effort local type of a receiver expression, or None if unresolved.

    Recognizes a name already bound in ``env`` (from a parameter annotation
    or an earlier local assignment — see ``_seed_type_env`` and
    ``_collect_assign_types``), a direct constructor call
    (``CouchbaseCloud(...)``), and ``<CBLPyTest-typed-expr>.simple_cloud()``.
    Anything else — attribute chains through un-annotated helpers, dict/list
    lookups, etc. — returns None, excluding it from consideration rather
    than guessing.
    """
    if isinstance(expr, ast.Name):
        return env.get(expr.id)
    if isinstance(expr, ast.Call):
        func = expr.func
        if isinstance(func, ast.Name) and func.id in KNOWN_TYPES:
            return func.id
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "simple_cloud"
            and _infer_type(func.value, env) == "CBLPyTest"
        ):
            return "CouchbaseCloud"
    return None


def _member_marker(
    table: dict[str, dict[str, str]], receiver_type: str | None, name: str
) -> str | None:
    """Marker for ``receiver_type.name`` per ``table`` (class -> member -> marker)."""
    if receiver_type is None:
        return None
    return table.get(receiver_type, {}).get(name)


def _seed_type_env(func: ast.AST) -> dict[str, str]:
    """Seed a type env from a function's own parameter annotations."""
    env: dict[str, str] = {}
    if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return env
    args = func.args
    for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs):
        if isinstance(arg.annotation, ast.Name) and arg.annotation.id in KNOWN_TYPES:
            env[arg.arg] = arg.annotation.id
    return env


def _collect_assign_types(func: ast.AST, env: dict[str, str]) -> None:
    """Extend ``env`` in place from simple local assignments in ``func``.

    Runs two passes so a two-hop chain (e.g. an alias of an alias) still
    resolves; every pattern currently in the test suite only needs one.
    """
    for _ in range(2):
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


def _local_usage(func: ast.AST, env: dict[str, str]) -> tuple[dict[str, int], set[str]]:
    """Return (marker -> min required by a constant index, markers accessed with no constant index).

    Only considers accesses written directly in ``func``'s own body, not calls it makes.
    ``env`` maps local names to their inferred class (see ``_seed_type_env`` /
    ``_collect_assign_types``); a receiver's inferred class is looked up directly
    in ``TOPOLOGY_ATTRS`` / ``INDIRECT_TOPOLOGY_CALLS`` (class -> member -> marker),
    so an attribute or call only counts as topology usage when its receiver's own
    class actually exposes that member.

    A single walk suffices: ``ast.walk`` is breadth-first, so a ``Subscript`` node is
    always visited before its own ``.value`` child, meaning ``subscripted_attrs`` is
    already populated by the time that same ``Attribute`` node is (potentially) visited
    on its own.
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
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            receiver_type = _infer_type(node.func.value, env)
            marker = _member_marker(
                INDIRECT_TOPOLOGY_CALLS, receiver_type, node.func.attr
            )
            if marker is not None:
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
    target_scope = _load_scope(resolved_path)
    target = target_scope.module_funcs.get(original_name)
    return (target, {}, target_scope) if target is not None else None


def _scan_usage(
    func: ast.AST,
    class_methods: dict[str, ast.AST],
    scope: _FileScope,
    _visited: set[int] | None = None,
) -> tuple[dict[str, int], set[str]]:
    """Return usage in ``func``, plus usage in helpers it calls (recursively)."""
    if _visited is None:
        _visited = set()
    if id(func) in _visited:
        return {}, set()
    _visited.add(id(func))

    env = _seed_type_env(func)
    _collect_assign_types(func, env)
    required, dynamic = _local_usage(func, env)

    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        resolved = _resolve_call(node, class_methods, scope)
        if resolved is None:
            continue
        target, target_class_methods, target_scope = resolved
        sub_required, sub_dynamic = _scan_usage(
            target, target_class_methods, target_scope, _visited
        )
        for marker, needed in sub_required.items():
            required[marker] = max(required.get(marker, 0), needed)
        dynamic |= sub_dynamic

    return required, dynamic


class _Checker(ast.NodeVisitor):
    def __init__(self, filename: str, scope: _FileScope):
        self.filename = filename
        self.violations: list[str] = []
        self._class_markers: list[dict[str, int]] = []
        self._class_methods_stack: list[dict[str, ast.AST]] = []
        self._scope = scope

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
        required, dynamic = _scan_usage(node, class_methods, self._scope)

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

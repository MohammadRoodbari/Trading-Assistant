"""A safe expression evaluator for filters — parsed, never eval'd.

A filter is a boolean expression over a symbol's fields. We parse it to an AST,
reject anything outside a tiny whitelist (arithmetic, comparisons, and/or/not, a
few named functions), and evaluate the validated tree with a hand-written walker.
There is NO eval/exec, no attribute or subscript access, no comprehensions, no
imports — so a filter string cannot execute code or touch the system. Data errors
during evaluation (e.g. divide-by-zero on one symbol) fail that row to False, never
raising, so one bad row never aborts a market-wide scan.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Callable, Iterable

# AST node types allowed anywhere in a filter expression.
_ALLOWED = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Call,
)


class FilterError(ValueError):
    """Raised for an invalid/unsafe/unparseable filter expression."""


def _is_nan(v) -> bool:
    return isinstance(v, float) and v != v


def _truthy(v) -> bool:
    if _is_nan(v):
        return False
    return bool(v)


class Filter:
    """A validated, ready-to-evaluate filter."""

    def __init__(self, source: str, tree: ast.Expression, names: frozenset[str]):
        self.source = source
        self._tree = tree
        self.names = names  # variable names the expression reads (for classification)

    def evaluate(self, row: dict) -> bool:
        try:
            return _truthy(_eval(self._tree.body, row))
        except _RowError:
            return False


class _RowError(Exception):
    """Internal: a per-row data problem -> row does not match."""


def compile_filter(
    source: str, allowed_names: Iterable[str], safe_funcs: dict[str, Callable]
) -> Filter:
    """Parse + validate `source`. Raises FilterError on anything unsafe/unknown."""
    if not source or not source.strip():
        raise FilterError("empty filter expression")
    if len(source) > 1000:
        raise FilterError("filter expression too long (max 1000 chars)")
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise FilterError(f"could not parse filter: {exc.msg}") from exc
    except ValueError as exc:  # e.g. an over-long integer literal
        raise FilterError(f"invalid filter literal: {exc}") from exc

    nodes = list(ast.walk(tree))
    if len(nodes) > 200:  # bounds evaluation depth -> no RecursionError DoS
        raise FilterError("filter expression too complex (max 200 nodes)")

    allowed = set(allowed_names)
    names_used: set[str] = set()
    for node in nodes:
        if not isinstance(node, _ALLOWED):
            raise FilterError(f"disallowed syntax: {type(node).__name__}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, str, bool)):
            raise FilterError(f"disallowed constant: {node.value!r}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in safe_funcs:
                raise FilterError("only whitelisted functions may be called")
            if node.keywords:
                raise FilterError("keyword arguments are not allowed in filters")
    # Names: a Name is either a whitelisted function (in a Call) or a variable.
    func_names = set(safe_funcs)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in func_names:
                continue
            if node.id not in allowed:
                raise FilterError(f"unknown variable: {node.id!r}")
            names_used.add(node.id)
    return Filter(source, tree, frozenset(names_used))


def make_safe_funcs() -> dict[str, Callable]:
    def contains(hay, needle) -> bool:
        return str(needle) in str(hay)

    def _round(x, n=0):
        # Guard ndigits magnitude: round(int, -1e18) would build a 10**1e18 int
        # (CPU/memory DoS). Out-of-range -> ValueError -> caught -> row fails.
        n = int(n)
        if not -100 <= n <= 100:
            raise ValueError("round ndigits out of range")
        return round(x, n)

    return {
        "abs": lambda x: abs(x),
        "min": lambda *a: min(a),
        "max": lambda *a: max(a),
        "round": _round,
        "startswith": lambda s, p: str(s).startswith(str(p)),
        "endswith": lambda s, p: str(s).endswith(str(p)),
        "contains": contains,
    }


_SAFE_FUNCS = make_safe_funcs()

_CMP = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
}


def _eval(node, row: dict):
    if isinstance(node, ast.BoolOp):
        vals = (_eval(v, row) for v in node.values)
        if isinstance(node.op, ast.And):
            return all(_truthy(v) for v in vals)
        return any(_truthy(v) for v in vals)
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, row)
        if isinstance(node.op, ast.Not):
            # Propagate NaN through NOT so `not (missing != 0)` doesn't match a
            # row with missing data (NaN stays a no-match either way).
            return math.nan if _is_nan(v) else not _truthy(v)
        if isinstance(node.op, ast.USub):
            return -_num(v)
        return +_num(v)
    if isinstance(node, ast.BinOp):
        a, b = _num(_eval(node.left, row)), _num(_eval(node.right, row))
        if _is_nan(a) or _is_nan(b):
            return math.nan
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        if isinstance(node.op, ast.Mult):
            return a * b
        if isinstance(node.op, (ast.Div, ast.Mod)):
            if b == 0:
                return math.nan  # divide-by-zero -> excludes the row via nan compares
            return a / b if isinstance(node.op, ast.Div) else a % b
        raise _RowError()
    if isinstance(node, ast.Compare):
        left = _eval(node.left, row)
        for op, comp in zip(node.ops, node.comparators, strict=False):
            right = _eval(comp, row)
            if _is_nan(left) or _is_nan(right):
                return math.nan  # nan operand -> nan (no match, and safe under NOT)
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Call):
        args = [_eval(a, row) for a in node.args]
        try:
            return _SAFE_FUNCS[node.func.id](*args)
        except (TypeError, ValueError, ZeroDivisionError, OverflowError, MemoryError) as exc:
            raise _RowError() from exc
    if isinstance(node, ast.Name):
        if node.id not in row:
            raise _RowError()
        return row[node.id]
    if isinstance(node, ast.Constant):
        return node.value
    raise _RowError()


def _num(v) -> float:
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return v
    raise _RowError()

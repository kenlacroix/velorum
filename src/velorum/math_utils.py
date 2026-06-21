"""Detect math challenges and safely evaluate simple arithmetic."""
from __future__ import annotations

import ast
import operator
import re
from typing import NamedTuple

_MATH_KEYWORDS = [
    "calculate", "compute", "solve", "what is", "what's", r"=\s*\?",
    "equals", "sum of", "product of", "result of", "how much", "how many",
]
_EXPR_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([\+\-\*\/])\s*(\d+(?:\.\d+)?)")


class MathContext(NamedTuple):
    is_math_challenge: bool
    verified_answer: str  # e.g. "2 + 3 = 5", empty if not computable


def _safe_eval(expr: str) -> float | None:
    _OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
    }

    def _e(n: ast.expr) -> float:
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](_e(n.left), _e(n.right))
        raise ValueError(f"Unsupported node: {type(n)}")

    try:
        tree = ast.parse(expr.strip(), mode="eval")
        return _e(tree.body)
    except Exception:
        return None


def analyze_for_math(title: str, content: str) -> MathContext:
    """Detect whether a post is a math challenge and compute the answer if possible."""
    text = f"{title} {content}".lower()
    has_kw = any(re.search(k, text) for k in _MATH_KEYWORDS)
    has_nums = bool(_EXPR_RE.search(text))
    if not (has_kw or has_nums):
        return MathContext(False, "")

    m = _EXPR_RE.search(f"{title} {content}")
    if m:
        a, op, b = m.group(1), m.group(2), m.group(3)
        result = _safe_eval(f"{a}{op}{b}")
        if result is not None:
            fmt: int | float = int(result) if result == int(result) else round(result, 6)
            return MathContext(True, f"{a} {op} {b} = {fmt}")

    return MathContext(True, "")

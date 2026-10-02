"""Benchmark the hand-rolled JSON parser.

Correctness is gated against an EXTERNAL oracle -- Python's stdlib `json`
module -- not against the solution's own output. A candidate that parses
faster but produces different objects, or that stops raising on malformed
input, scores 0.0 throughput and cannot win.

Emits:  throughput: <MB/s>
"""
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent.parent / "corpus"

WARMUP_ITERS = 2
TIMED_ITERS = 5


# Modules that would trivially "win" by doing the parsing for us. The point
# of the demo is to optimize the hand-rolled scanner, not to delegate.
BANNED_MODULES = {
    "json", "ujson", "orjson", "simplejson", "rapidjson", "python_rapidjson",
    "msgspec", "cjson", "hyperjson", "pysimdjson", "simdjson", "yaml",
    "ast", "eval", "pickle", "marshal",
}


def check_no_delegation(path):
    """Reject a solution that imports a JSON library instead of parsing.

    Checked by AST so that `import json`, `from json import loads`,
    `importlib.import_module("json")` and `__import__("json")` are all
    caught, including inside functions.
    """
    import ast as _ast

    tree = _ast.parse(path.read_text(encoding="utf-8"))
    bad = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BANNED_MODULES:
                    bad.append(f"import {alias.name}")
        elif isinstance(node, _ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in BANNED_MODULES:
                bad.append(f"from {node.module} import ...")
        elif isinstance(node, _ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name in ("__import__", "import_module") and node.args:
                arg = node.args[0]
                if isinstance(arg, _ast.Constant) and isinstance(arg.value, str):
                    if arg.value.split(".")[0] in BANNED_MODULES:
                        bad.append(f"dynamic import of {arg.value!r}")
                else:
                    bad.append("dynamic import with non-literal module name")
            elif name in ("eval", "exec", "literal_eval"):
                bad.append(f"use of {name}()")
    return bad


def load_solution():
    """Import the file under optimization as a module."""
    path = HERE / "optimize.py"
    spec = importlib.util.spec_from_file_location("solution_parser", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "parse"):
        raise AttributeError("optimize.py must export a `parse(text)` function")
    return module


def deep_equal(a, b):
    """Structural equality that is strict about types.

    json.loads distinguishes int from float and True from 1; plain `==`
    in Python does not (1 == 1.0 == True). Without this, a candidate could
    return floats everywhere and still look correct.
    """
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        if len(a) != len(b):
            return False
        for k, v in a.items():
            if k not in b or not deep_equal(v, b[k]):
                return False
        return True
    if isinstance(a, list):
        return len(a) == len(b) and all(deep_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, float):
        if math.isnan(a) and math.isnan(b):
            return True
        return a == b or math.isclose(a, b, rel_tol=1e-15, abs_tol=0.0)
    return a == b


# Malformed documents the parser MUST reject. Guards against a candidate
# that "optimizes" by skipping validation entirely.
MALFORMED = [
    '{"a": 1,}',
    '{"a" 1}',
    "[1, 2",
    '{"a": }',
    '"unterminated',
    "[1, 2] extra",
    "{'a': 1}",
    "tru",
    "[01]" if False else "[--1]",
    '{"a": 1} {"b": 2}',
    "",
    "   ",
    '{"a": "\\q"}',
]


def check_correctness(module):
    """Returns a list of failure strings; empty means the gate passed."""
    failures = []

    for name in ("correctness", "edge_cases", "bench"):
        path = CORPUS / f"{name}.json"
        text = path.read_text(encoding="utf-8")
        expected = json.loads(text)
        try:
            actual = module.parse(text)
        except Exception as exc:
            failures.append(f"{name}: raised {type(exc).__name__}: {exc}")
            continue
        if not deep_equal(actual, expected):
            failures.append(f"{name}: output does not match json.loads")

    for bad in MALFORMED:
        try:
            module.parse(bad)
        except Exception:
            pass  # correct: rejected
        else:
            failures.append(f"malformed input accepted: {bad!r}")

    return failures


def benchmark(module, text):
    for _ in range(WARMUP_ITERS):
        module.parse(text)

    best = float("inf")
    for _ in range(TIMED_ITERS):
        start = time.perf_counter()
        module.parse(text)
        elapsed = time.perf_counter() - start
        best = min(best, elapsed)
    return best


def main():
    solution_path = HERE / "optimize.py"
    delegation = check_no_delegation(solution_path)
    if delegation:
        print("DELEGATION CHECK FAILED -- solution must parse JSON itself:", file=sys.stderr)
        for d in delegation:
            print(f"  - {d}", file=sys.stderr)
        print("throughput: 0.0")
        return

    try:
        module = load_solution()
    except Exception as exc:
        print(f"FAILED to load solution: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("throughput: 0.0")
        return

    failures = check_correctness(module)
    if failures:
        print("CORRECTNESS GATE FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        print("throughput: 0.0")
        return

    text = (CORPUS / "bench.json").read_text(encoding="utf-8")
    nbytes = len(text.encode("utf-8"))
    best = benchmark(module, text)
    mb_per_s = (nbytes / (1024 * 1024)) / best

    print(f"correctness: PASS ({nbytes / 1024:,.0f} KB corpus)")
    print(f"best time: {best * 1000:.1f} ms")
    print(f"throughput: {mb_per_s:.4f}")


if __name__ == "__main__":
    main()

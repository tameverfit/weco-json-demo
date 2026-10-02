"""Held-out evaluation for a parser candidate.

Run this BY HAND after a Weco run. It is deliberately not wired into
evaluate.sh: the whole point of corpus_test/ is that the optimizer never
saw it, so nothing here may feed back into the search.

    python evaluate_test.py [candidate.py]

Default candidate: the newest .runs/*/best/files/optimize.py.

corpus_test/test.json is a single file whose top-level array holds five
sections shaped differently from bench.json (pretty-printed, raw unicode,
escape-heavy strings, deep nesting, unusual number spellings). It gets a
correctness gate against json.loads (same deep_equal as the main
evaluator), then throughput for baseline.py and the candidate, and the
ratio between them. bench.json is printed alongside as the
in-distribution reference row.
"""
import json
import sys
import time
from pathlib import Path

from evaluate import (
    HERE,
    CORPUS,
    TIMED_ITERS,
    WARMUP_ITERS,
    check_no_delegation,
    deep_equal,
)
import importlib.util

TEST_FILE = HERE.parent.parent / "corpus_test" / "test.json"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "parse"):
        raise AttributeError(f"{path} must export parse(text)")
    return module


def default_candidate():
    runs = sorted((HERE / ".runs").glob("*/best/files/optimize.py"),
                  key=lambda p: p.stat().st_mtime)
    if not runs:
        sys.exit("no .runs/*/best/files/optimize.py found; pass a candidate path")
    return runs[-1]


def time_parse(module, text):
    for _ in range(WARMUP_ITERS):
        module.parse(text)
    best = float("inf")
    for _ in range(TIMED_ITERS):
        t0 = time.perf_counter()
        module.parse(text)
        best = min(best, time.perf_counter() - t0)
    return best


def mb_per_s(text, seconds):
    return (len(text.encode("utf-8")) / (1024 * 1024)) / seconds


def gate(module, text):
    """Return None if the candidate matches json.loads, else a reason."""
    expected = json.loads(text)
    try:
        actual = module.parse(text)
    except Exception as exc:
        return f"raised {type(exc).__name__}: {exc}"
    if not deep_equal(actual, expected):
        return "output does not match json.loads"
    return None


def main():
    cand_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_candidate()
    base_path = HERE / "baseline.py"

    delegation = check_no_delegation(cand_path)
    if delegation:
        print("DELEGATION CHECK FAILED:", *delegation, sep="\n  - ")
        sys.exit(1)

    baseline = load_module(base_path, "baseline_parser")
    candidate = load_module(cand_path, "candidate_parser")
    print(f"candidate: {cand_path}")
    print(f"baseline:  {base_path}\n")

    if not TEST_FILE.exists():
        sys.exit(f"{TEST_FILE} missing; run make_test_corpus.py first")

    rows = [("bench (in-dist)", CORPUS / "bench.json"), ("test (held-out)", TEST_FILE)]
    results = {}
    print(f"{'corpus':<18}{'size':>9}{'gate':>7}{'base MB/s':>11}{'cand MB/s':>11}{'speedup':>9}")
    for name, path in rows:
        text = path.read_text(encoding="utf-8")
        size = f"{path.stat().st_size / 1024:,.0f}K"
        reason = gate(candidate, text)
        if reason:
            print(f"{name:<18}{size:>9}{'FAIL':>7}  {reason}")
            continue
        base = mb_per_s(text, time_parse(baseline, text))
        cand = mb_per_s(text, time_parse(candidate, text))
        results[name] = cand / base
        print(f"{name:<18}{size:>9}{'PASS':>7}{base:>11.2f}{cand:>11.2f}{results[name]:>8.2f}x")

    held_out = results.get(rows[1][0])
    if held_out is None:
        print("\nheld-out: FAIL (correctness gate)")
        sys.exit(1)
    print(f"\nheld-out speedup: {held_out:.2f}x")


if __name__ == "__main__":
    main()

# Weco demo: JSON parser throughput

A traditional-software optimization demo. No LLMs, no ML — a hand-rolled
recursive-descent JSON parser that is correct but slow, and a benchmark
that Weco optimizes against.

## Baseline

| | |
|---|---|
| Throughput | **12.33 MB/s** (± 0.06, 0.5% over 5 runs) |
| Parse time | ~150 ms for a 1.96 MB corpus |
| Reference | stdlib `json` does the same corpus at ~183 MB/s |

The stdlib number is the practical ceiling (it is C). A pure-Python
parser will not reach it — that gap is the headroom Weco explores.

## Layout

```
parser.py                  the baseline parser (reference copy)
make_corpus.py             deterministic corpus generator (seeded)
corpus/
  bench.json               1.96 MB — the benchmark input
  correctness.json         246 KB  — different seed, correctness only
  edge_cases.json          3.4 KB  — hand-written nasty cases
.weco/json-parser-throughput/
  optimize.py              the file Weco rewrites
  baseline.py              frozen original, for diffing
  evaluate.py              benchmark + correctness gate
  evaluate.sh              wrapper (uses the local .venv)
  .venv/                   isolated env
```

## The contract

`optimize.py` must export `parse(text: str) -> object`, returning what
`json.loads` returns and raising on invalid input. Weco may restructure
everything behind that signature.

## How the gate works

This is the part that makes the demo honest. Throughput is only reported
if the candidate passes three independent checks — otherwise it scores
`throughput: 0.0` and cannot win.

1. **External oracle.** Output is compared to `json.loads` on all three
   corpora, not to the solution's own output. Self-referential checks
   cannot detect regressions.
2. **Strict types.** `deep_equal` rejects `1` vs `1.0` vs `True`, which
   plain `==` in Python treats as equal. Stops a candidate from returning
   floats everywhere.
3. **No delegation.** An AST scan rejects `import json` and friends
   (`from json import loads`, `importlib.import_module("json")`,
   `__import__`, `ast.literal_eval`, and the third-party parsers). Without
   this, the optimizer wins in one step by calling the C parser — a 14x
   "improvement" that demonstrates nothing.
4. **Malformed input.** 13 invalid documents must still raise. Stops a
   candidate from getting fast by skipping validation.

All four were verified by writing adversarial solutions and confirming
each scores 0.0.

## Setup

`evaluate.sh` runs the evaluator with a local `.venv`, which is not
checked in. Create it once after cloning:

```bash
cd .weco/json-parser-throughput
python3 -m venv .venv
bash evaluate.sh        # should print: throughput: ~12
```

No packages to install — the evaluator only uses the standard library.

## Run it

```bash
cd .weco/json-parser-throughput   # or pass absolute paths

weco run \
  --source optimize.py \
  --eval-command "bash evaluate.sh" \
  --metric throughput \
  --goal maximize \
  --steps 10 \
  --output plain
```

## Reset between demos

```bash
cp .weco/json-parser-throughput/baseline.py \
   .weco/json-parser-throughput/optimize.py
```

## Regenerate the corpus

Seeded, so output is identical across machines:

```bash
python3 make_corpus.py
```

## What to expect

Likely directions: hoisting attribute lookups out of the scan loop,
replacing char-by-char string building with slice-and-join, `str.find`
to jump to the next delimiter, dispatch tables over if-chains, and
flattening the scanner class into closures. The interesting demo
question is which combination wins — and that is genuinely hard to
call in advance, which is the argument for running the search rather
than hand-optimizing.

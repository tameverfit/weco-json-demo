# Weco practice: make a JSON parser faster

`optimize.py` is a JSON parser written by hand in pure Python. It is
correct but slow (about 12 MB/s). In this exercise you let Weco rewrite
it, step by step, to make it faster without breaking it.

One earlier 10-step run reached about 25 MB/s (2x faster). Your result
will differ: that is the point of the exercise.

## What you need

- Python 3.10 or newer
- The Weco CLI, logged in with your own account:

  ```bash
  pipx install weco
  weco login
  ```

  No `pipx`? Install it with `brew install pipx`. A plain
  `pip install weco` also works, but only inside a virtual environment:
  Homebrew's Python refuses system-wide installs.

## Step 1: Set up

```bash
git clone https://github.com/tameverfit/weco-json-demo.git
cd weco-json-demo/.weco/json-parser-throughput
python3 -m venv .venv
```

There is nothing to install into the venv. All commands below are run
from this folder.

## Step 2: Measure the baseline

```bash
bash evaluate.sh
```

You should see something like:

```
correctness: PASS (1,965 KB corpus)
best time: 154.2 ms
throughput: 12.4402
```

`throughput` is the number Weco will try to raise.

## Step 3: Run Weco

Pick one of the two ways. A 10-step run takes about 15 minutes and uses
Weco credits.

### Option A: run the command yourself

```bash
weco run \
  --source optimize.py \
  --eval-command "bash evaluate.sh" \
  --metric throughput \
  --goal maximize \
  --steps 10 \
  --output plain
```

### Option B: ask Claude Code or Cursor to do it

Install the Weco skill into your agent once:

```bash
weco setup claude-code     # or: weco setup cursor
```

Open this repo in the agent and paste:

```text
Use Weco to make the JSON parser in this repo faster.

Work in .weco/json-parser-throughput/:
- File to optimize: optimize.py. Do not edit any other file.
- Eval command: bash evaluate.sh
- Metric: throughput (MB/s, printed as "throughput: <number>"), maximize.
- Steps: 10

Before starting, run `bash evaluate.sh` once and tell me the baseline
throughput. If it fails because .venv is missing, create it with
`python3 -m venv .venv` in that directory and try again.

Rules:
- optimize.py must keep exporting parse(text) with the same behaviour as
  json.loads. The evaluator scores 0.0 for any candidate that returns a
  different result, accepts malformed JSON, or imports a JSON library.
  Do not edit evaluate.py to get around this.
- Do not hand-optimize optimize.py yourself. Let Weco do the search.

When the run finishes, do not apply the result to optimize.py yet.
Report back with:
1. Baseline throughput and best throughput, and which step was best.
2. A table of every step and its throughput, marking any step that
   scored 0.0 and why it failed.
3. A short summary of what the best version changed compared to
   baseline.py.
```

## Step 4: Look at the result

Weco saves every step under `.runs/<run-id>/`:

```
.runs/<run-id>/steps/0/files/optimize.py    step 0 (the baseline)
.runs/<run-id>/steps/1/files/optimize.py    step 1
...
.runs/<run-id>/best/files/optimize.py       the fastest version that passed
```

See what changed:

```bash
diff baseline.py .runs/*/best/files/optimize.py
```

Try the best version yourself:

```bash
cp .runs/*/best/files/optimize.py optimize.py
bash evaluate.sh
```

## Step 5: Reset before the next run

```bash
cp baseline.py optimize.py
```

## How scoring works

A candidate only gets a throughput score if it passes all four checks.
If it fails any of them it scores `throughput: 0.0`.

1. **It parses by itself.** `import json`, `orjson`, `eval`, and similar
   shortcuts are rejected.
2. **Same output as `json.loads`** on all three files in `corpus/`.
3. **Same types.** `1`, `1.0` and `True` are treated as different, even
   though Python's `==` says they are equal.
4. **Bad JSON is still rejected.** 13 invalid documents must raise an
   error.

Expect one or two steps in a run to score 0.0. That is the gate doing
its job, not a problem with your setup.

For reference, Python's built-in `json` (written in C) parses the same
file at about 183 MB/s. A pure-Python parser will not reach that.

## Files

```
parser.py                    the original parser, for reading
corpus/
  bench.json                 1.96 MB  speed is measured on this file
  correctness.json           246 KB   correctness check only
  edge_cases.json            3.4 KB   hand-written hard cases
.weco/json-parser-throughput/
  optimize.py                the file Weco rewrites
  baseline.py                untouched copy, for diff and reset
  evaluate.py                the benchmark and the four checks
  evaluate.sh                runs evaluate.py with the local .venv
```

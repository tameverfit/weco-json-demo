"""Generate a HELD-OUT test corpus for the parser benchmark.

`corpus/` is what the Weco evaluator sees on every step, so the optimizer
is free to specialise for its distribution. Nothing in `corpus_test/` is
read by `evaluate.py`; it exists so that, after a run finishes, we can ask
two questions the optimizer never got feedback on:

    1. Does the winning candidate still parse correctly on data shaped
       differently from bench.json?
    2. Does its speedup over the baseline survive on that data, or was it
       tuned to the exact shape of bench.json?

Each slice deliberately pushes on one thing bench.json under-samples.
"""
import json
import random
import string
from pathlib import Path

from make_corpus import NASTY_STRINGS, WORDS, build, rand_number, rand_string

CORPUS_TEST = Path(__file__).parent / "corpus_test"
SEED = 20260930
TARGET_BYTES = 500_000

# Raw (unescaped) non-ASCII text. bench.json is written with the default
# ensure_ascii=True, so every non-ASCII character there arrives as \uXXXX.
RAW_UNICODE = [
    "Xin chào, đây là một chuỗi tiếng Việt có dấu.",
    "Hà Nội – Đà Nẵng – Thành phố Hồ Chí Minh",
    "日本語のテキストと中文文本",
    "Ελληνικά και кириллица",
    "emoji 🚀🔥😀🎉 và cờ 🇻🇳",
    "café naïve façade résumé",
    "ﬁ ligature, ‘curly’ “quotes”, em—dash",
]


def _rand_ascii(rng, lo, hi):
    n = rng.randint(lo, hi)
    return "".join(rng.choice(string.ascii_letters + string.digits + " _-") for _ in range(n))


# --- slices -----------------------------------------------------------------


def slice_pretty(rng):
    """Same generator as bench, but pretty-printed."""
    return json.dumps(build(TARGET_BYTES, rng.randint(0, 2**31)), indent=2)


def slice_unicode_raw(rng):
    def rand_text():
        if rng.random() < 0.6:
            return rng.choice(RAW_UNICODE) + " " + _rand_ascii(rng, 0, 12)
        return rand_string(rng)

    records = []
    size = 0
    while size < TARGET_BYTES:
        rec = {
            "tiêu_đề": rand_text(),
            "mô_tả": " ".join(rand_text() for _ in range(rng.randint(1, 4))),
            "tags": [rand_text() for _ in range(rng.randint(0, 4))],
            "điểm": rand_number(rng),
            "meta": {rng.choice(WORDS): rand_text() for _ in range(rng.randint(0, 3))},
        }
        records.append(rec)
        size += len(json.dumps(rec, ensure_ascii=False))
    return json.dumps(records, ensure_ascii=False)


def slice_escape_heavy(rng):
    """Long strings where nearly every few characters is an escape."""
    pieces = [
        '"', "\\", "\n", "\t", "\r", "\b", "\f", "/",
        "\u0001", "\u001f",           # control chars -> \u00XX
        "\U0001f600", "\U0001f680",   # astral -> surrogate pairs (😀)
        "é", "中",           # BMP non-ASCII -> \uXXXX under ensure_ascii
    ]

    def long_escaped():
        n = rng.randint(200, 2000)
        out = []
        for _ in range(n):
            if rng.random() < 0.4:
                out.append(rng.choice(pieces))
            else:
                out.append(rng.choice(string.ascii_letters))
        return "".join(out)

    records = []
    size = 0
    while size < TARGET_BYTES:
        rec = {
            "body": long_escaped(),
            "short": rng.choice(NASTY_STRINGS),
            "list": [long_escaped() for _ in range(rng.randint(0, 2))],
        }
        records.append(rec)
        size += len(json.dumps(rec))
    return json.dumps(records)


def slice_deep(rng):
    """Deeply nested, small containers."""

    def nest(depth):
        if depth == 0:
            return rand_number(rng) if rng.random() < 0.5 else _rand_ascii(rng, 1, 8)
        if rng.random() < 0.5:
            return [nest(depth - 1)] + ([rand_number(rng)] if rng.random() < 0.3 else [])
        key = f"{rng.choice(WORDS)}_{depth}"
        obj = {key: nest(depth - 1)}
        if rng.random() < 0.3:
            obj["leaf"] = rng.choice([True, False, None])
        return obj

    records = []
    size = 0
    while size < TARGET_BYTES:
        rec = nest(rng.randint(40, 60))
        records.append(rec)
        size += len(json.dumps(rec))
    return json.dumps(records)


def slice_numeric(rng):
    """Big arrays of numbers, in spellings json.dumps never emits.

    Written by hand so we can include `1E5`, `-0`, `1e+05`, and other
    valid-but-unusual forms. The result must still round-trip through
    json.loads (that is asserted in main()).
    """

    def num_text():
        r = rng.random()
        if r < 0.30:
            return str(rng.randint(-10**6, 10**6))
        if r < 0.40:
            return str(rng.randint(10**18, 10**30))          # beyond int64
        if r < 0.55:
            return f"{rng.uniform(-1e4, 1e4):.{rng.randint(1, 12)}f}"
        if r < 0.70:
            mant = f"{rng.uniform(-9, 9):.4f}"
            exp = rng.randint(-20, 20)
            e = rng.choice(["e", "E"])
            sign = rng.choice(["", "+"]) if exp >= 0 else ""
            return f"{mant}{e}{sign}{exp}"
        if r < 0.80:
            return rng.choice(["0", "-0", "0.0", "-0.0", "1E5", "1e5", "5E-3", "0.000001"])
        if r < 0.90:
            return f"{rng.randint(0, 9)}"                     # single digits
        return f"{rng.randint(1, 9)}e{rng.randint(300, 308)}"  # near float max

    arrays = []
    size = 0
    while size < TARGET_BYTES:
        n = rng.randint(50, 400)
        arr = "[" + ", ".join(num_text() for _ in range(n)) + "]"
        arrays.append(arr)
        size += len(arr) + 2
    return "[" + ",\n".join(arrays) + "]"


SLICES = {
    "pretty": slice_pretty,
    "unicode_raw": slice_unicode_raw,
    "escape_heavy": slice_escape_heavy,
    "deep": slice_deep,
    "numeric": slice_numeric,
}


def main():
    CORPUS_TEST.mkdir(exist_ok=True)
    parts = []
    for i, (name, fn) in enumerate(SLICES.items()):
        rng = random.Random(SEED + i)
        text = fn(rng)
        json.loads(text)  # every slice must be valid JSON for the oracle
        parts.append(text)
        print(f"  {name}: {len(text.encode('utf-8')) / 1024:,.1f} KB")

    # One file, one top-level array. Concatenated as text (not re-dumped) so
    # each section keeps its own formatting: indent, raw unicode, 1E5, etc.
    combined = "[\n" + ",\n".join(parts) + "\n]"
    json.loads(combined)
    path = CORPUS_TEST / "test.json"
    path.write_text(combined, encoding="utf-8")
    print(f"{path.name}: {path.stat().st_size / 1024:,.1f} KB")


if __name__ == "__main__":
    main()

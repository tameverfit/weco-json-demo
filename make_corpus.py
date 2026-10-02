"""Generate a deterministic JSON corpus for the parser benchmark.

Deliberately includes the cases that make a hand-rolled parser hard to get
right: escape sequences, unicode escapes, floats with exponents, deep
nesting, empty containers, and the literals null/true/false.
"""
import json
import random
import string
from pathlib import Path

CORPUS = Path(__file__).parent / "corpus"
SEED = 20260924

WORDS = [
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
    "user", "event", "payload", "session", "metric", "trace", "span",
]

# Strings that exercise the escape paths of a scanner.
NASTY_STRINGS = [
    'quote: "inner"',
    "backslash: \\ and \\\\",
    "newline:\nand tab:\t",
    "unicode escape: é中文",
    "emoji: \U0001f600",
    "control: \x01\x02",
    "solidus: /",
    "carriage:\r",
    "",
    " " * 40,
]


def rand_string(rng):
    if rng.random() < 0.25:
        return rng.choice(NASTY_STRINGS)
    n = rng.randint(1, 24)
    return "".join(rng.choice(string.ascii_letters + string.digits + " _-") for _ in range(n))


def rand_number(rng):
    r = rng.random()
    if r < 0.4:
        return rng.randint(-1_000_000, 1_000_000)
    if r < 0.6:
        return rng.randint(0, 10) 
    if r < 0.85:
        return round(rng.uniform(-1e4, 1e4), rng.randint(1, 10))
    return float(f"{rng.uniform(-9, 9):.6f}e{rng.randint(-12, 12)}")


def rand_value(rng, depth=0):
    if depth > 5:
        r = rng.random()
        if r < 0.45:
            return rand_string(rng)
        if r < 0.9:
            return rand_number(rng)
        return rng.choice([True, False, None])

    r = rng.random()
    if r < 0.24:
        return rand_string(rng)
    if r < 0.46:
        return rand_number(rng)
    if r < 0.56:
        return rng.choice([True, False, None])
    if r < 0.78:
        n = rng.randint(0, 6)
        return [rand_value(rng, depth + 1) for _ in range(n)]
    n = rng.randint(0, 7)
    return {
        f"{rng.choice(WORDS)}_{rng.randint(0, 999)}": rand_value(rng, depth + 1)
        for _ in range(n)
    }


def build(target_bytes, seed):
    rng = random.Random(seed)
    records = []
    size = 0
    while size < target_bytes:
        rec = {
            "id": rng.randint(1, 10**9),
            "name": rand_string(rng),
            "active": rng.choice([True, False]),
            "score": rand_number(rng),
            "tags": [rand_string(rng) for _ in range(rng.randint(0, 5))],
            "meta": rand_value(rng, 2),
            "nullable": None if rng.random() < 0.3 else rand_string(rng),
        }
        records.append(rec)
        size += len(json.dumps(rec))
    return records


def main():
    CORPUS.mkdir(exist_ok=True)

    # Main benchmark corpus: ~2 MB of realistic records.
    bench = build(2_000_000, SEED)
    bench_path = CORPUS / "bench.json"
    bench_path.write_text(json.dumps(bench), encoding="utf-8")

    # Smaller, denser correctness corpus: same generator, different seed.
    correct = build(250_000, SEED + 1)
    correct_path = CORPUS / "correctness.json"
    correct_path.write_text(json.dumps(correct), encoding="utf-8")

    # Hand-written edge cases that random generation may under-sample.
    edge = [
        {}, [], "", 0, -0.0, True, False, None,
        {"a": {}}, {"a": []}, [[]], [{}],
        {"deep": {"deep": {"deep": {"deep": {"deep": {"deep": 1}}}}}},
        "\u0000-ish: \\u0000 literal text",
        [1e308, -1e308, 1e-308, 0.1, 1 / 3],
        {"escapes": '"\\/\b\f\n\r\t'},
        {"unicode": "é中文\U0001f600"},
        [0, -0, 1, -1, 123456789012345678901234567890],
        {"k" * 200: "v" * 500},
        list(range(500)),
    ]
    edge_path = CORPUS / "edge_cases.json"
    edge_path.write_text(json.dumps(edge), encoding="utf-8")

    for p in (bench_path, correct_path, edge_path):
        kb = p.stat().st_size / 1024
        print(f"{p.name}: {kb:,.1f} KB")


if __name__ == "__main__":
    main()

"""A hand-rolled JSON parser.

Public API (the contract the optimizer must preserve):

    parse(text: str) -> object

Returns the same Python object that `json.loads` would return for valid
input, and raises `JSONParseError` for invalid input.

This is a straightforward recursive-descent scanner. It is correct but
slow: it advances one character at a time and builds strings by repeated
concatenation.
"""


class JSONParseError(ValueError):
    """Raised when the input is not valid JSON."""


WHITESPACE = " \t\n\r"

ESCAPE_MAP = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}


class _Scanner:
    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.length = len(text)

    def error(self, message):
        raise JSONParseError(f"{message} at position {self.pos}")

    def peek(self):
        if self.pos >= self.length:
            return None
        return self.text[self.pos]

    def skip_whitespace(self):
        while self.pos < self.length and self.text[self.pos] in WHITESPACE:
            self.pos += 1

    def parse_value(self):
        self.skip_whitespace()
        ch = self.peek()
        if ch is None:
            self.error("unexpected end of input")
        if ch == "{":
            return self.parse_object()
        if ch == "[":
            return self.parse_array()
        if ch == '"':
            return self.parse_string()
        if ch == "t":
            return self.parse_literal("true", True)
        if ch == "f":
            return self.parse_literal("false", False)
        if ch == "n":
            return self.parse_literal("null", None)
        if ch == "-" or ch.isdigit():
            return self.parse_number()
        self.error(f"unexpected character {ch!r}")

    def parse_literal(self, word, value):
        for expected in word:
            if self.pos >= self.length or self.text[self.pos] != expected:
                self.error(f"invalid literal, expected {word!r}")
            self.pos += 1
        return value

    def parse_object(self):
        self.pos += 1  # consume '{'
        result = {}
        self.skip_whitespace()
        if self.peek() == "}":
            self.pos += 1
            return result

        while True:
            self.skip_whitespace()
            if self.peek() != '"':
                self.error("expected string key")
            key = self.parse_string()
            self.skip_whitespace()
            if self.peek() != ":":
                self.error("expected ':'")
            self.pos += 1
            value = self.parse_value()
            result[key] = value
            self.skip_whitespace()
            ch = self.peek()
            if ch == ",":
                self.pos += 1
                continue
            if ch == "}":
                self.pos += 1
                return result
            self.error("expected ',' or '}'")

    def parse_array(self):
        self.pos += 1  # consume '['
        result = []
        self.skip_whitespace()
        if self.peek() == "]":
            self.pos += 1
            return result

        while True:
            value = self.parse_value()
            result.append(value)
            self.skip_whitespace()
            ch = self.peek()
            if ch == ",":
                self.pos += 1
                continue
            if ch == "]":
                self.pos += 1
                return result
            self.error("expected ',' or ']'")

    def parse_string(self):
        self.pos += 1  # consume opening quote
        out = ""
        while True:
            if self.pos >= self.length:
                self.error("unterminated string")
            ch = self.text[self.pos]
            if ch == '"':
                self.pos += 1
                return out
            if ch == "\\":
                self.pos += 1
                if self.pos >= self.length:
                    self.error("unterminated escape")
                esc = self.text[self.pos]
                if esc in ESCAPE_MAP:
                    out = out + ESCAPE_MAP[esc]
                    self.pos += 1
                elif esc == "u":
                    hex_digits = self.text[self.pos + 1 : self.pos + 5]
                    if len(hex_digits) != 4:
                        self.error("truncated \\u escape")
                    try:
                        code = int(hex_digits, 16)
                    except ValueError:
                        self.error("invalid \\u escape")
                    self.pos += 5
                    # Handle surrogate pairs.
                    if 0xD800 <= code <= 0xDBFF and self.text[self.pos : self.pos + 2] == "\\u":
                        low_digits = self.text[self.pos + 2 : self.pos + 6]
                        try:
                            low = int(low_digits, 16)
                        except ValueError:
                            low = None
                        if low is not None and 0xDC00 <= low <= 0xDFFF:
                            code = 0x10000 + (code - 0xD800) * 0x400 + (low - 0xDC00)
                            self.pos += 6
                    out = out + chr(code)
                else:
                    self.error(f"invalid escape {esc!r}")
                continue
            out = out + ch
            self.pos += 1

    def parse_number(self):
        start = self.pos
        if self.peek() == "-":
            self.pos += 1
        while self.pos < self.length and self.text[self.pos].isdigit():
            self.pos += 1

        is_float = False
        if self.pos < self.length and self.text[self.pos] == ".":
            is_float = True
            self.pos += 1
            while self.pos < self.length and self.text[self.pos].isdigit():
                self.pos += 1

        if self.pos < self.length and self.text[self.pos] in "eE":
            is_float = True
            self.pos += 1
            if self.pos < self.length and self.text[self.pos] in "+-":
                self.pos += 1
            while self.pos < self.length and self.text[self.pos].isdigit():
                self.pos += 1

        raw = self.text[start : self.pos]
        if not raw or raw in ("-",):
            self.error("invalid number")
        try:
            return float(raw) if is_float else int(raw)
        except ValueError:
            self.error(f"invalid number {raw!r}")


def parse(text):
    """Parse a JSON document and return the corresponding Python object."""
    scanner = _Scanner(text)
    value = scanner.parse_value()
    scanner.skip_whitespace()
    if scanner.pos != scanner.length:
        scanner.error("trailing data after top-level value")
    return value

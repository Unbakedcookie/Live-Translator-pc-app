"""T012 — no colour or size literals outside livetranslator/theme/ (spec §6.5).

Scans string literals (including f-string parts) with the tokenizer, so comments such as
"# T012" never count. Also flags QColor(...) built from numbers.
"""

import io
import re
import tokenize
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "livetranslator"
THEME = PACKAGE / "theme"

STYLE_IN_STRING = re.compile(
    r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?\b"  # #RRGGBB / #RRGGBBAA
    r"|#[0-9A-Fa-f]{3}\b(?![\w-])"  # #RGB
    r"|\brgba?\s*\("  # rgb( / rgba(
    r"|\b\d+(?:\.\d+)?\s*(?:px|pt)\b"  # 12px / 10pt
)
STRING_TOKENS = {tokenize.STRING, tokenize.FSTRING_MIDDLE}


def style_violations(source: str) -> list[str]:
    """Return 'line: text' for every hardcoded style value in `source`."""
    found: list[str] = []
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    for i, tok in enumerate(tokens):
        if tok.type in STRING_TOKENS and STYLE_IN_STRING.search(tok.string):
            found.append(f"{tok.start[0]}: {tok.string}")
        if (
            tok.type == tokenize.NAME
            and tok.string == "QColor"
            and i + 2 < len(tokens)
            and tokens[i + 1].string == "("
            and tokens[i + 2].type in (tokenize.NUMBER, tokenize.STRING)
        ):
            found.append(f"{tok.start[0]}: QColor({tokens[i + 2].string}...)")
    return found


def test_checker_catches_bad_code():
    bad = (
        'label.setStyleSheet("color: #ff0000")\n'
        'w.setStyleSheet(f"padding: {x}px; margin: 4px")\n'
        "c = QColor(255, 0, 0)\n"
        'c2 = QColor("#abc")\n'
        's = "background: rgba(0,0,0,0.5)"\n'
        'f = "font-size: 10pt"\n'
    )
    assert [v.split(":")[0] for v in style_violations(bad)] == ["1", "2", "3", "4", "4", "5", "6"]


def test_checker_ignores_comments_and_token_use():
    good = (
        "# T012 colours come from #tokens, e.g. #FFFFFF in a comment is fine\n"
        "color = palette.accent\n"
        "c = QColor(palette.bg)\n"
        'issue = "see issue #12 and #1234567"\n'
        'name = "push-pin-fill"\n'
    )
    assert style_violations(good) == []


def test_package_has_no_hardcoded_style_outside_theme():
    problems = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if THEME in path.parents:
            continue
        for violation in style_violations(path.read_text(encoding="utf-8")):
            problems.append(f"{path.relative_to(PACKAGE.parent)}:{violation}")
    assert problems == []

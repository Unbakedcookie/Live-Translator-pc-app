# ruff: noqa: RUF001  (real foreign-language sentences on purpose)
"""T083 — screen-text language detection on fixed sentences (Tier A)."""

import pytest

from livetranslator.services.langdetect import detect, latin_scores, script_language

SENTENCES = [
    ("Wait for me at the gate, I have the key.", "en"),
    ("Espera en la puerta, yo tengo la llave.", "es"),
    ("Attends-moi à la porte, je pense que c'est fermé.", "fr"),
    ("Warte am Tor auf mich, ich habe den Schlüssel.", "de"),
    ("門で待ってて、鍵を持ってるよ。", "ja"),
    ("문 앞에서 기다려, 열쇠는 내가 가지고 있어.", "ko"),
    ("在门口等我，我有钥匙。", "zh"),
    ("Подожди меня у ворот, ключ у меня.", "ru"),
]


@pytest.mark.parametrize(("text", "expected"), SENTENCES)
def test_fixed_sentences(text: str, expected: str):
    assert detect(text) == expected


def test_short_or_ambiguous_text_falls_back_to_the_hint():
    assert detect("GG", hint="en") == "en"
    assert detect("ok ok", hint="es") == "es"
    assert detect("Paris London Berlin Madrid", hint="fr") == "fr"  # no function words
    assert detect("", hint=None) is None


def test_candidates_limit_the_answer():
    spanish = "Espera en la puerta, yo tengo la llave."
    assert detect(spanish, candidates={"en", "es"}) == "es"
    assert detect(spanish, candidates={"en", "de"}, hint="en") == "en"  # es not installed
    assert detect("門で待ってて", candidates={"en"}, hint="en") == "en"


def test_script_rules():
    assert script_language("漢字だけ") == "ja"  # kana wins over Han
    assert script_language("汉字") == "zh"
    assert script_language("Привіт, як справи?") == "uk"
    assert script_language("hello") is None


def test_own_letters_count():
    scores = latin_scores("Straße über Köln")
    assert scores["de"] == 3  # ß, ü, ö


def test_a_short_foreign_tag_does_not_decide_the_language():
    """Live screen test 2026-10-18: a Chinese team tag before an English message."""
    assert detect("[队伍] Mika: wait for me at the gate") == "en"
    assert detect("[队伍]小明:兄弟们快上车，我们去打BOSS了") == "zh"  # some English, mostly Chinese
    assert detect("[Party] 小明：等等我") == "zh"  # Chinese message with an English tag

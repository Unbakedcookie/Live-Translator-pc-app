"""Settings "Others speak" (2026-10-20): which language a line is in (hand-worked)."""

from livetranslator.services.asr.language_choice import (
    PREFER_RATIO,
    SUPPORTED,
    choose,
    others_candidates,
)


def test_candidates_for_each_setting():
    assert others_candidates((), True) == (SUPPORTED, ())  # detect any of ours
    assert others_candidates(("zh",), False) == (("zh",), ())  # only Chinese
    languages, preferred = others_candidates(("zh", "en"), True)
    assert preferred == ("zh", "en") and languages[:2] == ("zh", "en")
    assert set(languages) == set(SUPPORTED) and len(languages) == len(SUPPORTED)
    assert "is" not in SUPPORTED and len(SUPPORTED) == 47  # Icelandic: we can't translate it


def test_choose_prefers_listed_languages_when_plausible():
    assert PREFER_RATIO == 0.1
    scores = {"en": 0.70, "zh": 0.08, "ja": 0.22}
    assert choose(scores, ()) == "en"  # no preference: the top one
    assert choose(scores, ("zh",)) == "zh"  # 0.08 >= 0.1 * 0.70
    assert choose({"en": 0.95, "zh": 0.05}, ("zh",)) == "en"  # 0.05 < 0.095
    assert choose(scores, ("ja", "zh")) == "ja"  # the stronger listed one
    assert choose({"zh": 0.6, "en": 0.4}, ("zh",)) == "zh"  # listed and on top

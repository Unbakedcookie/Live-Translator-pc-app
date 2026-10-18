# ruff: noqa: RUF001  (real Chinese punctuation on purpose)
"""Mandarin follow-up — one Chinese script (OpenCC)."""

from livetranslator.services.asr.chinese import is_chinese, to_script


def test_conversion_both_ways_and_other_text_untouched():
    assert (
        to_script("門口等我，我有鑰匙。這個遊戲很好玩", "simplified")
        == "门口等我，我有钥匙。这个游戏很好玩"
    )
    assert to_script("这个游戏很好玩", "traditional") == "這個遊戲很好玩"
    assert to_script("GG 打得好 OK", "simplified") == "GG 打得好 OK"
    assert to_script("", "simplified") == ""


def test_is_chinese():
    assert is_chinese("zh") and is_chinese("zh-TW") and is_chinese("ZH")
    assert not is_chinese("ja") and not is_chinese(None) and not is_chinese("")

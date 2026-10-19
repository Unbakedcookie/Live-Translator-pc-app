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


LATIN_SENTENCES = {  # one game-chat line each, written for this test
    "sv": "Vänta på mig vid bron, jag har nästan slut på ammunition och vi måste gå nu.",
    "da": "Vent på mig ved broen, jeg er næsten løbet tør for ammunition og vi skal gå nu.",
    "no": "Vent på meg ved broen, jeg er nesten tom for ammunisjon og vi må gå nå.",
    "fi": "Odota minua sillalla, ammukset ovat melkein loppu ja meidän on mentävä nyt.",
    "pl": "Poczekaj na mnie przy moście, prawie skończyła mi się amunicja i musimy już iść.",
    "tr": "Beni köprüde bekle, cephanem neredeyse bitti ve şimdi gitmemiz gerek.",
    "id": "Tunggu aku di jembatan, amunisiku hampir habis dan kita harus pergi sekarang.",
    "vi": "Đợi tôi ở cây cầu, tôi sắp hết đạn rồi và chúng ta phải đi ngay bây giờ.",
    "cs": "Počkej na mě u mostu, skoro mi došla munice a musíme už jít.",
    "hu": "Várj meg a hídnál, majdnem elfogyott a lőszerem és most mennünk kell.",
    "ro": "Așteaptă-mă la pod, aproape am rămas fără muniție și trebuie să plecăm acum.",
    "tl": "Hintayin mo ako sa tulay, halos ubos na ang bala ko at kailangan na nating umalis.",
    "en": "Wait for me at the bridge, I am almost out of ammo and we have to go now.",
    "de": "Warte an der Brücke auf mich, mir geht fast die Munition aus und wir müssen jetzt los.",
    "nl": "Wacht op me bij de brug, ik heb bijna geen munitie meer en we moeten nu gaan.",
    "es": "Espérame en el puente, casi me quedo sin munición y tenemos que irnos ya.",
    "it": "Aspettami al ponte, sono quasi senza munizioni e dobbiamo andare adesso.",
    "pt": "Espera por mim na ponte, estou quase sem munição e temos de ir agora.",
    "fr": "Attends-moi au pont, je n'ai presque plus de munitions et on doit partir maintenant.",
}


def test_more_latin_languages_are_told_apart():
    """User report 2026-10-19: a Swedish screenshot wasn't translated (Swedish wasn't known,
    so it fell back to English and English -> English is passed through)."""
    wrong = {
        lang: detect(text, hint="en")
        for lang, text in LATIN_SENTENCES.items()
        if detect(text, hint="en") != lang
    }
    assert wrong == {}
    assert detect("Kan du hjälpa mig med uppdraget? Jag är nästan död.", hint="en") == "sv"

"""Language of a piece of screen text (T083; spec §5.6). Pure Python, no models.

Spec §5.6 named lingua-py, but its wheel is one 300 MB binary with every language compiled in
(measured 2026-10-18; it can't be trimmed), which is far too heavy for detecting a few lines of
game chat. This detector covers what OCR needs (D-033):

1. **Script**: kana → ja; hangul → ko; Han without kana → zh; Cyrillic → ru (uk if its
   letters appear); Arabic, Hebrew, Greek, Thai, Devanagari → ar, he, el, th, hi.
2. **Latin-script languages** (en, es, fr, de, it, pt, nl, …): count common short function
   words, plus a bonus for each language's own letters (ñ, ß, ç, ã, …).
3. **Short or ambiguous text** (fewer than `MIN_WORDS` words, or a tie): the caller's hint.

Results are limited to `candidates` (the installed language packs) when given.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection

MIN_WORDS = 3  # below this, Latin-script guesses are no better than the hint
MIN_SCORE = 2  # function-word hits needed to trust a Latin-script guess

_SCRIPTS: tuple[tuple[str, str], ...] = (
    # (language, a regex of characters that identify it), checked in order
    ("ja", "[぀-ヿㇰ-ㇿ]"),  # hiragana / katakana
    ("ko", "[가-힯ᄀ-ᇿ㄰-㆏]"),  # hangul
    ("zh", "[一-鿿㐀-䶿]"),  # Han (only reached when there's no kana)
    ("uk", "[ієїґІЄЇҐ]"),  # Ukrainian-only letters, before generic Cyrillic
    ("ru", "[Ѐ-ӿ]"),
    ("ar", "[؀-ۿ]"),
    ("he", "[֐-׿]"),
    ("el", "[Ͱ-Ͽ]"),
    ("th", "[฀-๿]"),
    ("hi", "[ऀ-ॿ]"),
)
_SCRIPT_RES = tuple((lang, re.compile(pattern)) for lang, pattern in _SCRIPTS)


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


# Common function words (articles, pronouns, prepositions, auxiliaries). Written for this
# project; a word shared by several languages counts for each of them.
_WORDS: dict[str, frozenset[str]] = {
    "en": _words(
        "the and is are was were you i to of in it that this for with on have has be "
        "not what we they he she do does at my your me so but just can will"
    ),
    "es": _words(
        "el la los las y es son que de en un una por para con no se lo me te mi tu "
        "pero muy está estoy qué cómo del al ya yo"
    ),
    "fr": _words(
        "le la les et est sont que de des en un une pour avec pas ne je tu il elle "
        "nous vous mais très c'est du au ce qui"
    ),
    "de": _words(
        "der die das und ist sind nicht ich du er sie wir ihr ein eine mit für auf "
        "zu den dem des auch noch aber was wie"
    ),
    "it": _words(
        "il lo la gli le e è sono che di da in un una per con non mi ti ma molto "
        "come del della io tu"
    ),
    "pt": _words(
        "o a os as e é são que de em um uma para com não se me te mas muito do da você eu está"
    ),
    "nl": _words(
        "de het een en is zijn niet ik je jij hij zij wij met voor op aan van maar wat hoe ook nog"
    ),
    # Added 2026-10-19 (user: a Swedish screenshot wasn't translated; Swedish fell back to
    # the hint, English, and English -> English is passed through).
    "sv": _words(
        "och är jag det inte att på med för en ett som har du vi de kan ska var men om så "
        "till vad hur här nu mig dig han hon"
    ),
    "da": _words(
        "og er jeg det ikke at på med for en et som har du vi de kan skal var men om så "
        "til hvad hvordan her nu mig dig af også"
    ),
    "no": _words(
        "og er jeg det ikke at på med for en et som har du vi de kan skal var men om så "
        "til hva hvordan her nå meg deg av også"
    ),
    "fi": _words(
        "ja on ei se että minä sinä hän me te he mutta kun niin myös vain jo kuin olen oli "
        "tämä mitä mikä"
    ),
    "pl": _words("i w z na nie się to jest że do co jak ale jestem tak ja ty on ona my wy czy już"),
    "tr": _words(
        "ve bir bu da de ne için ile çok ben sen o biz siz ama değil var yok mi mı ki şey"  # noqa: RUF001 - Turkish dotless i
    ),
    "id": _words(
        "dan yang di ke dari ini itu aku kamu dia kita tidak ada untuk dengan saya apa juga "
        "sudah akan"
    ),
    "ms": _words(
        "dan yang di ke dari ini itu saya awak dia kita tidak ada untuk dengan apa juga "
        "sudah akan boleh"
    ),
    "vi": _words("và là của có không tôi bạn này một những được cho với người đã sẽ đang rồi"),
    "cs": _words("a je se na v to že ne s z do jsem jsi ale co jak tak už jsme byl"),
    "hu": _words("a az és egy hogy nem van is de meg ez én te mi ti ők csak már"),
    "ro": _words("și în de la cu nu este sunt că pe un o eu tu el ea dar ce"),
    "tl": _words("ang ng sa na mga ako ikaw siya kami tayo hindi at ay ito iyan po"),
}
_LETTERS: dict[str, str] = {
    "es": "ñ¿¡",
    "fr": "çœàèùâêîôû",
    "de": "ßäöü",
    "pt": "ãõç",
    "it": "àèìòù",
    "sv": "åäö",
    "da": "æøå",
    "no": "æøå",
    "fi": "äö",
    "pl": "ąćęłńśźż",
    "tr": "ğışçöü",
    "cs": "ěščřžůý",
    "hu": "őűáéíóú",
    "ro": "ăâîșț",
    # Vietnamese: its own vowels and the tone marks, which no other language here uses.
    "vi": "ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ",
}
_WORD_RE = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?")


_LATIN_LETTER = re.compile(r"[A-Za-zÀ-ɏ]")
_ANY_SCRIPT = re.compile("|".join(pattern for _, pattern in _SCRIPTS))


def script_language(text: str) -> str | None:
    """A language identified by its writing system, or None for Latin/unknown text.

    The writing system must make up at least as many characters as Latin letters: a game
    chat row like "[队伍] Mika: wait for me at the gate" has a Chinese team tag but an
    English message (found in the 2026-10-18 live screen test)."""
    script_chars = len(_ANY_SCRIPT.findall(text))
    if script_chars == 0 or script_chars < len(_LATIN_LETTER.findall(text)):
        return None
    for language, pattern in _SCRIPT_RES:
        if pattern.search(text):
            return language
    return None


def latin_scores(text: str) -> dict[str, int]:
    words = [w.casefold() for w in _WORD_RE.findall(unicodedata.normalize("NFC", text))]
    scores = {lang: sum(w in vocab for w in words) for lang, vocab in _WORDS.items()}
    lowered = text.lower()  # not casefold(): it turns "ß" into "ss"
    for lang, letters in _LETTERS.items():
        scores[lang] += sum(lowered.count(ch) for ch in letters)
    return scores


def detect(
    text: str,
    candidates: Collection[str] | None = None,
    hint: str | None = None,
) -> str | None:
    """Best guess for `text`'s language among `candidates` (all supported if None);
    `hint` when the text is too short or ambiguous to tell."""

    def allowed(language: str) -> bool:
        return candidates is None or language in candidates

    by_script = script_language(text)
    if by_script is not None:
        return by_script if allowed(by_script) else hint
    words = _WORD_RE.findall(text)
    if len(words) < MIN_WORDS:
        return hint
    scores = {lang: s for lang, s in latin_scores(text).items() if allowed(lang)}
    if not scores:
        return hint
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best, score = ranked[0]
    if score < MIN_SCORE or (len(ranked) > 1 and ranked[1][1] == score):
        return hint
    return best

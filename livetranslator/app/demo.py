"""Scripted demo conversation for look-and-feel review (T062, gate G2).

`python -m livetranslator --demo` feeds this conversation into the store, exactly as the
speech and translation workers will: a line appears as a partial that grows word by word
(committed words + tentative tail), turns final, then its translations arrive a moment
later. It loops, so windows can be restyled while lines keep coming. Translations are
included for en/es/ja/fr/de; other target languages show the original text as "still
changing", which is also what a live window shows while a translation is pending.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer

from livetranslator.core import actions as a
from livetranslator.core.state import Source, Utterance
from livetranslator.core.store import Store

WORD_MS = 260  # a new partial every ~quarter second, like a 0.25-0.5 s ASR update
TRANSLATE_MS = 380  # translation arrives after the final line
GAP_MS = 1100  # pause between lines
TENTATIVE_WORDS = 2  # newest words shown as tentative in a partial


@dataclass(frozen=True)
class DemoLine:
    source: Source
    speaker_id: str
    language: str
    text: str
    translations: dict[str, str]


DEMO_NAMES = {"discord:demo-mika": "Mika"}

SCRIPT: tuple[DemoLine, ...] = (
    DemoLine(
        Source.ME,
        "me",
        "en",
        "Ready when you are, let's go!",
        {
            "es": "¡Listo cuando quieras, vamos!",
            "ja": "準備できたよ、行こう！",  # noqa: RUF001 - real Japanese punctuation
            "fr": "Prêt quand tu veux, on y va !",
            "de": "Bereit, wenn du es bist, los geht's!",
        },
    ),
    DemoLine(
        Source.OTHERS,
        "discord:demo-mika",
        "ja",
        "わかった、門で待ってて。",
        {
            "en": "Okay, wait for me at the gate.",
            "es": "Vale, espérame en la puerta.",
            "fr": "D'accord, attends-moi à la porte.",
            "de": "Okay, warte am Tor auf mich.",
        },
    ),
    DemoLine(
        Source.OTHERS,
        "voice:0",
        "es",
        "Creo que deberíamos ir por el camino de la izquierda y luego cruzar el puente.",
        {
            "en": "I think we should take the left path and then cross the bridge.",
            "ja": "左の道を行って、それから橋を渡るべきだと思う。",
            "fr": "Je pense qu'on devrait prendre le chemin de gauche puis traverser le pont.",
            "de": "Ich denke, wir sollten den linken Weg nehmen und dann die Brücke überqueren.",
        },
    ),
    DemoLine(
        Source.SCREEN,
        "screen",
        "fr",
        "Quête terminée : retournez en ville",
        {
            "en": "Quest complete: return to town",
            "es": "Misión completada: vuelve a la ciudad",
            "ja": "クエスト完了：町に戻る",  # noqa: RUF001
            "de": "Quest abgeschlossen: Kehre in die Stadt zurück",
        },
    ),
    DemoLine(
        Source.OTHERS,
        "voice:1",
        "de",
        "Wartet kurz, ich hole noch schnell die Heiltränke.",
        {
            "en": "Wait a second, I'm just grabbing the healing potions.",
            "es": "Esperad un momento, voy a por las pociones de curación.",
            "ja": "ちょっと待って、回復薬を取ってくる。",
            "fr": "Attendez une seconde, je vais chercher les potions de soin.",
        },
    ),
)


def _chunks(text: str) -> list[str]:
    """Words, or 3-character pieces for scripts written without spaces."""
    if " " in text:
        return text.split()
    return [text[i : i + 3] for i in range(0, len(text), 3)]


def line_steps(line: DemoLine, utterance_id: str, start: float) -> Iterator[tuple[int, a.Action]]:
    """(delay before, action) pairs that play one line: partials, final, translations."""
    chunks = _chunks(line.text)
    joiner = " " if " " in line.text else ""
    for count in range(1, len(chunks) + 1):
        shown = chunks[:count]
        cut = max(len(shown) - TENTATIVE_WORDS, 0) if joiner else 0
        committed, tentative = joiner.join(shown[:cut]), joiner.join(shown[cut:])
        if count == 1:
            utterance = Utterance(
                id=utterance_id,
                source=line.source,
                speaker_id=line.speaker_id,
                start=start,
                committed=committed,
                tentative=tentative,
                language=line.language,
            )
            yield 0, a.AddUtterance(utterance)
        else:
            yield (
                WORD_MS,
                a.UpdateUtterance(utterance_id, {"committed": committed, "tentative": tentative}),
            )
    yield (
        WORD_MS,
        a.UpdateUtterance(
            utterance_id,
            {"committed": line.text, "tentative": "", "is_final": True, "end": start + 1.0},
        ),
    )
    for i, (language, text) in enumerate(line.translations.items()):
        # The first language after the translation delay, the rest together with it.
        yield (
            (TRANSLATE_MS if i == 0 else 0),
            a.SetTranslation(utterance_id, language, text, line.text),
        )


def demo_steps() -> Iterator[tuple[int, a.Action]]:
    """The script, forever (new utterance ids each round)."""
    for name_id, name in DEMO_NAMES.items():
        yield 0, a.RenameSpeaker(name_id, name)
    for n in itertools.count():
        for i, line in enumerate(SCRIPT):
            first = True
            for delay, action in line_steps(line, f"demo-{n}-{i}", float(n * 100 + i)):
                yield (GAP_MS if first else delay), action
                first = False


class DemoFeed(QObject):
    def __init__(self, store: Store, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._steps = demo_steps()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._next)
        self._pending: a.Action | None = None

    def start(self) -> None:
        self._schedule()

    def stop(self) -> None:
        self._timer.stop()

    def _schedule(self) -> None:
        delay, self._pending = next(self._steps)
        self._timer.start(delay)

    def _next(self) -> None:
        if self._pending is not None:
            self._store.dispatch(self._pending)
        self._schedule()

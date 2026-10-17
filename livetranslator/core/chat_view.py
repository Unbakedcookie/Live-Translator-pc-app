"""What a window shows for each chat-log line (T062; spec §5.2, §5.5, §5.13). Pure logic.

For a window with target language T, an utterance is shown as:
- **Already in T** (detected language, or "my language" for the mic): the recognised text,
  committed words as stable and tentative words as still changing.
- **Translated into T**: the translation. It counts as stable only once the line is final
  *and* the translation was made from the line's current text; until then it is drawn as
  still changing (it may be redone).
- **No translation yet**: the recognised text, drawn as still changing, so a line never
  appears blank while the translator catches up.
The original is offered for "original + translation" mode whenever the line is not
already in T.
"""

from __future__ import annotations

from dataclasses import dataclass

from livetranslator.core.state import (
    AppState,
    DisplayMode,
    SessionState,
    Source,
    Utterance,
    WindowConfig,
)

SpeakerKey = str | int  # "me", "screen", or an index into the palette's speaker ramp

VOICE_PREFIX = "voice:"
SCREEN_LABEL = "Screen"
OTHERS_LABEL = "Others"


@dataclass(frozen=True)
class ChatLineData:
    utterance_id: str
    label: str
    speaker: SpeakerKey
    stable: str  # drawn in the primary text colour
    changing: str  # drawn in the secondary colour after `stable`
    original: str | None  # shown under the line in "original + translation" mode


def speaker_ramp_indexes(session: SessionState) -> dict[str, int]:
    """Other speakers numbered by first appearance, so each keeps one colour all session."""
    indexes: dict[str, int] = {}
    for utterance in session.utterances:
        speaker = utterance.speaker_id
        if speaker not in ("me", "screen") and speaker not in indexes:
            indexes[speaker] = len(indexes)
    return indexes


def speaker_label(state: AppState, speaker_id: str) -> str:
    """Session rename first, then the automatic label."""
    renamed = state.session.speaker_names.get(speaker_id)
    if renamed:
        return renamed
    if speaker_id == "me":
        return state.config.speakers.me_label
    if speaker_id == "screen":
        return SCREEN_LABEL
    if speaker_id.startswith(VOICE_PREFIX):
        number = speaker_id.removeprefix(VOICE_PREFIX)
        return f"Speaker {int(number) + 1}" if number.isdigit() else OTHERS_LABEL
    return OTHERS_LABEL  # "others", or a Discord user whose name hasn't arrived


def text_language(utterance: Utterance, state: AppState) -> str | None:
    if utterance.language:
        return utterance.language
    return state.config.my_language if utterance.source is Source.ME else None


def chat_line(
    utterance: Utterance,
    window: WindowConfig,
    state: AppState,
    ramp: dict[str, int],
) -> ChatLineData:
    target = window.target_lang
    speaker: SpeakerKey = (
        utterance.speaker_id
        if utterance.speaker_id in ("me", "screen")
        else ramp.get(utterance.speaker_id, 0)
    )
    label = speaker_label(state, utterance.speaker_id)
    original_text = utterance.text
    if text_language(utterance, state) == target:
        if utterance.is_final:
            stable, changing = original_text, ""
        else:
            stable, changing = utterance.committed, utterance.tentative
        return ChatLineData(utterance.id, label, speaker, stable, changing, None)
    original = original_text if window.display is DisplayMode.BOTH else None
    translation = utterance.translations.get(target)
    if translation is None:
        return ChatLineData(utterance.id, label, speaker, "", original_text, None)
    current = utterance.translated_from.get(target) == original_text
    if utterance.is_final and current:
        return ChatLineData(utterance.id, label, speaker, translation, "", original)
    return ChatLineData(utterance.id, label, speaker, "", translation, original)


def visible_lines(state: AppState, window: WindowConfig, limit: int) -> list[ChatLineData]:
    """The newest `limit` lines from the sources this window shows, oldest first."""
    ramp = speaker_ramp_indexes(state.session)
    shown = [u for u in state.session.utterances if u.source in window.sources and u.text.strip()]
    return [chat_line(u, window, state, ramp) for u in shown[-limit:]]

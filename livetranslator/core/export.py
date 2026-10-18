"""Transcript text and export formats (T063; spec §5.11).

Pure: session state in, text out. The transcript window shows `transcript_lines`, and export
writes `transcript_txt` or `transcript_json`; nothing here touches the disk (the chat log is
never saved unless the user exports it).

- Times are offsets from the first line ("00:03", or "1:02:05" past an hour).
- A translation is listed only if it was made from the line's final text (an older one,
  from words that later changed, would be wrong).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from livetranslator import APP_DISPLAY_NAME, __version__
from livetranslator.core.chat_view import SpeakerKey, speaker_label, speaker_ramp_indexes
from livetranslator.core.languages import language
from livetranslator.core.state import AppState, Utterance

TXT_INDENT = "  "
UNFINISHED = "still talking"


@dataclass(frozen=True)
class TranscriptLine:
    utterance_id: str
    offset: str  # "00:03"
    speaker: str  # "Speaker 1"
    language: str | None  # ISO code of what was said
    text: str
    translations: tuple[tuple[str, str], ...]  # (ISO code, text), sorted by code
    finished: bool
    speaker_key: SpeakerKey = "me"  # colour: "me", "screen" or the speaker-ramp index

    def heading(self) -> str:
        parts = [f"[{self.offset}] {self.speaker}"]
        if self.language:
            parts.append(f"({language(self.language).english})")
        if not self.finished:
            parts.append(f"— {UNFINISHED}")
        return " ".join(parts)

    def block(self) -> str:
        """The line as plain text: heading, what was said, then each translation."""
        rows = [self.heading(), self.text]
        rows += [
            f"{TXT_INDENT}{language(code).english}: {text}" for code, text in self.translations
        ]
        return "\n".join(rows)

    def matches(self, needle: str) -> bool:
        """Case-insensitive search over speaker, text and translations."""
        needle = needle.strip().casefold()
        if not needle:
            return True
        haystack = [self.speaker, self.text, *(text for _, text in self.translations)]
        return any(needle in part.casefold() for part in haystack)


def format_offset(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def current_translations(utterance: Utterance) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (code, text)
            for code, text in utterance.translations.items()
            if text and utterance.translated_from.get(code) == utterance.text
        )
    )


def transcript_lines(state: AppState) -> list[TranscriptLine]:
    utterances = [u for u in state.session.utterances if u.text.strip()]
    if not utterances:
        return []
    t0 = min(u.start for u in utterances)
    ramp = speaker_ramp_indexes(state.session)
    return [
        TranscriptLine(
            utterance_id=u.id,
            offset=format_offset(u.start - t0),
            speaker=speaker_label(state, u.speaker_id),
            language=u.language,
            text=u.text,
            translations=current_translations(u),
            finished=u.is_final,
            speaker_key=(
                u.speaker_id if u.speaker_id in ("me", "screen") else ramp.get(u.speaker_id, 0)
            ),
        )
        for u in sorted(utterances, key=lambda u: u.start)
    ]


def transcript_txt(state: AppState, exported_at: datetime) -> str:
    header = [
        f"{APP_DISPLAY_NAME} transcript",
        f"Exported {exported_at:%Y-%m-%d %H:%M}",
    ]
    blocks = [line.block() for line in transcript_lines(state)]
    return "\n\n".join(["\n".join(header), *blocks]) + "\n"


def transcript_json(state: AppState, exported_at: datetime) -> str:
    """Every line in full (the Utterance fields) plus its speaker label and offset."""
    utterances = sorted(
        (u for u in state.session.utterances if u.text.strip()), key=lambda u: u.start
    )
    t0 = utterances[0].start if utterances else 0.0
    items = [
        {
            **u.model_dump(mode="json"),
            "speaker": speaker_label(state, u.speaker_id),
            "offset_s": round(u.start - t0, 3),
        }
        for u in utterances
    ]
    document = {
        "app": APP_DISPLAY_NAME,
        "version": __version__,
        "exported_at": exported_at.isoformat(timespec="seconds"),
        "utterances": items,
    }
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"

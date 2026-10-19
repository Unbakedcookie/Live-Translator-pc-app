"""Pure reducers: (state, action) -> (new state, changes) (T013; spec §6.3).

`changes` lists exactly what changed, so the store can emit narrow signals (a style change
re-renders one window, not the chat log). An action that changes nothing returns the same
state and no changes. Updates aimed at ids that no longer exist (a window closed while a
worker was still reporting) are ignored; programming errors (duplicate ids, unknown fields,
invalid values) raise ValueError.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ValidationError

from livetranslator.core import actions as a
from livetranslator.core.state import (
    HOTKEY_ACTION_NAMES,
    AppConfig,
    AppState,
    Away,
    RuntimeStatus,
    Utterance,
    WindowConfig,
)


class ChangeKind(StrEnum):
    CONFIG = "config"  # key = section name, "windows" or "all"; persisted
    WINDOW = "window"  # key = window id (added, removed or changed)
    UTTERANCE_ADDED = "utterance_added"
    UTTERANCE_UPDATED = "utterance_updated"
    UTTERANCE_REMOVED = "utterance_removed"
    SESSION_CLEARED = "session_cleared"
    SPEAKER = "speaker"  # key = speaker id (rename)
    RUNTIME = "runtime"  # key = "status:<key>", "metric:<name>", "all_hidden", "away"


@dataclass(frozen=True)
class Change:
    kind: ChangeKind
    key: str = ""


Changes = tuple[Change, ...]
Result = tuple[AppState, Changes]

WINDOW_FIXED_FIELDS = frozenset({"id", "style"})  # style has its own action
UTTERANCE_FIXED_FIELDS = frozenset({"id", "source", "translations", "translated_from"})


def _updated[M: BaseModel](model: M, fields: Mapping[str, object], fixed: frozenset[str]) -> M:
    """Return a validated copy of `model` with `fields` replaced."""
    names = set(type(model).model_fields)
    unknown = set(fields) - names
    if unknown:
        raise ValueError(f"{type(model).__name__} has no field(s) {sorted(unknown)}")
    blocked = set(fields) & fixed
    if blocked:
        raise ValueError(f"{type(model).__name__} field(s) {sorted(blocked)} can't be updated here")
    data: dict[str, Any] = {name: getattr(model, name) for name in names}
    data.update(fields)
    try:
        return type(model).model_validate(data)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


def _with_config(state: AppState, config: AppConfig, *changes: Change) -> Result:
    if config == state.config:
        return state, ()
    return state.model_copy(update={"config": config}), changes


def _with_away(state: AppState, away: dict[str, Away]) -> Result:
    if away == state.runtime.away:
        return state, ()
    runtime = state.runtime.model_copy(update={"away": away})
    return state.model_copy(update={"runtime": runtime}), (Change(ChangeKind.RUNTIME, "away"),)


def _replace_window(state: AppState, window: WindowConfig) -> Result:
    old = state.config.window(window.id)
    if old is None or old == window:
        return state, ()
    windows = tuple(window if w.id == window.id else w for w in state.config.windows)
    config = state.config.model_copy(update={"windows": windows})
    return _with_config(
        state, config, Change(ChangeKind.WINDOW, window.id), Change(ChangeKind.CONFIG, "windows")
    )


def _reduce_config(state: AppState, action: a.Action) -> Result | None:
    config = state.config
    match action:
        case a.ReplaceConfig(config=new):
            if new == config:
                return state, ()
            ids = dict.fromkeys([*(w.id for w in config.windows), *(w.id for w in new.windows)])
            replaced: Changes = (
                Change(ChangeKind.CONFIG, "all"),
                *(Change(ChangeKind.WINDOW, i) for i in ids),
            )
            return state.model_copy(update={"config": new}), replaced
        case a.SetMyLanguage(language=language):
            return _with_config(
                state,
                _updated(config, {"my_language": language}, frozenset()),
                Change(ChangeKind.CONFIG, "my_language"),
            )
        case a.UpdateConfigSection(section=section, fields=fields):
            section_model: BaseModel = getattr(config, section)
            new_section = _updated(section_model, fields, frozenset())
            return _with_config(
                state,
                config.model_copy(update={section: new_section}),
                Change(ChangeKind.CONFIG, section),
            )
        case a.SetHotkey(action=name, keys=keys):
            if name not in HOTKEY_ACTION_NAMES:
                raise ValueError(f"unknown hotkey action {name!r}")
            hotkeys = dict(config.hotkeys)
            if keys is None:
                hotkeys.pop(name, None)
            else:
                hotkeys[name] = keys
            return _with_config(
                state,
                config.model_copy(update={"hotkeys": hotkeys}),
                Change(ChangeKind.CONFIG, "hotkeys"),
            )
        case a.SetLockLayout(locked=locked):
            return _with_config(
                state,
                config.model_copy(update={"lock_layout": locked}),
                Change(ChangeKind.CONFIG, "lock_layout"),
            )
        case a.SetModelsDir(path=path):
            return _with_config(
                state,
                config.model_copy(update={"models_dir": path}),
                Change(ChangeKind.CONFIG, "models_dir"),
            )
        case a.SetWizardCompleted(completed=completed):
            return _with_config(
                state,
                config.model_copy(update={"wizard_completed": completed}),
                Change(ChangeKind.CONFIG, "wizard_completed"),
            )
        case a.AddWindow(window=window):
            if config.window(window.id) is not None:
                raise ValueError(f"window id {window.id!r} already exists")
            return _with_config(
                state,
                config.model_copy(update={"windows": (*config.windows, window)}),
                Change(ChangeKind.WINDOW, window.id),
                Change(ChangeKind.CONFIG, "windows"),
            )
        case a.RemoveWindow(window_id=window_id):
            if config.window(window_id) is None:
                return state, ()
            windows = tuple(w for w in config.windows if w.id != window_id)
            removed, window_changes = _with_config(
                state,
                config.model_copy(update={"windows": windows}),
                Change(ChangeKind.WINDOW, window_id),
                Change(ChangeKind.CONFIG, "windows"),
            )
            if window_id not in state.runtime.away:
                return removed, window_changes
            away = {k: v for k, v in state.runtime.away.items() if k != window_id}
            gone, away_changes = _with_away(removed, away)
            return gone, (*window_changes, *away_changes)
        case a.UpdateWindow(window_id=window_id, fields=fields):
            window = config.window(window_id)
            if window is None:
                return state, ()
            return _replace_window(state, _updated(window, fields, WINDOW_FIXED_FIELDS))
        case a.UpdateWindowStyle(window_id=window_id, fields=fields):
            window = config.window(window_id)
            if window is None:
                return state, ()
            style = _updated(window.style, fields, frozenset())
            return _replace_window(state, window.model_copy(update={"style": style}))
        case a.UpdateAllWindows(fields=fields):
            changes: list[Change] = []
            for window in config.windows:
                state, window_changes = _replace_window(
                    state, _updated(window, fields, WINDOW_FIXED_FIELDS)
                )
                changes.extend(c for c in window_changes if c.kind is ChangeKind.WINDOW)
            if changes:
                changes.append(Change(ChangeKind.CONFIG, "windows"))
            return state, tuple(changes)
        case _:
            return None


def _reduce_session(state: AppState, action: a.Action) -> Result | None:
    session = state.session
    match action:
        case a.AddUtterance(utterance=utterance):
            if session.utterance(utterance.id) is not None:
                raise ValueError(f"utterance id {utterance.id!r} already exists")
            new = session.model_copy(update={"utterances": (*session.utterances, utterance)})
            return state.model_copy(update={"session": new}), (
                Change(ChangeKind.UTTERANCE_ADDED, utterance.id),
            )
        case a.UpdateUtterance(utterance_id=uid, fields=fields):
            old = session.utterance(uid)
            if old is None:
                return state, ()
            return _replace_utterance(state, _updated(old, fields, UTTERANCE_FIXED_FIELDS))
        case a.SetTranslation(
            utterance_id=uid, language=language, text=text, source_text=source_text
        ):
            old = session.utterance(uid)
            if old is None:
                return state, ()
            translations = {**old.translations, language: text}
            translated_from = {**old.translated_from, language: source_text}
            return _replace_utterance(
                state,
                old.model_copy(
                    update={"translations": translations, "translated_from": translated_from}
                ),
            )
        case a.RemoveUtterance(utterance_id=uid):
            if session.utterance(uid) is None:
                return state, ()
            remaining = tuple(u for u in session.utterances if u.id != uid)
            new = session.model_copy(update={"utterances": remaining})
            return state.model_copy(update={"session": new}), (
                Change(ChangeKind.UTTERANCE_REMOVED, uid),
            )
        case a.ClearSession():
            if not session.utterances and not session.speaker_names:
                return state, ()
            cleared = session.model_copy(update={"utterances": (), "speaker_names": {}})
            return state.model_copy(update={"session": cleared}), (
                Change(ChangeKind.SESSION_CLEARED),
            )
        case a.RenameSpeaker(speaker_id=speaker_id, name=name):
            names = dict(session.speaker_names)
            if name is None or not name.strip():
                if speaker_id not in names:
                    return state, ()
                del names[speaker_id]
            else:
                if names.get(speaker_id) == name.strip():
                    return state, ()
                names[speaker_id] = name.strip()
            new = session.model_copy(update={"speaker_names": names})
            return state.model_copy(update={"session": new}), (
                Change(ChangeKind.SPEAKER, speaker_id),
            )
        case _:
            return None


def _replace_utterance(state: AppState, utterance: Utterance) -> Result:
    session = state.session
    if session.utterance(utterance.id) == utterance:
        return state, ()
    utterances = tuple(utterance if u.id == utterance.id else u for u in session.utterances)
    new = session.model_copy(update={"utterances": utterances})
    return state.model_copy(update={"session": new}), (
        Change(ChangeKind.UTTERANCE_UPDATED, utterance.id),
    )


def _reduce_runtime(state: AppState, action: a.Action) -> Result | None:
    runtime = state.runtime
    match action:
        case a.SetStatus(key=key, level=level, message=message):
            status = RuntimeStatus(level=level, message=message)
            if runtime.statuses.get(key) == status:
                return state, ()
            statuses = {**runtime.statuses, key: status}
            new = runtime.model_copy(update={"statuses": statuses})
            return state.model_copy(update={"runtime": new}), (
                Change(ChangeKind.RUNTIME, f"status:{key}"),
            )
        case a.ClearStatus(key=key):
            if key not in runtime.statuses:
                return state, ()
            statuses = {k: v for k, v in runtime.statuses.items() if k != key}
            new = runtime.model_copy(update={"statuses": statuses})
            return state.model_copy(update={"runtime": new}), (
                Change(ChangeKind.RUNTIME, f"status:{key}"),
            )
        case a.SetMetric(name=name, value=value):
            if runtime.metrics.get(name) == value:
                return state, ()
            new = runtime.model_copy(update={"metrics": {**runtime.metrics, name: value}})
            return state.model_copy(update={"runtime": new}), (
                Change(ChangeKind.RUNTIME, f"metric:{name}"),
            )
        case a.SetAllHidden(hidden=hidden):
            away = runtime.away if hidden else {}  # "show all" also brings back single windows
            if runtime.all_hidden == hidden and away == runtime.away:
                return state, ()
            new = runtime.model_copy(update={"all_hidden": hidden, "away": away})
            return state.model_copy(update={"runtime": new}), (
                Change(ChangeKind.RUNTIME, "all_hidden"),
            )
        case a.SetWindowAway(window_id=window_id, away=how):
            away = {k: v for k, v in runtime.away.items() if k != window_id}
            if how is not None and state.config.window(window_id) is not None:
                away[window_id] = how
            return _with_away(state, away)
        case a.RestoreMinimized():
            return _with_away(
                state, {k: v for k, v in runtime.away.items() if v is not Away.MINIMIZED}
            )
        case _:
            return None


def reduce(state: AppState, action: a.Action) -> Result:
    """Apply one action. Raises ValueError for invalid actions; state is then unchanged."""
    if isinstance(action, a.Batch):
        changes: list[Change] = []
        for inner in action.actions:
            state, inner_changes = reduce(state, inner)
            changes.extend(c for c in inner_changes if c not in changes)
        return state, tuple(changes)
    for reducer in (_reduce_config, _reduce_session, _reduce_runtime):
        result = reducer(state, action)
        if result is not None:
            return result
    raise ValueError(f"no reducer handles {type(action).__name__}")

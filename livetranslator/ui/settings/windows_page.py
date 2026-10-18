"""Settings → Windows (T072): lock all, open a new window, and the list of open windows."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QPushButton, QWidget

from livetranslator.core.languages import language
from livetranslator.core.state import Source, WindowConfig
from livetranslator.ui.settings.context import SettingsContext
from livetranslator.ui.settings.rows import Section, SettingsPage, silently

SOURCE_NAMES = {Source.ME: "Me", Source.OTHERS: "Others", Source.SCREEN: "Screen"}


def window_title(index: int, cfg: WindowConfig) -> str:
    name = cfg.title or f"Window {index + 1}"
    return f"{name} — {language(cfg.target_lang).english}"


def window_description(cfg: WindowConfig) -> str:
    shows = " + ".join(SOURCE_NAMES[s] for s in cfg.sources) or "nothing"
    flags = [
        text
        for on, text in (
            (cfg.pinned, "on top"),
            (cfg.click_through, "click-through"),
            (cfg.locked, "locked"),
        )
        if on
    ]
    return f"Shows {shows}" + (f" · {', '.join(flags)}" if flags else "")


class WindowsPage(SettingsPage):
    title_text = "Windows"
    icon_name = "app-window"

    def __init__(self, ctx: SettingsContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        everything = self.section("All windows")
        self.lock_all = QCheckBox()
        self.lock_all.toggled.connect(ctx.settings.set_all_locked)
        everything.row(
            "Lock all windows",
            "Stops windows from being moved or resized by accident.",
            self.lock_all,
        )
        new = QPushButton("New window")
        new.clicked.connect(lambda: ctx.windows.add_window())
        everything.row(
            "Open a new window",
            "Each window can translate into its own language.",
            new,
        )
        self._list_holder = QWidget()
        self.body.addWidget(self._list_holder)
        self.list: Section | None = None
        self._shown: tuple[WindowConfig, ...] | None = None
        self.finish()
        self.refresh()

    def refresh(self) -> None:
        windows = self._ctx.settings.store.state.config.windows
        locked = bool(windows) and all(w.locked for w in windows)
        silently(self.lock_all, lambda: self.lock_all.setChecked(locked))
        if windows != self._shown:
            self._shown = windows
            self._rebuild(windows)

    def _rebuild(self, windows: tuple[WindowConfig, ...]) -> None:
        index = self.body.indexOf(self.list if self.list is not None else self._list_holder)
        old = self.list if self.list is not None else self._list_holder
        self.list = Section("Open windows")
        if not windows:
            self.list.row("No windows are open", "Use “New window” above or the tray icon.")
        for i, cfg in enumerate(windows):
            remove = QPushButton("Close")
            remove.clicked.connect(lambda _=False, wid=cfg.id: self._ctx.windows.remove_window(wid))
            self.list.row(window_title(i, cfg), window_description(cfg), remove)
        self.body.insertWidget(index, self.list)
        old.setParent(None)
        old.deleteLater()

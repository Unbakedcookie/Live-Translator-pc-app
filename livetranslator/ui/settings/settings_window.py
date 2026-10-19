"""The Settings window (T072; spec §5.8; gate G3): a normal app window with a page list on
the left and the chosen page on the right.

Every control writes through SettingsController / WindowController and every page re-reads
the store when it changes, so Settings, tray, hotkeys and overlays always agree. Changes
apply immediately and persist through the store's debounced save (no OK/Apply buttons).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QStackedWidget, QWidget

from livetranslator.theme.icons import icon
from livetranslator.theme.qss import settings_qss, window_qss
from livetranslator.theme.tokens import SETTINGS, SPACE, WINDOW
from livetranslator.ui.session import session_ending
from livetranslator.ui.settings.advanced_page import AdvancedPage
from livetranslator.ui.settings.audio_page import AudioPage
from livetranslator.ui.settings.context import SettingsContext
from livetranslator.ui.settings.general_page import GeneralPage
from livetranslator.ui.settings.hotkeys_page import HotkeysPage
from livetranslator.ui.settings.performance_page import PerformancePage
from livetranslator.ui.settings.rows import SettingsPage
from livetranslator.ui.settings.speakers_page import SpeakersPage
from livetranslator.ui.settings.translation_page import TranslationPage
from livetranslator.ui.settings.windows_page import WindowsPage

PAGE_TYPES: tuple[Callable[[SettingsContext], SettingsPage], ...] = (
    GeneralPage,
    AudioPage,
    SpeakersPage,
    WindowsPage,
    TranslationPage,
    HotkeysPage,
    PerformancePage,
    AdvancedPage,
)


class SettingsWindow(QWidget):
    def __init__(self, ctx: SettingsContext, parent: QWidget | None = None) -> None:
        # Above pinned (always-on-top) overlays, which otherwise covered it (user report
        # 2026-10-18: "Settings doesn't appear").
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self._ctx = ctx
        self.setObjectName("SettingsRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setWindowTitle("Settings")  # Qt adds " - Live Translator"
        self.setWindowIcon(icon("translate", ctx.palette, "accent"))
        self.setStyleSheet(window_qss(ctx.palette) + settings_qss(ctx.palette))
        self.resize(SETTINGS.width, SETTINGS.height)

        self.nav = QListWidget(self)
        self.nav.setObjectName("SettingsNav")
        self.nav.setFixedWidth(SETTINGS.nav_width)
        self.nav.setIconSize(QSize(WINDOW.icon_size, WINDOW.icon_size))
        self.nav.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.stack = QStackedWidget(self)
        self.pages: dict[str, SettingsPage] = {}
        for page_type in PAGE_TYPES:
            page = page_type(ctx)
            self.pages[page.title_text] = page
            self.stack.addWidget(page)
            item = QListWidgetItem(
                icon(page.icon_name, ctx.palette, "text_secondary"), page.title_text
            )
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE.md, SPACE.md, 0, 0)
        layout.setSpacing(SPACE.sm)
        layout.addWidget(self.nav)
        layout.addWidget(self.stack, 1)

        store = ctx.settings.store
        store.config_changed.connect(self._on_config)
        store.window_changed.connect(lambda _id: self._refresh(WindowsPage.title_text))
        store.runtime_changed.connect(self._on_runtime)

    def show_page(self, title: str) -> None:
        row = list(self.pages).index(title)
        self.nav.setCurrentRow(row)

    def _refresh(self, *titles: str) -> None:
        if not self.isVisible():
            return  # showEvent re-reads everything when the window opens again
        for title in titles or tuple(self.pages):
            self.pages[title].refresh()

    def _on_config(self, section: str) -> None:
        self._refresh()  # cheap: every page just re-reads a few fields
        del section

    def _on_runtime(self, key: str) -> None:
        if key == "status:discord":
            self._refresh(SpeakersPage.title_text)
        if key.startswith("status:hotkey."):
            self._refresh(HotkeysPage.title_text)

    def bring_to_front(self) -> None:
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event: QShowEvent) -> None:
        self._refresh()
        super().showEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Closing only hides: the window is reused next time (and a recording shortcut box
        gives the global hotkeys back)."""
        focus = self.focusWidget()
        if focus is not None:
            focus.clearFocus()
        if session_ending():
            event.accept()  # Windows is logging off / shutting down: never block it
            return
        event.ignore()
        self.hide()

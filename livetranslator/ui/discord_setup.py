"""Discord names: guided own-app setup (T104; spec §5.13 "Own-app mode"; D-013, D-030).

Discord only lets an app read who is speaking if it is the user's own (or they're a tester),
so the user makes a free Discord application once. The steps were checked against Discord's
docs on 2026-10-18; the parts the docs don't settle (the tester step) are written as "if".
The secret is stored DPAPI-encrypted on this PC only (never shared, never logged).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from livetranslator.app.discord_controller import DiscordController
from livetranslator.core.state import is_discord_id
from livetranslator.services.speakers.discord_rpc import REDIRECT_URI
from livetranslator.theme.qss import settings_qss, window_qss
from livetranslator.theme.tokens import SETTINGS, SPACE, Palette
from livetranslator.ui.session import session_ending
from livetranslator.ui.settings.rows import Section, note

# Opens the "create app" box directly (Discord's own quick-start links this).
PORTAL = "https://discord.com/developers/applications?new_application=true"
# Steps re-checked on the live site 2026-10-18 (user report: no "New Application" button —
# a "What brings you to the Developer Portal?" page now comes first, with Skip at the bottom).
OPEN_STEP = 1
COPY_REDIRECT_STEP = 5
TEST_STEP = 7  # the Test connection button sits in this step (user couldn't find it below)
STEPS = (
    "Click Open. Discord's developer website opens in your web browser (this is a website, "
    "not the Discord app). Log in with your normal Discord account if it asks.",
    "If it asks “What brings you to the Developer Portal?”, click Skip at the bottom.",
    "Click “New Application” at the top right (skip this if a name box is already open). "
    "Type a name such as “My Live Translator”, tick the box agreeing to Discord's terms, "
    "and click Create.",
    "On “General Information”, copy the Application ID (a long number) and paste it below.",
    f"In the menu on the left, open “OAuth2”. Under Redirects click “Add Redirect”, paste "
    f"{REDIRECT_URI} exactly (the Copy button copies it), and click Save Changes.",
    "On the same page click “Reset Secret”, confirm, copy the secret and paste it below. It "
    "stays encrypted on this PC and is only ever sent to Discord.",
    "Open the Discord app, join a voice channel, then click Test connection (right here) and "
    "approve the request that pops up inside Discord.",
    "Usually not needed: you own the app, which Discord normally allows. Only if the message "
    "under Test connection mentions App Testers: open that page on the developer website, "
    "add your own account, accept the invite, and test again.",
)


class DiscordSetup(QWidget):
    checked = Signal(bool, str)  # from the test thread → shown on the UI thread

    def __init__(
        self, discord: DiscordController, palette: Palette, parent: QWidget | None = None
    ) -> None:
        # On top: the guide is read while working in the browser and Discord (user report
        # 2026-10-18: it fell behind them, and opened behind Settings).
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self._discord = discord
        self.setObjectName("SettingsRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setWindowTitle("Set up Discord names")
        self.setStyleSheet(window_qss(palette) + settings_qss(palette))
        self.setMinimumWidth(SETTINGS.width * 3 // 4)

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE.xl, SPACE.xl, SPACE.xl, SPACE.xl)
        root.setSpacing(SPACE.lg)
        title = QLabel("Show Discord names on speakers", self)
        title.setObjectName("SettingsPageTitle")
        root.addWidget(title)
        root.addWidget(
            note(
                "Discord only shares who is talking with apps you own, so you make your own "
                "free Discord app once (about 3 minutes). Nothing is posted anywhere."
            )
        )
        self.test = QPushButton("Test connection")
        steps = Section("Steps")
        for i, text in enumerate(STEPS, start=1):
            control: QWidget | None = None
            if i == OPEN_STEP:
                control = QPushButton("Open")
                control.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(PORTAL)))
            elif i == COPY_REDIRECT_STEP:
                control = QPushButton("Copy")
                control.clicked.connect(lambda: QGuiApplication.clipboard().setText(REDIRECT_URI))
            elif i == TEST_STEP:
                control = self.test
            steps.row(f"Step {i}", text, control)
        root.addWidget(steps)

        fields = Section("Your Discord app")
        self.app_id = QLineEdit()
        self.app_id.setPlaceholderText("e.g. 1234567890123456789")
        self.app_id.setFixedWidth(SETTINGS.control_width)
        fields.row("Application ID", "", self.app_id)
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret.setPlaceholderText("paste the secret")
        self.secret.setFixedWidth(SETTINGS.control_width)
        fields.row("Client secret", "", self.secret)
        root.addWidget(fields)

        self.result = note("", self)
        root.addWidget(self.result)
        buttons = QHBoxLayout()
        self.save = QPushButton("Save")
        self.remove = QPushButton("Disconnect")
        buttons.addStretch(1)
        buttons.addWidget(self.remove)
        buttons.addWidget(self.save)
        root.addLayout(buttons)

        self.test.clicked.connect(self._on_test)
        self.save.clicked.connect(self._on_save)
        self.remove.clicked.connect(self._on_disconnect)
        self.checked.connect(self._on_checked)
        self.app_id.textChanged.connect(lambda _t: self._update_buttons())
        self.secret.textChanged.connect(lambda _t: self._update_buttons())
        self.load()

    def load(self) -> None:
        speakers = self._discord_config()
        self.app_id.setText(speakers or "")
        self.secret.setText(self._discord.secret())
        self._update_buttons()

    def _discord_config(self) -> str | None:
        return self._discord.app_id

    def _ready(self) -> bool:
        return is_discord_id(self.app_id.text().strip()) and bool(self.secret.text().strip())

    def _update_buttons(self) -> None:
        ready = self._ready()
        self.test.setEnabled(ready)
        self.save.setEnabled(ready)
        self.remove.setEnabled(bool(self._discord_config()) or bool(self._discord.secret()))

    def _on_test(self) -> None:
        self.test.setEnabled(False)
        self.result.setText("Connecting… approve the request in Discord if it asks.")
        self._discord.check(self.app_id.text(), self.secret.text(), self.checked.emit)

    def _on_checked(self, ok: bool, message: str) -> None:
        self.result.setObjectName("SettingsNote" if ok else "SettingsError")
        self.result.style().unpolish(self.result)
        self.result.style().polish(self.result)
        self.result.setText(message)
        self._update_buttons()

    def _on_save(self) -> None:
        self._discord.save_setup(self.app_id.text(), self.secret.text())
        self.result.setText("Saved. Names appear in your windows while you're in a voice channel.")
        self._update_buttons()

    def _on_disconnect(self) -> None:
        self._discord.disconnect()
        self.app_id.clear()
        self.secret.clear()
        self.result.setText("Disconnected. The token and secret were deleted from this PC.")
        self._update_buttons()

    def closeEvent(self, event: QCloseEvent) -> None:
        if session_ending():
            event.accept()
            return
        event.ignore()
        self.hide()

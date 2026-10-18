"""The floating overlay window shell (T024; spec §5.1, gate G1).

Presentational: it renders its WindowConfig from the store and reports user intents to the
WindowController. Drags and resizes move the window locally and commit the final geometry
once, on mouse release, so the store (and the settings file) isn't flooded while dragging.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QCursor,
    QEnterEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QShowEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QWidget,
)

from livetranslator.app.window_controller import WindowController
from livetranslator.core.chat_view import automatic_label, speaker_label
from livetranslator.core.languages import language
from livetranslator.core.state import Source, WindowConfig
from livetranslator.platform import win32
from livetranslator.theme.icons import icon
from livetranslator.theme.palette_gen import palette_for
from livetranslator.theme.qss import badge_qss, pill_qss, window_qss
from livetranslator.theme.tokens import FONTS, MOTION, RADIUS, SPACE, WINDOW, Palette
from livetranslator.ui.geometry import (
    EDGE_BOTTOM,
    EDGE_LEFT,
    EDGE_RIGHT,
    EDGE_TOP,
    Rect,
    clamp_into,
    edges_at,
    monitor_for,
    resize_rect,
    snap,
)
from livetranslator.ui.readout import ReadoutStrip
from livetranslator.ui.screens import monitors, qrect_from_rect, rect_from_qrect
from livetranslator.ui.status_strip import StatusStrip
from livetranslator.ui.style_popover import StylePopover
from livetranslator.ui.translation_view import TranslationView
from livetranslator.ui.widgets.icon_button import IconButton
from livetranslator.ui.widgets.language_picker import LanguagePicker
from livetranslator.ui.widgets.pin_button import PinButton
from livetranslator.ui.widgets.speaker_label import RenamePopup
from livetranslator.ui.widgets.toast import Toast

CURSOR_POLL_MS = 200
OTHERS_ID = "others"  # the catch-all speaker (no single person to rename)

MIN_HIT_ALPHA = 1 / 255  # fully transparent pixels let clicks through on Windows; keep 1/255

_CURSORS = {
    EDGE_LEFT: Qt.CursorShape.SizeHorCursor,
    EDGE_RIGHT: Qt.CursorShape.SizeHorCursor,
    EDGE_TOP: Qt.CursorShape.SizeVerCursor,
    EDGE_BOTTOM: Qt.CursorShape.SizeVerCursor,
    EDGE_LEFT | EDGE_TOP: Qt.CursorShape.SizeFDiagCursor,
    EDGE_RIGHT | EDGE_BOTTOM: Qt.CursorShape.SizeFDiagCursor,
    EDGE_RIGHT | EDGE_TOP: Qt.CursorShape.SizeBDiagCursor,
    EDGE_LEFT | EDGE_BOTTOM: Qt.CursorShape.SizeBDiagCursor,
}
SOURCE_NAMES = {Source.ME: "Me", Source.OTHERS: "Others", Source.SCREEN: "Screen"}


def sources_summary(sources: tuple[Source, ...]) -> str:
    return " + ".join(SOURCE_NAMES[s] for s in sources)


@dataclass
class _Drag:
    edges: int  # 0 = move
    start_global: QPoint
    start_rect: Rect


class ChromeBar(QWidget):
    """Hover title strip: [pin] [language] sources ... [style] [hide] [close]."""

    style_requested = Signal()
    hide_requested = Signal()
    close_requested = Signal()

    def __init__(self, controller: WindowController, window_id: str, palette: Palette) -> None:
        super().__init__()
        self._palette = palette
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE.xs, 0, SPACE.xs, 0)
        layout.setSpacing(SPACE.xs)
        self.pin = PinButton(palette, self)
        self.pin.toggled.connect(lambda on: controller.set_pinned(window_id, on))
        self.language = LanguagePicker("en", parent=self)
        self.language.setProperty("flat", True)  # blends into the strip (G1 verifier note)
        self.language.language_changed.connect(
            lambda code: controller.set_target_lang(window_id, code)
        )
        self.sources = QLabel(self)
        self.style_button = IconButton("palette", "Style", palette, parent=self)
        self.style_button.clicked.connect(self.style_requested.emit)
        self.hide_button = IconButton("minus", "Hide (Ctrl+Alt+H shows all)", palette, parent=self)
        self.hide_button.clicked.connect(self.hide_requested.emit)
        self.close_button = IconButton("x", "Close this window", palette, parent=self)
        self.close_button.clicked.connect(self.close_requested.emit)
        layout.addWidget(self.pin)
        layout.addWidget(self.language)
        layout.addWidget(self.sources)
        layout.addStretch(1)
        for button in (self.style_button, self.hide_button, self.close_button):
            layout.addWidget(button)
        self._apply_palette(palette)

    def _apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.setStyleSheet(window_qss(palette))
        for button in (self.pin, self.style_button, self.hide_button, self.close_button):
            button.apply_palette(palette)
        self.language.apply_palette(palette)
        self.sources.setStyleSheet(f"color: {palette.text_secondary};")
        self.update()

    def set_state(self, palette: Palette, cfg: WindowConfig) -> None:
        if palette != self._palette:
            self._apply_palette(palette)
        self.pin.set_checked_silently(cfg.pinned)
        self.language.set_language(cfg.target_lang)
        self.sources.setText(sources_summary(cfg.sources))

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._palette.surface))
        r = self.rect()
        painter.drawRoundedRect(r, RADIUS.md, RADIUS.md)
        painter.drawRect(r.adjusted(0, RADIUS.md, 0, 0))  # square bottom corners
        painter.end()


class FloatingWindow(QWidget):
    hide_requested = Signal(str)
    new_window_requested = Signal()
    settings_requested = Signal()
    transcript_requested = Signal()
    screen_region_requested = Signal()
    quit_requested = Signal()

    def __init__(
        self,
        controller: WindowController,
        window_id: str,
        snap_targets: Callable[[str], list[Rect]],
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.window_id = window_id
        self._controller = controller
        self._snap_targets = snap_targets
        self._drag: _Drag | None = None
        self._press_global: QPoint | None = None  # left press, to tell a click from a drag
        self.rename_popup: RenamePopup | None = None
        self._hovered = False
        self._native: tuple[bool, bool] | None = None  # (pinned, click-through) applied
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setMinimumSize(WINDOW.min_width, WINDOW.min_height)
        self.setWindowTitle("Live Translator")

        cfg = self.config
        if cfg is None:
            raise ValueError(f"no window config {window_id!r}")
        self.palette_value = palette_for(
            cfg.style.palette_id, cfg.style.custom_seed, cfg.style.custom_dark
        )
        self.content = TranslationView(controller.store, window_id, self)
        # "New lines" pill (T062): shown while scrolled up and newer lines arrived.
        self.new_lines = QPushButton("New lines", self)
        self.new_lines.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_lines.hide()
        self.new_lines.clicked.connect(self.content.scroll_to_bottom)
        self.content.unread_changed.connect(self._on_unread)
        self.chrome = ChromeBar(controller, window_id, self.palette_value)
        self.chrome.setParent(self)
        self.chrome.style_requested.connect(self.open_style_popover)
        self.chrome.hide_requested.connect(lambda: self.hide_requested.emit(self.window_id))
        self.chrome.close_requested.connect(lambda: controller.remove_window(self.window_id))
        self._chrome_effect = QGraphicsOpacityEffect(self.chrome)
        self._chrome_effect.setOpacity(0.0)
        self.chrome.setGraphicsEffect(self._chrome_effect)
        self.chrome.hide()
        self._chrome_anim = QPropertyAnimation(self._chrome_effect, b"opacity", self)
        self._chrome_anim.setDuration(MOTION.chrome_fade_ms)
        self._chrome_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._chrome_anim.finished.connect(self._on_chrome_anim_done)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(MOTION.chrome_hide_delay_ms)
        self._hide_timer.timeout.connect(self._maybe_hide_chrome)
        self.popover: StylePopover | None = None

        # Click-through help (user feedback G1): the window gets no mouse events while
        # click-through is on, so the cursor is polled to show how to turn it off.
        self.click_through_hint = QLabel(self)
        self.click_through_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.click_through_hint.hide()
        self._hint_timer = QTimer(self)
        self._hint_timer.setInterval(CURSOR_POLL_MS)
        self._hint_timer.timeout.connect(self._update_click_through_hint)
        self._was_click_through = False
        self._toast: Toast | None = None

        # Performance readout (T093): a small line under the chat, when turned on in Settings.
        self.readout = ReadoutStrip(controller.store, self)
        # Problem line (T111; spec §9): e.g. "No microphone found…", hidden when all is well.
        self.status_strip = StatusStrip(controller.store, self)
        self.status_strip.hide()
        self.status_strip.changed.connect(self._on_status)
        controller.store.config_changed.connect(self._on_config_section)

        controller.store.window_changed.connect(self._on_window_changed)
        self.apply_config(cfg)
        self._apply_readout()

    # ------------------------------------------------------------ store -> window

    @property
    def config(self) -> WindowConfig | None:
        return self._controller.store.state.config.window(self.window_id)

    def _on_config_section(self, section: str) -> None:
        if section in ("performance", "all"):
            self._apply_readout()

    def _apply_readout(self) -> None:
        shown = self._controller.store.state.config.performance.show_readout
        self.readout.setVisible(shown)
        self._layout_children()

    def _on_window_changed(self, window_id: str) -> None:
        if window_id == self.window_id:
            cfg = self.config
            if cfg is not None:
                self.apply_config(cfg)

    def apply_config(self, cfg: WindowConfig) -> None:
        style = cfg.style
        self.palette_value = palette_for(style.palette_id, style.custom_seed, style.custom_dark)
        self.chrome.set_state(self.palette_value, cfg)
        self.content.set_view(self.palette_value, cfg)
        self.new_lines.setStyleSheet(pill_qss(self.palette_value))
        self.readout.apply_palette(self.palette_value)
        self.status_strip.apply_palette(self.palette_value)
        self.new_lines.setIcon(icon("arrow-down", self.palette_value, "on_accent"))
        self.setWindowOpacity(style.window_opacity)
        self.setToolTip(f"Live Translator: {language(cfg.target_lang).english}")
        if cfg.geometry is not None and self._drag is None:
            target = qrect_from_rect(
                Rect(cfg.geometry.x, cfg.geometry.y, cfg.geometry.width, cfg.geometry.height)
            )
            if self.geometry() != target:
                self.setGeometry(target)
        if cfg.locked:
            self.unsetCursor()
        if cfg.click_through:
            self._set_chrome_visible(False, animate=False)
        self._apply_click_through_help(cfg)
        self._apply_native(cfg)
        self.update()

    def _apply_native(self, cfg: WindowConfig) -> None:
        """Pin and click-through live on the native window, so they need a shown HWND.

        Applied only when they change: SetWindowPos(TOPMOST) re-raises the window, which
        used to cover the open style popover on every setting change (G1 feedback).
        """
        if not self.isVisible():
            return
        wanted = (cfg.pinned, cfg.click_through)
        if wanted == self._native:
            return
        hwnd = int(self.winId())
        win32.set_topmost(hwnd, cfg.pinned)
        win32.set_click_through(hwnd, cfg.click_through)
        self._native = wanted
        if self.popover is not None and self.popover.isVisible():
            self.popover.raise_()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._native = None  # a fresh show needs the flags again
        cfg = self.config
        if cfg is not None:
            self._apply_native(cfg)

    # ------------------------------------------------------------ painting / layout

    # ------------------------------------------------------------ click-through help

    def click_through_message(self) -> str:
        combo = self._controller.store.state.config.hotkeys.get("click_through_all")
        if combo:
            return f"Click-through is on. Press {combo} to turn it off."
        return "Click-through is on. Set a shortcut for it in Settings to turn it off."

    def _apply_click_through_help(self, cfg: WindowConfig) -> None:
        self.click_through_hint.setStyleSheet(badge_qss(self.palette_value))
        self.click_through_hint.setText(self.click_through_message())
        self.click_through_hint.adjustSize()
        self._place_hint()
        if cfg.click_through and not self._was_click_through and self.isVisible():
            anchor = self.mapToGlobal(QPoint(self.width() // 2, 0))
            # Keep a reference: a parentless Toast with none would be garbage-collected
            # (and vanish) immediately. It deletes itself when its timer ends.
            self._toast = Toast(self.click_through_message(), self.palette_value)
            self._toast.show_at(anchor)
        if cfg.click_through:
            self._hint_timer.start()
        else:
            self._hint_timer.stop()
            self.click_through_hint.hide()
        self._was_click_through = cfg.click_through

    def _update_click_through_hint(self) -> None:
        inside = self.geometry().contains(QCursor.pos())
        if inside != self.click_through_hint.isVisible():
            self.click_through_hint.setVisible(inside)
            if inside:
                self.click_through_hint.raise_()

    def _place_hint(self) -> None:
        hint = self.click_through_hint
        hint.move(max((self.width() - hint.width()) // 2, 0), SPACE.sm)

    def _on_unread(self, unread: bool) -> None:
        self.new_lines.setVisible(unread)
        if unread:
            self._place_pill()
            self.new_lines.raise_()

    def _readout_height(self) -> int:
        if not self.readout.isVisibleTo(self):
            return 0
        return self.readout.fontMetrics().height() + 2 * SPACE.xs

    def _status_height(self) -> int:
        if not self.status_strip.isVisibleTo(self):
            return 0
        return max(self.status_strip.text.fontMetrics().height(), WINDOW.icon_size) + 2 * SPACE.xs

    def _footer_height(self) -> int:
        return self._readout_height() + self._status_height()

    def _place_pill(self) -> None:
        pill = self.new_lines
        pill.adjustSize()
        bottom = self.height() - self._footer_height()
        pill.move((self.width() - pill.width()) // 2, bottom - pill.height() - SPACE.sm)

    def _on_status(self) -> None:
        self.status_strip.setVisible(self.status_strip.shown is not None)
        self._layout_children()

    def _layout_children(self) -> None:
        """Chat on top; at the bottom the problem line (T111), then the readout (T093)."""
        readout, status = self._readout_height(), self._status_height()
        self.content.setGeometry(0, 0, self.width(), self.height() - readout - status)
        inner = self.width() - 2 * SPACE.md
        if status:
            top = self.height() - readout - status
            self.status_strip.setGeometry(SPACE.md, top, inner, status)
        if readout:
            self.readout.setGeometry(SPACE.md, self.height() - readout, inner, readout)
        self._place_pill()

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._place_hint()
        self.chrome.setGeometry(0, 0, self.width(), WINDOW.chrome_height)
        self._layout_children()
        super().resizeEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        cfg = self.config
        if cfg is None:
            return
        p = self.palette_value
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(p.bg)
        bg.setAlphaF(max(cfg.style.bg_opacity, MIN_HIT_ALPHA))
        painter.setBrush(bg)
        if self._hovered and not cfg.click_through:
            painter.setPen(QPen(QColor(p.border), WINDOW.border_width))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), RADIUS.md, RADIUS.md)
        painter.end()

    # ------------------------------------------------------------ chrome on hover

    def _set_chrome_visible(self, visible: bool, animate: bool = True) -> None:
        self._chrome_anim.stop()
        if visible:
            self.chrome.show()
            self.chrome.raise_()
        target = 1.0 if visible else 0.0
        if animate:
            self._chrome_anim.setStartValue(self._chrome_effect.opacity())
            self._chrome_anim.setEndValue(target)
            self._chrome_anim.start()
        else:
            self._chrome_effect.setOpacity(target)
            self._on_chrome_anim_done()

    def _on_chrome_anim_done(self) -> None:
        if self._chrome_effect.opacity() == 0.0:
            self.chrome.hide()

    def enterEvent(self, event: QEnterEvent) -> None:
        self._hovered = True
        self._hide_timer.stop()
        cfg = self.config
        if cfg is not None and not cfg.click_through:
            self._set_chrome_visible(True)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hide_timer.start()
        super().leaveEvent(event)

    def _maybe_hide_chrome(self) -> None:
        popover_open = self.popover is not None and self.popover.isVisible()
        if popover_open or self.geometry().contains(QCursor.pos()) or self._drag is not None:
            self._hide_timer.start()
            return
        self._hovered = False
        self._set_chrome_visible(False)
        self.update()

    # ------------------------------------------------------------ move / resize / wheel

    def mousePressEvent(self, event: QMouseEvent) -> None:
        cfg = self.config
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()  # T104 click vs. drag
        if event.button() != Qt.MouseButton.LeftButton or cfg is None or cfg.locked:
            super().mousePressEvent(event)
            return
        pos = event.position().toPoint()
        self._drag = _Drag(
            edges=edges_at(self.width(), self.height(), pos.x(), pos.y()),
            start_global=event.globalPosition().toPoint(),
            start_rect=rect_from_qrect(self.geometry()),
        )
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag is None:
            cfg = self.config
            pos = event.position().toPoint()
            edges = (
                0
                if cfg is None or cfg.locked
                else edges_at(self.width(), self.height(), pos.x(), pos.y())
            )
            if edges:
                self.setCursor(_CURSORS[edges])
            elif self.renamable_label_at(pos) is not None:
                self.setCursor(Qt.CursorShape.PointingHandCursor)  # T104: click to rename
            else:
                self.unsetCursor()
            return
        delta = event.globalPosition().toPoint() - self._drag.start_global
        if self._drag.edges:
            rect = resize_rect(self._drag.start_rect, self._drag.edges, delta.x(), delta.y())
        else:
            moved = self._drag.start_rect.moved(delta.x(), delta.y())
            work_areas = [m.work for m in monitors()]
            rect = snap(moved, work_areas, self._snap_targets(self.window_id))
        self.setGeometry(qrect_from_rect(rect))
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._is_click(event):
            uid = self.renamable_label_at(event.position().toPoint())
            if uid is not None:
                self._drag = None  # nothing moved: no geometry to save
                self.open_rename(uid)
                event.accept()
                return
        if self._drag is None or event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        self._drag = None
        rect = rect_from_qrect(self.geometry())
        screens = monitors()
        screen = monitor_for(rect, screens).name if screens else ""
        self._controller.set_geometry(self.window_id, rect, screen)
        event.accept()

    # ------------------------------------------------------------ speaker rename (T104)

    def _is_click(self, event: QMouseEvent) -> bool:
        if self._press_global is None:
            return False
        moved = event.globalPosition().toPoint() - self._press_global
        self._press_global = None
        return moved.manhattanLength() < QApplication.startDragDistance()

    def renamable_label_at(self, pos: QPoint) -> str | None:
        """Utterance id under `pos` (window coordinates) if its speaker can be renamed (the
        catch-all "Others" label can't: it isn't one person)."""
        uid = self.content.label_at(QPointF(self.content.mapFrom(self, pos)))
        if uid is None:
            return None
        utterance = self._controller.store.state.session.utterance(uid)
        if utterance is None or utterance.speaker_id == OTHERS_ID:
            return None
        return uid

    def open_rename(self, utterance_id: str) -> None:
        state = self._controller.store.state
        utterance = state.session.utterance(utterance_id)
        rect = next((r for r, uid in self.content.label_hits if uid == utterance_id), None)
        if utterance is None or rect is None:
            return
        speaker = utterance.speaker_id
        popup = RenamePopup(
            speaker_label(state, speaker), automatic_label(state, speaker), self.palette_value
        )
        popup.renamed.connect(lambda name: self._controller.rename_speaker(speaker, name))
        self.rename_popup = popup
        popup.open_at(self.content.mapToGlobal(rect.topLeft().toPoint()))

    def wheelEvent(self, event: QWheelEvent) -> None:
        cfg = self.config
        if cfg is None:
            super().wheelEvent(event)
            return
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            notches = event.angleDelta().y() / 120  # T062: plain wheel scrolls the chat
            self.content.scroll_by(notches * self.content.wheel_step())
            event.accept()
            return
        step = 1 if event.angleDelta().y() > 0 else -1
        size = min(max(cfg.style.font_size + step, FONTS.overlay_size_min), FONTS.overlay_size_max)
        if size != cfg.style.font_size:
            self._controller.set_style(self.window_id, font_size=size)
        event.accept()

    # ------------------------------------------------------------ popover / menu

    def open_style_popover(self) -> None:
        if self.popover is None:
            self.popover = StylePopover(self._controller, self.window_id, self)
        self.popover.refresh()
        self.popover.adjustSize()
        anchor = self.chrome.style_button.mapToGlobal(QPoint(0, self.chrome.style_button.height()))
        wanted = Rect(
            anchor.x(), anchor.y() + SPACE.xs, self.popover.width(), self.popover.height()
        )
        screens = monitors()
        if screens:
            wanted = clamp_into(wanted, monitor_for(wanted, screens).work)
        self.popover.move(wanted.x, wanted.y)
        self.popover.show()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(window_qss(self.palette_value))
        menu.addAction("Style…", self.open_style_popover)
        menu.addAction("New window", self.new_window_requested.emit)
        menu.addSeparator()
        menu.addAction("Hide this window", lambda: self.hide_requested.emit(self.window_id))
        menu.addAction("Close this window", lambda: self._controller.remove_window(self.window_id))
        menu.addSeparator()
        menu.addAction("Translate a screen region…", self.screen_region_requested.emit)
        menu.addAction("Transcript…", self.transcript_requested.emit)
        menu.addAction("Settings…", self.settings_requested.emit)
        menu.addAction("Quit Live Translator", self.quit_requested.emit)
        menu.exec(event.globalPos())

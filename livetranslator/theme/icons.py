"""Icons: QtAwesome with the Phosphor set only (T012; spec §6.5).

Callers pass a bare Phosphor name (e.g. "push-pin") and a palette role; colours always come
from the palette. Other QtAwesome sets (Font Awesome, MDI, Codicons...) are deliberately not
reachable from here, which keeps the look consistent and lets packaging strip their fonts.
"""

from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon

from livetranslator.theme.tokens import Palette

os.environ.setdefault("QT_API", "pyside6")  # QtAwesome uses QtPy; pin it to PySide6
_qta: Any = importlib.import_module("qtawesome")  # untyped package

PREFIX = "ph"
IconRole = Literal["text_primary", "text_secondary", "accent", "on_accent", "danger", "ok"]


def _qualified(name: str) -> str:
    if "." in name:
        raise ValueError(f"pass a bare Phosphor icon name such as 'push-pin', not {name!r}")
    return f"{PREFIX}.{name}"


def icon(
    name: str,
    palette: Palette,
    role: IconRole = "text_primary",
    *,
    active_role: IconRole | None = None,
) -> QIcon:
    """A Phosphor icon coloured from `palette` (needs a QApplication).

    `active_role` colours the hover/pressed state; disabled icons use text_secondary.
    """
    color: str = getattr(palette, role)
    active: str = getattr(palette, active_role or role)
    try:
        result: QIcon = _qta.icon(
            _qualified(name),
            color=color,
            color_active=active,
            color_disabled=palette.text_secondary,
        )
    except ValueError:
        raise
    except Exception as exc:  # QtAwesome raises a bare Exception for unknown names
        raise ValueError(f"unknown Phosphor icon {name!r}") from exc
    return result


def has_icon(name: str) -> bool:
    try:
        _qta.icon(_qualified(name))
    except Exception:
        return False
    return True


ICON_CACHE = Path(tempfile.gettempdir()) / "LiveTranslator" / "icons"


def icon_file(name: str, palette: Palette, role: IconRole, size: int) -> Path:
    """The icon rendered to a PNG (QSS can only load images from files, e.g. a combobox
    arrow). Cached per name/colour/size; needs a QApplication."""
    color: str = getattr(palette, role)
    path = ICON_CACHE / f"{name}-{color.lstrip('#')}-{size}.png"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        icon(name, palette, role).pixmap(QSize(size, size)).save(str(path))
    return path

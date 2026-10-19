"""The app loads all of its own screens at startup (2026-10-18: Settings was imported only when
first opened, picked up newer code from disk while the app ran, and failed with an
ImportError). Heavy third-party engines may still load lazily."""

import ast
from pathlib import Path

import livetranslator.app.application as application


def test_application_imports_its_screens_at_module_level():
    tree = ast.parse(Path(application.__file__).read_text(encoding="utf-8"))
    late = [
        f"line {node.lineno}: {node.module}"
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef)
        for node in ast.walk(function)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("livetranslator.ui")
    ]
    assert late == []

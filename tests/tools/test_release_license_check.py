"""T113 — release licence check on fixture build folders."""

from pathlib import Path

from tools.release_license_check import LICENSES_DIR, REQUIRED_NOTICES, THIRD_PARTY, main, scan


def clean_build(root: Path) -> Path:
    build = root / "LiveTranslator"
    (build / "PySide6").mkdir(parents=True)
    for dll in ("Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll"):
        (build / "PySide6" / dll).write_bytes(b"")
    fonts = build / "qtawesome" / "fonts"
    fonts.mkdir(parents=True)
    (fonts / "phosphor-1.3.0.ttf").write_bytes(b"")
    (build / "cv2").mkdir()
    (build / "cv2" / "cv2.pyd").write_bytes(b"")
    (build / LICENSES_DIR).mkdir()
    for notice in REQUIRED_NOTICES:
        (build / LICENSES_DIR / notice).write_text("text", encoding="utf-8")
    (build / THIRD_PARTY).write_text("# list", encoding="utf-8")
    return build


def test_a_clean_build_passes(tmp_path: Path, capsys):
    build = clean_build(tmp_path)
    assert scan(build) == []
    assert main([str(build)]) == 0
    assert "0 blocking" in capsys.readouterr().out


def test_each_problem_is_caught(tmp_path: Path):
    build = clean_build(tmp_path)
    (build / "PySide6" / "Qt6Charts.dll").write_bytes(b"")  # GPL-only module
    (build / "PySide6" / "Qt6Quick3DPhysics.dll").write_bytes(b"")
    (build / "av").mkdir()  # PyAV
    (build / "av" / "libx264-164.dll").write_bytes(b"")
    (build / "cv2" / "opencv_videoio_ffmpeg4140_64.dll").write_bytes(b"")
    (build / "qtawesome" / "fonts" / "fontawesome6-solid-webfont-6.7.2.ttf").write_bytes(b"")
    (build / LICENSES_DIR / "GPL-3.0.txt").unlink()
    (build / THIRD_PARTY).unlink()
    found = {(f.path, f.blocking) for f in scan(build)}
    assert ("PySide6/Qt6Charts.dll", True) in found
    assert ("PySide6/Qt6Quick3DPhysics.dll", True) in found
    assert ("av", True) in found and ("av/libx264-164.dll", True) in found
    assert ("cv2/opencv_videoio_ffmpeg4140_64.dll", True) in found
    assert ("qtawesome/fonts/fontawesome6-solid-webfont-6.7.2.ttf", True) in found
    assert (f"{LICENSES_DIR}/GPL-3.0.txt", True) in found
    assert (THIRD_PARTY, True) in found
    assert main([str(build)]) == 1


def test_nvidia_dlls_only_warn(tmp_path: Path, capsys):
    build = clean_build(tmp_path)
    (build / "ctranslate2").mkdir()
    (build / "ctranslate2" / "cublas64_12.dll").write_bytes(b"")
    findings = scan(build)
    assert [(f.path, f.blocking) for f in findings] == [("ctranslate2/cublas64_12.dll", False)]
    assert main([str(build)]) == 0
    assert "warn" in capsys.readouterr().out


def test_not_a_folder(tmp_path: Path):
    assert main([str(tmp_path / "missing")]) == 2

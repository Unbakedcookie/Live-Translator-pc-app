"""T113 — third-party notices stay in step with what's installed; every package has its text."""

from pathlib import Path

from tools.release_license_check import REQUIRED_NOTICES
from tools.third_party import collect_texts, main, package_texts, shipped_packages


def test_notices_are_up_to_date():
    """If this fails after a dependency change: python -m tools.third_party."""
    assert main(["--check"]) == 0


def test_every_shipped_package_has_a_licence_text_and_the_build_gets_them(tmp_path: Path):
    packages = shipped_packages()
    assert len(packages) > 50
    assert [p.name for p in packages if not package_texts(p.name)] == []
    dest = tmp_path / "licenses"
    assert collect_texts(dest, packages) == []
    for notice in REQUIRED_NOTICES:  # what the release check demands
        assert (dest / notice).is_file(), notice
    assert (dest / "packages" / "ctranslate2" / "ctranslate2.txt").is_file()  # kept by hand
    assert (dest / "packages" / "winrt-runtime" / "winrt.txt").is_file()  # by prefix
    assert any((dest / "packages" / "numpy").iterdir())  # the wheel's own file

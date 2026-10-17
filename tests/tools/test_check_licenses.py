"""T010 — license gate (Tier A). Expected verdicts are hand-written from spec §10.1."""

from pathlib import Path

import pytest
from packaging.requirements import Requirement

from tools.check_licenses import (
    LicenseRecord,
    Override,
    evaluate,
    load_overrides,
    load_policy,
    parse_requirements,
    runtime_closure,
)

POLICY = load_policy(Path(__file__).resolve().parents[2] / "tools" / "license_policy.toml")


def verdict(
    name: str,
    *,
    expression: str = "UNKNOWN",
    classifier: str = "UNKNOWN",
    meta: str = "UNKNOWN",
    override: Override | None = None,
):
    return evaluate(LicenseRecord(name, expression, classifier, meta), POLICY, override)


# ---------------------------------------------------------------- classification


def test_mit_passes():
    assert verdict("foo", expression="MIT").ok


def test_gpl_fails_with_reason():
    v = verdict("foo", expression="GPL-3.0-only")
    assert not v.ok
    assert v.reason == "not on the allow-list: GPL-3.0-only"


def test_lgpl_allowed_only_for_pyside6_essentials():
    assert verdict("PySide6_Essentials", expression="LGPL-3.0-only").ok
    v = verdict("foo", expression="LGPL-3.0-only")
    assert not v.ok
    assert v.reason == "LGPL is only allowed for pyside6-essentials, shiboken6"


def test_pyside6_real_expression():
    expr = "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only"  # PyPI 6.12.0 (D-021)
    assert verdict("shiboken6", expression=expr).ok
    assert not verdict("pyside6-addons", expression=expr).ok


def test_or_and_semantics():
    assert verdict("packaging", expression="Apache-2.0 OR BSD-2-Clause").ok
    assert not verdict("foo", expression="MIT AND GPL-2.0-only").ok
    assert verdict("foo", expression="(MIT OR GPL-2.0-only) AND BSD-3-Clause").ok
    assert not verdict("foo", expression="(GPL-3.0-only OR AGPL-3.0-only) AND MIT").ok


def test_with_exception_judged_on_base_license():
    assert not verdict("pyinstaller", expression="GPL-2.0-or-later WITH Bootloader-exception").ok
    assert verdict("foo", expression="Apache-2.0 WITH LLVM-exception").ok


def test_non_commercial_fails():
    assert not verdict("model", expression="CC-BY-NC-4.0").ok


def test_expression_preferred_over_classifier():
    v = verdict("foo", expression="MIT", classifier="GNU General Public License v3 (GPLv3)")
    assert v.ok
    assert v.reason == "allowed (expression)"


def test_classifiers_all_must_pass():
    assert verdict("foo", classifier="MIT License; BSD License").ok
    v = verdict("foo", classifier="MIT License; GNU General Public License v3 (GPLv3)")
    assert not v.ok
    assert v.reason == "not on the allow-list: GPL-3.0"


def test_metadata_alias_and_full_text():
    assert verdict("foo", meta="Apache License 2.0").ok
    long_text = "Permission is hereby granted, free of charge, " * 5
    v = verdict("foo", meta=long_text)
    assert not v.ok
    assert v.license == "UNKNOWN"


def test_free_text_name_is_one_unknown_license():
    v = verdict("foo", meta="Some Custom License")
    assert not v.ok
    assert v.reason == "not on the allow-list: Some Custom License"


def test_unparseable_expression_fails():
    v = verdict("foo", expression="MIT OR")
    assert not v.ok
    assert v.reason.startswith("cannot parse license")


def test_unknown_fails_until_override():
    assert not verdict("materialyoucolor").ok
    ov = Override("materialyoucolor", "MIT", "D-022", "LICENSE file in wheel is MIT")
    v = verdict("materialyoucolor", override=ov)
    assert v.ok
    assert v.reason == "allowed (override D-022)"


def test_override_cannot_launder_gpl():
    ov = Override("foo", "GPL-3.0-only", "D-022", "wrong")
    assert not verdict("foo", expression="MIT", override=ov).ok


# ---------------------------------------------------------------- overrides file


def test_override_requires_tracker_id(tmp_path: Path):
    bad = tmp_path / "o.toml"
    bad.write_text(
        '[[override]]\npackage = "x"\nlicense = "MIT"\ntracker = "see chat"\nreason = "r"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="DATA_TRACKER id"):
        load_overrides(bad)


def test_override_missing_field(tmp_path: Path):
    bad = tmp_path / "o.toml"
    bad.write_text('[[override]]\npackage = "x"\nlicense = "MIT"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="missing tracker, reason"):
        load_overrides(bad)


def test_override_loaded_and_normalised(tmp_path: Path):
    good = tmp_path / "o.toml"
    good.write_text(
        '[[override]]\npackage = "Foo_Bar"\nlicense = "MIT"\ntracker = "D-022"\nreason = "r"\n',
        encoding="utf-8",
    )
    assert load_overrides(good) == {"foo-bar": Override("foo-bar", "MIT", "D-022", "r")}


def test_missing_override_file_is_empty(tmp_path: Path):
    assert load_overrides(tmp_path / "none.toml") == {}


# ---------------------------------------------------------------- requirements + closure


def test_parse_requirements_skips_noise():
    text = "# comment\n\n-r other.txt\nPySide6-Essentials==6.12.0  # UI\nloguru>=0.7\n"
    assert [str(r) for r in parse_requirements(text)] == [
        "PySide6-Essentials==6.12.0",
        "loguru>=0.7",
    ]


INSTALLED: dict[str, list[str]] = {
    "app": ["a", 'b[fast]; python_version >= "3.8"'],
    "a": ["c", 'linux-only; sys_platform == "linux"'],
    "b": ['speedup; extra == "fast"', 'docs-tool; extra == "docs"'],
    "c": [],
    "speedup": [],
    "devtool": ["c"],  # installed, but not reachable from the runtime roots
    "docs-tool": [],
    "linux-only": [],
}


def test_closure_follows_extras_and_markers():
    closure, missing = runtime_closure([Requirement("app")], INSTALLED.get)
    # Hand-derived: app -> a, b[fast]; a -> c (linux-only skipped on Windows);
    # b[fast] -> speedup (docs-tool needs extra "docs").
    assert closure == {"app", "a", "b", "c", "speedup"}
    assert missing == set()


def test_closure_excludes_dev_tools():
    closure, _ = runtime_closure([Requirement("app")], INSTALLED.get)
    assert "devtool" not in closure


def test_closure_reports_missing():
    closure, missing = runtime_closure([Requirement("app"), Requirement("ghost")], INSTALLED.get)
    assert missing == {"ghost"}
    assert "ghost" not in closure


def test_closure_normalises_names():
    installed = {"pyside6-essentials": ["shiboken6==6.12.0"], "shiboken6": []}
    closure, _ = runtime_closure([Requirement("PySide6_Essentials")], installed.get)
    assert closure == {"pyside6-essentials", "shiboken6"}


def test_root_marker_false_is_skipped():
    closure, _ = runtime_closure([Requirement('app; sys_platform == "darwin"')], INSTALLED.get)
    assert closure == set()


def test_excluded_packages_need_a_tracker_id(tmp_path: Path):
    # T045: av is installed by faster-whisper but never shipped (D-027).
    assert POLICY.excluded == {"av": "D-027"}
    policy = tmp_path / "policy.toml"
    policy.write_text(
        'allowed = ["MIT"]\nlgpl_ids = []\nlgpl_packages = []\n[excluded]\nPyAV_Thing = "later"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="DATA_TRACKER id"):
        load_policy(policy)
    policy.write_text(
        'allowed = ["MIT"]\nlgpl_ids = []\nlgpl_packages = []\n[excluded]\nPyAV_Thing = "D-027"\n',
        encoding="utf-8",
    )
    assert load_policy(policy).excluded == {"pyav-thing": "D-027"}

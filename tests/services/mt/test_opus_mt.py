"""T051 — Opus-MT adapter: model discovery, contract errors, and (when the converted models
are on this PC) real translations + unload."""

import json
import os
from pathlib import Path

import pytest

from livetranslator.services.errors import EngineNotLoaded, UnsupportedLanguage
from livetranslator.services.mt.base import TranslationEngine
from livetranslator.services.mt.engines.opus_mt import OpusMtEngine, installed_pairs
from livetranslator.services.mt.router import TranslationRouter

BENCH_MODELS = Path(os.environ.get("LT_BENCH_DIR", r"D:\LiveTranslator\bench-data")) / "models"
HAVE_MODELS = (BENCH_MODELS / "opus-mt" / "en-es" / "model.bin").is_file()


def fake_pair(root: Path, name: str, tag: str = "", model: bool = True) -> None:
    folder = root / "opus-mt" / name
    folder.mkdir(parents=True)
    if model:
        (folder / "model.bin").write_bytes(b"")
    (folder / "opus_mt.json").write_text(json.dumps({"language_tag": tag}), encoding="utf-8")


def test_discovers_complete_pair_folders_only(tmp_path: Path):
    fake_pair(tmp_path, "en-zh", ">>cmn_Hans<<")
    fake_pair(tmp_path, "ja-en")
    fake_pair(tmp_path, "en-de", model=False)  # interrupted download: ignored
    (tmp_path / "opus-mt" / "notes").mkdir()
    pairs = installed_pairs(tmp_path)
    assert sorted(pairs) == [("en", "zh"), ("ja", "en")]
    assert pairs[("en", "zh")].language_tag == ">>cmn_Hans<<"
    assert installed_pairs(tmp_path / "missing") == {}


def test_contract_errors(tmp_path: Path):
    fake_pair(tmp_path, "ja-en")
    engine = OpusMtEngine(tmp_path, device="cpu")
    assert isinstance(engine, TranslationEngine)
    assert engine.supports("ja", "en") and not engine.supports("en", "ja")
    with pytest.raises(EngineNotLoaded):
        engine.translate(["こんにちは"], "ja", "en")
    with pytest.raises(UnsupportedLanguage):
        engine.translate(["hi"], "en", "ja")
    engine.load()
    assert engine.is_loaded and engine.device == "cpu"
    engine.unload()
    assert not engine.is_loaded


@pytest.mark.skipif(not HAVE_MODELS, reason="converted Opus-MT models not on this PC")
def test_real_models_translate_and_pivot():
    engine = OpusMtEngine(BENCH_MODELS, device="cpu")
    engine.load()
    try:
        out = engine.translate(["Wait for me at the gate.", "Thank you!"], "en", "es")
        assert len(out) == 2 and all(o.strip() for o in out)
        assert "puerta" in out[0].lower()
        router = TranslationRouter([engine])
        korean = router.translate("わかった、門で待ってて。", "ja", "ko")  # ja -> en -> ko
        assert any("\uac00" <= ch <= "\ud7a3" for ch in korean)  # Hangul syllables
        assert "\u2047" not in korean  # no "⁇" unknown pieces (the broken HF en-ko port)
    finally:
        engine.unload()
    assert not engine.is_loaded

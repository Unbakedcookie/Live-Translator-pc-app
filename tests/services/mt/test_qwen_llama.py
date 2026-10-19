# ruff: noqa: RUF001  (real Chinese punctuation on purpose)
"""Qwen through llama-server (Mandarin follow-up): helpers, routing preference, fallback, and
a real run when the files are on this PC."""

import os
from collections.abc import Sequence
from pathlib import Path

import pytest

from livetranslator.core.presets import effective
from livetranslator.core.state import AppConfig, EngineConfig, PerformanceConfig
from livetranslator.services.errors import EngineError, EngineNotLoaded
from livetranslator.services.mt.engines.qwen_llama import (
    MODEL_FILE,
    SERVER_DIR,
    SERVER_EXE,
    QwenLlamaEngine,
    clean_reply,
    installed,
)
from livetranslator.services.mt.router import TranslationRouter


def test_clean_reply():
    assert clean_reply("  Your microphone is loud.  ") == "Your microphone is loud."
    assert clean_reply("Translation: hi") == "hi"
    assert clean_reply('"Good night."') == "Good night."
    assert clean_reply("翻译：晚安") == "晚安"
    assert clean_reply("'quoted' inside") == "'quoted' inside"  # only wrapping quotes go


def test_not_installed(tmp_path: Path):
    engine = QwenLlamaEngine(tmp_path)
    assert not installed(tmp_path)
    assert not engine.supports("zh", "en")  # nothing installed: never preferred
    with pytest.raises(EngineNotLoaded):
        engine.load()
    (tmp_path / SERVER_DIR).mkdir(parents=True)
    (tmp_path / SERVER_DIR / SERVER_EXE).write_bytes(b"")
    (tmp_path / MODEL_FILE).parent.mkdir(parents=True)
    (tmp_path / MODEL_FILE).write_bytes(b"")
    assert installed(tmp_path)
    assert engine.supports("zh", "en") and not engine.supports("zh", "zh")
    assert not engine.supports("xx", "en")


def test_game_mode_turns_smart_translation_off():
    on = AppConfig(engines=EngineConfig(smart_languages=("zh",)))
    assert effective(on).smart_languages == {"zh"}
    gaming = on.model_copy(update={"performance": PerformanceConfig(game_mode=True)})
    assert effective(gaming).smart_languages == frozenset()
    assert effective(AppConfig()).smart_languages == {"zh"}  # Chinese on by default
    off = AppConfig(engines=EngineConfig(smart_languages=()))
    assert effective(off).smart_languages == frozenset()


class Fake:
    def __init__(self, name: str, pairs: set[tuple[str, str]], fail: bool = False) -> None:
        self.name = name
        self.pairs = pairs
        self.fail = fail
        self.is_loaded = True

    def supports(self, src: str, tgt: str) -> bool:
        return (src, tgt) in self.pairs

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    def translate(self, texts: Sequence[str], src: str, tgt: str) -> list[str]:
        if self.fail:
            raise EngineError("server gone")
        return [f"{self.name}:{t}" for t in texts]


def test_preferred_engine_for_chosen_languages_with_fallback():
    opus = Fake("opus", {("zh", "en"), ("es", "en")})
    qwen = Fake("qwen", {("zh", "en"), ("es", "en")})
    wanted = {"zh"}
    router = TranslationRouter(
        [opus], preferred=lambda s, t: qwen if s in wanted or t in wanted else None
    )
    assert router.translate("你好", "zh", "en") == "qwen:你好"
    assert router.translate("hola", "es", "en") == "opus:hola"  # not a chosen language
    qwen.fail = True
    assert router.translate("再见", "zh", "en") == "opus:再见"  # Qwen down: still translated
    opus.fail = True
    with pytest.raises(EngineError):
        router.translate("谢谢", "zh", "en")  # both failed: reported as usual


BENCH = Path(os.environ.get("LT_BENCH_DIR", r"D:\LiveTranslator\bench-data")) / "models"


@pytest.mark.skipif(
    not installed(Path(os.environ.get("LOCALAPPDATA", "")) / "LiveTranslator" / "models"),
    reason="Qwen files not installed on this PC",
)
def test_real_qwen_translates_chinese_gaming_slang():
    models = Path(os.environ["LOCALAPPDATA"]) / "LiveTranslator" / "models"
    engine = QwenLlamaEngine(models)
    try:
        engine.load()
        out = engine.translate(
            ["你的麦有点吵，能不能调小一点", "明天晚上八点继续开黑吧"], "zh", "en"
        )
    finally:
        engine.unload()
    assert "mic" in out[0].lower()
    assert "8" in out[1] and "dark" not in out[1].lower()
    assert not engine.is_loaded  # the server process is gone


@pytest.mark.skipif(
    not installed(Path(os.environ.get("LOCALAPPDATA", "")) / "LiveTranslator" / "models"),
    reason="Qwen files not installed on this PC",
)
def test_real_qwen_covers_languages_without_an_opus_model():
    """The fallback languages from the user's log (2026-10-18). load() warms the server, so
    the first line isn't the ~10 s first request."""
    import time

    engine = QwenLlamaEngine(Path(os.environ["LOCALAPPDATA"]) / "LiveTranslator" / "models")
    try:
        engine.load()
        start = time.perf_counter()
        pt = engine.translate(["Estou sem munição."], "pt", "en")[0]
        first_line_s = time.perf_counter() - start
        hi = engine.translate(["भाई, मेरा माइक काम नहीं कर रहा है।"], "hi", "en")[0]
        sv = engine.translate(["Kan du ge mig lite hälsa?"], "sv", "en")[0]
    finally:
        engine.unload()
    assert "ammo" in pt.lower() or "ammunition" in pt.lower()
    assert "mic" in hi.lower()
    assert "health" in sv.lower()
    assert first_line_s < 3.0


QWEN_MODELS = Path(os.environ.get("LOCALAPPDATA", "")) / "LiveTranslator" / "models"


@pytest.mark.skipif(not installed(QWEN_MODELS), reason="Qwen files not installed on this PC")
def test_server_dies_with_a_crashed_app(tmp_path: Path):
    """The llama-server is tied to the app with a Windows job object: a crash (no cleanup)
    must not leave it running with ~2.8 GB of graphics memory."""
    import subprocess  # nosec B404 - runs our own interpreter and Windows tasklist
    import sys
    import time

    script = tmp_path / "crash.py"
    script.write_text(
        "import os\n"
        "from pathlib import Path\n"
        "from livetranslator.services.mt.engines.qwen_llama import QwenLlamaEngine\n"
        f"e = QwenLlamaEngine(Path(r'{QWEN_MODELS}'))\n"
        "e.load()\n"
        "print(e._proc.pid, flush=True)\n"
        "os._exit(1)\n",
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parents[3]
    run = subprocess.run(  # nosec B603 - our own interpreter and script
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=root,
        timeout=180,
        env={**os.environ, "PYTHONPATH": str(root)},
    )
    pid = int(run.stdout.strip().splitlines()[-1])
    time.sleep(1.5)
    tasks = subprocess.run(  # nosec B603 B607 - Windows tasklist
        ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True
    )
    assert str(pid) not in tasks.stdout

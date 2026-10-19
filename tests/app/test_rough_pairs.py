"""D-039: a downloaded model that's weak on chat (Hindi, Urdu) goes after Qwen while Qwen is on;
in game mode (Qwen off) the model still translates."""

import json
from collections.abc import Sequence
from pathlib import Path

from livetranslator.app.application import build_translation
from livetranslator.core import actions as a
from livetranslator.core.state import AppState
from livetranslator.core.store import Store
from livetranslator.services.mt.engines.opus_mt import OpusMtEngine


class FakeQwen:
    name = "qwen"
    is_loaded = True

    def supports(self, src: str, tgt: str) -> bool:
        return src != tgt

    def translate(self, texts: Sequence[str], src: str, tgt: str) -> list[str]:
        return [f"qwen:{t}" for t in texts]


def fake_pair(models: Path, src: str, tgt: str) -> None:
    folder = models / "opus-mt" / f"{src}-{tgt}"
    folder.mkdir(parents=True)
    (folder / "model.bin").write_bytes(b"")
    (folder / "opus_mt.json").write_text(json.dumps({"language_tag": ""}), encoding="utf-8")


def test_rough_pairs_go_to_qwen_only_while_it_is_allowed(tmp_path: Path):
    fake_pair(tmp_path, "hi", "en")
    fake_pair(tmp_path, "de", "en")
    store = Store(AppState())
    controller = build_translation(
        store,
        OpusMtEngine(tmp_path, device="cpu"),
        smart=FakeQwen(),  # type: ignore[arg-type]
        rough=frozenset({("hi", "en")}),
    )
    router = controller.worker._router  # pyright: ignore[reportPrivateUsage]
    assert [s.engine.name for s in router.route("hi", "en")] == ["qwen"]
    assert [s.engine.name for s in router.route("de", "en")] == ["opus-mt"]  # a good model
    store.dispatch(a.UpdateConfigSection("performance", {"game_mode": True}))
    assert [s.engine.name for s in router.route("hi", "en")] == ["opus-mt"]  # Qwen is off
    store.dispatch(a.UpdateConfigSection("performance", {"game_mode": False}))
    store.dispatch(a.UpdateConfigSection("engines", {"smart_fallback": False}))
    assert [s.engine.name for s in router.route("hi", "en")] == ["opus-mt"]  # user said no
    controller.stop()

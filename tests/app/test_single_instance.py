"""Starting the app again shows the running copy's windows instead of a second copy."""

import subprocess  # nosec B404
import sys
import uuid
from pathlib import Path

from livetranslator.app.single_instance import SingleInstance, server_name


def test_name_is_per_user_and_pipe_safe():
    name = server_name("LiveTranslator")
    assert name.startswith("LiveTranslator-")
    assert all(c.isalnum() or c in "_-" for c in name)
    one = server_name("LiveTranslator", Path("D:/a/config"))
    assert one == server_name("LiveTranslator", Path("d:/A/config"))  # same folder, same app
    assert one != server_name("LiveTranslator", Path("D:/b/config"))  # a test profile apart


def ask_from_another_process(name: str) -> subprocess.Popen[bytes]:
    """The second copy is a real separate process, as when the shortcut is clicked again."""
    code = "\n".join(
        (
            "import sys",
            "from PySide6.QtCore import QCoreApplication",
            "from livetranslator.app.single_instance import ask_running_copy_to_show",
            "app = QCoreApplication([])",
            "sys.exit(0 if ask_running_copy_to_show(sys.argv[1]) else 3)",
        )
    )
    return subprocess.Popen([sys.executable, "-c", code, name])  # nosec B603


def test_second_start_asks_the_first_to_show(qtbot):
    name = f"LiveTranslatorTest-{uuid.uuid4().hex}"
    nobody = ask_from_another_process(name)
    assert nobody.wait(30) == 3  # nobody running yet: the new copy starts normally
    shown: list[int] = []
    first = SingleInstance(name, lambda: shown.append(1))
    assert first.listening
    second = ask_from_another_process(name)
    qtbot.waitUntil(lambda: second.poll() is not None, timeout=30000)
    assert second.returncode == 0  # it found the running copy and will exit
    qtbot.waitUntil(lambda: shown == [1])
    first.server.close()

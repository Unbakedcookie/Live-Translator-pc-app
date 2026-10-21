# Live Translator

Live translation for Windows gamers. Small floating windows show what you and the people
you talk to are saying, translated, with who said it. It can also translate text on your
screen, such as game chat. Everything runs on your own PC.

## What you need

- Windows 10 or 11.
- An NVIDIA graphics card is recommended (fast, accurate speech recognition). Without one,
  a smaller speech model runs on the processor.
- About 2 GB of disk space for the basics, about 4 GB with the smarter Qwen translator.

## Install

Run `LiveTranslator-Setup.exe` and follow the steps. The installer is part of the first
release and isn't published yet; until then, see **Running from source** below.

## First run

A setup window walks you through:

1. **Your languages.** *Translate into* is the language you read. *I speak* is what your
   microphone hears: leave it as "Same as above", pick another language you're practising
   (your own lines are then translated too, so you can check yourself), or "Detect any
   language". *I also speak* is for switching between two languages.
2. **Microphone and speakers.** Talk and play some sound: the bars should move.
3. **What to download.** The speech model (sized to your PC), speaker labels, optionally the
   smarter Qwen translator, and language packs. You see the total size and free space.
4. **Download.** One progress bar; you can pause and continue later without losing anything.

Then your first window opens. Everything can be changed later in **Settings** (right-click a
window, click the Live Translator icon by the clock, or start the app again from its icon).

**Keep the icon by the clock visible:** Windows 11 hides new icons behind the **^** arrow next
to the clock. Drag the red Live Translator icon from there onto the taskbar, or turn it on in
**Windows Settings → Personalization → Taskbar → Other system tray icons**. It shows the app's
state: red = listening, grey = paused, a yellow dot = something needs attention.

## Everyday use

- **Windows:** drag to move, drag an edge to resize. Hover to see the top bar: pin (stay on
  top), language, style, minimize, close. Right-click for everything else.
- **Who said it:** *Me* is your microphone; other voices get *Speaker 1*, *Speaker 2*… Click
  a name to rename it for this session. With Discord set up, people's Discord names appear.
- **People talking at once (experimental):** turn on **Settings → Speakers → Separate people
  talking over each other** (a 26 MB download). A line where two people overlapped is split
  into two lines, each with its own name and translation, a few seconds after it ends. It
  works on the processor and pauses in game mode.
- **Language tag:** a line shows e.g. `ZH→EN` when it was translated.
- **Minimize:** the "–" button puts the window on the taskbar; click "Live Translator" there to
  bring it back.

### Shortcuts

| Shortcut | What it does |
|---|---|
| Ctrl+Alt+H | Show or hide all windows (one press always brings hidden ones back) |
| Ctrl+Alt+T | Click-through on/off (clicks go to the game underneath) |
| Ctrl+Alt+P | Pin all windows on top |
| Ctrl+Alt+O | Translate a part of the screen (drag a box) |
| Ctrl+Alt+R | Read the same part of the screen again |
| Ctrl+Alt+M | Mute your microphone |
| Ctrl+Alt+N | Mute the others |
| Ctrl+Alt+G | Game mode (lighter on the graphics card while you play) |

Every shortcut can be changed, and more actions can get one, in **Settings → Hotkeys**. If
Windows or another app already uses a combination, Settings says so.

### Click-through recovery

With click-through on, a window ignores the mouse, so you can't right-click it. To get the
mouse back: press **Ctrl+Alt+T** again, or use the **Click-through** item in the tray menu (the
Live Translator icon by the clock).

### Translating text on the screen

Press **Ctrl+Alt+O**, drag a box around the text (for example the game's chat box), and the
lines appear in a "Screen" window. **Ctrl+Alt+R** reads the same box again and adds only new
lines. Chinese, Japanese and Latin-alphabet languages are read out of the box. Korean and
Cyrillic (e.g. Russian) need Windows' own text-recognition pack for that language (Windows
Settings → Time & language → Language & region → add the language).

### Languages and translation

**Settings → Languages** downloads a language pack (that language to and from English). Other
combinations go through English. With the smarter Qwen translator on, languages without a pack
are still translated, and Chinese uses Qwen for better slang (麦 = mic, 开黑 = play together).
Game mode pauses Qwen to free graphics memory.

## Discord names (optional)

Discord only tells apps who is speaking if you made the app yourself, so you create a free
Discord application once (about 3 minutes). Open **Settings → Speakers → Discord names →
Set up…** and follow the steps:

1. Click **Open**: Discord's developer website opens in your browser (a website, not the
   Discord app). Log in with your normal account.
2. If it asks "What brings you to the Developer Portal?", click **Skip**.
3. Click **New Application**, give it any name, accept the terms, **Create**.
4. Copy the **Application ID** into the setup window.
5. Under **OAuth2 → Redirects**, add `http://127.0.0.1` (the Copy button copies it) and save.
6. Click **Reset Secret**, copy the secret into the setup window.
7. Open the Discord app, join a voice channel, click **Test connection** and approve once.

After that it reconnects by itself. The secret and sign-in are stored encrypted on your PC and
only ever sent to Discord.

## Privacy

- Speech recognition, translation and screen reading all run on your PC. Nothing anyone says
  is sent over the internet. The only downloads are the models.
- Conversations live in memory and are gone when the app closes, unless you export them
  (you're asked when you quit, and the Transcript window can export at any time).
- Log files never contain what anyone said or anyone's name.
- Voices are told apart in memory only; nothing about anyone's voice is saved.

## Licences

Live Translator itself is free and open source under the [MIT License](LICENSE).

Live Translator uses open-source software and models under their own licences, listed in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) and in **Settings → About**. Qt for Python
(PySide6) is used under the LGPL v3.

## Running from source (developers)

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m livetranslator
```

- Python 3.12. `LIVETRANSLATOR_HOME=<folder>` keeps settings, models and logs in one folder
  (a fresh folder shows the setup wizard).
- Tests: `.venv\Scripts\python.exe -m pytest -q`. Lint: `ruff check .`. Types: `pyright`.
- Licence notices: `python -m tools.third_party` (a test fails if they're out of date).
- Project rules and status: `CLAUDE.md`, `TASKS.md`, `project-spec.md`.

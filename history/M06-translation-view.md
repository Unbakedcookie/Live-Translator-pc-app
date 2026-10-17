# M06 — Translation view (gate G2) — narrative

## 2026-10-17 — T061 ChatLine + T062 TranslationView (commit 57c1c8e; user away, autonomous)
**Context.** G1 was approved minutes earlier, which unblocked M06. The user then left ("work until I'm out of tokens") after asking for a push.

**Design forks**
- **One painted widget vs. a widget per line.** I chose one painted widget, with ChatLine as a layout-plus-paint helper rather than a QWidget.
  - 200 child widgets inside a QScrollArea would each need translucent repaints, and partial updates several times a second would re-layout the container. That risks the flicker the acceptance criterion rules out.
  - A single widget with a per-line layout cache only re-measures the line that changed. A test asserts that the other lines' cached rows stay the same object.
- **Where display logic lives.** `core/chat_view.py` is pure: same-language, translated, pending and stale cases, speaker labels, and colour order. The widget only paints, which matches the "UI is presentational" rule.
- **Stale translations.** The store kept only `translations[lang]`, so after a line turned final the view couldn't tell whether the stored translation came from an older partial.
  - Added `Utterance.translated_from[lang]`, set from the new `SetTranslation.source_text`; the TranslationController passes `job.text`.
  - A translation counts as stable only when the line is final and `translated_from == text`.
  - This is session state only, so there is no settings migration. `translated_from` is a fixed field, like `translations`.
- **Pending translation shows the original as "changing"** rather than leaving the line blank. Readers see something at once, and the colour signals that it isn't settled yet.
- **Scroll-back.** The offset is measured from the bottom. When new lines arrive while scrolled up, the offset grows by the added height so the text being read doesn't move. A "New lines" pill (accent, Phosphor arrow-down) sits on the window, not the view: the view is mouse-transparent so dragging works anywhere, and Qt skips children of transparent widgets.
  - The plain wheel scrolls (3 rows per notch); Ctrl+wheel still changes the font size.
- **Speaker colours.** Other speakers are numbered by first appearance in the session, so a person keeps one colour across all windows.
- **Demo feed** (`--demo`). This replaces the G1 static sample lines, which `sample_content.py` held (now deleted).
  - It plays a scripted conversation through the store exactly as the workers will: AddUtterance, then partial updates with 2 tentative words, then the final, then SetTranslation 380 ms later.
  - Translations are included for en/es/ja/fr/de.
  - It lets the user review G2 before speech is wired, and it doubles as the first end-to-end store-to-view test.
- **New tokens:** `OVERLAY.original_scale` (0.8, previously a literal in the sample) and `OVERLAY.line_gap` (8). Added `pill_qss`.

**Verification**
- **Tier A:**
  - test_chat_view: 9 tests with hand-written expectations for every display case, labels, ramp order and source filter.
  - test_chat_line: layout with a fake 10 px/char font, with hand-computed runs and x positions (e.g. the changing run at 60 + 100 = 160). Covers char-breaking a long word, a label-only empty line, and real-font paint smoke.
  - A reducer test for `translated_from`.
- **Tier B (pytest-qt, real windows):** store sync with sources, the partial-update layout cache, scroll-back keeping position plus pill show and click, Ctrl+wheel vs wheel, the 200-line cap, demo step order, and DemoFeed filling a window.
- **Offscreen renders** in all 5 palettes, translation-only and original+translation, are in the scratchpad (chat_en.png, chat_both.png).
- **Live check:**
  - I launched `python -m livetranslator --demo` with `LIVETRANSLATOR_HOME` set to a scratch folder, so the user's settings weren't touched and their running instance was left alone.
  - From a desktop screenshot I confirmed that lines flow in, a partial Spanish line shows in the secondary colour, and older lines scroll off the top.
  - Then I stopped the demo instance.
- **Not verified yet:**
  - The "live audio → lines" acceptance check needs the ASR worker (T045).
  - G2, the user's look approval of ChatLine, is pending until they're back.

**Noticed for T045:** `Utterance.text` joins committed and tentative with a space. Japanese and Chinese have no spaces, so the ASR worker must decide the joiner per language, or keep Whisper's own leading-space tokens. The demo works around this by keeping unspaced scripts all-tentative until final.

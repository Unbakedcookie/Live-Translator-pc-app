# M10 — Speaker identification (gate G6) — narrative

## 2026-10-17 — T101 fusion + calibration, T102 per-line voice labels (commit 8885086; user away)

### Context
- T035 measured that per-line fingerprints beat the spec's sliding-window plan: DER 0.10 vs 0.35, 93 % of turns right, robust to big loudness differences.
- The engine (sherpa-onnx) was already the spec's recommendation, so T102 went ahead with the per-line design before G4. It is listed as question 4 on the G4 sheet and is easy to change: only the worker's job source would differ.

### T101 (Tier A)
- `fusion.py` implements the spec §5.13 rules as pure functions:
  - one Discord user covering ≥ 60 % of the line wins, and the line's voice cluster gets a vote for that user;
  - when several users overlap, the cluster's vote majority decides; otherwise the largest overlap;
  - with no Discord data, the voice label is used;
  - lines under 1 s, or with low confidence, become "others".
  - The vote table is passed in and a new one is returned; nothing is mutated.
- `calibration.py`: each SPEAKING_START is paired with the nearest VAD onset within 2 s, and the lag is the median over the first 10 pairs (at least 3 needed).
- 11 tests on hand-built timelines, e.g. 2.5 s of 4 s is 62.5 %, so the single speaker wins. The calibration test includes outliers of +1.8 s and −1.5 s plus one unpaired start; the expected median is 0.3.

### T102
- **`VoiceClusters`:** duration-weighted running sums with a similarity threshold of 0.55 (inside the T035 plateau of 0.5–0.6) and at most 6 speakers. `peek` serves partial lines and never learns or creates a speaker.
  - **Test bug caught by re-checking my own arithmetic:** the first "weighted mean" test would also have passed with an unweighted mean (a 60° voice joins either way). It now uses 70°, which joins only without weighting: 4.5° centroid → cos 65.5° = 0.41.
- **`SherpaEmbedder`:** TitaNet-large on CPU, 2 threads, model in `<models>/speakers/`.
- **`SpeakerWorker`:**
  - Runs on its own thread.
  - A partial line is embedded once it has ≥ 1.5 s of audio; it is labelled only if it matches a known voice, otherwise it keeps the neutral label.
  - The final line assigns (learns), fuses, and dispatches `UpdateUtterance(speaker_id)`.
  - A load failure turns labels off with a plain-language status.
  - The session reset forgets every voice (D-028).
- **ASR worker hook:** `on_line_audio(id, audio, start, end, final)`, for the Others stream only and never the mic. It keeps the ASR module independent of speakers.
- **Licence gate:** sherpa-onnx 1.13.8's metadata is free text, so an override (D-029) was added after reading the wheel's `licenses/LICENSE`, which is Apache-2.0. The gate passes 42 packages.

### Verification
- **Tier A / unit tests:** clusters (5), worker with a fake embedder (7: stable labels, peek-only partials, short lines, OFF mode, Discord name + vote teaching, load failure, reset, thread), the ASR hook (one early + one final hand-over, Others only), and the controller (settings follow, voices cleared with the session).
- **Real model on the T035 3-speaker mix:** DER within 10 % of the M03 value of 0.113. The tmp app dirs are byte-for-byte unchanged afterwards, so no fingerprint was written.
- **Live Tier B:**
  - Setup: scratch profile, mic muted. The level-matched 2-speaker (en M+F) and 3-speaker (es M+M+F) mixes were played through the default output and captured by the loopback.
  - All 10 lines got the right speaker. The English pair alternated Speaker 1/2; the Spanish trio became Speakers 3/4/5 and stayed consistent on their second turns.
  - The only miss is the known back-to-back turn (es S3 → S1 with no pause), which was merged into one line. That is T105's job.

### Not done / open
- **T103 Discord RPC:** blocked on T036, which needs the user's own Discord application (5-step setup approved in Phase 1).
- **T104 label UI:** rename by clicking a label, plus the Speakers settings page.
- **T105:** split a line at a speaker change.
- **Live test:** a real Discord call with 2–4 people.

## 2026-10-17 — T105 split a line at a speaker change (commit c804cb7; user away)
- **Problem:** two people talking back-to-back with no pause land in one VAD line, so both get one label. This was the only remaining T035/T102 error.
- **Attempts, measured on the real T035 lines (level-matched and as recorded):**
  1. **pyannote segmentation run on the line alone** (sherpa offline pipeline): it found neither of the 2 changes.
  2. **1.5 s window fingerprints compared with the line's first window:** changes scored a minimum similarity of 0.06–0.08, but single-speaker lines dipped to 0.30 or lower.
  3. **Left-half vs right-half averaged windows:** changes 0.10 / 0.50 / 0.22; single-speaker lines as low as 0.17.
     - Attempts 2 and 3 overlap, so either would cause false splits. They also cost up to 1.1 s of CPU per line.
  4. **Windows matched against the speakers already known (`peek`):**
     - Single-speaker lines never showed two different known speakers. Real patterns: `000000000?`, `???????`, `??000?`, `2?22`.
     - Both changes did: `11111?????22` (known→known) and `???000` (new voice→known).
     - This works because in a conversation the people who interrupt have usually spoken before. **Chosen.**
- **Rule (pure, `change.py`):**
  - Runs of window labels. A known run needs ≥ 2 windows; an unclear ("new voice") run needs ≥ 3.
  - The first adjacent pair of solid runs with different labels (not both unclear) marks the change, estimated between the two runs' window centres.
  - The estimate is then snapped to the nearest gap between recognised words (within 0.8 s).
  - Only lines ≥ 3 s are checked, and only once at least one voice is known.
- **My own test expectation was wrong once:**
  - I expected `11111?????22` to split halfway to speaker 2's run (4.25 s).
  - The code splits where speaker 1 stops being recognised (3.0 s), because the unclear stretch is a run of its own.
  - The real line's true change was at 3.42 s, so the code's choice is the better one. The test was fixed, with that reasoning.
- **Plumbing:**
  - The ASR worker's hand-over became a `LineAudio` record that also carries the final line's timed words (`LocalAgreement.committed_words`) and its language.
  - On a change, the speaker worker splits the text by word midpoints:
    - the first part keeps the id and gets its own text, end time and label;
    - the second part becomes `<id>-2` and gets its own label.
  - Both parts teach their voices.
  - TranslationController re-translates the shortened first line on its own, because its text snapshot changed.
- **Verification:**
  - Tier A: 15 tests for runs, single-speaker patterns from T035, both change kinds, short-run noise, word snapping and window geometry.
  - Synthetic worker test: speaker A 2.5 s, then B 2.5 s; a fake embedder using the window's mean angle (like a real model, a mostly-B window sounds like B). The split lands at 2.475 s against a true 2.5 s, within 300 ms ✓.
  - No split for a long single-speaker line, with no words, or with no known voices.
- **Real audio** (real faster-whisper + TitaNet + store, T035 mixes fed in real time, `split_e2e.py` in the scratchpad):
  - Both back-to-back turns were split.
    - es 3-speaker: 10.50 s vs true 10.36 s (**140 ms**).
    - en 4-speaker: 34.62 s vs true 34.22 s (**400 ms**). The recogniser blurred words across the seam ("…efficiently. Them inv"), so the nearest word gap came late.
  - **Every line in both mixes now has the right speaker.**
- **Open:**
  - The 400 ms case misses spec §8's 300 ms on real audio, though the synthetic acceptance passes. A finer local search around the estimate could tighten it later.
  - Live test with a real multi-person call.

## 2026-10-18 — T104 click-to-rename (Discord parts still blocked on T036; user asleep)
- **Design:** the chat view records where it painted each line's speaker label (`label_hits`, rebuilt every paint, so hit-testing always matches what's on screen, scrolled or not). In the overlay, a left press + release that moved less than the system drag distance on a label opens `RenamePopup` over it; anything more is a normal window drag. A pointing-hand cursor shows over renamable labels.
- The popup is its own `Qt.Popup` window because overlays are `WindowDoesNotAcceptFocus` (they must never steal focus from a game). It is pre-filled and selected; Enter saves, Esc/click-away cancels, an empty box returns to the automatic name (shown as the placeholder via new `automatic_label`).
- The rename is the existing session-only `RenameSpeaker` (D-028: nothing about voices is saved), so it applies to past and future lines of that speaker and to the transcript. The catch-all "Others" label isn't renamable (it isn't one person).
- **Verification:** 5 pytest-qt tests (hit-testing, click → popup → Enter renames lines 1 and 3 and a later line 4, Esc cancels, empty reverts, a 40 px drag from a label doesn't open it, automatic labels). **Tier B** (real app, demo feed): scrolled up to freeze the view, clicked "Speaker 2" → box over the label with the name selected → typed "Kenji" + Enter → the line now reads "Kenji" in the same colour, re-wrapped.
- **Still open in T104:** Discord connect/disconnect and the own-app setup guide with "Test connection" (need T036 / the user's Discord app). The Speakers settings page already covers mode, max voices and the "Me" label (T072).

## 2026-10-18 — T103 Discord RPC service + T104 setup guide (live test still needs the user)
- **User:** "I don't know how to make the Discord app" → the app now walks them through it.
- **Research (fact-checker, official docs, 2026-10-18; D-013/D-030 updated):** `rpc`/`rpc.voice.read` are partner-only; unapproved apps work for listed testers (≤ 50); owner-only access is unconfirmed, so the guide has an "if Discord says it isn't allowed, add yourself as an App Tester" step. The token exchange needs the client secret and a registered redirect URI (Public Client + PKCE is documented only for the Social SDK) → Plan A: the user pastes their own secret, stored DPAPI-encrypted. No approval-free official alternative exists.
- **Client** (`services/speakers/discord_rpc.py`, own implementation instead of pypresence): named-pipe framing, HANDSHAKE → READY, stored token → AUTHENTICATE (refresh token if stale; a token for another app ID is ignored), else AUTHORIZE (Discord's own prompt) → HTTPS code exchange → AUTHENTICATE; GET_SELECTED_VOICE_CHANNEL → names (server nick > global name > username); SUBSCRIBE VOICE_CHANNEL_SELECT and SPEAKING_START/STOP (moved when the channel changes; timeline cleared); reconnect loop every 5 s when Discord isn't running or closes; `check()` for the guide's Test connection.
- **SpeakingTimeline** feeds the speaker worker's fusion (T101) with intervals shifted by the calibrated lag; **DiscordController** re-estimates the lag every 5 s from SPEAKING_START times vs "Others" line starts (calibration.py), turns channel members into "discord:<id>" labels via session renames — **never over a name the user typed** — and runs only when set up and the speaker mode allows (Auto/Discord). Disconnect deletes the token and secret.
- **Token store** (`token_store.py`): DPAPI `CryptProtectData` with app entropy, atomic write; an unreadable file (e.g. copied from another account) counts as signed out. Verified the token isn't readable in the file.
- **Guide** (`ui/discord_setup.py`): 7 plain-language steps with "Open the Discord site" and "Copy" (redirect) buttons, Application ID + secret fields (Save/Test enabled only for a valid 15–21-digit ID — the settings model already enforced that, my first tests used short IDs and caught the mismatch), Test connection on a background thread, Save, Disconnect. Settings → Speakers → "Discord names · Set up…" shows the live status. Disabled buttons now look disabled (settings QSS).
- **A test I wrote too loosely** (an `or` fallback in an assertion) hid a wrong expected order; tightened it — the client correctly reads the new channel first, then moves the subscriptions.
- **Tests:** 8 client tests against a scripted fake Discord (first connect, stored/stale token, other app ID, timeline + lag, channel change, reconnect, wrong ID), 5 controller tests (when it runs, names vs user renames, lag calibration 0.3 s, disconnect, background check), 4 guide tests. Suite 595.
- **Not done (needs the user):** the live run — their own Discord app, a real call, speaking events vs loopback lag (T036 items 1–3), and screenshots for the guide.
- **Commit hooks caught test data:** gitleaks flagged the fake Discord ID "123456789012345678" in a test as a real client ID, and bandit flagged fake tokens ("good", "r1") next to `access_token` keys plus two file-name constants. Fixed without weakening the hooks: fake IDs are generated (`"1" * 18`), test token records are built by a helper from variables, and the three production constants carry a reasoned `# nosec B105`. Gitleaks and bandit then passed.

## 2026-10-18 — User report on the Discord setup guide (T104)
User's words: "when I open the discord link page it isn't in front of other things so I'm stuck moving it to be able to read it. secondly it went away when I opened discord so I couldn't see the next steps. 3rdly, step 2. I don't see create new app or new app."
- **Behind other windows / disappeared:** the guide was a normal window. Since the Settings fix earlier today, Settings is always-on-top, so the guide (opened from Settings) opened *behind* it; and clicking into the browser or Discord covered it. Fix: `WindowStaysOnTopHint`, and on first opening it is placed beside Settings with the new `ui/screens.place_beside` (same `geometry.beside` rule; the app's Settings/Transcript placement now uses it too).
- **No "New Application" button:** checked the live portal in the browser (view only, nothing clicked on the user's account): Discord now shows a "What brings you to the Developer Portal?" survey first (7 choices, "Continue to Portal" / "Skip"); the page behind it still has "New Application" top right. Discord's own quick-start links `applications?new_application=true`, which the Open button now uses. Steps rewritten (now 8): Open (a website, not the Discord app) → Skip the survey → New Application (or the already-open name box) → Application ID → OAuth2 redirect (Copy) → Reset Secret → open the Discord app, voice channel, Test → App Testers fallback. Step controls keyed by constants, not positions.
- Verified on the real app (fresh screenshots): Settings → Speakers → Set up… opens the guide at the right of Settings, topmost; after focusing VS Code the guide is still fully visible above it. Suite 617 passed.
- Not verified: whether `?new_application=true` opens the name box right after Skip (the guide covers both cases).
- Follow-up same day: "I'm up to step 7. I can't find the test connection button?" The button was at the bottom-left of the guide, below the fields, far from the step that names it (screenshot confirmed it visible and enabled; the user had already saved the ID and secret). Moved "Test connection" into step 7's row, like Open (step 1) and Copy (step 5); bottom row keeps Disconnect / Save. Checked by rendering the guide off-screen (the user's running app was left alone mid-setup; the change applies on next start).

## 2026-10-18 — "the Discord authorization window keeps popping up very fast. constantly" + "I cannot add my own account to the App Testers"
- Stopped the user's app at once (killed the process; settings are saved on change) to end the popups, then investigated.
- **Cause:** after Save, `DiscordController.apply()` started the background `DiscordClient`. Its `_run` loop called `session()` → `_sign_in()` → with no saved token it sent AUTHORIZE (Discord's approve window). Any failure (user not approving, Discord refusing, or the token exchange failing) raised RpcError, the loop waited `RETRY_S` = 5 s and AUTHORIZEd again — forever. The error text only went to the status line, never the log, and the app was gone, so the actual refusal reason is unknown. No token file was ever written, so the sign-in never completed once.
- **Fix:** only `check()` (the guide's Test connection) may AUTHORIZE (`_sign_in(allow_prompt=...)`). The background session raises `NeedsApproval` without a usable token; `_run` then shows "Discord isn't signed in. Open Settings, Speakers, Set up… and click Test connection." and *stops* (connection failures still retry quietly — they never prompt). A passed check emits `_check_passed` → `DiscordController.restart()` on the UI thread, so names start without restarting the app.
- **Errors now say what to do:** AUTHORIZE errors are read (check=False) and mapped (`authorize_error_advice`: closed/denied → click Authorize; scope/not allowed → App Testers, quoting Discord's message); token-endpoint HTTP errors read Discord's OAuth2 `error` code (`token_error_advice`: invalid_client → redo the secret, invalid_grant → check the redirect, invalid_scope → App Testers). Logged as codes only (no tokens, secrets or names).
- **App Testers:** Discord's docs say unapproved apps' RPC is limited to the tester list; docs.discord.food (community) says the rpc scope is allowed for the application owner. The user couldn't add themselves (likely because the owner is already allowed — unconfirmed). Step 8 now says it's usually not needed and only applies if the Test connection message mentions App Testers.
- Tests: check-then-session flow; background never sends AUTHORIZE and its thread ends after one attempt without a token; refused AUTHORIZE / token errors give the advice; controller restarts the client after a passed check. Suite 620 passed.
- **Next:** the user clicks Test connection once; the message (and the log's error code) tells us which step is wrong.
- Follow-up: Test connection said "Discord refused the sign-in". Log: `token request refused (HTTP 403, ?)` x3 — no OAuth2 error body. Reproduced with dummy credentials (nothing of the user's): Python's default `Python-urllib/3.12` agent → 403 `error code: 1010` (Discord's firewall blocks the default agent); a named agent → 400 `{"error": "invalid_client"}` (a normal answer). The user's setup was fine; our request was being blocked. Fix: `USER_AGENT = "LiveTranslator (<repo url>, <version>)"` on token requests; test asserts the header. Lesson: always name the app in HTTP requests to Discord.

## 2026-10-20: a Discord stream was named after people in the call

User: "ive run this on discord with a stream going. the stream usually picks up as others or speaker x. sometimes it picks up as one of the people in the call. can it not manage multiple people talking over each other?"
- Cause (fusion.py): whenever any call member's SPEAKING interval overlapped a line, the line got a Discord name (single cover ≥ 60 % → that user and a vote linking the voice to them; otherwise largest overlap). A stream's audio never fires SPEAKING events, so when a member talked over the stream, the stream's line took the member's name and even taught its voice cluster that name.
- Fix: while Discord is live (someone in the call spoke in the last 60 s), a line during which nobody in the call spoke votes its voice cluster NOT_IN_CALL. A cluster with ≥ 3 such votes and ≥ 2× the votes of any member speaking now keeps "Speaker N" and casts no vote. Members are unaffected: their voices get member votes every time they speak. Worker queries Discord over [start − 60 s, end] to know "live". Thresholds: D-041 (Medium). Tests: 4 fusion cases (hand-built) + a worker scenario (mika, a stream voice heard 3× in silence, mika talking over the stream → "voice:1", mika's own line → "discord:mika").
- Overlapping talkers: not solvable with what we have. The app hears one mixed stream from the speakers; when two people talk at once Whisper writes the louder one (or a mix) as one line and it gets one label. Separating voices needs either a speech-separation model (heavy, adds delay) or each person's own audio — only a Discord bot in the voice channel receives that, which needs a bot added to the server and uses an unofficial receive path. Back-to-back turns are already split (T105). Explained to the user; not built.
- Suite 701.

## 2026-10-20: overlapping talkers — licence check + detection/separation spike

User: "how much would this voice separation add? and could it maybe be a feature you turn on?" → "make sure all the licensing works and then run your tests please".
- Licences first (fact-checker agent + my own HF API checks). Only two clear candidates: pyannote segmentation-3.0 ONNX from k2-fsa (MIT, read in the tarball) for overlap detection, and ConvTasNet Libri2Mix sep_clean 16k (CC-BY-SA-4.0, LibriSpeech-only data) for separation. The agent's top pick ("MIT DPRNNTasNet sep_clean 16k") doesn't exist: HF API 401, and the author's full model list is CC-BY-SA only — caught before downloading anything. Everything WSJ0/WHAM!-trained, sep_noisy, 8 kHz, private-data, undocumented-data or gated was rejected. D-042, D-043.
- Asteroid 0.7.0 installed `--no-deps` into the PyTorch conversion venv on D: (its `pesq` extra needs a compiler); added soundfile, scipy, onnx there. The app venv is untouched.
- Results (`benchmarks/results/separation.md`): 192 two-talker FLEURS mixtures (en+en, en+es, es+fr, en+zh; full/half overlap; 0/−6 dB; clean/pink noise). Today's single transcript: talker errors 0.58/0.61, both talkers understood in 0 %. After separation: 0.12/0.17, both understood 72 % (62–83 % per condition; en+zh 69 %). Detector: 91 % of mixtures flagged (all full overlaps, 79/96 half), 0 % of 320 single-talker clips. Cost: 25.7 MB download, no VRAM (onnxruntime CPU), ~0.008 s/s for detection on every line, separation ~0.23 s per second of overlapped audio on the CPU (+ one extra recognition and translation) ≈ +1.5–2 s on an overlapped 6 s line.
- Caveat: read speech like the training data; real Discord/stream audio will be worse. Next if the user wants it: an opt-in "Separate people talking over each other (experimental)" setting, with the CC-BY-SA model approved first.

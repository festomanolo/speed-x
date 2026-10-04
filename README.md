# Speed-X

**Private AI Control Layer & Fluid Desktop Assistant for macOS**  
*Offline · Warm on-device engine · Bilingual (English & Swahili) · Native macOS 26 Liquid Glass*

[![macOS](https://img.shields.io/badge/macOS-26.0%2B-blue.svg?logo=apple)](https://apple.com)
[![Swift](https://img.shields.io/badge/Swift-5.9%2B-orange.svg?logo=swift)](https://swift.org)
[![Python](https://img.shields.io/badge/Python-3.11%2B-yellow.svg?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)

---

## Highlights

- **Real Liquid Glass side notch (macOS 26)**: The UI is native SwiftUI using Apple's `glassEffect` with custom shapes, not painted-on translucency. The notch sits flush against the right screen bezel, and concave fillets flare it into the edge. Its gauges show engine confidence, memory and assistant state. Each card is a glass bubble whose pointer aims at the active gauge, and it grows out of the notch with critically damped springs. Reduced Motion and Reduced Transparency are respected.
- **Three distinct modules**, each with its own glyph, colour and live gauge:
  - **Decision Engine** (brain, amber): the last decision, each step's confidence, latency, which pipeline layer answered, the Core ML toggle, and recent history.
  - **System** (gauge, mint): CPU and memory rings, the active app, the **microphone picker** with a live level meter, shortcuts, and open-at-login.
  - **Assistant** (waveform, indigo): a large live transcript, **real-time intent chips while you speak**, results per step, confirm or cancel (also by voice), "did you mean…", quick actions, and a sound-reactive aurora.
- **Works with any microphone**: Speed-X picks the input device itself. The input selected in macOS comes first, then USB mics, other wired mics, Bluetooth (AirPods), and built-in last, so a silent built-in Hackintosh mic is never used when a real mic is connected. You can pin a specific mic in System › Microphone. Recognition is on-device and pre-warmed. It ends your command after about 0.8 s of silence instead of a fixed 2.2 s, and it tells you when the chosen mic delivers no audio.
- **Warm engine daemon**: The UI keeps one `python -m speed_x.server` process alive and talks to it in JSON lines, instead of spawning Python for every command. Typical commands now finish in 5–400 ms (they took 2–13 s before). AppleScript runs inside the app, so macOS asks "SpeedX wants to control Music" once and remembers it.
- **Layered decision making**: normalize (wake words, fillers, dictation punctuation) → bilingual rules with parameter extraction → fuzzy semantic matcher that tolerates ASR typos → Core ML (optional; only when it's already warm, never blocking).
  - Multi-step plans: "open safari and play music", "set a timer for ten minutes and remind me to water the plants"
  - Context: "open calculator … close it"; sensitive steps need confirmation
  - English and Swahili numbers and durations: "weka sauti hamsini", "dakika kumi na tano", "saa moja na nusu"
  - "Did you mean…?" suggestions instead of dead ends
- **Local AI brain (Ollama, offline)**: Questions ("eleza jinsi ya kupika chai", "tell me a joke") get streamed answers. Requests to reason over content ("summarize what's on my screen", "translate my clipboard to Swahili") run as read → think. Unknown actions ("get me ready for a zoom meeting") are planned into tool calls by a few-shot planner. Tools the AI invents are dropped, and anything outward or destructive it proposes needs your OK. Model: `qwen2.5:3b` by default (`ollama pull qwen2.5:3b`); override with `SPEEDX_LLM_MODEL`.
- **Optional Claude brain**: add an Anthropic API key on the Decision Engine card (stored in `~/.config/speed_x/anthropic_api_key`, mode 600), or set `ANTHROPIC_API_KEY`. Speed-X then answers and plans with `claude-opus-5` at low effort, with server-side refusal fallbacks, and falls back to the local model whenever you're offline. Known commands never leave the Mac. `SPEEDX_CLOUD=0` forces local-only. Requires `pip install 'speed-x[cloud]'`.
- **WhatsApp by name**: "open whatsapp and send message to Manolo saying hi" opens WhatsApp, searches Manolo, opens the chat, pastes and sends. This needs Speed-X enabled in Privacy & Security › Accessibility. iMessage goes through Contacts.
- **Commands**: apps (fuzzy-matched to installed apps), music (including specific songs: "open music and play nadina song", "play shape of you by ed sheeran on spotify", "cheza wimbo wa nadina"), volume, mute, lock, sleep, dark or light mode, **timers & reminders**, **web and YouTube search**, websites, time and date, files and PDFs, clipboard, screen OCR, Notes, Mail, workspaces.
- **Spotify songs by name**: Spotify can play an exact track but can't search from AppleScript, so Speed-X looks the song up with the Spotify Web API (app key only, no login, no Premium) and plays it in the desktop app. Create an app at [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard), then save `{"client_id": "…", "client_secret": "…"}` to `~/.config/speed_x/spotify.json` (or set `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET`). Without keys it opens Spotify search instead. Only song queries are sent, and only when you ask for Spotify.
- **Workspaces by voice**: "create a workspace called writing with pages and safari", "save my current apps as design", "add slack to the coding workspace", "start writing workspace", "delete the writing workspace" (asks first).
- **Timers survive restarts**: running timers are saved to `~/.config/speed_x/timers.json` and rescheduled when the engine starts; one that ended while Speed-X was off still notifies you.
- **Hotkeys & URL scheme**: **⌘ ⌥ P** slides the side notch out of the bezel and tucks it back in, **⌥ Space** to talk, **⌘ ⇧ Space** to type, **esc** to dismiss. `speedx://toggle` (`/show`, `/hide`), `speedx://listen`, `speedx://run?cmd=…` and `speedx://open/<engine|system|assistant>` are available for Shortcuts and scripts.

---

## Architecture

```
┌──────────────────────── SpeedX.app (SwiftUI, Liquid Glass) ────────────────────────┐
│  RootView ─ GlassEffectContainer ─┬─ Card (Engine / System / Assistant)            │
│                                   └─ Side notch (bezel-flared glass, 3 gauges)     │
│  SpeechManager ─ AudioDevices (any mic)       ─ on-device SFSpeechRecognizer       │
│  EngineClient ── JSON lines ──┐          OSAThread (runs AppleScript for engine)   │
└───────────────────────────────┼────────────────────────────────────────────────────┘
                                ▼
┌──────────── python -m speed_x.server (warm) ────────────┐
│  LayaBrain: normalize → rules → semantic → Core ML      │
│  CommandRouter: plan → guardrails → tools → memory      │
│  Tools: apps · music · system · timer · web · files ... │
└─────────────────────────────────────────────────────────┘
```

> **Voice permissions:** the first time you talk, macOS asks for Microphone and Speech Recognition access for Speed-X. If you ever see "Speech recognition is off", use the **Open Privacy Settings** button on the card and enable Speed-X.

---

## Quick Start

### 1. Build and Run App
```bash
# Clone the repository
git clone https://github.com/festomanolo/speed-x.git
cd speed-x

# Compile Swift UI and build SpeedX.app & DMG
bash scripts/build_app.sh

# Launch Speed-X
open dist/SpeedX.app
```

### 2. Interactive CLI Shell
```bash
# Set up Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run interactive CLI
python3 main.py
```

### 3. Run Automated Tests
```bash
.venv/bin/python -m unittest discover tests
```

---

## Voice & Text Commands Reference

| English Command | Swahili / Sheng Command | Action |
|---|---|---|
| `open notes app and write a new note` | `andika note mpya` | Creates a new note in Apple Notes |
| `update the existing one` | `ongeza kwenye note` | Appends update to latest Apple Note |
| `make new file` | `tengeneza faili jipya` | Generates a new file on Desktop and reveals in Finder |
| `send email with a message` | `tuma email` | Composes draft in Apple Mail |
| `volume up` / `volume down` | `ongeza sauti` / `punguza sauti` | Native system audio control |
| `play music` / `pause music` | `cheza muziki` / `simamisha muziki` | Controls macOS Music app |
| `lock screen` / `sleep mac` | `funga screen` / `laza mac` | Secure system intervention |
| `read clipboard` / `inspect clipboard` | `angalia clipboard` | Real-time clipboard inspector |
| `set a timer for ten minutes` | `weka timer ya dakika tano` | Countdown timer with notification |
| `remind me in 20 minutes to call mom` | `nikumbushe kunywa maji baada ya dakika kumi` | Apple Reminders entry |
| `search for best pizza near me` / `play lofi on youtube` | `tafuta … mtandaoni` | Web / YouTube search |
| `what time is it` | `saa ngapi` | Time and date |
| `open safari and play music` | `fungua safari halafu cheza muziki` | Multi-step plan |
| `open music and play nadina song` | `cheza wimbo wa nadina` | Plays a specific song (Apple Music library / Spotify) |
| `create a workspace called writing with pages and safari` | `tengeneza workspace ya kazi na slack na mail` | Saves a named set of apps |
| `what window am i in` | `niko kwenye app gani` | Frontmost app and window title |
| `clear my clipboard` | `futa clipboard` | Empties the clipboard |

---

## License

Apache License 2.0. Copyright (c) 2026 festomanolo.

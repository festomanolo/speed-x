# Speed-X

**Private AI Control Layer & Fluid Desktop Assistant for macOS**  
*100% Offline · Core ML & Neural Engine · Bilingual (English & Swahili) · Liquid Glass Dynamic Island*

[![macOS](https://img.shields.io/badge/macOS-13.0%2B-blue.svg?logo=apple)](https://apple.com)
[![Swift](https://img.shields.io/badge/Swift-5.9%2B-orange.svg?logo=swift)](https://swift.org)
[![Python](https://img.shields.io/badge/Python-3.11%2B-yellow.svg?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)

---

## Highlights

- **Dynamic Island Glass Dock**: Hugs the physical right bezel of the macOS display with a 25% opacity specular glass surface, responsive Control Center gauges (CoreML confidence, RAM, Assistant readiness), and interactive popovers.
- **VoiceBeam Sound-Reactive Aurora Stage**: High-fidelity native Swift implementation with real-time vocal luminescence blooming and organic exponential decay. Emanates from the bottom curved contour of the assistant card with an emerald/jade hero pillar, cyan floor flare, deep plum/magenta atmospheric clouds, and a multi-stop chromatic refraction rim that dynamically breathes at rest and flares intensely with live speech volume.
- **Conversational Assistant Stage**: Floating dark glass card (cornerRadius = 22) featuring spacious prompt typography, generous vertical breathing room, and a floating frosted glass control bar (`Agent (auto) ⌵`, circular microphone, and circular close buttons) floating seamlessly over the aurora stage.
- **ThinkingOrb Engine**: Native 60 FPS Core Graphics port of [`Libraries.dev thinking-orbs`](https://libraries.dev/orbs.html) with 9 mathematical states (`working`, `searching`, `solving`, `listening`, `connecting`, `weaving`, `composing`, `breathing`, `shaping`).
- **Comprehensive Desktop Command System**:
  - **Apple Notes**: "open notes app and write a new note", "update the existing one", "andika note mpya".
  - **Apple Mail**: "send email with a message", "compose email to alice@example.com", "tuma barua pepe".
  - **Desktop File Discovery & Creation**: "make new file named todo.txt", "find pdf", "latest screenshot", "tengeneza faili".
  - **System Control**: Volume up/down, mute/unmute, lock screen, sleep mac, dark/light mode toggle.
  - **Media Control**: Apple Music play, pause, next track, previous track ("cheza muziki", "simamisha").
- **Global HotKey & Background Stream**: Instant toggle with **⌥ + Space** or **⌘ + ⇧ + Space**, real-time microphone stream with speech recognition, and automatic launch at login.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Speed-X macOS Panel                      │
├──────────────────────────────┬───────────────────────────────┤
│  Fluid Glass Popover Card    │   Bezel-Anchored Island Dock  │
│  • Thinking Orb Stage        │   • CoreML Decision Gauge     │
│  • Speech / Text Input       │   • System RAM & CPU Gauge    │
│  • VoiceBeam Spectro Waves   │   • Assistant Readiness Gauge │
│  • Quick Actions (Cheza, etc)│                               │
│  • 100% Offline Status       │                               │
└──────────────────────────────┴───────────────────────────────┘
```

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

---

## License

Apache License 2.0. Copyright (c) 2026 festomanolo.

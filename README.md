<div align="center">

# 🦝 Enot Translator

**AI-powered book translator — runs 100% locally on your machine**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![tests](https://img.shields.io/badge/tests-18%20passed-brightgreen)](#-testing)

Translate entire `.epub` and `.txt` books using local LLMs via **Ollama** — no data leaves your computer, no API bills, no internet required.

</div>

---

## ✨ Features

- **📖 Full book support** — translates `.epub` (preserves internal HTML layout) and `.txt` files
- **🤖 Local AI** — works with any Ollama model (recommended: `qwen3:14b`)
- **🧠 Batch translation** — groups segments for speed, with auto-repair for bad translations
- **💾 Checkpoint resume** — pause, crash, or run out of VRAM? Resume from where you left off
- **🔍 Quality control** — detects echo translations, leftover source-language characters, and fixes them
- **🎨 Dark-themed GUI** — built with PyQt6, optimized for Linux (Wayland & X11)
- **🌍 25 languages** — wide language pair support

## 📸 Demo

![screenshot](https://github.com/user-attachments/assets/82e31101-6205-496b-9687-ab135ca1ddb3)

## 🚀 Quick Start

### Prerequisites

1. Install **[Ollama](https://ollama.com)** and pull a model:
   ```bash
   ollama pull qwen3:14b
   ```

### Installation

```bash
git clone https://github.com/EnotSM/Enot_Translator.git
cd Enot_Translator
pip install -r requirements.txt
python enot_translator.py
```

> **NixOS?** One-command launch:
> ```bash
> nix-shell -p qt6.qtwayland "python3.withPackages(ps: [ps.pyqt6 ps.requests ps.ebooklib ps.beautifulsoup4])" --run "export QT_QPA_PLATFORM=wayland; python3 enot_translator.py"
> ```

## 🎮 Usage

1. Launch the app
2. Select your input `.txt` or `.epub` file
3. Choose source & target languages
4. Pick your Ollama model
5. Click **Start / Resume**

Progress is saved automatically — you can pause and resume anytime.

## 🧪 Running Tests

```bash
python -m unittest discover -v
```

## 🏗️ Architecture

```
enot_translator.py    Main GUI + translation logic (~790 LOC)
constants.py         Language list, stylesheet, configuration
test_enot_translator.py  Unit tests (18 tests, 8 test classes)
```

The app uses **QThread** for non-blocking translation, **Ollama's structured JSON output** for reliable batch parsing, and **atomic file writes** for safe checkpointing.

## 🛠️ Tech Stack

| Layer | Tech |
|-------|------|
| Language | Python 3.10+ |
| GUI | PyQt6 |
| LLM Backend | Ollama (local) |
| EPUB Parsing | EbookLib + BeautifulSoup |
| Testing | unittest |

## 📄 License

[MIT](LICENSE) — free to use, modify, and distribute.

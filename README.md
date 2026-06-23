# Enot Translator

First off, a quick disclaimer: I'm just an enthusiast, not a professional developer. Almost all of the code in this project was written with the help of Claude and Gemini. I just guided the logic and glued the pieces together because I needed a privacy-focused tool to translate books locally and couldn't find exactly what I wanted.

### What is this?
It's a standalone Python GUI app that translates whole `.txt` and `.epub` files using your local LLMs via Ollama. It’s built with PyQt6 and specifically tweaked to run smoothly on Linux Wayland. 

### How it actually works
Instead of blindly feeding text to an LLM, the script has a few built-in safety nets:
* **Batching:** It groups text segments and asks the model to return a JSON array of translations, which is way faster than doing it line-by-line.
* **Auto-Repair:** The script actively checks for bad translations (like echoing the original text or leaving Cyrillic characters in an English translation). If it spots one, it isolates that segment and forces the model to re-translate it strictly.
* **Checkpoints:** Progress is continuously saved to a `_enot.state.json` file. If you close the app, run out of VRAM, or hit pause, you won't lose your progress.
* **Format safety:** For EPUBs, it translates only the text nodes without breaking the book's internal HTML layout.

### Setup Requirements

You need [Ollama](https://ollama.com) installed. For the best balance of speed and quality right now in 2026, I highly recommend using **`qwen3:14b`** (`ollama pull qwen3:14b`).(req 10GB VRAM)

**Option 1: Standard Linux**
Make sure your system has Qt6 Wayland support installed (e.g., `qt6-wayland`), then run:
```bash
git clone [https://github.com/EnotSM/Enot_Translator.git](https://github.com/EnotSM/Enot_Translator.git)
cd Enot_Translator
pip install -r requirements.txt
```

**Option 2: NixOS**
If you are on NixOS, you can launch the app in one go without installing packages globally:
```bash
nix-shell -p qt6.qtwayland "python3.withPackages(ps: [ps.pyqt6 ps.requests ps.ebooklib ps.beautifulsoup4])" --run "export QT_QPA_PLATFORM=wayland; python3 enot_translator.py"
```

### Usage

Using the tool is super straightforward:

1. Open the app.
2. Browse and select your input file.
3. Pick your source and target languages.
4. Choose your model, batch size, and context.
5. Hit "Start / Resume".

*⚠️ **Note:** Local LLMs are great, but they aren't perfect. Even with the built-in auto-repair checks, you might still occasionally run into translation mistakes or weird phrasing.*

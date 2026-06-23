#!/usr/bin/env python3

import sys
import os
import time
import json
import threading
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple

if "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "wayland"
os.environ.setdefault("QT_WAYLAND_DISABLE_WINDOWDECORATION", "1")

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("EnotTranslator")

try:
    import requests
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
except ImportError:
    print("❌ Missing dependencies: requests, ebooklib, beautifulsoup4")
    sys.exit(1)

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QComboBox, QProgressBar, QTextEdit,
        QFileDialog, QLineEdit, QSpinBox, QGroupBox, QSplitter,
        QMessageBox, QFrame
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
    from PyQt6.QtGui import QTextCursor, QCloseEvent
except ImportError:
    print("❌ Missing dependency: PyQt6")
    sys.exit(1)

LANGUAGES = [
    "", "English 🇬🇧", "Ukrainian 🇺🇦", "Russian 🇺🇦", "German 🇩🇪", "French 🇫🇷",
    "Spanish 🇪🇸", "Italian 🇮🇹", "Polish 🇵🇱", "Portuguese 🇵🇹", "Dutch 🇳🇱",
    "Swedish 🇸🇪", "Czech 🇨🇿", "Greek 🇬🇷", "Romanian 🇷🇴", "Hungarian 🇭🇺",
    "Bulgarian 🇧🇬", "Danish 🇩🇰", "Finnish 🇫🇮", "Norwegian 🇳🇴", "Slovak 🇸🇰",
    "Croatian 🇭🇷", "Lithuanian 🇱🇹", "Slovenian 🇸🇮", "Latvian 🇱🇻", "Estonian 🇪🇪"
]

CONTEXT_SIZES = ["2048", "4096", "8192", "16384", "32768"]

STYLESHEET = """
QMainWindow, QWidget { background: #0f1117; color: #e2e8f0; font-family: 'monospace'; font-size: 13px; }
QGroupBox { border: 1px solid #1e2d3d; border-radius: 10px; margin-top: 14px; padding: 14px 12px 10px 12px; font-weight: 600; color: #38bdf8; text-transform: uppercase; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 14px; padding: 0 6px; background: #0f1117; }
QPushButton { background: #0ea5e9; color: #0f1117; border: none; border-radius: 7px; padding: 8px 20px; font-weight: 700; }
QPushButton:hover { background: #38bdf8; }
QPushButton:disabled { background: #1e2d3d; color: #475569; }
QPushButton#cancel { background: #1e293b; color: #f87171; border: 1px solid #7f1d1d; }
QPushButton#cancel:hover { background: #7f1d1d; color: #fff; }
QPushButton#small { background: #1e293b; color: #94a3b8; padding: 6px 12px; font-size: 12px; border: 1px solid #1e2d3d; }
QPushButton#small:hover { background: #0ea5e9; color: #0f1117; }
QLineEdit, QSpinBox, QComboBox { background: #0d1520; border: 1px solid #1e2d3d; border-radius: 7px; padding: 7px 11px; color: #e2e8f0; }
QComboBox QAbstractItemView { background: #0d1520; color: #e2e8f0; selection-background-color: #0ea5e9; }
QProgressBar { background: #0d1520; border: 1px solid #1e2d3d; border-radius: 7px; text-align: center; color: #94a3b8; height: 22px; }
QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0ea5e9, stop:1 #38bdf8); border-radius: 6px; }
QTextEdit { background: #080d14; border: 1px solid #1e2d3d; border-radius: 8px; padding: 10px; color: #4ade80; }
QLabel { color: #94a3b8; }
QLabel#hero { color: #38bdf8; font-size: 22px; font-weight: 800; }
"""

class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def list_models(self) -> List[str]:
        try:
            r = self.session.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            return sorted(m["name"] for m in r.json().get("models", []))
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            raise

    def flush_cache(self, model: str) -> None:
        try:
            self.session.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "keep_alive": 0},
                timeout=5
            )
        except Exception as e:
            logger.error(f"Failed to flush cache for {model}: {e}")

    def translate_batch(self, texts: List[str], src_lang: str, tgt_lang: str, model: str, context_size: int, cancel_event: Optional[threading.Event] = None, timeout: int = 300) -> List[str]:
        if not texts:
            return []

        schema = {
            "type": "object",
            "properties": {
                "translations": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["translations"]
        }

        prompt = (
            f"You are a professional book translator.\n"
            f"Translate the following JSON array of text segments from {src_lang} to {tgt_lang}.\n"
            f"CRITICAL: You must return exactly {len(texts)} strings inside the array. Do not join or skip segments.\n"
            f"Original data: {json.dumps(texts, ensure_ascii=False)}"
        )

        for attempt in range(3):
            try:
                r = self.session.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "format": schema, 
                        "options": {
                            "temperature": 0.1,
                            "num_predict": -1,
                            "num_ctx": context_size, 
                        },
                    },
                    timeout=timeout,
                )
                r.raise_for_status()
                data = json.loads(r.json().get("response", "{}"))
                translations = data.get("translations", [])
                
                if len(translations) == len(texts):
                    return translations
            except Exception as e:
                logger.warning(f"Batch translation attempt {attempt + 1} failed: {e}")
                backoff_time = 2.0 ** attempt
                if cancel_event and cancel_event.wait(backoff_time):
                    return []
                elif not cancel_event:
                    time.sleep(backoff_time)

        if cancel_event and cancel_event.is_set():
            return []
            
        return self._translate_isolated(texts, src_lang, tgt_lang, model, context_size, cancel_event)

    def _translate_isolated(self, texts: List[str], src_lang: str, tgt_lang: str, model: str, context_size: int, cancel_event: Optional[threading.Event] = None) -> List[str]:
        isolated_results = []
        for text in texts:
            if cancel_event and cancel_event.is_set():
                break
                
            if not text.strip():
                isolated_results.append(text)
                continue
                
            prompt = f"Translate this text directly from {src_lang} to {tgt_lang}. Output only the translation.\n\nText:\n{text}"
            try:
                r = self.session.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.1, "num_ctx": context_size},
                    },
                    timeout=60,
                )
                r.raise_for_status()
                translated_text = r.json().get("response", "").strip()
                isolated_results.append(translated_text if translated_text else text)
            except Exception as e:
                logger.error(f"Isolated translation failed for segment: {e}")
                isolated_results.append(text)
        return isolated_results


class ModelFetcherWorker(QThread):
    sig_models = pyqtSignal(list)
    sig_error = pyqtSignal()

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self) -> None:
        client = OllamaClient(self.url)
        try:
            models = client.list_models()
            self.sig_models.emit(models)
        except Exception:
            self.sig_error.emit()


class TranslationWorker(QThread):
    sig_progress = pyqtSignal(int, int, str)
    sig_log      = pyqtSignal(str)
    sig_done     = pyqtSignal(str)
    sig_error    = pyqtSignal(str)
    sig_paused   = pyqtSignal()

    def __init__(self, in_path: str, out_path: str, src_lang: str,
             tgt_lang: str, model: str, batch_sz: int,
             context_size: int, ollama_url: str) -> None:
        super().__init__()
        self.in_path = in_path
        self.out_path = out_path
        self.src_lang = src_lang
        self.tgt_lang = tgt_lang
        self.model = model
        self.batch_sz = batch_sz
        self.context_size = context_size
        self.ollama_url = ollama_url
        self._cancel = threading.Event()
        self._error_emitted = False
        
        in_p = Path(self.in_path)
        self.state_file = str(in_p.with_name(f"{in_p.stem}_enot.state.json"))

    def cancel(self) -> None:
        self._cancel.set()
        threading.Thread(target=self._force_flush_gpu, daemon=True).start()

    def _force_flush_gpu(self) -> None:
        client = OllamaClient(self.ollama_url)
        client.flush_cache(self.model)

    def _load_checkpoint(self) -> Dict[str, str]:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load checkpoint file: {e}")
                return {}
        return {}

    def _save_checkpoint(self, state: Dict[str, str]) -> None:
        tmp_file = self.state_file + ".tmp"
        try:
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self.state_file)
        except Exception as e:
            self.sig_log.emit(f"⚠️ Checkpoint preservation failed: {e}")

    def is_translatable(self, text: str) -> bool:
        stripped = text.strip()
        return len(stripped) > 0 and any(char.isalpha() for char in stripped)

    def _is_bad_translation(self, orig: str, trans: str) -> bool:
        o = orig.strip()
        t = trans.strip()
        if not o or not t:
            return False
        
        if o == t and len(o) > 15 and any(c.isalpha() for c in o):
            return True
            
        cyrillic_targets = ["Russian 🇺🇦", "Ukrainian 🇺🇦", "Bulgarian 🇧🇬"]
        if not any(lang in self.tgt_lang for lang in cyrillic_targets):
            if any('\u0400' <= c <= '\u04FF' for c in t):
                return True
        return False

    def _repair_segment(self, client: OllamaClient, text: str) -> str:
        prompt = (
            f"Translate the following text completely into {self.tgt_lang}.\n"
            f"CRITICAL: Output ONLY the translation. Do not echo the original text.\n\n"
            f"Text: {text}"
        )
        try:
            r = client.session.post(
                f"{client.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.0, "num_ctx": self.context_size},
                },
                timeout=45,
            )
            r.raise_for_status()
            repaired = r.json().get("response", "").strip()
            return repaired if repaired else text
        except Exception as e:
            logger.error(f"Segment repair failed: {e}")
            return text

    def run(self) -> None:
        try:
            client = OllamaClient(self.ollama_url)
            client.list_models()
        except Exception:
            self._error_emitted = True
            self.sig_error.emit("Ollama server unreachable.")
            return

        try:
            ext = Path(self.in_path).suffix.lower()
            
            estimated_tokens = self.batch_sz * 150
            if estimated_tokens > self.context_size * 0.75:
                self.sig_log.emit("⚠️ Warning: Batch size may exceed context. Reduce batch or increase context.")

            if ext == '.epub':
                self._translate_epub(client)
            else:
                self._translate_txt(client)
        except Exception as exc:
            self._error_emitted = True
            self.sig_error.emit(str(exc))
        finally:
            if self._cancel.is_set() and not self._error_emitted:
                self.sig_paused.emit()

    def _run_batches(self, client: OllamaClient, segments: List[Tuple[str, str]]) -> Optional[Dict[str, str]]:
        total_segments = len(segments)
        translated_map = self._load_checkpoint()
        
        pending_segments = [(uid, text) for uid, text in segments if uid not in translated_map]
        initial_completed = len(translated_map)
        completed_segs = initial_completed
        
        if initial_completed > 0:
            self.sig_log.emit(f"🔄 Resuming from index {initial_completed}.")

        if not pending_segments:
            return translated_map

        batches = [pending_segments[i : i + self.batch_sz] for i in range(0, len(pending_segments), self.batch_sz)]
        batch_counter = 0
        t0 = time.time()

        for batch in batches:
            if self._cancel.is_set():
                self.sig_log.emit("⏸ Paused safely. State saved.")
                return None

            batch_counter += 1
            texts_to_translate = [text for _, text in batch]
            
            try:
                res = client.translate_batch(
                    texts_to_translate, 
                    self.src_lang, 
                    self.tgt_lang, 
                    self.model,
                    self.context_size,
                    self._cancel
                )
                
                if self._cancel.is_set():
                    self.sig_log.emit("⏸ Paused safely. State saved.")
                    return None
                
                for (uid, orig_text), trans_text in zip(batch, res):
                    if self._is_bad_translation(orig_text, trans_text):
                        self.sig_log.emit("👁️ Checker caught error. Repairing segment...")
                        trans_text = self._repair_segment(client, orig_text)
                        
                    translated_map[uid] = trans_text
            except Exception as exc:
                self.sig_log.emit(f"⚠️ Batch error: {exc}")
                for uid, orig_text in batch:
                    translated_map[uid] = orig_text

            self._save_checkpoint(translated_map)
            completed_segs += len(batch)

            if batch_counter % 50 == 0:
                client.flush_cache(self.model)

            elapsed = time.time() - t0
            processed_this_session = completed_segs - initial_completed
            rate = processed_this_session / elapsed if elapsed > 0 else 0
            remain = (total_segments - completed_segs) / rate if rate > 0 else 0
            
            eta_str = f"{int(remain // 60)}m {int(remain % 60)}s"
            self.sig_progress.emit(completed_segs, total_segments, f"Segments {completed_segs}/{total_segments} · ETA {eta_str}")

        return translated_map

    def _translate_txt(self, client: OllamaClient) -> None:
        self.sig_log.emit("📖 Reading TXT file...")
        with open(self.in_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        segments = [(str(i), line.strip()) for i, line in enumerate(lines) if self.is_translatable(line)]
        if not segments: 
            self._error_emitted = True
            self.sig_error.emit("No text found.")
            return

        self.sig_log.emit(f"🚀 Found {len(segments)} segments.")
        translated_map = self._run_batches(client, segments)
        if translated_map is None: return

        self.sig_log.emit("💾 Saving translated TXT...")
        out_lines = lines.copy()
        for idx_str, trans_text in translated_map.items():
            idx = int(idx_str)
            orig_line = lines[idx]
            out_lines[idx] = orig_line.replace(orig_line.strip(), trans_text, 1)

        with open(self.out_path, 'w', encoding='utf-8') as f:
            f.writelines(out_lines)
            
        if os.path.exists(self.state_file): os.remove(self.state_file)
        self.sig_done.emit(self.out_path)

    def _translate_epub(self, client: OllamaClient) -> None:
        self.sig_log.emit("📖 Reading EPUB file...")
        book = epub.read_epub(self.in_path)
        html_items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        soups = {}
        segments = []

        for item in html_items:
            item_id = item.get_id()
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            soups[item_id] = soup
            
            for idx, node in enumerate(soup.find_all(string=True)):
                text = str(node)
                if self.is_translatable(text) and node.parent.name not in ['style', 'script', 'head', 'title', 'meta']:
                    uid = f"{item_id}::{idx}"
                    segments.append((uid, text.strip()))

        if not segments: 
            self._error_emitted = True
            self.sig_error.emit("No text found.")
            return

        self.sig_log.emit(f"🚀 Found {len(segments)} segments.")
        translated_map = self._run_batches(client, segments)
        if translated_map is None: return

        self.sig_log.emit("💾 Saving translated EPUB...")
        for item in html_items:
            item_id = item.get_id()
            soup = soups[item_id]
            modified = False
            
            for idx, node in enumerate(soup.find_all(string=True)):
                uid = f"{item_id}::{idx}"
                if uid in translated_map:
                    original_text = str(node)
                    stripped_text = original_text.strip()
                    new_text = original_text.replace(stripped_text, translated_map[uid], 1)
                    node.replace_with(new_text)
                    modified = True
                    
            if modified:
                item.set_content(soup.encode('utf-8'))

        epub.write_epub(self.out_path, book)
        if os.path.exists(self.state_file): os.remove(self.state_file)
        self.sig_done.emit(self.out_path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker: Optional[TranslationWorker] = None
        self.fetcher_worker: Optional[ModelFetcherWorker] = None
        
        self.setWindowTitle("Enot Translator")
        self.setMinimumSize(1020, 720)
        self.setStyleSheet(STYLESHEET)
        
        self._build_interface_layout()
        QTimer.singleShot(200, self._trigger_model_fetch)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()
            
        if self.fetcher_worker and self.fetcher_worker.isRunning():
            self.fetcher_worker.quit()
            self.fetcher_worker.wait()
            
        event.accept()

    def _build_interface_layout(self) -> None:
        main_container = QWidget()
        self.setCentralWidget(main_container)
        base_layout = QVBoxLayout(main_container)

        self._build_header(base_layout)

        ui_splitter = QSplitter(Qt.Orientation.Vertical)
        base_layout.addWidget(ui_splitter)
        
        control_card = QWidget()
        controls_layout = QVBoxLayout(control_card)
        ui_splitter.addWidget(control_card)

        self._build_file_section(controls_layout)
        self._build_settings_section(controls_layout)
        self._build_progress_section(controls_layout)
        self._build_action_section(controls_layout)
        self._build_terminal_section(ui_splitter)

    def _build_header(self, base_layout: QVBoxLayout) -> None:
        header_frame = QHBoxLayout()
        title_lbl = QLabel("🦝 Enot Translator")
        title_lbl.setObjectName("hero")
        header_frame.addWidget(title_lbl)
        header_frame.addStretch()
        self.server_status = QLabel("⬤")
        self.server_status.setStyleSheet("color: #334155;")
        header_frame.addWidget(self.server_status)
        base_layout.addLayout(header_frame)

    def _build_file_section(self, controls_layout: QVBoxLayout) -> None:
        input_group = QGroupBox("📂 File")
        input_box = QHBoxLayout(input_group)
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Path to .txt or .epub file …")
        browse_in_btn = QPushButton("Browse …")
        browse_in_btn.setObjectName("small")
        browse_in_btn.clicked.connect(self._select_input_file)
        input_box.addWidget(self.input_field)
        input_box.addWidget(browse_in_btn)
        controls_layout.addWidget(input_group)

        output_group = QGroupBox("💾 Output")
        output_box = QHBoxLayout(output_group)
        self.output_field = QLineEdit()
        browse_out_btn = QPushButton("Browse …")
        browse_out_btn.setObjectName("small")
        browse_out_btn.clicked.connect(self._select_output_destination)
        output_box.addWidget(self.output_field)
        output_box.addWidget(browse_out_btn)
        controls_layout.addWidget(output_group)

    def _add_separator(self, layout: QHBoxLayout) -> None:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

    def _build_settings_section(self, controls_layout: QVBoxLayout) -> None:
        settings_group = QGroupBox("⚙️ Settings")
        settings_box = QHBoxLayout(settings_group)

        settings_box.addWidget(QLabel("API:"))
        self.server_url_input = QLineEdit("http://localhost:11434")
        self.server_url_input.setFixedWidth(160)
        self.server_url_input.editingFinished.connect(self._trigger_model_fetch)
        settings_box.addWidget(self.server_url_input)

        self._add_separator(settings_box)

        settings_box.addWidget(QLabel("From:"))
        self.source_lang_combo = QComboBox()
        self.source_lang_combo.addItems(LANGUAGES)
        self.source_lang_combo.setCurrentText("")
        settings_box.addWidget(self.source_lang_combo)

        settings_box.addWidget(QLabel(" To:"))
        self.target_lang_combo = QComboBox()
        self.target_lang_combo.addItems(LANGUAGES)
        self.target_lang_combo.setCurrentText("")
        settings_box.addWidget(self.target_lang_combo)

        self._add_separator(settings_box)

        self.model_selection_combo = QComboBox()
        settings_box.addWidget(QLabel("Model:"))
        settings_box.addWidget(self.model_selection_combo)

        self._add_separator(settings_box)

        settings_box.addWidget(QLabel("Batch:"))
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(1, 50)
        self.batch_size_spin.setValue(10)
        settings_box.addWidget(self.batch_size_spin)

        settings_box.addWidget(QLabel("Context:"))
        self.context_combo = QComboBox()
        self.context_combo.addItems(CONTEXT_SIZES)
        self.context_combo.setCurrentText("4096")
        settings_box.addWidget(self.context_combo)
        
        controls_layout.addWidget(settings_group)

    def _build_progress_section(self, controls_layout: QVBoxLayout) -> None:
        progress_group = QGroupBox("📊 Progress")
        progress_box = QVBoxLayout(progress_group)
        self.metrics_bar = QProgressBar()
        progress_box.addWidget(self.metrics_bar)
        self.metrics_lbl = QLabel("Idle")
        self.metrics_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_box.addWidget(self.metrics_lbl)
        controls_layout.addWidget(progress_group)

    def _build_action_section(self, controls_layout: QVBoxLayout) -> None:
        action_frame = QHBoxLayout()
        self.execute_btn = QPushButton("▶ Start / Resume")
        self.execute_btn.clicked.connect(self._begin_translation)
        self.halt_btn = QPushButton("⏸ Pause / Save")
        self.halt_btn.setObjectName("cancel")
        self.halt_btn.setEnabled(False)
        self.halt_btn.clicked.connect(self._pause_translation)
        action_frame.addStretch()
        action_frame.addWidget(self.halt_btn)
        action_frame.addWidget(self.execute_btn)
        controls_layout.addLayout(action_frame)

    def _build_terminal_section(self, ui_splitter: QSplitter) -> None:
        terminal_card = QWidget()
        terminal_box = QVBoxLayout(terminal_card)
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        terminal_box.addWidget(self.console_output)
        ui_splitter.addWidget(terminal_card)

    def _select_input_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Open", str(Path.home()), "Files (*.txt *.epub)")
        if file_path:
            self.input_field.setText(file_path)
            ext = Path(file_path).suffix
            self.output_field.setText(str(Path(file_path).parent / f"{Path(file_path).stem}_translated{ext}"))

    def _select_output_destination(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(self, "Save", str(Path.home()), "Files (*.txt *.epub)")
        if file_path:
            self.output_field.setText(file_path)

    def _trigger_model_fetch(self) -> None:
        if self.fetcher_worker and self.fetcher_worker.isRunning():
            self.fetcher_worker.quit()
            self.fetcher_worker.wait()

        self.server_status.setStyleSheet("color: #eab308;")
        url = self.server_url_input.text().strip()
        
        self.fetcher_worker = ModelFetcherWorker(url)
        self.fetcher_worker.sig_models.connect(self._on_models_fetched)
        self.fetcher_worker.sig_error.connect(self._on_models_error)
        self.fetcher_worker.start()

    def _on_models_fetched(self, detected_models: List[str]) -> None:
        if detected_models:
            current_selection = self.model_selection_combo.currentText()
            self.model_selection_combo.clear()
            self.model_selection_combo.addItems(detected_models)
            
            if current_selection in detected_models:
                self.model_selection_combo.setCurrentText(current_selection)
            else:
                self.model_selection_combo.setCurrentIndex(0)
                
            self.server_status.setStyleSheet("color: #4ade80;")
        else:
            self._on_models_error()

    def _on_models_error(self) -> None:
        self.model_selection_combo.clear()
        self.server_status.setStyleSheet("color: #ef4444;")

    def _post_log_message(self, text: str) -> None:
        self.console_output.append(f'<span style="color:#4ade80">[{time.strftime("%H:%M:%S")}] {text}</span>')
        self.console_output.moveCursor(QTextCursor.MoveOperation.End)

    def _begin_translation(self) -> None:
        if not self.input_field.text() or not self.output_field.text():
            QMessageBox.warning(self, "Error", "Select input and output files.")
            return
            
        if not self.source_lang_combo.currentText() or not self.target_lang_combo.currentText():
            QMessageBox.warning(self, "Error", "Select source and target languages.")
            return
            
        if not self.model_selection_combo.currentText():
            QMessageBox.warning(self, "Error", "No model selected. Check API connection.")
            return

        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()

        self.execute_btn.setEnabled(False)
        self.halt_btn.setEnabled(True)
        self.metrics_bar.setValue(0)
        self.console_output.clear()

        self.worker = TranslationWorker(
            in_path=self.input_field.text().strip(),
            out_path=self.output_field.text().strip(),
            src_lang=self.source_lang_combo.currentText(),
            tgt_lang=self.target_lang_combo.currentText(),
            model=self.model_selection_combo.currentText(),
            batch_sz=self.batch_size_spin.value(),
            context_size=int(self.context_combo.currentText()),
            ollama_url=self.server_url_input.text().strip()
        )
        self.worker.sig_progress.connect(self._update_progress_state)
        self.worker.sig_log.connect(self._post_log_message)
        self.worker.sig_done.connect(self._on_pipeline_success)
        self.worker.sig_error.connect(self._on_pipeline_failure)
        self.worker.sig_paused.connect(self._on_pipeline_paused)
        self.worker.start()

    def _pause_translation(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
        self.halt_btn.setEnabled(False)

    def _on_pipeline_paused(self) -> None:
        self.execute_btn.setEnabled(True)
        self.halt_btn.setEnabled(False)
        self.metrics_lbl.setText("Paused")

    def _update_progress_state(self, steps_completed: int, absolute_steps: int, textual_feedback: str) -> None:
        self.metrics_bar.setMaximum(absolute_steps)
        self.metrics_bar.setValue(steps_completed)
        self.metrics_lbl.setText(textual_feedback)

    def _on_pipeline_success(self, destination_path: str) -> None:
        self.execute_btn.setEnabled(True)
        self.halt_btn.setEnabled(False)
        self.metrics_lbl.setText("Done")
        QMessageBox.information(self, "Done", f"Translation complete:\n{destination_path}")

    def _on_pipeline_failure(self, error_message: str) -> None:
        self.execute_btn.setEnabled(True)
        self.halt_btn.setEnabled(False)
        self.metrics_lbl.setText("Error")
        QMessageBox.critical(self, "Error", error_message)

def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
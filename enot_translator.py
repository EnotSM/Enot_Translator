#!/usr/bin/env python3

import sys
import os
import re
import time
import json
import threading
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from constants import LANGUAGES, CONTEXT_SIZES, STYLESHEET, CYRILLIC_LANGUAGES, VALID_EXTENSIONS

if "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "wayland"
os.environ.setdefault("QT_WAYLAND_DISABLE_WINDOWDECORATION", "1")

log_level = logging.DEBUG if "--debug" in sys.argv else logging.WARNING
logging.basicConfig(
    level=log_level,
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
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSettings
    from PyQt6.QtGui import QTextCursor, QCloseEvent
except ImportError:
    print("❌ Missing dependency: PyQt6")
    sys.exit(1)

def repair_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()
    first_brace = raw.find("{")
    last_brace = raw.rfind("}")
    first_bracket = raw.find("[")
    last_bracket = raw.rfind("]")
    if first_brace != -1 and last_brace > first_brace:
        raw = raw[first_brace:last_brace + 1]
    elif first_bracket != -1 and last_bracket > first_bracket:
        raw = raw[first_bracket:last_bracket + 1]
    raw = re.sub(r',\s*}', '}', raw)
    raw = re.sub(r',\s*]', ']', raw)
    return raw


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

    def translate_batch(self, texts: List[str], src_lang: str, tgt_lang: str, model: str, context_size: int, cancel_event: Optional[threading.Event] = None, timeout: int = 300, progress_callback: Optional[callable] = None) -> List[str]:
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
                data = json.loads(repair_json(r.json().get("response", "{}")))
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
            
        return self._translate_isolated(texts, src_lang, tgt_lang, model, context_size, cancel_event, progress_callback)

    def _translate_isolated(self, texts: List[str], src_lang: str, tgt_lang: str, model: str, context_size: int, cancel_event: Optional[threading.Event] = None, progress_callback: Optional[callable] = None) -> List[str]:
        isolated_results = []
        total = len(texts)
        for i, text in enumerate(texts):
            if cancel_event and cancel_event.is_set():
                break

            if progress_callback:
                progress_callback(i + 1, total)

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

        if self.tgt_lang not in CYRILLIC_LANGUAGES:
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

            total_chars = sum(len(t) for t in texts_to_translate)
            estimated_tokens = total_chars // 3
            if estimated_tokens > self.context_size:
                self.sig_log.emit(f"⚠️ Batch {batch_counter}: ~{estimated_tokens} tokens exceeds context ({self.context_size}). Truncating may occur.")

            completed_before_batch = completed_segs

            def on_isolated_progress(current, total):
                self.sig_progress.emit(
                    completed_before_batch + current,
                    total_segments,
                    f"Isolated fallback {completed_before_batch + current}/{total_segments}"
                )

            try:
                res = client.translate_batch(
                    texts_to_translate, 
                    self.src_lang, 
                    self.tgt_lang, 
                    self.model,
                    self.context_size,
                    self._cancel,
                    progress_callback=on_isolated_progress
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
                self.sig_log.emit(f"⚠️ Batch {batch_counter} failed: {exc}")
                for uid, orig_text in batch:
                    self.sig_log.emit(f"   ⚠️ Segment {uid} kept as-is (batch error)")
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
            prefix = orig_line[:len(orig_line) - len(orig_line.lstrip())]
            suffix = orig_line[len(orig_line.rstrip()):]
            out_lines[idx] = prefix + trans_text + suffix

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
                    prefix = original_text[:len(original_text) - len(original_text.lstrip())]
                    suffix = original_text[len(original_text.rstrip()):]
                    node.replace_with(prefix + translated_map[uid] + suffix)
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
        self.settings = QSettings("EnotTranslator", "EnotTranslator")

        self.setWindowTitle("Enot Translator")
        self.setMinimumSize(1020, 720)
        self.setStyleSheet(STYLESHEET)

        self._build_interface_layout()
        self._load_settings()
        QTimer.singleShot(200, self._trigger_model_fetch)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_settings()
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

    def _load_settings(self) -> None:
        self.server_url_input.setText(self.settings.value("server_url", "http://localhost:11434"))
        self.source_lang_combo.setCurrentText(self.settings.value("source_lang", ""))
        self.target_lang_combo.setCurrentText(self.settings.value("target_lang", ""))
        self.batch_size_spin.setValue(int(self.settings.value("batch_size", 10)))
        context = self.settings.value("context_size", "4096")
        idx = self.context_combo.findText(context)
        if idx >= 0:
            self.context_combo.setCurrentIndex(idx)
        geo = self.settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)

    def _save_settings(self) -> None:
        self.settings.setValue("server_url", self.server_url_input.text())
        self.settings.setValue("source_lang", self.source_lang_combo.currentText())
        self.settings.setValue("target_lang", self.target_lang_combo.currentText())
        self.settings.setValue("batch_size", self.batch_size_spin.value())
        self.settings.setValue("context_size", self.context_combo.currentText())
        self.settings.setValue("geometry", self.saveGeometry())

    def _post_log_message(self, text: str) -> None:
        self.console_output.append(f'<span style="color:#4ade80">[{time.strftime("%H:%M:%S")}] {text}</span>')
        self.console_output.moveCursor(QTextCursor.MoveOperation.End)

    def _begin_translation(self) -> None:
        if not self.input_field.text() or not self.output_field.text():
            QMessageBox.warning(self, "Error", "Select input and output files.")
            return

        in_ext = Path(self.input_field.text()).suffix.lower()
        if in_ext not in VALID_EXTENSIONS:
            QMessageBox.warning(self, "Error", f"Unsupported format '{in_ext}'. Use .txt or .epub.")
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
    argv = [a for a in sys.argv if a != "--debug"]
    app = QApplication(argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

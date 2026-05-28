"""Speech-to-Text Module — Real-time microphone/system audio recognition with floating window display

Dependencies: sounddevice, numpy, faster-whisper
Standalone module, runs without plugin system. Exposes interface via VoiceToTextManager.

Note: onnxruntime must be imported before QApplication is created, otherwise it will segfault.
"""

import os
import queue
import threading
import time
from collections import deque
from datetime import datetime

# Pre-import faster_whisper (must be done before QApplication is created)
# Otherwise onnxruntime C extension initialization will conflict with Qt event loop, causing segfault
try:
    from faster_whisper import WhisperModel as _WhisperModel  # noqa: F401
except Exception:
    pass  # If not installed, load_model() will give a clear error later

import numpy as np
from PyQt5.QtCore import (
    Qt, QTimer, QPoint, pyqtSignal, QObject, QSettings
)
from PyQt5.QtGui import (
    QCursor, QMouseEvent
)
from PyQt5.QtWidgets import (
    QWidget, QTextEdit, QVBoxLayout, QHBoxLayout,
    QPushButton, QApplication
)

from config import SETTINGS_PATH

# ── Module-level Constants ──────────────────────────────────
SAMPLE_RATE = 16000          # Sample rate (Hz)
CHUNK_SECONDS = 1.0          # Chunk duration (seconds)
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_SECONDS)
SILENCE_THRESHOLD = 0.0001   # RMS silence threshold

# Project root directory (directory of this file)
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SAVE_DIR = os.path.join(_PROJECT_DIR, "STT_records")
MODEL_CACHE_DIR = os.path.join(_PROJECT_DIR, "stt_models")
os.makedirs(DEFAULT_SAVE_DIR, exist_ok=True)
os.makedirs(MODEL_CACHE_DIR, exist_ok=True)


# ── AudioCapture ─────────────────────────────────────────────
class AudioCapture:
    """Microphone audio capture"""

    def __init__(self):
        import sounddevice as sd
        self._sd = sd
        self._running = False
        self._stream = None
        self._audio_deque = deque()
        self._output_queue = queue.Queue(maxsize=60)
        self._push_timer: QTimer | None = None

    @property
    def output_queue(self):
        return self._output_queue

    def start(self):
        """Start microphone capture"""
        if self._running:
            return
        self._running = True
        self._output_queue = queue.Queue(maxsize=60)

        try:
            device = self._sd.default.device[0]
            if device is None or device < 0:
                device = self._sd.query_hostapis()[0]['default_input_device']
        except Exception:
            device = None

        def callback(indata, frames, time_info, status):
            if self._running:
                self._audio_deque.extend(indata[:, 0].tolist())

        stream = self._sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype='float32',
            device=device, callback=callback
        )
        stream.start()
        self._stream = stream

        self._push_timer = QTimer()
        self._push_timer.setInterval(int(CHUNK_SECONDS * 1000))
        self._push_timer.timeout.connect(self._push_chunk)
        self._push_timer.start()

    def stop(self):
        """Stop capture"""
        self._running = False
        if self._push_timer:
            self._push_timer.stop()
            self._push_timer = None
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._audio_deque.clear()
        while not self._output_queue.empty():
            try:
                self._output_queue.get_nowait()
            except queue.Empty:
                break

    def _push_chunk(self):
        """Fetch 1 second of audio from buffer and push to output queue"""
        if not self._running:
            return
        n = min(len(self._audio_deque), CHUNK_SAMPLES)
        if n == 0:
            return
        data = [self._audio_deque.popleft() for _ in range(n)]
        arr = np.array(data, dtype=np.float32)
        rms = float(np.sqrt(np.mean(arr ** 2)))
        if rms < SILENCE_THRESHOLD:
            return
        try:
            self._output_queue.put_nowait(arr)
        except queue.Full:
            pass


# ── STTRecognizer ────────────────────────────────────────────
class STTRecognizer(QObject):
    """Offline speech recognizer based on faster-whisper, runs in a separate worker thread"""

    result_ready = pyqtSignal(str)        # Recognized result text
    error_occurred = pyqtSignal(str)      # Error message
    model_loaded = pyqtSignal()           # Model loading complete
    loading_progress = pyqtSignal(str)    # Loading progress message
    rms_level = pyqtSignal(float)         # Real-time audio RMS level

    def __init__(self, model_size="base", device="cpu", compute_type="int8"):
        super().__init__()
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def model_size(self):
        return self._model_size

    @model_size.setter
    def model_size(self, value):
        self._model_size = value

    def load_model(self):
        """Load faster-whisper model in the main thread (must be called from main thread, ctranslate2 does not support child thread initialization)"""
        try:
            # Prefer HuggingFace domestic mirror (hf-mirror.com)
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

            # Set model cache directory to project folder
            os.environ.setdefault("HF_HOME", MODEL_CACHE_DIR)
            os.environ.setdefault("HUGGINGFACE_HUB_CACHE",
                                  os.path.join(MODEL_CACHE_DIR, "hub"))

            from faster_whisper import WhisperModel

            self.loading_progress.emit(
                f"Loading faster-whisper model ({self._model_size})..."
            )
            # Process pending Qt events to avoid UI freeze
            QApplication.processEvents()

            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
            self.model_loaded.emit()
        except Exception as e:
            self.error_occurred.emit(f"Model loading failed: {e}")

    def start_recognize(self, audio_queue: queue.Queue):
        """Start the recognition worker thread"""
        if self._model is None:
            self.error_occurred.emit("Model not loaded, please call load_model() first")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._recognize_loop,
            args=(audio_queue,),
            daemon=True
        )
        self._thread.start()

    def stop_recognize(self):
        """Stop the recognition thread"""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _recognize_loop(self, audio_queue: queue.Queue):
        """Recognition worker thread main loop"""
        while not self._stop_event.is_set():
            try:
                audio = audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if audio is None or self._stop_event.is_set():
                continue

            # Silence detection
            rms = float(np.sqrt(np.mean(audio ** 2)))
            if rms < SILENCE_THRESHOLD:
                continue

            # Notify UI of current audio level
            self.rms_level.emit(rms)

            # Auto gain: normalize audio to target RMS level to improve Whisper recognition rate
            if rms > 0:
                target_rms = 0.1
                audio = audio * (target_rms / rms)
                audio = np.clip(audio, -1.0, 1.0)

            try:
                segments, _ = self._model.transcribe(
                    audio,
                    language="zh",
                    beam_size=5,
                    vad_filter=True,
                    vad_parameters=dict(
                        min_silence_duration_ms=300,
                        threshold=0.3,
                    ),
                )
                text = "".join(seg.text for seg in segments).strip()
                if text:
                    # Traditional to Simplified Chinese conversion
                    try:
                        import zhconv
                        text = zhconv.convert(text, 'zh-cn')
                    except Exception:
                        pass
                    self.result_ready.emit(text)
            except Exception as e:
                self.error_occurred.emit(f"Recognition error: {e}")


# ── STTResultWindow ─────────────────────────────────────────
class STTResultWindow(QWidget):
    """Floating dark window displaying the last N lines of recognized text, follows the pet anchor"""

    closed = pyqtSignal()

    def __init__(self, anchor_widget: QWidget | None = None):
        super().__init__()
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(380, 200)

        self._anchor = anchor_widget
        self._max_lines = 5
        self._show_timestamp = True
        self._source_label = ""
        self._drag_pos = None     # Window drag start point
        self._dragging = False

        self._setup_ui()
        self._setup_follow_timer()

    def _setup_ui(self):
        """Build UI layout"""
        self.setObjectName("STTResultWindow")
        self.setStyleSheet("""
            #STTResultWindow {
                background-color: rgba(40, 40, 45, 220);
                border: 1px solid #555;
                border-radius: 8px;
            }
        """)

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        # Title bar
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(0, 0, 0, 0)

        self._title_label = QPushButton("Speech to Text")
        self._title_label.setStyleSheet("""
            QPushButton {
                color: #ccc; font-size: 11px; font-weight: bold;
                background: transparent; border: none; text-align: left;
                padding: 2px 0;
            }
            QPushButton:hover { color: #fff; }
        """)
        self._title_label.setCursor(Qt.OpenHandCursor)
        self._title_label.pressed.connect(self._on_title_pressed)
        self._title_label.move

        self._status_label = QPushButton("Ready")
        self._status_label.setStyleSheet("""
            QPushButton {
                color: #888; font-size: 10px;
                background: transparent; border: none;
                padding: 2px 4px;
            }
        """)
        self._status_label.setEnabled(False)

        close_btn = QPushButton("x")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("""
            QPushButton {
                color: #999; font-size: 14px; font-weight: bold;
                background: transparent; border: none; border-radius: 4px;
            }
            QPushButton:hover { color: #fff; background: #c0392b; }
        """)
        close_btn.clicked.connect(self.hide_window)

        title_bar.addWidget(self._title_label)
        title_bar.addStretch()
        title_bar.addWidget(self._status_label)
        title_bar.addWidget(close_btn)

        # Text display area
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setStyleSheet("""
            QTextEdit {
                background-color: rgba(30, 30, 35, 180);
                color: #e0e0e0;
                font-family: "Microsoft YaHei", "Consolas", sans-serif;
                font-size: 12px;
                border: none;
                border-radius: 4px;
                padding: 4px;
            }
            QScrollBar:vertical {
                background: #2b2b2b; width: 6px; border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #555; border-radius: 3px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        layout.addLayout(title_bar)
        layout.addWidget(self._text_edit)

    def _setup_follow_timer(self):
        """Set up timer to follow anchor"""
        self._follow_timer = QTimer(self)
        self._follow_timer.setInterval(100)
        self._follow_timer.timeout.connect(self._reposition)
        # Not started initially, starts when show_window is called

    def set_anchor(self, widget: QWidget):
        """Set the anchor widget to follow"""
        self._anchor = widget

    def set_source_label(self, label: str):
        """Set the audio source label display"""
        self._source_label = label
        self._update_title()

    def set_status(self, text: str, color: str = "#888"):
        """Update the status bar text"""
        self._status_label.setText(text)
        self._status_label.setStyleSheet(f"""
            QPushButton {{
                color: {color}; font-size: 10px;
                background: transparent; border: none;
                padding: 2px 4px;
            }}
        """)

    def add_text(self, text: str):
        """Add a line of recognized text"""
        timestamp = ""
        if self._show_timestamp:
            timestamp = datetime.now().strftime("[%H:%M:%S] ")

        line = f"{timestamp}{text}"
        self._text_edit.append(line)

        # Limit the number of lines
        doc = self._text_edit.document()
        while doc.blockCount() > self._max_lines + 1:
            cursor = doc.findBlockByNumber(0)
            if cursor.isValid():
                cursor_sel = self._text_edit.textCursor()
                cursor_sel.movePosition(
                    cursor_sel.MoveOperation.Start
                )
                cursor_sel.movePosition(
                    cursor_sel.MoveOperation.Down,
                    cursor_sel.MoveMode.KeepAnchor
                )
                cursor_sel.removeSelectedText()
                cursor_sel.deleteChar()
            else:
                break

        # Scroll to bottom
        scrollbar = self._text_edit.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def set_max_lines(self, n: int):
        """Set the maximum number of displayed lines"""
        self._max_lines = max(2, min(n, 20))

    def set_show_timestamp(self, show: bool):
        """Set whether to show timestamps"""
        self._show_timestamp = show

    def show_window(self):
        """Show the window and start following"""
        self._reposition()
        self.show()
        self._follow_timer.start()

    def hide_window(self):
        """Hide the window and stop following"""
        self._follow_timer.stop()
        self.hide()
        self.closed.emit()

    def _reposition(self):
        """Position to the right of the anchor widget"""
        if self._anchor and not self._dragging:
            ap = self._anchor.pos()
            ax = ap.x() + self._anchor.width()
            ay = ap.y()
            self.move(ax + 8, ay)

    def _update_title(self):
        """Update the title bar"""
        if self._source_label:
            self._title_label.setText(f"Speech to Text — {self._source_label}")
        else:
            self._title_label.setText("Speech to Text")

    def _on_title_pressed(self):
        """Title bar pressed - start dragging"""
        self._drag_pos = self.mapFromGlobal(QCursor.pos())
        self._dragging = True
        self._title_label.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Drag to move the window"""
        if self._dragging and self._drag_pos:
            delta = event.pos() - self._drag_pos
            self.move(self.pos() + delta)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """End dragging"""
        if self._dragging:
            self._dragging = False
            self._drag_pos = None
            self._title_label.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)


# ── VoiceToTextManager ──────────────────────────────────────
class VoiceToTextManager:
    """Speech-to-text controller, coordinates capture, recognition, display, and configuration"""

    def __init__(self, pet_widget: QWidget | None = None):
        self._pet = pet_widget
        self._capture: AudioCapture | None = None
        self._recognizer: STTRecognizer | None = None
        self._window: STTResultWindow | None = None
        self._running = False

        # Load configuration
        self._settings = QSettings(SETTINGS_PATH, QSettings.IniFormat)
        self._model_size = self._settings.value("stt/model_size", "base")
        self._save_enabled = self._settings.value("stt/save_enabled", "true") == "true"
        self._save_folder = self._settings.value("stt/save_folder", DEFAULT_SAVE_DIR)
        self._max_lines = int(self._settings.value("stt/max_lines", "5"))
        self._show_timestamp = self._settings.value("stt/show_timestamp", "true") == "true"

    @property
    def running(self):
        return self._running

    @property
    def model_size(self):
        return self._model_size

    @property
    def save_folder(self):
        return self._save_folder

    def _ensure_recognizer(self):
        """Ensure the recognizer is initialized and model is loaded"""
        if self._recognizer is None:
            self._recognizer = STTRecognizer(
                model_size=self._model_size,
                device="cpu",
                compute_type="int8"
            )
            self._recognizer.result_ready.connect(self._on_result)
            self._recognizer.error_occurred.connect(self._on_error)
            self._recognizer.model_loaded.connect(self._on_model_loaded)
            self._recognizer.loading_progress.connect(self._on_loading_progress)
            self._recognizer.rms_level.connect(self._on_rms_level)
            self._recognizer.load_model()

    def _ensure_window(self):
        """Ensure the floating window is created"""
        if self._window is None:
            self._window = STTResultWindow(self._pet)
            self._window.set_max_lines(self._max_lines)
            self._window.set_show_timestamp(self._show_timestamp)
            self._window.closed.connect(self._on_window_closed)

    def start(self):
        """Start speech to text"""
        if self._running:
            self.stop()

        self._ensure_window()
        self._window.set_source_label("Microphone")
        self._window.set_status("Loading model...", "#f39c12")
        self._window.show_window()
        QApplication.processEvents()

        self._ensure_recognizer()
        if self._recognizer._model is None:
            return

        self._do_start()

    def _do_start(self):
        """Actually start capture and recognition"""
        try:
            self._capture = AudioCapture()
            self._capture.start()
        except Exception as e:
            if self._window:
                self._window.set_status(f"Start failed: {e}", "#e74c3c")
            return

        self._recognizer.start_recognize(self._capture.output_queue)
        self._running = True

        if self._window:
            self._window.set_source_label("Microphone")
            self._window.set_status("Capturing", "#2ecc71")
            self._window.show_window()

    def stop(self):
        """Stop speech to text"""
        self._running = False
        if self._capture:
            self._capture.stop()
            self._capture = None
        if self._recognizer:
            self._recognizer.stop_recognize()
        if self._window:
            self._window.set_status("Stopped", "#888")

    def toggle(self):
        """Toggle start/stop"""
        if self._running:
            self.stop()
        else:
            self.start()

    def show_settings(self):
        """Show settings dialog"""
        from PyQt5.QtWidgets import (
            QDialog, QComboBox, QLineEdit, QSpinBox, QCheckBox,
            QPushButton, QHBoxLayout, QFileDialog,
            QVBoxLayout, QLabel,
        )

        dlg = QDialog(self._pet)
        dlg.setWindowTitle("Speech to Text Settings")
        dlg.setFixedSize(400, 280)
        dlg.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: #e0e0e0; }
            QLabel { color: #ccc; font-size: 12px; }
            QCheckBox { color: #ccc; font-size: 12px; }
            QComboBox {
                background: #3c3c3c; color: #e0e0e0; border: 1px solid #555;
                padding: 4px; border-radius: 3px;
            }
            QLineEdit {
                background: #3c3c3c; color: #e0e0e0; border: 1px solid #555;
                padding: 4px; border-radius: 3px;
            }
            QSpinBox {
                background: #3c3c3c; color: #e0e0e0; border: 1px solid #555;
                padding: 4px; border-radius: 3px;
            }
            QPushButton {
                background: #3c3c3c; color: #e0e0e0; border: 1px solid #555;
                padding: 6px 16px; border-radius: 4px;
            }
            QPushButton:hover { background: #4a4a4a; }
            QPushButton#OkBtn {
                background: #2980b9; color: white; font-weight: bold;
            }
            QPushButton#OkBtn:hover { background: #3498db; }
        """)

        layout = QVBoxLayout(dlg)

        # ── Recognition Model ──
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Recognition Model:"))
        model_combo = QComboBox()
        model_combo.addItems(["tiny", "base", "small"])
        model_combo.setCurrentText(self._model_size)
        model_layout.addWidget(model_combo)
        model_layout.addStretch()
        layout.addLayout(model_layout)

        # ── Save Folder ──
        save_layout = QHBoxLayout()
        save_layout.addWidget(QLabel("Save Folder:"))
        save_edit = QLineEdit(self._save_folder)
        save_layout.addWidget(save_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(lambda: self._browse_folder(save_edit))
        save_layout.addWidget(browse_btn)
        layout.addLayout(save_layout)

        # ── Options ──
        cb_save = QCheckBox("Auto-save to file")
        cb_save.setChecked(self._save_enabled)
        cb_ts = QCheckBox("Show timestamps")
        cb_ts.setChecked(self._show_timestamp)
        layout.addWidget(cb_save)
        layout.addWidget(cb_ts)

        # ── Line Count ──
        line_layout = QHBoxLayout()
        line_layout.addWidget(QLabel("Max displayed lines:"))
        line_spin = QSpinBox()
        line_spin.setRange(2, 20)
        line_spin.setValue(self._max_lines)
        line_layout.addWidget(line_spin)
        line_layout.addStretch()
        layout.addLayout(line_layout)

        layout.addStretch()

        # ── Buttons ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("OkBtn")
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        def on_ok():
            new_model = model_combo.currentText()
            new_folder = save_edit.text().strip()
            new_save = cb_save.isChecked()
            new_ts = cb_ts.isChecked()
            new_lines = line_spin.value()

            self._model_size = new_model
            self._save_folder = new_folder
            self._save_enabled = new_save
            self._show_timestamp = new_ts
            self._max_lines = new_lines

            self._settings.setValue("stt/model_size", new_model)
            self._settings.setValue("stt/save_folder", new_folder)
            self._settings.setValue("stt/save_enabled", str(new_save).lower())
            self._settings.setValue("stt/show_timestamp", str(new_ts).lower())
            self._settings.setValue("stt/max_lines", str(new_lines))
            self._settings.sync()

            if self._window:
                self._window.set_max_lines(new_lines)
                self._window.set_show_timestamp(new_ts)

            dlg.accept()

        ok_btn.clicked.connect(on_ok)
        dlg.exec_()

    def show_quick_menu(self):
        """Show STT quick menu (called on double-click)"""
        from PyQt5.QtWidgets import QMenu

        menu = QMenu(self._pet)
        menu.setStyleSheet("""
            QMenu { background-color: #2b2b2b; color: #e0e0e0; border: 1px solid #555; padding: 4px; }
            QMenu::item { padding: 6px 28px 6px 12px; }
            QMenu::item:selected { background-color: #3a3a3a; }
            QMenu::separator { height: 1px; background: #444; margin: 4px 8px; }
        """)

        if self._running:
            start_action = menu.addAction("Start Recognition")
            start_action.setEnabled(False)
            stop_action = menu.addAction("Stop Recognition")
            stop_action.triggered.connect(self.stop)
        else:
            start_action = menu.addAction("Start Recognition")
            start_action.triggered.connect(self.start)
            stop_action = menu.addAction("Stop Recognition")
            stop_action.setEnabled(False)

        menu.addSeparator()
        settings_action = menu.addAction("Settings...")
        settings_action.triggered.connect(self.show_settings)

        if self._pet:
            pos = self._pet.mapToGlobal(QPoint(self._pet.width() + 4, 0))
            menu.exec_(pos)

    def _browse_folder(self, line_edit):
        """Browse folder dialog"""
        from PyQt5.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(
            self._pet or self._window,
            "Select Save Folder",
            line_edit.text() or DEFAULT_SAVE_DIR
        )
        if folder:
            line_edit.setText(folder)

    # ── Signal Handlers ──
    def _on_result(self, text: str):
        """Handle recognized result"""
        if self._window:
            self._window.add_text(text)

        if self._save_enabled:
            self._save_to_file(text)

    def _on_error(self, message: str):
        """Handle error"""
        if self._window:
            self._window.set_status(message, "#e74c3c")
        print(f"[STT Error] {message}")

    def _on_rms_level(self, rms: float):
        """Update status bar with real-time audio level"""
        if self._window and self._running:
            # Display level with progress bar style text
            bars = int(min(rms / 0.01, 1.0) * 10)
            level_bar = "█" * bars + "░" * (10 - bars)
            self._window.set_status(f"Level [{level_bar}]", "#2ecc71" if rms > 0.001 else "#f39c12")

    def _on_model_loaded(self):
        """Model loaded (for logging only; start() already synchronously handles subsequent flow)"""
        self._window.set_status("Model Ready", "#2ecc71")

    def _on_loading_progress(self, message: str):
        """Model loading progress"""
        if self._window:
            self._window.set_status(message, "#f39c12")
        print(f"[STT] {message}")

    def _on_window_closed(self):
        """Floating window closed by user"""
        if self._running:
            self.stop()

    def _save_to_file(self, text: str):
        """Append recognized text to a file"""
        try:
            folder = self._save_folder or DEFAULT_SAVE_DIR
            os.makedirs(folder, exist_ok=True)
            filename = datetime.now().strftime("%Y-%m-%d") + ".txt"
            filepath = os.path.join(folder, filename)
            timestamp = datetime.now().strftime("[%H:%M:%S] ")
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(f"{timestamp}{text}\n")
        except Exception as e:
            print(f"[STT Save Failed] {e}")

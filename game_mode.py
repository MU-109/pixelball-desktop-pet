"""Game mode module — Performance monitoring panel + Keyboard input recording panel"""

import time

from PyQt5.QtCore import QObject, QTimer, pyqtSignal, Qt, QPoint
from PyQt5.QtGui import QPainter, QColor, QFont, QFontDatabase
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QApplication

import config as cfg


# ═══════════════════════════════════════════════════════════════
# Performance Monitoring Panel
# ═══════════════════════════════════════════════════════════════

class PerformancePanel(QWidget):
    """Semi-transparent floating panel displaying FPS / CPU / GPU+temperature / RAM / Battery in a horizontal row"""

    BAR_CHARS = "█▇▆▅▄▃▂▁ "

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gpu_handle = None
        self._has_gpu = False
        self._fps_frames = 0
        self._fps_value = 0
        self._cpu = 0
        self._ram_used_gb = 0.0
        self._ram_total_gb = 0.0
        self._gpu_util = 0
        self._gpu_temp = 0

        self._init_ui()
        self._init_gpu()

        # FPS sampling (settle once per second)
        self._fps_timer = QTimer(self)
        self._fps_timer.setInterval(1000)
        self._fps_timer.timeout.connect(self._tick_fps)
        self._fps_timer.start()

        # Frame counter (+1 every 16ms)
        self._frame_counter = QTimer(self)
        self._frame_counter.setInterval(16)
        self._frame_counter.timeout.connect(lambda: setattr(self, '_fps_frames', self._fps_frames + 1))
        self._frame_counter.start()

        # Data refresh
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000)
        self._refresh_timer.timeout.connect(self._refresh_data)
        self._refresh_timer.start()

    def _init_ui(self):
        self.setWindowTitle("Performance Monitor")
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedHeight(30)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 4, 14, 4)
        layout.setSpacing(16)

        font = QFont("Consolas", 10)
        self._label = QLabel("")
        self._label.setFont(font)
        self._label.setStyleSheet("color: #00ff88; background: transparent;")
        layout.addWidget(self._label)

        screen = QApplication.primaryScreen().geometry()
        self.resize(640, 30)
        x = (screen.width() - self.width()) // 2
        self.move(x, 0)

    def _init_gpu(self):
        try:
            from pynvml import nvmlInit, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex
            nvmlInit()
            if nvmlDeviceGetCount() > 0:
                self._gpu_handle = nvmlDeviceGetHandleByIndex(0)
                self._has_gpu = True
        except Exception:
            self._gpu_handle = None

    def _tick_fps(self):
        self._fps_value = self._fps_frames
        self._fps_frames = 0

    @staticmethod
    def _bar(percent, width=6):
        """Simple progress bar"""
        if percent < 0:
            percent = 0
        elif percent > 100:
            percent = 100
        filled = round(percent / 100 * width)
        return "▐" + "█" * filled + "░" * (width - filled) + "▌"

    def _refresh_data(self):
        try:
            import psutil
            self._cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory()
            self._ram_used_gb = ram.used / (1024 ** 3)
            self._ram_total_gb = ram.total / (1024 ** 3)

            if self._has_gpu:
                try:
                    from pynvml import (
                        nvmlDeviceGetUtilizationRates,
                        nvmlDeviceGetTemperature,
                        NVML_TEMPERATURE_GPU,
                    )
                    util = nvmlDeviceGetUtilizationRates(self._gpu_handle)
                    self._gpu_util = util.gpu
                    self._gpu_temp = nvmlDeviceGetTemperature(self._gpu_handle, NVML_TEMPERATURE_GPU)
                except Exception:
                    self._gpu_util = -1
                    self._gpu_temp = -1

            bat = psutil.sensors_battery()
        except ImportError:
            self._label.setText("psutil not installed")
            return
        except Exception:
            return
        segments = []

        # FPS
        fps_color = "#00ff88" if self._fps_value >= 60 else ("#ffaa00" if self._fps_value >= 30 else "#ff4444")
        segments.append(
            f"<span style='color:#aaaaaa;'>FPS</span> "
            f"<span style='color:{fps_color};'>{self._fps_value:>3}</span>"
        )

        # CPU
        segments.append(
            f"<span style='color:#aaaaaa;'>CPU</span> "
            f"<span style='color:#00ccff;'>{self._cpu:>3}%</span>"
            f"<span style='color:#0088aa;'>{self._bar(self._cpu)}</span>"
        )

        # GPU
        if self._has_gpu and self._gpu_util >= 0:
            gpu_parts = [
                f"<span style='color:#aaaaaa;'>GPU</span> ",
                f"<span style='color:#cc88ff;'>{self._gpu_util:>3}%</span>",
                f"<span style='color:#8866aa;'>{self._bar(self._gpu_util)}</span>",
            ]
            if self._gpu_temp >= 0:
                gpu_parts.append(
                    f"<span style='color:#ff8888;'>{self._gpu_temp}°C</span>"
                )
            segments.append("".join(gpu_parts))
        else:
            segments.append("<span style='color:#666666;'>GPU N/A</span>")

        # RAM
        ram_pct = self._ram_used_gb / self._ram_total_gb * 100 if self._ram_total_gb > 0 else 0
        segments.append(
            f"<span style='color:#aaaaaa;'>RAM</span> "
            f"<span style='color:#ffcc00;'>{self._ram_used_gb:.1f}/{self._ram_total_gb:.0f}G</span>"
            f"<span style='color:#887700;'>{self._bar(ram_pct)}</span>"
        )

        # Battery
        if bat and bat.percent >= 0:
            status = "⚡" if bat.power_plugged else "🔋"
            bat_pct = bat.percent
            bat_color = "#00ff88" if bat_pct > 50 or bat.power_plugged else ("#ffaa00" if bat_pct > 20 else "#ff4444")
            segments.append(
                f"<span style='color:{bat_color};'>{status} {bat_pct}%</span>"
            )

        self._label.setText("  │  ".join(segments))
        self.adjustSize()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 170))
        painter.setPen(QColor(0, 255, 136, 60))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)

    # ── Drag ─────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.globalPos()

    def mouseMoveEvent(self, event):
        if hasattr(self, '_drag_start'):
            delta = event.globalPos() - self._drag_start
            self.move(self.pos() + delta)
            self._drag_start = event.globalPos()

    def mouseReleaseEvent(self, event):
        if hasattr(self, '_drag_start'):
            del self._drag_start
            self._save_position()

    def _save_position(self):
        from PyQt5.QtCore import QSettings
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        s.setValue("game_mode/perf_panel_x", self.x())
        s.setValue("game_mode/perf_panel_y", self.y())

    def _load_position(self):
        from PyQt5.QtCore import QSettings
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        x = s.value("game_mode/perf_panel_x", None)
        y = s.value("game_mode/perf_panel_y", None)
        if x is not None and y is not None:
            self.move(int(x), int(y))

    def closeEvent(self, event):
        self._save_position()
        super().closeEvent(event)

    def contextMenuEvent(self, event):
        from PyQt5.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: #222; color: #ddd; border: 1px solid #555; } QMenu::item:selected { background: #444; }")
        menu.addAction("Exit Game Mode").triggered.connect(self._exit_game_mode)
        menu.exec_(event.globalPos())

    def _exit_game_mode(self):
        if hasattr(self, 'exit_callback') and self.exit_callback:
            self.exit_callback()


# ═══════════════════════════════════════════════════════════════
# Keyboard Input Recording Panel
# ═══════════════════════════════════════════════════════════════

class KeyboardPanel(QWidget):
    """Semi-transparent floating panel recording keyboard + mouse clicks in vertical layout, latest 10 entries, relative time toggleable"""

    _key_event = pyqtSignal(str)

    # Common key name mapping
    _KEY_MAP = {
        "space": "Space", "enter": "Enter", "tab": "Tab", "esc": "Esc",
        "backspace": "Bksp", "delete": "Del", "shift": "Shift", "shift_r": "R-Shift",
        "ctrl": "Ctrl", "ctrl_r": "R-Ctrl", "alt": "Alt", "alt_r": "R-Alt",
        "alt_gr": "AltGr", "cmd": "Win", "cmd_r": "R-Win",
        "up": "↑", "down": "↓", "left": "←", "right": "→",
        "caps_lock": "Caps", "num_lock": "NumLk", "print_screen": "PrtSc",
        "page_up": "PgUp", "page_down": "PgDn", "home": "Home", "end": "End",
        "insert": "Ins", "pause": "Pause", "menu": "Menu",
        "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4",
        "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
        "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
        "media_volume_up": "⏐⋊", "media_volume_down": "⏐⋉",
        "media_volume_mute": "🔇",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[tuple[float, str]] = []
        self._show_interval = True
        self._listener_kb = None
        self._listener_ms = None

        self._init_ui()
        self._load_settings()

        self._key_event.connect(self._add_entry)
        self._start_listeners()

    def _init_ui(self):
        self.setWindowTitle("Key Log")
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(1)

        font = QFont("Consolas", 9)
        self._labels: list[QLabel] = []
        for _ in range(10):
            lbl = QLabel("")
            lbl.setFont(font)
            lbl.setStyleSheet("color: #cccccc; background: transparent;")
            lbl.setFixedHeight(17)
            layout.addWidget(lbl)
            self._labels.append(lbl)

        screen = QApplication.primaryScreen().geometry()
        self.setFixedWidth(200)
        x = screen.width() - self.width() - 10
        y = (screen.height() - 220) // 2
        self.move(x, y)

    def _load_settings(self):
        from PyQt5.QtCore import QSettings
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        self._show_interval = s.value(
            "game_mode/keyboard_show_interval", True, type=bool
        )

    def _start_listeners(self):
        try:
            from pynput.keyboard import Listener as KBListener, Key, KeyCode
            from pynput.mouse import Listener as MSListener

            def _on_key_press(key):
                if isinstance(key, KeyCode) and key.char is not None:
                    # Regular printable character
                    name = key.char
                elif isinstance(key, Key):
                    # Special key
                    name = self._KEY_MAP.get(key.name, key.name.title())
                else:
                    name = str(key)
                self._key_event.emit(name)

            def _on_click(x, y, button, pressed):
                if pressed:
                    btn_name = str(button).split(".")[-1]
                    btn_map = {
                        "left": "L-Click", "right": "R-Click", "middle": "M-Click",
                        "x1": "Side1", "x2": "Side2",
                    }
                    self._key_event.emit(btn_map.get(btn_name, btn_name))

            def _on_scroll(x, y, dx, dy):
                if dy > 0:
                    self._key_event.emit("Scroll↑")
                elif dy < 0:
                    self._key_event.emit("Scroll↓")

            self._listener_kb = KBListener(on_press=_on_key_press)
            self._listener_ms = MSListener(on_click=_on_click, on_scroll=_on_scroll)
            self._listener_kb.daemon = True
            self._listener_ms.daemon = True
            self._listener_kb.start()
            self._listener_ms.start()
        except Exception:
            pass

    def _stop_listeners(self):
        for lst in [self._listener_kb, self._listener_ms]:
            if lst:
                try:
                    lst.stop()
                except Exception:
                    pass
        self._listener_kb = None
        self._listener_ms = None

    def _add_entry(self, text):
        now = time.time()
        self._entries.append((now, text))
        if len(self._entries) > 10:
            self._entries = self._entries[-10:]
        self._refresh_display()

    def _refresh_display(self):
        entries = self._entries
        for i in range(10):
            lbl = self._labels[i]
            # Map from oldest to newest: label[0] = entries[-10], label[9] = entries[-1]
            idx = len(entries) - 10 + i
            if idx < 0 or idx >= len(entries):
                lbl.setText("")
                continue
            ts, text = entries[idx]
            if self._show_interval and idx > 0:
                interval = ts - entries[idx - 1][0]
                lbl.setText(f"[+{interval:.1f}s] {text}")
            elif self._show_interval and idx == 0:
                lbl.setText(f"[+0.0s] {text}")
            else:
                lbl.setText(text)

    def set_show_interval(self, show: bool):
        self._show_interval = show
        from PyQt5.QtCore import QSettings
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        s.setValue("game_mode/keyboard_show_interval", show)
        self._refresh_display()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 170))
        painter.setPen(QColor(100, 100, 100, 60))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)

    # ── Drag ─────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.globalPos()

    def mouseMoveEvent(self, event):
        if hasattr(self, '_drag_start'):
            delta = event.globalPos() - self._drag_start
            self.move(self.pos() + delta)
            self._drag_start = event.globalPos()

    def mouseReleaseEvent(self, event):
        if hasattr(self, '_drag_start'):
            del self._drag_start
            self._save_position()

    def _save_position(self):
        from PyQt5.QtCore import QSettings
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        s.setValue("game_mode/key_panel_x", self.x())
        s.setValue("game_mode/key_panel_y", self.y())

    def _load_position(self):
        from PyQt5.QtCore import QSettings
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        x = s.value("game_mode/key_panel_x", None)
        y = s.value("game_mode/key_panel_y", None)
        if x is not None and y is not None:
            self.move(int(x), int(y))

    def closeEvent(self, event):
        self._stop_listeners()
        self._save_position()
        super().closeEvent(event)

    def contextMenuEvent(self, event):
        from PyQt5.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: #222; color: #ddd; border: 1px solid #555; } QMenu::item:selected { background: #444; }")
        menu.addAction("Exit Game Mode").triggered.connect(self._exit_game_mode)
        menu.exec_(event.globalPos())

    def _exit_game_mode(self):
        if hasattr(self, 'exit_callback') and self.exit_callback:
            self.exit_callback()


# ═══════════════════════════════════════════════════════════════
# Game Mode Manager
# ═══════════════════════════════════════════════════════════════

class GameModeManager(QObject):
    """Unified management of game mode state and panel lifecycle"""

    state_changed = pyqtSignal(bool)

    def __init__(self, pet_window, parent=None):
        super().__init__(parent)
        self._pet = pet_window
        self._active = False
        self._perf_panel: PerformancePanel | None = None
        self._key_panel: KeyboardPanel | None = None

        from PyQt5.QtCore import QSettings
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        self._perf_enabled = s.value("game_mode/performance_panel_enabled", True, type=bool)
        self._key_enabled = s.value("game_mode/keyboard_panel_enabled", True, type=bool)
        self._key_show_interval = s.value("game_mode/keyboard_show_interval", True, type=bool)

    # ── Enter/Exit Game Mode ─────────────────────────

    def enter(self):
        if self._active:
            return
        self._active = True
        self._pet.hide()
        if hasattr(self._pet, 'set_hotkey_enabled'):
            self._pet.set_hotkey_enabled(False)

        if self._perf_enabled:
            self._perf_panel = PerformancePanel()
            self._perf_panel.exit_callback = self.exit
            self._perf_panel.show()
        if self._key_enabled:
            self._key_panel = KeyboardPanel()
            self._key_panel.exit_callback = self.exit
            self._key_panel.set_show_interval(self._key_show_interval)
            self._key_panel.show()

        self.state_changed.emit(True)

    def exit(self):
        if not self._active:
            return
        self._active = False
        self._pet.show()
        if hasattr(self._pet, 'set_hotkey_enabled'):
            self._pet.set_hotkey_enabled(True)

        if self._perf_panel:
            self._perf_panel.close()
            self._perf_panel = None
        if self._key_panel:
            self._key_panel.close()
            self._key_panel = None

        self.state_changed.emit(False)

    def toggle(self):
        if self._active:
            self.exit()
        else:
            self.enter()

    def is_active(self) -> bool:
        return self._active

    # ── Panel Toggle Settings ────────────────────────

    def _save_bool(self, key, value):
        from PyQt5.QtCore import QSettings
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        s.setValue(f"game_mode/{key}", value)

    def set_performance_panel_enabled(self, enabled: bool):
        self._perf_enabled = enabled
        self._save_bool("performance_panel_enabled", enabled)
        if self._active:
            if enabled and self._perf_panel is None:
                self._perf_panel = PerformancePanel()
                self._perf_panel.show()
            elif not enabled and self._perf_panel:
                self._perf_panel.close()
                self._perf_panel = None

    def set_keyboard_panel_enabled(self, enabled: bool):
        self._key_enabled = enabled
        self._save_bool("keyboard_panel_enabled", enabled)
        if self._active:
            if enabled and self._key_panel is None:
                self._key_panel = KeyboardPanel()
                self._key_panel.show()
            elif not enabled and self._key_panel:
                self._key_panel.close()
                self._key_panel = None

    def set_keyboard_show_interval(self, show: bool):
        self._key_show_interval = show
        self._save_bool("keyboard_show_interval", show)
        if self._key_panel:
            self._key_panel.set_show_interval(show)

    # ── Status Query ─────────────────────────────────

    def is_perf_enabled(self) -> bool:
        return self._perf_enabled

    def is_key_enabled(self) -> bool:
        return self._key_enabled

    def is_keyboard_interval_enabled(self) -> bool:
        return self._key_show_interval

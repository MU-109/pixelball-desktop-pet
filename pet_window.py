"""Pet window — borderless transparent always-on-top window, 60fps driven character rendering and interaction"""

import json
import math
import random
import time
import ctypes
import ctypes.wintypes
import threading
import urllib.request
import urllib.error
import webbrowser
from urllib.parse import quote
from PyQt5.QtCore import (
    Qt, QTimer, QPoint, QRect, QSettings, pyqtSignal,
)
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QPolygon, QFont, QFontMetrics, QGuiApplication,
)
from PyQt5.QtWidgets import (
    QWidget, QMenu, QAction, QActionGroup, QApplication,
    QInputDialog, QMessageBox, QListWidgetItem,
)

import config as cfg
from character import PixelBall
from animation import AnimationEngine
from behavior import BehaviorAI
from plugin_base import PetPlugin
from secure_store import encrypt_value, decrypt_value
from game_mode import GameModeManager


class SpeechBubble(QWidget):
    """Pixel-style speech bubble — ivory white rounded rectangle + bottom triangle pointer, auto fade-out"""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._lines: list[str] = []
        self._line_height = 0

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(50)
        self._fade_timer.timeout.connect(self._fade_step)
        self._opacity = 1.0

    def show_text(self, text: str, anchor_widget: QWidget, duration: float = None):
        """Show text bubble above the pet, supports \\n line breaks"""
        font = QFont("Microsoft YaHei", cfg.BUBBLE_FONT_SIZE)
        font.setStyleHint(QFont.SansSerif)
        fm = QFontMetrics(font)
        self._line_height = fm.height() + 2

        self._lines = self._wrap_text(text, fm)
        text_w = max(fm.horizontalAdvance(line) for line in self._lines)
        text_h = len(self._lines) * self._line_height

        bw = text_w + cfg.BUBBLE_PADDING_H * 2 + 6
        bh = text_h + cfg.BUBBLE_PADDING_V * 2 + 6 + cfg.BUBBLE_POINTER_H
        self.setFixedSize(bw, bh)

        ap = anchor_widget.pos()
        ax = ap.x() + anchor_widget.width() // 2
        ay = ap.y()
        self.move(ax - bw // 2, ay - bh + cfg.BUBBLE_POINTER_H)

        self._opacity = 1.0
        self.show()
        self.update()

        dur_ms = int((duration or cfg.BUBBLE_DURATION) * 1000)
        self._hide_timer.start(dur_ms)

    def _wrap_text(self, text: str, fm) -> list[str]:
        """Wrap text by maximum width, split character by character for CJK support"""
        lines = []
        max_w = cfg.BUBBLE_MAX_WIDTH - cfg.BUBBLE_PADDING_H * 2 - 6
        for paragraph in text.split("\n"):
            if fm.horizontalAdvance(paragraph) <= max_w:
                lines.append(paragraph)
            else:
                current = ""
                for ch in paragraph:
                    test = current + ch
                    if fm.horizontalAdvance(test) > max_w and current:
                        lines.append(current)
                        current = ch
                    else:
                        current = test
                if current:
                    lines.append(current)
        return lines

    def _fade_out(self):
        self._fade_timer.start()

    def _fade_step(self):
        self._opacity -= 0.08
        if self._opacity <= 0:
            self._fade_timer.stop()
            self.hide()
        else:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setOpacity(self._opacity)

        w, h = self.width(), self.height()
        ph = cfg.BUBBLE_POINTER_H
        body_h = h - ph

        bg = QColor(255, 252, 240)
        border = QColor(60, 60, 60)

        pen = painter.pen()
        pen.setColor(border)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(bg)
        painter.drawRoundedRect(1, 1, w - 2, body_h - 1, 6, 6)

        painter.setPen(Qt.NoPen)
        painter.setBrush(border)
        cx = w // 2
        poly = QPolygon([
            QPoint(cx - 5, body_h),
            QPoint(cx + 5, body_h),
            QPoint(cx, body_h + ph - 1),
        ])
        painter.drawPolygon(poly)

        font = QFont("Microsoft YaHei", cfg.BUBBLE_FONT_SIZE)
        font.setStyleHint(QFont.SansSerif)
        painter.setFont(font)
        pen.setColor(QColor(40, 40, 40))
        painter.setPen(pen)

        tx = 4 + cfg.BUBBLE_PADDING_H
        ty = 4 + cfg.BUBBLE_PADDING_V
        for i, line in enumerate(self._lines):
            painter.drawText(tx, ty + i * self._line_height + self._line_height - 3, line)
        painter.end()


class CountdownBubble(QWidget):
    """Countdown bubble — dark rounded rectangle displayed below the pet, turns red on timeout and shows stop button"""

    finished = pyqtSignal()
    POINTER_H = 6
    BTN_H = 28

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(130, 48 + self.BTN_H)

        self._remaining = 0
        self._overtime = 0
        self._running = False
        self._overtime_mode = False

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._tick)

        from PyQt5.QtWidgets import QPushButton
        self._stop_btn = QPushButton("Stop", self)
        self._stop_btn.setFixedSize(60, 22)
        self._stop_btn.setStyleSheet(
            "QPushButton { background: #c0392b; color: #fff; border: none;"
            " border-radius: 4px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background: #e74c3c; }"
        )
        self._stop_btn.clicked.connect(self._do_stop)
        self._stop_btn.hide()

    def start_countdown(self, seconds: int, anchor_widget: QWidget):
        self._remaining = seconds
        self._overtime = 0
        self._running = True
        self._overtime_mode = False
        self._anchor = anchor_widget
        self._stop_btn.hide()
        self.setFixedSize(130, 48)
        self._reposition()
        self.show()
        self._tick_timer.start()

    def _reposition(self):
        if hasattr(self, '_anchor') and self._anchor:
            ap = self._anchor.pos()
            ax = ap.x() + self._anchor.width() // 2
            ay = ap.y() + self._anchor.height()
            self.move(ax - self.width() // 2, ay + 2)

    def _tick(self):
        if self._overtime_mode:
            self._overtime += 1
        else:
            self._remaining -= 1
            if self._remaining <= 0:
                self._overtime_mode = True
                self._overtime = 0
                self._remaining = 0
                self.setFixedSize(130, 48 + self.BTN_H)
                body_h = 48 - self.POINTER_H
                self._stop_btn.move(
                    (self.width() - self._stop_btn.width()) // 2,
                    self.POINTER_H + body_h + 3
                )
                self._stop_btn.show()
                if self._anchor and hasattr(self._anchor, 'say'):
                    self._anchor.say("Time's up!", 4.0)
                self._reposition()
        self._reposition()
        self.update()

    def _do_stop(self):
        self._tick_timer.stop()
        self._running = False
        self.hide()
        self.finished.emit()

    def stop(self):
        self._tick_timer.stop()
        self._running = False
        self.hide()

    def is_running(self):
        return self._running

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        w, h = self.width(), self.height()
        ph = self.POINTER_H
        btn_area = self.BTN_H if self._overtime_mode else 0
        body_h = h - ph - btn_area
        body_top = ph

        if self._overtime_mode:
            bg = QColor(180, 30, 30, 240)
            border_c = QColor(220, 60, 60)
            text_c = QColor(255, 180, 180)
        else:
            bg = QColor(45, 45, 50, 240)
            border_c = QColor(90, 90, 95)
            text_c = QColor(255, 220, 120)

        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        cx = w // 2
        poly = QPolygon([
            QPoint(cx, 0),
            QPoint(cx - 5, ph),
            QPoint(cx + 5, ph),
        ])
        painter.drawPolygon(poly)

        painter.setPen(QPen(border_c, 2))
        painter.setBrush(bg)
        painter.drawRoundedRect(1, body_top, w - 2, body_h - 1, 6, 6)

        if self._overtime_mode:
            mins, secs = divmod(self._overtime, 60)
            text = f"+{mins:02d}:{secs:02d}"
        else:
            mins, secs = divmod(max(0, self._remaining), 60)
            text = f"{mins:02d}:{secs:02d}"

        font = QFont("Consolas", 18)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(text_c)
        tr = painter.boundingRect(0, body_top, w, body_h, Qt.AlignCenter, text)
        painter.drawText(tr, Qt.AlignCenter, text)
        painter.end()


class AreaSelector(QWidget):
    """Full-screen overlay drag-select for activity area, similar to screenshot tool"""

    area_selected = pyqtSignal(QRect)
    selection_cancelled = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        total = QRect()
        for screen in QGuiApplication.screens():
            total = total.united(screen.geometry())
        self.setGeometry(total)

        self._origin = None
        self._current = None
        self._dragging = False
        self.setCursor(Qt.CrossCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))

        if self._dragging and self._origin and self._current:
            r = QRect(self._origin, self._current).normalized()
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(r, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(255, 200, 0), 2, Qt.SolidLine))
            painter.drawRect(r)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._origin = event.pos()
            self._current = event.pos()
            self._dragging = True

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._current = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            r = QRect(self._origin, self._current).normalized()
            min_w, min_h = cfg.WINDOW_WIDTH, cfg.WINDOW_HEIGHT
            if r.width() >= min_w and r.height() >= min_h:
                self.hide()
                self.area_selected.emit(r)
            else:
                self._show_too_small_hint(r)
                self._origin = None
                self._current = None
                self.update()

    def _show_too_small_hint(self, r):
        from PyQt5.QtWidgets import QLabel
        hint = QLabel(
            f"Area must be at least {cfg.WINDOW_WIDTH}x{cfg.WINDOW_HEIGHT} pixels",
            self
        )
        hint.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(
            "background-color: rgba(40,40,40,220); color: #ff7878;"
            "padding: 6px 14px; font-size: 13px; border-radius: 4px;"
        )
        hint.adjustSize()
        hint.move(r.center().x() - hint.width() // 2,
                  r.center().y() - hint.height() // 2)
        hint.show()
        QTimer.singleShot(1500, hint.close)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            self.selection_cancelled.emit()


class ImagePinWidget(QWidget):
    """Screenshot pin window — borderless always-on-top, draggable, right-click menu operations"""

    def __init__(self, pixmap: 'QPixmap', parent=None):
        super().__init__(parent)
        self._pixmap = pixmap
        self._pinned = True  # Default always-on-top

        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(pixmap.width() + 4, pixmap.height() + 4)
        self.setMouseTracking(True)
        self._drag_pos = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        # Border
        painter.setPen(QPen(QColor(100, 100, 100), 2))
        painter.drawRect(1, 1, self.width() - 2, self.height() - 2)
        # Image
        painter.drawPixmap(2, 2, self._pixmap)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPos())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.close()

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #2b2b2b; color: #e0e0e0; border: 1px solid #555; }
            QMenu::item { padding: 5px 20px; }
            QMenu::item:selected { background-color: #505050; }
        """)
        act_pin = menu.addAction("Always on Top")
        act_pin.setCheckable(True)
        act_pin.setChecked(self._pinned)
        act_pin.triggered.connect(self._toggle_pin)
        menu.addAction("Save as File...").triggered.connect(self._save_to_file)
        menu.addAction("Copy to Clipboard").triggered.connect(self._copy_to_clipboard)
        menu.addAction("Recognize Text").triggered.connect(self._ocr_text)
        menu.addSeparator()
        menu.addAction("Close").triggered.connect(self.close)
        menu.exec_(pos)

    def _toggle_pin(self, pinned: bool):
        self._pinned = pinned
        flags = self.windowFlags()
        if pinned:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()  # Re-show to apply flag changes

    def _save_to_file(self):
        from PyQt5.QtWidgets import QFileDialog
        import os
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Screenshot", os.path.join(os.path.expanduser("~"), "Desktop", "screenshot.png"),
            "PNG (*.png);;JPEG (*.jpg)",
        )
        if path:
            self._pixmap.save(path)

    def _copy_to_clipboard(self):
        QApplication.clipboard().setPixmap(self._pixmap)

    def _ocr_text(self):
        """Recognize text in screenshot"""
        from ocr_tool import pixmap_to_text
        from PyQt5.QtWidgets import QDialog, QTextEdit, QVBoxLayout, QPushButton, QHBoxLayout

        self.setCursor(Qt.WaitCursor)
        text = pixmap_to_text(self._pixmap)
        self.setCursor(Qt.ArrowCursor)

        dlg = QDialog(self)
        dlg.setWindowTitle("Recognition Result")
        dlg.setMinimumSize(350, 200)
        dlg.setStyleSheet("""
            QDialog { background-color: #2b2b2b; }
            QTextEdit { background: #1e1e1e; color: #e0e0e0; border: 1px solid #555;
                font-family: 'Microsoft YaHei'; font-size: 13px; padding: 8px;
                border-radius: 4px; }
            QPushButton { background: #3c3c3c; color: #e0e0e0; border: 1px solid #555;
                padding: 6px 16px; border-radius: 4px; }
            QPushButton:hover { background: #4a4a4a; }
        """)

        layout = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setPlainText(text if text else "(No text recognized)")
        layout.addWidget(te)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(te.toPlainText()))
        btn_layout.addWidget(copy_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.close)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        dlg.exec_()


class PetWindow(QWidget):
    """Pet main window — pixel ball desktop pet, 60fps render loop"""

    clicked = pyqtSignal(object)
    double_clicked = pyqtSignal(object)
    _weather_ready = pyqtSignal(str)  # Cross-thread weather callback safe channel
    _ai_ready = pyqtSignal(str)        # Cross-thread AI callback safe channel
    _screenshot_hotkey_triggered = pyqtSignal()  # Cross-thread screenshot hotkey trigger

    def __init__(self):
        super().__init__()
        self._plugins: list[PetPlugin] = []
        self._mouse_pressed = False
        self._drag_start = QPoint()
        self._window_start = QPoint()
        self._drag_resume_timer = 0.0
        self._saved_state = None

        self._character = PixelBall(self)
        self._animation = AnimationEngine()
        self._behavior = BehaviorAI(self)

        self._fx = 100.0
        self._fy = 100.0

        self._render_scale = cfg.PIXEL_SCALE
        self._extra_scale = 1.0
        self._shake = (0.0, 0.0)
        self._shake_timer = 0.0

        # Zzz particles
        self._zzz_particles: list[dict] = []
        self._zzz_emit_timer = 0.0

        # Snot bubble particles
        self._bubble_particles: list[dict] = []
        self._bubble_timer = 0.0

        # Bubble burst fragments
        self._pop_particles: list[dict] = []

        # Heart particles
        self._heart_particles: list[dict] = []

        self._passthrough = False
        self._eye_rest_overlay = False

        # Name
        self._pet_name = cfg.DEFAULT_PET_NAME
        self._user_title = cfg.DEFAULT_USER_TITLE
        self._load_name_settings()

        # City (for weather location)
        self._city = ""
        self._load_city_setting()

        # Dialog database (jokes/facts/compliments)
        self._dialog_data: dict = {}
        self._load_dialog_data()

        # Weather callback storage (cross-thread safe delivery)
        self._weather_callback = None
        self._cached_weather = ""  # AI context use, updated after each successful fetch

        # Speech bubble
        self._bubble: SpeechBubble | None = None

        # Countdown bubble
        self._countdown: CountdownBubble | None = None

        # Todo system (hover 1s to show)
        self._todo_items: list[dict] = []
        self._todo_panel: QWidget | None = None
        self._todo_close_timer = QTimer(self)
        self._todo_close_timer.setSingleShot(True)
        self._todo_close_timer.setInterval(400)
        self._todo_close_timer.timeout.connect(self._close_todo_panel)
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(cfg.TODO_HOVER_DELAY)
        self._hover_timer.timeout.connect(self._show_todo_panel)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self._load_todos()

        # Alarm system
        self._alarms: list[dict] = []
        self._next_alarm_id = 1
        self._alarm_check_timer = QTimer(self)
        self._alarm_check_timer.setInterval(15000)  # Check every 15 seconds
        self._alarm_check_timer.timeout.connect(self._check_alarms)
        self._load_alarms()
        self._alarm_check_timer.start()

        # Keyboard & mouse stats
        self._stats: dict[str, dict] = {}
        self._stats_today: dict = {"keystrokes": 0, "clicks": 0, "distance_m": 0.0}
        self._stats_lock = None  # threading.Lock, created on demand
        self._kb_listener = None
        self._ms_listener = None
        self._stats_save_timer = QTimer(self)
        self._stats_save_timer.setInterval(600000)  # Save every 10 minutes
        self._stats_save_timer.timeout.connect(self._save_stats)
        self._stats_enabled = False
        self._load_stats()
        _sqs = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        if _sqs.value("stats/keyboard_mouse_enabled", False, type=bool):
            self._start_stats_listeners()

        # Screenshot global hotkey
        self._screenshot_hotkey = cfg.DEFAULT_SCREENSHOT_HOTKEY
        self._hotkey_listener = None
        self._hotkey_registered = False
        self._hotkey_enabled = True  # Disabled in game mode
        self._load_hotkey_settings()
        self._screenshot_hotkey_triggered.connect(self._start_screenshot)
        self._register_hotkey()

        # Desktop cleanup reminder (check once on startup, then every 6 hours)
        self._check_desktop_cleanup()
        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.setInterval(21600000)  # 6 hours
        self._cleanup_timer.timeout.connect(self._check_desktop_cleanup)
        self._cleanup_timer.start()

        # Drag interaction
        self._drag_start_time = 0.0
        self._drag_distance = 0.0
        self._drag_total_distance = 0.0
        self._drag_shake_count = 0
        self._drag_last_shake_pos = QPoint()
        self._dragging_active = False

        # Activity area
        self._activity_areas: list[dict] = []
        self._active_area_key: str = "full"
        self._area_selector: AreaSelector | None = None
        self._load_areas()
        self._load_behavior_settings()

        # AI chat config (API credentials)
        self._ai_config: dict = {}
        self._ai_callback = None
        self._load_ai_settings()

        # AI advanced settings (personality, chat history, proactive chat)
        self._ai_profile: dict = {}
        self._last_ai_prompt = ""
        self._save_last_to_history = False
        self._proactive_timer: QTimer | None = None
        self._chat_reply_callback = None  # Chat dialog AI reply callback
        self._ai_expr_timer: QTimer | None = None  # AI reply expression animation timer
        self._load_ai_profile()

        # Body tracking (weight tracking, BMI, goals)
        self._body_records: list[dict] = []
        self._body_height: float = 0.0
        self._body_target_weight: float = 0.0
        self._body_start_weight: float = 0.0
        self._weigh_reminder_enabled: bool = False
        self._weigh_reminder_time: str = cfg.DEFAULT_WEIGH_TIME
        self._last_weigh_reminder_date: str = ""
        self._body_panel: QWidget | None = None
        self._body_panel_close_timer = QTimer(self)
        self._body_panel_close_timer.setSingleShot(True)
        self._body_panel_close_timer.setInterval(cfg.BODY_PANEL_CLOSE_DELAY)
        self._body_panel_close_timer.timeout.connect(self._close_body_panel)
        self._weigh_check_timer = QTimer(self)
        self._weigh_check_timer.setInterval(60 * 1000)
        self._weigh_check_timer.timeout.connect(self._check_weigh_reminder)
        self._load_body_settings()
        self._load_body_records()

        # Game mode manager
        self._game_mode = GameModeManager(self)

        self._init_ui()
        self._connect_signals()
        self._start_proactive_timer()
        self._restore_position()
        self._apply_active_area()

    # ── Window initialization ─────────────────────────────────────

    def _init_ui(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(cfg.WINDOW_WIDTH, cfg.WINDOW_HEIGHT)
        self.setWindowOpacity(cfg.WINDOW_OPACITY)
        self.setWindowTitle("Pixel Ball Desktop Pet")

        self._timer = QTimer(self)
        self._timer.setInterval(1000 // cfg.FPS)
        self._timer.timeout.connect(self._update_loop)
        self._timer.start()

        self._last_tick = time.time()

        screen = QApplication.primaryScreen()
        if screen:
            self._behavior.set_screen_rect(screen.availableGeometry())

        # Weather cache refresh every 30 minutes for AI context
        QTimer.singleShot(2000, self._refresh_weather_cache)
        self._weather_timer = QTimer(self)
        self._weather_timer.setInterval(30 * 60 * 1000)
        self._weather_timer.timeout.connect(self._refresh_weather_cache)
        self._weather_timer.start()

        if self._weigh_reminder_enabled:
            self._weigh_check_timer.start()

    def _connect_signals(self):
        self._behavior.action_changed.connect(self._on_action)
        self._behavior.expression_changed.connect(self._on_expression)
        self._behavior.reminder_drink.connect(self._on_drink_reminder)
        self._behavior.reminder_eye_rest.connect(self._on_eye_rest_reminder)
        self._weather_ready.connect(self._on_weather_ready)
        self._ai_ready.connect(self._on_ai_ready)

    # ── Position Management ─────────────────────────────

    def _save_position(self):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        s.setValue("position/x", int(self._fx))
        s.setValue("position/y", int(self._fy))

    def _restore_position(self):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        self._fx = float(s.value("position/x", 100, type=int))
        self._fy = float(s.value("position/y", 100, type=int))
        self.move(int(self._fx), int(self._fy))

    def move_to(self, x, y):
        """Programmatically move pet to specified position"""
        self._fx, self._fy = float(x), float(y)
        self.move(x, y)
        self._save_position()

    @property
    def character(self):
        return self._character

    @property
    def behavior(self):
        return self._behavior

    @property
    def plugins(self):
        return self._plugins

    def set_passthrough(self, enabled):
        """Toggle mouse passthrough mode, prompt exit method on entry"""
        self._passthrough = enabled
        if enabled:
            self.setWindowFlags(self.windowFlags() | Qt.WindowTransparentForInput)
            self.show()
            # Prompt user how to exit passthrough mode via system tray
            self.say("Passthrough mode enabled\n(Exit via system tray)", 3.0)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowTransparentForInput)
            self.show()

    # ── Plugin Management ───────────────────────────────

    def load_plugin(self, plugin: PetPlugin):
        plugin.on_load(self)
        self._plugins.append(plugin)

    def unload_plugin(self, plugin: PetPlugin):
        if plugin in self._plugins:
            plugin.on_unload(self)
            self._plugins.remove(plugin)

    # ── Particle System ────────────────────────────────

    def _add_shake(self, intensity=5.0, duration=0.3):
        self._shake = (intensity, intensity)
        self._shake_timer = duration

    def _emit_particles(self, count=3):
        now = time.time()
        for i in range(count):
            self._zzz_particles.append({
                "x": -4 + i * 8,
                "y": -8 - i * 4,
                "life": random.uniform(2.0, 4.0),
                "spawn": now,
                "speed": random.uniform(0.15, 0.35),
            })

    def _emit_bubble(self):
        """Emit a snot bubble — only created when no existing bubble is present"""
        if self._bubble_particles:
            return
        max_sz = random.randint(10, 15)
        half = max_sz - 1
        self._bubble_particles.append({
            "life": float(half * 2),
            "spawn": time.time(),
            "min_size": 1,
            "max_size": max_sz,
        })

    def _pop_bubble(self):
        """Pop a bubble — generate 8 radially scattered burst fragments"""
        grid_size = cfg.PIXEL_SIZE * cfg.PIXEL_SCALE
        offset_x = (self.width() - grid_size) // 2
        offset_y = (self.height() - grid_size) // 2
        mouth_cx = int(offset_x + 8 * cfg.PIXEL_SCALE)
        mouth_cy = int(offset_y + 10 * cfg.PIXEL_SCALE)

        block_size = 1
        center_x = mouth_cx
        center_y = mouth_cy
        for p in self._bubble_particles:
            elapsed = time.time() - p["spawn"]
            half_life = p["life"] / 2
            if elapsed <= half_life:
                block_size = p["min_size"] + (p["max_size"] - p["min_size"]) * (elapsed / half_life)
            else:
                decay_elapsed = elapsed - half_life
                block_size = p["max_size"] - (p["max_size"] - p["min_size"]) * (decay_elapsed / half_life)
            block_size = max(1, min(p["max_size"], int(block_size + 0.5)))
            radius_px = int(block_size * cfg.PIXEL_SCALE) // 2
            center_x = mouth_cx + radius_px
            center_y = mouth_cy
            break

        self._bubble_particles.clear()

        now = time.time()
        for i in range(8):
            angle = (i / 8) * 2 * math.pi + random.uniform(-0.2, 0.2)
            speed = random.uniform(1.5, 3.5)
            self._pop_particles.append({
                "x": float(center_x),
                "y": float(center_y),
                "vx": math.cos(angle) * speed * cfg.PIXEL_SCALE,
                "vy": math.sin(angle) * speed * cfg.PIXEL_SCALE,
                "life": random.uniform(0.5, 1.0),
                "spawn": now,
                "size": random.randint(2, 4),
            })

    def _emit_hearts(self, count=3):
        now = time.time()
        for i in range(count):
            self._heart_particles.append({
                "x": random.uniform(-8, 8),
                "y": 12 + i * 6,
                "life": random.uniform(1.5, 3.0),
                "spawn": now,
                "speed": random.uniform(0.3, 0.6),
            })

    # ── Main Loop 60fps ───────────────────────────────

    def _update_loop(self):
        now = time.time()
        delta_ms = (now - self._last_tick) * 1000
        # Prevent position mutation from time jumps after system sleep resume
        delta_ms = min(delta_ms, 200)
        self._last_tick = now

        # Resume countdown after drag
        if self._drag_resume_timer > 0:
            self._drag_resume_timer -= delta_ms / 1000.0
            if self._drag_resume_timer <= 0:
                self._drag_resume_timer = 0.0
                if self._saved_state is not None:
                    st = self._saved_state
                    self._saved_state = None
                    self._behavior.transition_to(st, {"manual": True})

        # Behavior update
        move_dx, move_dy = self._behavior.update(delta_ms, self._fx, self._fy)

        # Countdown follow
        if self._countdown is not None and self._countdown.is_running():
            self._countdown._reposition()

        # Animation engine
        move_target, scale_val, bounce_offset = self._animation.tick()

        if move_target is not None:
            self._fx, self._fy = move_target

        # Manual walk position update
        if move_dx or move_dy:
            self._fx += move_dx
            self._fy += move_dy
            sr = self._behavior._screen_rect
            if sr is not None:
                self._fx = max(sr.x(), min(self._fx, sr.x() + sr.width() - cfg.WINDOW_WIDTH))
                self._fy = max(sr.y(), min(self._fy, sr.y() + sr.height() - cfg.WINDOW_HEIGHT))

        # Hard screen boundary clamp (executed every frame, safety net)
        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            self._fx = max(sg.x(), min(self._fx, sg.x() + sg.width() - cfg.WINDOW_WIDTH))
            self._fy = max(sg.y(), min(self._fy, sg.y() + sg.height() - cfg.WINDOW_HEIGHT))

        breath = self._behavior.get_breath_offset()

        # Shake decay
        if self._shake_timer > 0:
            self._shake_timer -= delta_ms / 1000.0
            ratio = max(0, self._shake_timer / 0.3)
            sx = random.uniform(-ratio, ratio) * self._shake[0]
            sy = random.uniform(-ratio, ratio) * self._shake[1]
        else:
            sx, sy = 0.0, 0.0

        # Update all particles
        self._update_particles(delta_ms)
        self._update_pop_particles(delta_ms)
        self._update_hearts(delta_ms)

        # Continuously generate Zzz and bubbles during sleep
        if self._behavior.get_state() == "sleep":
            self._zzz_emit_timer += delta_ms / 1000.0
            if self._zzz_emit_timer >= random.uniform(1.0, 2.5):
                self._zzz_emit_timer = 0.0
                self._emit_particles(1)

            self._bubble_timer += delta_ms / 1000.0
            if self._bubble_timer >= random.uniform(2.0, 5.0):
                self._bubble_timer = 0.0
                self._emit_bubble()

        self._update_bubbles(delta_ms)

        self._extra_scale = 1.0 + scale_val * 0.2 if scale_val else 1.0

        render_x = int(self._fx + sx)
        render_y = int(self._fy - bounce_offset + breath + sy)
        self.move(render_x, render_y)
        self.update()

        for plugin in self._plugins:
            try:
                plugin.on_tick(delta_ms)
            except Exception:
                pass

    def _update_particles(self, dt_ms):
        now = time.time()
        survivors = []
        for p in self._zzz_particles:
            p["y"] -= p["speed"] * dt_ms / 1000.0 * 30
            if now - p["spawn"] < p["life"]:
                survivors.append(p)
        self._zzz_particles = survivors

    def _update_bubbles(self, dt_ms):
        now = time.time()
        self._bubble_particles = [
            p for p in self._bubble_particles if now - p["spawn"] < p["life"]
        ]

    def _update_pop_particles(self, dt_ms):
        now = time.time()
        dt = dt_ms / 1000.0
        survivors = []
        for p in self._pop_particles:
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["vy"] += 80 * dt
            p["vx"] *= 0.95
            if now - p["spawn"] < p["life"]:
                survivors.append(p)
        self._pop_particles = survivors

    # ── Drawing ────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        grid_size = cfg.PIXEL_SIZE * cfg.PIXEL_SCALE
        offset_x = (self.width() - grid_size) // 2
        offset_y = (self.height() - grid_size) // 2

        if self._extra_scale != 1.0:
            cx, cy = self.width() // 2, self.height() // 2
            painter.translate(cx, cy)
            painter.scale(self._extra_scale, self._extra_scale)
            painter.translate(-cx, -cy)

        # Facing direction flip (read from BehaviorAI to avoid duplicate state maintenance)
        if not self._behavior.get_facing_right():
            wx = self.width() // 2
            painter.translate(wx, 0)
            painter.scale(-1, 1)
            painter.translate(-wx, 0)

        self._character.render(painter, offset_x, offset_y)

        if self._zzz_particles:
            self._render_zzz(painter)
        if self._bubble_particles:
            self._render_bubbles(painter)
        if self._pop_particles:
            self._render_pop_particles(painter)
        if self._heart_particles:
            self._render_hearts(painter)

        # Eye rest semi-transparent overlay
        if self._eye_rest_overlay:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 128))

        painter.end()

    def _render_zzz(self, painter):
        for p in self._zzz_particles:
            elapsed = time.time() - p["spawn"]
            alpha = max(0, min(255, int(255 * (1 - elapsed / p["life"]))))
            c = QColor(100, 180, 255, alpha)
            bx = int(36 + p["x"])
            by = int(5 * cfg.PIXEL_SCALE + p["y"])
            painter.setPen(c)
            painter.setBrush(c)
            painter.fillRect(bx, by, 12, 2, c)
            painter.fillRect(bx + 10, by + 2, 2, 2, c)
            painter.fillRect(bx + 8, by + 4, 2, 2, c)
            painter.fillRect(bx + 6, by + 6, 2, 2, c)
            painter.fillRect(bx + 4, by + 8, 2, 2, c)
            painter.fillRect(bx + 2, by + 10, 2, 2, c)
            painter.fillRect(bx, by + 12, 12, 2, c)

    def _render_bubbles(self, painter):
        grid_size = cfg.PIXEL_SIZE * cfg.PIXEL_SCALE
        offset_x = (self.width() - grid_size) // 2
        offset_y = (self.height() - grid_size) // 2
        mouth_x = offset_x + 8 * cfg.PIXEL_SCALE
        mouth_y = offset_y + 10 * cfg.PIXEL_SCALE

        for p in self._bubble_particles:
            elapsed = time.time() - p["spawn"]
            half_life = p["life"] / 2
            if elapsed <= half_life:
                block_size = p["min_size"] + (p["max_size"] - p["min_size"]) * (elapsed / half_life)
            else:
                decay = elapsed - half_life
                block_size = p["max_size"] - (p["max_size"] - p["min_size"]) * (decay / half_life)
            block_size = max(1, min(p["max_size"], int(block_size + 0.5)))
            diameter_px = int(block_size * cfg.PIXEL_SCALE)
            radius_px = diameter_px // 2
            center_x = int(mouth_x + radius_px)
            center_y = int(mouth_y)

            fill_color = QColor(100, 150, 255, 128)
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill_color)
            painter.drawEllipse(QPoint(center_x, center_y), radius_px, radius_px)

    def _render_pop_particles(self, painter):
        for p in self._pop_particles:
            elapsed = time.time() - p["spawn"]
            alpha = max(0, min(255, int(255 * (1 - elapsed / p["life"]))))
            c = QColor(100, 150, 255, alpha)
            painter.setPen(Qt.NoPen)
            painter.setBrush(c)
            sz = p["size"]
            painter.fillRect(int(p["x"]), int(p["y"]), sz, sz, c)

    # ── Mouse Events ──────────────────────────────────

    def mousePressEvent(self, event):
        if self._passthrough:
            return super().mousePressEvent(event)

        self._hover_timer.stop()

        if event.button() == Qt.LeftButton:
            self._mouse_pressed = True
            self._drag_start = event.globalPos()
            self._window_start = QPoint(int(self._fx), int(self._fy))
            self._drag_distance = 0.0
            self._drag_total_distance = 0.0
            self._drag_start_time = time.time()
            self._drag_shake_count = 0
            self._drag_last_shake_pos = event.globalPos()
            self._drag_resume_timer = 0.0

            state = self._behavior.get_state()
            if state in ("sleep", "walk") and self._behavior._manual_mode:
                self._saved_state = state
                self._behavior.transition_to("idle")
            else:
                self._saved_state = None

            self.setFocus()  # Grab keyboard focus to support Ctrl+V search
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._passthrough:
            return super().mouseMoveEvent(event)

        # Mouse button physically released but _mouse_pressed not cleared (occurs when release event lands outside window)
        if self._mouse_pressed and not (QApplication.mouseButtons() & Qt.LeftButton):
            self._mouse_pressed = False
            return

        if self._mouse_pressed:
            delta = event.globalPos() - self._drag_start
            self._drag_distance = delta.manhattanLength()
            self._drag_total_distance += (event.globalPos() - self._drag_last_shake_pos).manhattanLength()
            self._drag_last_shake_pos = event.globalPos()

            # Fast shake → pout expression
            if self._drag_distance > 30 and self._drag_total_distance > 120:
                if self._behavior.get_state() != "clicked":
                    self._character.set_expression("pout")
                    self._drag_shake_count += 1

            self._fx = float(self._window_start.x() + delta.x())
            self._fy = float(self._window_start.y() + delta.y())
            self.move(int(self._fx), int(self._fy))

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._passthrough:
            return super().mouseReleaseEvent(event)

        if event.button() == Qt.LeftButton and self._mouse_pressed:
            self._mouse_pressed = False

            if self._drag_distance < 5:
                # Click
                self._on_click()
                if self._saved_state is not None:
                    if self._saved_state == "sleep":
                        self._saved_state = None
                    else:
                        st = self._saved_state
                        self._saved_state = None
                        self._behavior.transition_to(st, {"manual": True})
            else:
                # Drag
                if self._saved_state is not None:
                    self._drag_resume_timer = 2.0

                drag_duration = time.time() - self._drag_start_time
                if self._drag_shake_count > 3 and drag_duration < 1.5:
                    self._character.set_expression("dizzy")
                    QTimer.singleShot(2000, lambda: self._character.set_expression("idle"))
                    self.say("Whoa... so dizzy...", 2.0)
                else:
                    self._character.set_expression("idle")

            self._save_position()
            self._dragging_active = False

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._passthrough:
            return super().mouseDoubleClickEvent(event)
        if event.button() == Qt.LeftButton:
            self._mouse_pressed = False  # Clear drag state after double-click to prevent mouse "sticking" after menu
            self._show_double_click_menu()
            for plugin in self._plugins:
                try:
                    plugin.on_double_click(event)
                except Exception:
                    pass
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        """Ctrl+V paste clipboard text to search"""
        if event.key() == Qt.Key_V and event.modifiers() == Qt.ControlModifier:
            text = QApplication.clipboard().text().strip()
            if text:
                webbrowser.open(f"https://cn.bing.com/search?q={quote(text)}")
                self.say(f"Search: {text[:20]}{'...' if len(text) > 20 else ''}", 2.0)
            return
        super().keyPressEvent(event)

    # ── Drag-drop Search ───────────────────────────────

    def dragEnterEvent(self, event):
        """Accept externally dragged text"""
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Drag text → Bing search"""
        text = event.mimeData().text().strip()
        if text:
            webbrowser.open(f"https://cn.bing.com/search?q={quote(text)}")
            self.say(f"Search: {text[:20]}{'...' if len(text) > 20 else ''}", 2.0)

    def _quick_search_dialog(self):
        """Double-click menu: manually enter search keyword"""
        text, ok = QInputDialog.getText(self, "Quick Search", "Enter search keyword:")
        if ok and text.strip():
            webbrowser.open(f"https://cn.bing.com/search?q={quote(text.strip())}")
            self.say(f"Search: {text.strip()[:20]}{'...' if len(text.strip()) > 20 else ''}", 2.0)

    # ── Keyboard/Mouse Stats ──────────────────────────

    def _stats_path(self):
        import os as _os
        return _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "stats.json")

    def _load_stats(self):
        try:
            with open(self._stats_path(), "r", encoding="utf-8") as f:
                self._stats = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._stats = {}
        # Clean data older than 30 days
        import datetime as _dt
        cutoff = (_dt.datetime.now() - _dt.timedelta(days=30)).strftime("%Y-%m-%d")
        self._stats = {k: v for k, v in self._stats.items() if k >= cutoff}

    def _save_stats(self):
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        self._stats[today] = dict(self._stats_today)
        with open(self._stats_path(), "w", encoding="utf-8") as f:
            json.dump(self._stats, f, ensure_ascii=False, indent=2)

    def _start_stats_listeners(self):
        if self._stats_enabled:
            return
        try:
            from pynput.keyboard import Listener as KBListener
            from pynput.mouse import Listener as MSListener
            import threading as _th

            self._stats_lock = _th.Lock()

            def _on_key_press(key):
                with self._stats_lock:
                    self._stats_today["keystrokes"] += 1

            def _on_click(x, y, button, pressed):
                if pressed:
                    with self._stats_lock:
                        self._stats_today["clicks"] += 1

            self._last_mouse_pos = [0, 0]
            def _on_move(x, y):
                dx = x - self._last_mouse_pos[0]
                dy = y - self._last_mouse_pos[1]
                dist = (dx * dx + dy * dy) ** 0.5 / 1000.0  # pixels → meters (rough)
                if dist > 0:
                    with self._stats_lock:
                        self._stats_today["distance_m"] += dist
                self._last_mouse_pos[0] = x
                self._last_mouse_pos[1] = y

            self._kb_listener = KBListener(on_press=_on_key_press)
            self._ms_listener = MSListener(on_click=_on_click, on_move=_on_move)
            self._kb_listener.daemon = True
            self._ms_listener.daemon = True
            self._kb_listener.start()
            self._ms_listener.start()
            self._stats_enabled = True
            self._stats_save_timer.start()
        except ImportError:
            pass  # pynput not installed

    def _stop_stats_listeners(self):
        self._stats_save_timer.stop()
        self._save_stats()
        if self._kb_listener:
            try:
                self._kb_listener.stop()
            except Exception:
                pass
            self._kb_listener = None
        if self._ms_listener:
            try:
                self._ms_listener.stop()
            except Exception:
                pass
            self._ms_listener = None
        self._stats_enabled = False

    def _toggle_stats(self, enabled: bool):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        s.setValue("stats/keyboard_mouse_enabled", enabled)
        if enabled:
            self._start_stats_listeners()
        else:
            self._stop_stats_listeners()

    # ── Screenshot Hotkey (Win32 RegisterHotKey) ───────

    # Virtual key code mapping
    _VK_MAP = {
        "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
        "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
        "f9": 0x78, "f10": 0x79, "f11": 0x7a, "f12": 0x7b,
        "space": 0x20, "tab": 0x09, "enter": 0x0d, "esc": 0x1b,
        "backspace": 0x08, "delete": 0x2e, "insert": 0x2d,
        "home": 0x24, "end": 0x23, "page_up": 0x21, "page_down": 0x22,
        "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
        "print_screen": 0x2c, "pause": 0x13,
    }

    _HOTKEY_ID = 1  # RegisterHotKey identifier

    def _load_hotkey_settings(self):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        self._screenshot_hotkey = s.value(
            "hotkeys/screenshot", cfg.DEFAULT_SCREENSHOT_HOTKEY
        )

    def _save_hotkey_settings(self):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        s.setValue("hotkeys/screenshot", self._screenshot_hotkey)

    @staticmethod
    def _parse_hotkey(hotkey_str):
        """Parse hotkey string into (modifiers, vk_code)
        Format: <mod>+<key>  e.g. '<ctrl_r>+<f12>' or '<ctrl>+<shift>+s'
        Returns (modifiers, vk_code), returns (0, 0) on failure
        """
        MOD_ALT = 0x0001
        MOD_CONTROL = 0x0002
        MOD_SHIFT = 0x0004
        MOD_WIN = 0x0008
        MOD_NOREPEAT = 0x4000

        parts = [p.strip() for p in hotkey_str.lower().split("+")]
        modifiers = MOD_NOREPEAT
        vk = 0

        for part in parts:
            if part.startswith("<") and part.endswith(">"):
                name = part[1:-1]
                if name in ("ctrl", "ctrl_l", "ctrl_r", "control"):
                    modifiers |= MOD_CONTROL
                elif name in ("alt", "alt_l", "alt_r"):
                    modifiers |= MOD_ALT
                elif name in ("shift", "shift_l", "shift_r"):
                    modifiers |= MOD_SHIFT
                elif name in ("cmd", "win", "cmd_l", "cmd_r"):
                    modifiers |= MOD_WIN
                elif name in PetWindow._VK_MAP:
                    vk = PetWindow._VK_MAP[name]
                else:
                    # Try single character
                    if len(name) == 1:
                        vk = ord(name.upper())
            elif len(part) == 1:
                vk = ord(part.upper())
            elif part in PetWindow._VK_MAP:
                vk = PetWindow._VK_MAP[part]

        return (modifiers, vk) if vk != 0 else (0, 0)

    def _register_hotkey(self):
        """Start global keyboard listener, manually track modifier combinations"""
        if not self._hotkey_enabled or self._hotkey_listener is not None:
            return
        mods, vk = self._parse_hotkey(self._screenshot_hotkey)
        if vk == 0:
            return
        self._hotkey_mods = mods
        self._hotkey_vk = vk
        try:
            from pynput.keyboard import Listener, Key, KeyCode
            self._pressed_keys: set = set()
            self._modifiers_satisfied = False

            def _on_press(key):
                if isinstance(key, KeyCode):
                    ident = key.vk if key.vk else key.char
                else:
                    ident = key
                self._pressed_keys.add(ident)
                self._check_hotkey()

            def _on_release(key):
                if isinstance(key, KeyCode):
                    ident = key.vk if key.vk else key.char
                else:
                    ident = key
                self._pressed_keys.discard(ident)

            self._hotkey_listener = Listener(on_press=_on_press, on_release=_on_release)
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
            self._hotkey_registered = True
        except Exception:
            self._hotkey_registered = False

    def _check_hotkey(self):
        """Check if currently pressed keys match the screenshot hotkey"""
        if not self._hotkey_enabled:
            return
        from pynput.keyboard import Key as K
        req_mods, req_vk = self._hotkey_mods, self._hotkey_vk
        pressed = self._pressed_keys

        MOD_CONTROL, MOD_ALT, MOD_SHIFT, MOD_WIN = 0x0002, 0x0001, 0x0004, 0x0008

        if req_mods & MOD_CONTROL and not ({K.ctrl, K.ctrl_l, K.ctrl_r} & pressed):
            return
        if req_mods & MOD_ALT and not ({K.alt, K.alt_l, K.alt_r} & pressed):
            return
        if req_mods & MOD_SHIFT and not ({K.shift, K.shift_l, K.shift_r} & pressed):
            return
        if req_mods & MOD_WIN and not ({K.cmd, K.cmd_l, K.cmd_r} & pressed):
            return

        # Match all pressed keys by vk code
        for k in pressed:
            k_vk = self._key_to_vk(k)
            if k_vk is not None and k_vk == req_vk:
                self._screenshot_hotkey_triggered.emit()
                return

    @staticmethod
    def _key_to_vk(key):
        """Convert pynput key object to Windows virtual key code"""
        from pynput.keyboard import Key, KeyCode
        if isinstance(key, KeyCode):
            return key.vk if key.vk else None
        if isinstance(key, Key):
            # pynput special keys → vk codes
            _KEY_VK = {
                Key.f1: 0x70, Key.f2: 0x71, Key.f3: 0x72, Key.f4: 0x73,
                Key.f5: 0x74, Key.f6: 0x75, Key.f7: 0x76, Key.f8: 0x77,
                Key.f9: 0x78, Key.f10: 0x79, Key.f11: 0x7a, Key.f12: 0x7b,
                Key.space: 0x20, Key.tab: 0x09, Key.enter: 0x0d,
                Key.esc: 0x1b, Key.backspace: 0x08, Key.delete: 0x2e,
                Key.insert: 0x2d, Key.home: 0x24, Key.end: 0x23,
                Key.page_up: 0x21, Key.page_down: 0x22,
                Key.up: 0x26, Key.down: 0x28, Key.left: 0x25, Key.right: 0x27,
                Key.print_screen: 0x2c, Key.pause: 0x13,
                Key.shift: 0x10, Key.shift_l: 0xa0, Key.shift_r: 0xa1,
                Key.ctrl: 0x11, Key.ctrl_l: 0xa2, Key.ctrl_r: 0xa3,
                Key.alt: 0x12, Key.alt_l: 0xa4, Key.alt_r: 0xa5,
                Key.cmd: 0x5b, Key.cmd_l: 0x5b, Key.cmd_r: 0x5c,
            }
            return _KEY_VK.get(key, None)
        if isinstance(key, int):
            return key
        if isinstance(key, str) and len(key) == 1:
            return ord(key.upper())
        return None

    def _unregister_hotkey(self):
        """Stop global keyboard listener"""
        if self._hotkey_listener is not None:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._hotkey_listener = None
        self._hotkey_registered = False

    def nativeEvent(self, event_type, message):
        """No longer using RegisterHotKey"""
        return super().nativeEvent(event_type, message)

    def _show_pin_settings(self):
        """Open window pin settings dialog"""
        from window_pin import get_manager
        mgr = get_manager()
        if mgr:
            mgr.show_settings(self)

    def _show_hotkey_dialog(self):
        """Open dialog for user to set screenshot hotkey"""
        from PyQt5.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            self, "Screenshot Hotkey",
            "Enter hotkey combination:\n"
            "Modifiers: <ctrl> <alt> <shift> <win>\n"
            "Examples: <ctrl>+<f12>  <ctrl>+<shift>+s  <f12>\n"
            "Current: " + self._screenshot_hotkey,
            text=self._screenshot_hotkey
        )
        if ok and text.strip():
            self._unregister_hotkey()
            self._screenshot_hotkey = text.strip()
            self._save_hotkey_settings()
            self._register_hotkey()
            self.say(f"Screenshot hotkey set to {self._screenshot_hotkey}", 3.0)

    def set_hotkey_enabled(self, enabled: bool):
        """Disable/enable global hotkey for game mode and other scenarios"""
        self._hotkey_enabled = enabled
        if enabled:
            self._register_hotkey()
        else:
            self._unregister_hotkey()

    # ── Auto Start ────────────────────────────────────

    @staticmethod
    def _startup_vbs_path():
        import os as _os
        startup_dir = _os.path.join(
            _os.environ.get("APPDATA", ""),
            "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
        )
        return _os.path.join(startup_dir, "PixelBallPet.vbs")

    def _is_autostart_enabled(self) -> bool:
        import os as _os
        return _os.path.isfile(self._startup_vbs_path())

    def _toggle_autostart(self, enabled: bool):
        import os as _os
        path = self._startup_vbs_path()
        if enabled:
            # Create VBS startup script in startup directory
            project_dir = _os.path.dirname(_os.path.abspath(__file__))
            pythonw = _os.path.join(project_dir, ".venv", "Scripts", "pythonw.exe")
            main_py = _os.path.join(project_dir, "main.py")
            content = (
                'CreateObject("WScript.Shell").Run '
                f'"{pythonw} {main_py}", 0, False'
            )
            _os.makedirs(_os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.say("Auto-start enabled~\nI'll appear automatically next boot!", 3.0)
        else:
            try:
                _os.remove(path)
            except OSError:
                pass
            self.say("Auto-start disabled~", 2.0)

    def _show_stats_panel(self):
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Today's Stats")
        dlg.setWindowFlags(dlg.windowFlags() | Qt.Tool)
        dlg.setFixedSize(320, 220)
        dlg.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: #e0e0e0; border: 2px solid #555; }
            QLabel { color: #ccc; font-size: 15px; }
            QPushButton { background-color: #505050; color: #e0e0e0; border: 1px solid #666;
                padding: 5px 14px; font-size: 14px; border-radius: 3px; }
            QPushButton:hover { background-color: #666; }
        """)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.addWidget(QLabel(f"Today's keystrokes: {self._stats_today['keystrokes']:,}"))
        layout.addWidget(QLabel(f"Today's mouse clicks: {self._stats_today['clicks']:,}"))
        layout.addWidget(QLabel(f"Today's mouse movement: {self._stats_today['distance_m']:.1f} m"))
        # Yesterday comparison
        import datetime as _dt
        yesterday = (_dt.datetime.now() - _dt.timedelta(days=1)).strftime("%Y-%m-%d")
        yd = self._stats.get(yesterday, {})
        if yd:
            layout.addWidget(QLabel(f"Yesterday: {yd.get('keystrokes',0):,} keys / {yd.get('clicks',0):,} clicks"))
        btn = QPushButton("Close")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn, alignment=Qt.AlignCenter)
        dlg.move(self.mapToGlobal(QPoint(self.width() + 8, 0)))
        dlg.exec_()

    # ── Desktop Cleanup Reminder ──────────────────────

    @staticmethod
    def _get_dir_size_and_count(path: str):
        """Recursively count total files and total occupied space (bytes) in directory"""
        import os as _os
        total_size = 0
        total_count = 0
        try:
            for dirpath, dirnames, filenames in _os.walk(path):
                for fn in filenames:
                    fp = _os.path.join(dirpath, fn)
                    try:
                        total_size += _os.path.getsize(fp)
                        total_count += 1
                    except OSError:
                        pass
        except Exception:
            pass
        return total_count, total_size

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes >= 1073741824:
            return f"{size_bytes / 1073741824:.1f} GB"
        elif size_bytes >= 1048576:
            return f"{size_bytes / 1048576:.1f} MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes} B"

    def _check_desktop_cleanup(self):
        import os as _os, datetime as _dt
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        desktop_enabled = s.value("cleanup/desktop_enabled", False, type=bool)
        recycle_enabled = s.value("cleanup/recycle_enabled", False, type=bool)
        if not desktop_enabled and not recycle_enabled:
            return

        interval = s.value("cleanup/interval_days", 7, type=int)
        last_str = s.value("cleanup/last_check", "", type=str)
        today_str = _dt.date.today().isoformat()
        if last_str == today_str:
            return
        if last_str:
            last = _dt.date.fromisoformat(last_str)
            if (_dt.date.today() - last).days < interval:
                return

        threshold_mb = s.value("cleanup/size_threshold_mb", 500, type=int)
        threshold_bytes = threshold_mb * 1048576
        messages = []

        if desktop_enabled:
            desktop = _os.path.join(_os.environ.get("USERPROFILE", ""), "Desktop")
            cnt, sz = self._get_dir_size_and_count(desktop)
            if sz > threshold_bytes:
                messages.append(f"Desktop: {cnt} files, {self._format_size(sz)} total")

        if recycle_enabled:
            sysdrive = _os.environ.get("SYSTEMDRIVE", "C:")
            recycle = _os.path.join(sysdrive + "\\", "$Recycle.Bin")
            cnt, sz = self._get_dir_size_and_count(recycle)
            if sz > threshold_bytes:
                messages.append(f"Recycle Bin: {cnt} files, {self._format_size(sz)} total")

        if messages:
            prefix = "Time to clean up~"
            self.say(prefix + "\n" + "\n".join(messages), 8.0)

        s.setValue("cleanup/last_check", today_str)

    def _start_screenshot(self):
        """Full screen screenshot → Select area → Pin to desktop"""
        self.hide()
        QTimer.singleShot(200, self._do_screenshot)

    def _do_screenshot(self):
        screen = QGuiApplication.primaryScreen()
        full = screen.grabWindow(0)
        selector = AreaSelector()
        # Give selector a background image
        selector._bg = full
        selector._captured = False

        # Override paintEvent to show background image
        orig_paint = selector.paintEvent

        def _paint_with_bg(event):
            painter = QPainter(selector)
            painter.drawPixmap(0, 0, full)
            # Semi-transparent overlay
            painter.fillRect(selector.rect(), QColor(0, 0, 0, 120))
            if selector._dragging and selector._origin and selector._current:
                r = QRect(selector._origin, selector._current).normalized()
                painter.setCompositionMode(QPainter.CompositionMode_Clear)
                painter.fillRect(r, Qt.transparent)
                painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
                painter.setPen(QPen(QColor(255, 200, 0), 2, Qt.DashLine))
                painter.drawRect(r)
            painter.end()

        selector.paintEvent = _paint_with_bg

        def _on_selected(rect):
            cropped = full.copy(rect)
            pin = ImagePinWidget(cropped)
            pin.move(rect.topLeft())
            pin.show()
            self._pinned_images = getattr(self, '_pinned_images', [])
            self._pinned_images.append(pin)
            self.show()

        def _on_cancelled():
            self.show()

        selector.area_selected.connect(_on_selected)
        selector.selection_cancelled.connect(_on_cancelled)
        selector.show()

    def _set_cleanup_interval(self):
        days, ok = QInputDialog.getInt(
            self, "Cleanup Reminder Interval", "Check every how many days?", value=7, min=1, max=30, step=1,
        )
        if ok:
            s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
            s.setValue("cleanup/interval_days", days)
            self.say(f"Cleanup reminder interval set to {days} days~", 2.0)

    def _toggle_cleanup_desktop(self, enabled: bool):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        s.setValue("cleanup/desktop_enabled", enabled)

    def _toggle_cleanup_recycle(self, enabled: bool):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        s.setValue("cleanup/recycle_enabled", enabled)

    def _on_click(self):
        """Click handler: sleep→wake, non-idle→switch to idle, idle→head pat hearts"""
        state = self._behavior.get_state()

        if state == "sleep":
            if self._bubble_particles:
                self._pop_bubble()
            else:
                self._bubble_particles.clear()
            self._zzz_particles.clear()
            self._behavior.on_click()
            self._add_shake(2, 0.15)
        elif state != "idle":
            self._behavior.on_click()
            self._add_shake(1, 0.1)
        else:
            self._character.set_expression("happy")
            self._emit_hearts(5)
            self._add_shake(2, 0.15)
            QTimer.singleShot(1500, lambda: self._character.set_expression("idle"))

        self.clicked.emit(None)
        for plugin in self._plugins:
            try:
                plugin.on_click(None)
            except Exception:
                pass

    def _on_double_click(self):
        self.double_clicked.emit(None)

    # ── Menu System ───────────────────────────────────

    def _add_utility_tools_menu(self, parent_menu):
        """Add utility tools submenu (shared by double-click/right-click)"""
        from utility_tools import (
            show_clipboard_history, show_calculator,
            show_timestamp_converter, show_password_generator, show_qr_generator,
            show_text_stats, show_countdown, show_noise_meter,
        )
        util_menu = parent_menu.addMenu("  Utility Tools")
        util_menu.addAction("  Clipboard History").triggered.connect(lambda: show_clipboard_history(self))
        util_menu.addAction("  Quick Calculator...").triggered.connect(lambda: show_calculator(self))
        util_menu.addAction("  Countdown Days...").triggered.connect(lambda: show_countdown(self))
        util_menu.addAction("  Timestamp Converter...").triggered.connect(lambda: show_timestamp_converter(self))
        util_menu.addAction("  Password Generator...").triggered.connect(lambda: show_password_generator(self))
        util_menu.addAction("  QR Code Generator...").triggered.connect(lambda: show_qr_generator(self))
        util_menu.addAction("  Text Statistics").triggered.connect(lambda: show_text_stats(self))
        util_menu.addAction("  Noise Meter").triggered.connect(lambda: show_noise_meter(self))
        util_menu.addSeparator()
        util_menu.addAction("  Quick Search...").triggered.connect(self._quick_search_dialog)

    def _add_voice_menu_if_available(self, parent_menu):
        """If speech-to-text plugin is available, add its submenu"""
        for plugin in self._plugins:
            if plugin.name == "Speech-to-Text" and hasattr(plugin, '_mgr'):
                mgr = plugin._mgr
                voice_menu = parent_menu.addMenu("  Speech to Text")
                if mgr.running:
                    voice_menu.addAction("  ⏹ Stop Recognition").triggered.connect(mgr.stop)
                else:
                    voice_menu.addAction("  Start Recognition").triggered.connect(mgr.start)
                voice_menu.addAction("  Settings...").triggered.connect(mgr.show_settings)
                return

    def _show_double_click_menu(self):
        """Double-click menu — all quick action entries"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #2b2b2b; color: #e0e0e0; border: 1px solid #555; padding: 4px; }
            QMenu::item { padding: 6px 24px; border-radius: 3px; }
            QMenu::item:selected { background-color: #505050; }
            QMenu::separator { height: 1px; background: #555; margin: 4px 8px; }
        """)

        # ── Chat ──
        chat_menu = menu.addMenu("  Chat")
        if self._has_ai_config():
            chat_menu.addAction("  Ask AI...").triggered.connect(self._ask_ai)
        chat_menu.addAction("  AI Settings...").triggered.connect(self._show_ai_profile_dialog)
        chat_menu.addSeparator()
        chat_menu.addAction("  What time is it?").triggered.connect(self._say_time)
        chat_menu.addAction("  How's the weather?").triggered.connect(self._say_weather)
        chat_menu.addAction("  Any todos?").triggered.connect(self._say_todo_status)
        chat_menu.addSeparator()
        chat_menu.addAction("  Tell a dark joke").triggered.connect(self._say_joke)
        chat_menu.addAction("  Share a fun fact").triggered.connect(self._say_fact)
        chat_menu.addAction("  Praise me").triggered.connect(self._say_compliment)

        # ── Time Management ──
        time_menu = menu.addMenu("  Time Management")
        time_menu.addAction("  Open Todo List").triggered.connect(self._show_todo_panel)
        time_menu.addAction("  Set Countdown...").triggered.connect(self._show_countdown_dialog)
        from utility_tools import show_stopwatch
        time_menu.addAction("  Stopwatch").triggered.connect(
            lambda: show_stopwatch(self))
        time_menu.addAction("  Alarm Manager...").triggered.connect(self._show_alarm_manager)

        # ── Utility Tools ──
        self._add_utility_tools_menu(menu)

        # ── Speech-to-Text ──
        self._add_voice_menu_if_available(menu)

        # ── Body Tracking ──
        body_sub = menu.addMenu("  Body Tracking")
        body_sub.addAction("  Record Weight...").triggered.connect(self._record_weight)
        body_sub.addAction("  View Trend").triggered.connect(self._show_body_panel)

        # ── Enter Mode ──
        mode_menu = menu.addMenu("  Enter Mode")
        act_game = mode_menu.addAction("  Game Mode")
        act_game.setCheckable(True)
        act_game.setChecked(self._game_mode.is_active())
        act_game.triggered.connect(lambda checked: self._game_mode.toggle())
        menu.aboutToShow.connect(
            lambda: act_game.setChecked(self._game_mode.is_active())
        )

        # ── Other Quick Actions ──
        menu.addSeparator()
        menu.addAction("  Today's Stats").triggered.connect(self._show_stats_panel)
        menu.addAction("  Screenshot Pin").triggered.connect(self._start_screenshot)

        menu.exec_(self.mapToGlobal(QPoint(self.width() + 4, 0)))

    def contextMenuEvent(self, event):
        if self._passthrough:
            return
        self._build_and_show_menu(self.mapToGlobal(QPoint(self.width() + 4, 0)))

    def _build_and_show_menu(self, menu_pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #2b2b2b; color: #e0e0e0; border: 1px solid #555; padding: 4px; }
            QMenu::item { padding: 6px 24px; border-radius: 3px; }
            QMenu::item:selected { background-color: #505050; }
            QMenu::separator { height: 1px; background: #555; margin: 4px 8px; }
        """)

        # Expression submenu
        expr_menu = menu.addMenu("Switch Expression")
        for name in self._character.expression_manager.get_names():
            action = expr_menu.addAction(f"  {self._expr_icon(name)}  {name}")
            action.triggered.connect(lambda checked, n=name: self._set_expression(n))
        expr_menu.addSeparator()
        expr_menu.addAction("  Manage Expressions...").triggered.connect(self._show_expression_editor)

        menu.addSeparator()

        # State submenu
        state_menu = menu.addMenu("Switch State")
        state_menu.addAction("Walk").triggered.connect(
            lambda: self._behavior.transition_to("walk", {"manual": True}))
        state_menu.addAction("Bounce").triggered.connect(
            lambda: self._behavior.transition_to("bounce"))
        state_menu.addAction("Jump").triggered.connect(
            lambda: self._behavior.transition_to("jump"))
        state_menu.addAction("Sleep").triggered.connect(
            lambda: self._behavior.transition_to("sleep", {"manual": True}))
        state_menu.addAction("Idle").triggered.connect(
            lambda: self._behavior.transition_to_idle())

        menu.addSeparator()

        # Settings submenu
        settings_menu = menu.addMenu("Settings")
        settings_menu.addAction("Name Settings").triggered.connect(self._show_name_settings)
        settings_menu.addAction("City Settings").triggered.connect(self._show_city_dialog)
        settings_menu.addSeparator()

        # Activity area
        area_menu = settings_menu.addMenu("Activity Area")
        area_group = QActionGroup(area_menu)
        area_group.setExclusive(True)

        act_full = area_menu.addAction("Full Desktop")
        act_full.setCheckable(True)
        act_full.setChecked(self._active_area_key == "full")
        area_group.addAction(act_full)
        act_full.triggered.connect(lambda: self._apply_area("full"))

        if self._activity_areas:
            area_menu.addSeparator()
            for a in self._activity_areas:
                act = area_menu.addAction(f"  {a['name']}")
                act.setCheckable(True)
                act.setChecked(self._active_area_key == a["name"])
                area_group.addAction(act)
                act.triggered.connect(lambda checked, key=a["name"]: self._apply_area(key))

        area_menu.addSeparator()
        area_menu.addAction("+ New Area...").triggered.connect(self._start_area_selection)

        if self._activity_areas:
            area_menu.addSeparator()
            del_menu = area_menu.addMenu("Delete Area")
            for a in self._activity_areas:
                del_menu.addAction(f"x {a['name']}").triggered.connect(
                    lambda checked, key=a["name"]: self._delete_area(key))

        settings_menu.addSeparator()
        act_pt = settings_menu.addAction("Passthrough Mode")
        act_pt.setCheckable(True)
        act_pt.setChecked(self._passthrough)
        act_pt.triggered.connect(lambda checked: self.set_passthrough(checked))

        settings_menu.addSeparator()
        act_move = settings_menu.addAction("Disable Movement")
        act_move.setCheckable(True)
        act_move.setChecked(not self._behavior.is_movement_enabled())
        act_move.triggered.connect(lambda checked: (
            self._behavior.set_movement_enabled(not checked),
            self._save_behavior_settings()
        ))

        settings_menu.addSeparator()
        settings_menu.addAction("Set Countdown...").triggered.connect(self._show_countdown_dialog)

        act_drink = settings_menu.addAction("Drink Water Reminder")
        act_drink.setCheckable(True)
        act_drink.setChecked(self._behavior.is_drink_reminder_enabled())
        act_drink.triggered.connect(lambda checked: (
            self._behavior.set_drink_reminder_enabled(checked),
            self._save_behavior_settings()
        ))

        drink_interval_menu = settings_menu.addMenu("  Drink Interval")
        for mins in [15, 30, 45, 60, 90]:
            prefix = "> " if self._behavior.get_drink_interval() == mins else "  "
            act_int = drink_interval_menu.addAction(f"{prefix}{mins} min")
            act_int.triggered.connect(lambda checked, m=mins: (
                self._behavior.set_drink_interval(m),
                self._save_behavior_settings()
            ))

        act_eye = settings_menu.addAction("Eye Rest Reminder (20-20-20)")
        act_eye.setCheckable(True)
        act_eye.setChecked(self._behavior.is_eye_rest_enabled())
        act_eye.triggered.connect(lambda checked: (
            self._behavior.set_eye_rest_enabled(checked),
            self._save_behavior_settings()
        ))

        # Proactive chat (interval acts as toggle, never = off)
        proactive_menu = settings_menu.addMenu("  Proactive Chat")
        _proactive_on = self._ai_profile.get("proactive_chat", False)
        cur_min = self._ai_profile.get("proactive_interval_min", cfg.PROACTIVE_CHAT_INTERVAL_MIN)
        cur_max = self._ai_profile.get("proactive_interval_max", cfg.PROACTIVE_CHAT_INTERVAL_MAX)

        # Never
        prefix_never = "> " if not _proactive_on else "  "
        act_never = proactive_menu.addAction(f"{prefix_never}Never")
        act_never.triggered.connect(lambda: (
            self._ai_profile.update({"proactive_chat": False}),
            self._save_ai_profile(),
            self._stop_proactive_timer(),
            self.say("Proactive chat disabled~\nDouble-click me if you want to chat!", 3.0)
        ))

        proactive_menu.addSeparator()

        # Interval presets
        interval_presets = [
            ("1-3 min (Frequent)", 1, 3),
            ("5-10 min (Normal)", 5, 10),
            ("15-30 min (Occasional)", 15, 30),
            ("30-60 min (Rare)", 30, 60),
        ]
        for label, _min, _max in interval_presets:
            selected = _proactive_on and cur_min == _min and cur_max == _max
            prefix = "> " if selected else "  "
            act = proactive_menu.addAction(f"{prefix}{label}")
            act.triggered.connect(
                lambda checked, a=_min, b=_max: (
                    self._ai_profile.update({"proactive_chat": True, "proactive_interval_min": a, "proactive_interval_max": b}),
                    self._save_ai_profile(),
                    self._start_proactive_timer(),
                    self.say(f"Proactive chat interval set to {a}-{b} min~", 2.0)
                )
            )

        proactive_menu.addSeparator()
        # Custom (if it happens to be a custom area and active, show as selected)
        _is_preset = any(cur_min == a and cur_max == b for _, a, b in interval_presets)
        prefix_custom = "> " if (_proactive_on and not _is_preset) else "  "
        act_custom = proactive_menu.addAction(f"{prefix_custom}Custom...")
        act_custom.triggered.connect(self._set_custom_proactive_interval)

        # Keyboard/mouse stats toggle
        act_stats = settings_menu.addAction("Keyboard & Mouse Stats")
        act_stats.setCheckable(True)
        act_stats.setChecked(self._stats_enabled)
        act_stats.triggered.connect(lambda checked: self._toggle_stats(checked))

        act_autostart = settings_menu.addAction("Auto-start on Boot")
        act_autostart.setCheckable(True)
        act_autostart.setChecked(self._is_autostart_enabled())
        act_autostart.triggered.connect(lambda checked: self._toggle_autostart(checked))

        settings_menu.addAction("  Screenshot Hotkey...").triggered.connect(self._show_hotkey_dialog)
        settings_menu.addAction("  Pin Settings...").triggered.connect(self._show_pin_settings)

        # Game mode settings submenu
        gm_menu = settings_menu.addMenu("  Game Mode")
        act_gm_perf = gm_menu.addAction("Performance Monitor Panel")
        act_gm_perf.setCheckable(True)
        act_gm_perf.setChecked(self._game_mode.is_perf_enabled())
        act_gm_perf.triggered.connect(lambda checked: self._game_mode.set_performance_panel_enabled(checked))

        act_gm_key = gm_menu.addAction("Keyboard Input Panel")
        act_gm_key.setCheckable(True)
        act_gm_key.setChecked(self._game_mode.is_key_enabled())
        act_gm_key.triggered.connect(lambda checked: self._game_mode.set_keyboard_panel_enabled(checked))

        gm_menu.addSeparator()
        act_gm_interval = gm_menu.addAction("Show Key Press Interval")
        act_gm_interval.setCheckable(True)
        act_gm_interval.setChecked(self._game_mode.is_keyboard_interval_enabled())
        act_gm_interval.triggered.connect(lambda checked: self._game_mode.set_keyboard_show_interval(checked))

        # Desktop cleanup submenu
        cleanup_menu = settings_menu.addMenu("Desktop Cleanup")
        s_cleanup = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        act_desktop = cleanup_menu.addAction("Desktop Cleanup Reminder")
        act_desktop.setCheckable(True)
        act_desktop.setChecked(s_cleanup.value("cleanup/desktop_enabled", False, type=bool))
        act_desktop.triggered.connect(lambda checked: self._toggle_cleanup_desktop(checked))
        act_recycle = cleanup_menu.addAction("Recycle Bin Cleanup Reminder")
        act_recycle.setCheckable(True)
        act_recycle.setChecked(s_cleanup.value("cleanup/recycle_enabled", False, type=bool))
        act_recycle.triggered.connect(lambda checked: self._toggle_cleanup_recycle(checked))
        cleanup_menu.addAction("Cleanup Reminder Interval...").triggered.connect(self._set_cleanup_interval)

        settings_menu.addSeparator()

        # AI chat submenu
        ai_menu = settings_menu.addMenu("  AI Chat")
        ai_menu.addAction("  Configure API...").triggered.connect(self._show_ai_config_dialog)
        ai_menu.addAction("  AI Advanced Settings...").triggered.connect(self._show_ai_profile_dialog)
        ai_menu.addAction("  Delete API Config").triggered.connect(self._delete_ai_config)

        settings_menu.addSeparator()

        # Body tracking settings (goals/weigh reminder)
        body_settings = settings_menu.addMenu("  Body Tracking")
        body_settings.addAction("Set Target Weight...").triggered.connect(
            lambda: self._set_body_target("weight"))
        body_settings.addAction("Set Height...").triggered.connect(
            lambda: self._set_body_target("height"))
        body_settings.addAction("Set Starting Weight...").triggered.connect(
            lambda: self._set_body_target("start"))
        body_settings.addSeparator()
        act_weigh = body_settings.addAction("Daily Weigh-in Reminder")
        act_weigh.setCheckable(True)
        act_weigh.setChecked(self._weigh_reminder_enabled)
        act_weigh.triggered.connect(lambda checked: (
            self._set_weigh_reminder_enabled(checked),
            self.say("Daily weigh-in reminder enabled~\nI'll remind you tomorrow morning!", 3.0) if checked
            else self.say("Weigh-in reminder disabled~", 2.0)
        ))
        remind_time_menu = body_settings.addMenu("  Reminder Time")
        for t in ["07:00", "07:30", "08:00", "08:30", "09:00", "21:00", "22:00"]:
            prefix = "> " if self._weigh_reminder_time == t else "  "
            act_t = remind_time_menu.addAction(f"{prefix}{t}")
            act_t.triggered.connect(lambda checked, tm=t: self._set_weigh_reminder_time(tm))

        # Plugin menu (keep in right-click)
        has_plugins = False
        for plugin in self._plugins:
            entries = plugin.context_menu_entries()
            if entries:
                if not has_plugins:
                    menu.addSeparator()
                    has_plugins = True
                sub = menu.addMenu(f"Plugin: {plugin.name}")
                for entry in entries:
                    if isinstance(entry, tuple) and len(entry) == 2:
                        label, callback = entry
                        if label is None:
                            sub.addSeparator()
                        elif isinstance(callback, list):
                            sub2 = sub.addMenu(label)
                            for sl, sc in callback:
                                sub2.addAction(sl).triggered.connect(sc)
                        else:
                            sub.addAction(label).triggered.connect(callback)

        menu.addSeparator()
        menu.addAction("Exit").triggered.connect(QApplication.instance().quit)

        menu.exec_(menu_pos)

    @staticmethod
    def _expr_icon(name):
        icons = {
            "idle": "", "happy": "", "sad": "",
            "sleepy": "", "surprised": "", "blink": "",
            "pout": "", "dizzy": "", "drink": "", "eye_mask": "",
        }
        return icons.get(name, "?")

    def _show_expression_editor(self):
        """Open expression manager dialog"""
        from expressions.expression_editor import ExpressionEditorDialog
        dlg = ExpressionEditorDialog(self._character, self)
        dlg.exec_()
        self._character.refresh_from_disk()
        # If current expression is deleted, switch back to first
        if self._character.get_expression() not in self._character.expression_manager.get_names():
            self._character.set_expression("idle")

    # ── Behavior Signal Response ──────────────────────

    def _on_action(self, action_name, params):
        # Clear all effects when exiting sleep
        if action_name != "sleep":
            if self._bubble_particles:
                self._pop_bubble()
            else:
                self._bubble_particles.clear()
            self._zzz_particles.clear()

        is_manual = params.get("manual", False)

        if action_name == "walk":
            if not self._behavior.is_movement_enabled():
                return
            if not is_manual:
                dx = params.get("dx", 0)
                dy = params.get("dy", 0)
                duration = params.get("duration", 2.0)
                from_pos = (self._fx, self._fy)
                to_pos = (self._fx + dx, self._fy + dy)
                self._animation.add_move(from_pos, to_pos, duration, "ease_in_out")
                self._animation.add_scale(0, 0.05, 0.3, "ease_out")

        elif action_name == "bounce":
            intensity = params.get("intensity", 1.0)
            self._animation.add_bounce(intensity, 0.6)
            self._animation.add_scale(0, 0.1, 0.2, "ease_out")

        elif action_name == "jump":
            height = params.get("height", 80)
            self._animation.add_jump(height, 0.7)

        elif action_name == "sleep":
            self._emit_particles()
            if not is_manual:
                self._animation.add_scale(0, -0.05, 1.0, "ease_in_out")

        elif action_name == "idle":
            self._animation.add_scale(0, 0, 0.5, "ease_out")
            self._zzz_particles.clear()
            self._bubble_particles.clear()
            self._pop_particles.clear()

        for plugin in self._plugins:
            try:
                plugin.on_action_changed(action_name)
            except Exception:
                pass

    def _on_expression(self, expr_name):
        self._character.set_expression(expr_name)
        for plugin in self._plugins:
            try:
                plugin.on_expression_changed(expr_name)
            except Exception:
                pass

    def _set_expression(self, name):
        """Manually set expression — force exit sleep and auto-revert after 10s delay"""
        # Cancel AI expression timer (manual operation takes priority)
        if self._ai_expr_timer is not None:
            self._ai_expr_timer.stop()
            self._ai_expr_timer = None
        if self._behavior.get_state() == "sleep":
            if self._bubble_particles:
                self._pop_bubble()
            else:
                self._bubble_particles.clear()
            self._zzz_particles.clear()
            self._pop_particles.clear()
            self._behavior.transition_to_idle()
            self._behavior._state_timer = -10.0

        self._character.set_expression(name)
        for plugin in self._plugins:
            try:
                plugin.on_expression_changed(name)
            except Exception:
                pass

    # ── Name Settings ─────────────────────────────────

    def _load_name_settings(self):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        self._pet_name = s.value("name/pet", cfg.DEFAULT_PET_NAME, type=str)
        self._user_title = s.value("name/user_title", cfg.DEFAULT_USER_TITLE, type=str)

    def _save_name_settings(self):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        s.setValue("name/pet", self._pet_name)
        s.setValue("name/user_title", self._user_title)

    def _show_name_settings(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout

        dlg = QDialog(self)
        dlg.setWindowTitle("Name Settings")
        dlg.setWindowFlags(dlg.windowFlags() | Qt.Tool)
        dlg.setFixedSize(260, 180)
        dlg.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: #e0e0e0; border: 2px solid #555; }
            QLabel { color: #ccc; font-size: 14px; }
            QLineEdit { background-color: #3a3a3a; color: #e0e0e0; border: 1px solid #666;
                        padding: 4px 8px; font-size: 15px; border-radius: 3px; }
            QLineEdit:focus { border-color: #ffc800; }
            QPushButton { background-color: #505050; color: #e0e0e0; border: 1px solid #666;
                          padding: 5px 18px; font-size: 14px; border-radius: 3px; }
            QPushButton:hover { background-color: #666; }
            QPushButton:pressed { background-color: #ffc800; color: #1e1e1e; }
        """)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Pet name:"))
        edit_pet = QLineEdit(self._pet_name)
        edit_pet.setPlaceholderText("Give your pet a name~")
        layout.addWidget(edit_pet)

        layout.addWidget(QLabel("What the pet calls you:"))
        edit_user = QLineEdit(self._user_title)
        edit_user.setPlaceholderText("e.g.: Master, Friend...")
        layout.addWidget(edit_user)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("OK")
        btn_cancel = QPushButton("Cancel")
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        def on_ok():
            new_pet = edit_pet.text().strip()
            new_user = edit_user.text().strip()
            if new_pet:
                self._pet_name = new_pet
            if new_user:
                self._user_title = new_user
            self._save_name_settings()
            dlg.accept()
            self.say(f"I'm now called {self._pet_name}!\nHello there, {self._user_title}~")

        btn_ok.clicked.connect(on_ok)
        btn_cancel.clicked.connect(dlg.reject)

        dlg.move(self.mapToGlobal(QPoint(self.width() + 8, 0)))
        dlg.exec_()

    # ── City Settings ─────────────────────────────────

    def _load_city_setting(self):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        self._city = s.value("weather/city", "", type=str)

    def _save_city_setting(self):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        s.setValue("weather/city", self._city)
        s.sync()

    def _show_city_dialog(self):
        """City settings dialog — for weather location"""
        text, ok = QInputDialog.getText(
            self, "City Settings",
            "Enter your city name (for weather location):\ne.g.: London, Beijing, Tokyo\nLeave empty for IP auto-location",
            text=self._city
        )
        if ok:
            self._city = text.strip()
            self._save_city_setting()
            self._refresh_weather_cache()
            if self._city:
                self.say(f"City set to {self._city}~\nWeather data updating!", 3.0)
            else:
                self.say("Switched to IP auto-location~", 3.0)

    # ── Behavior Settings Persistence ─────────────────

    def _load_behavior_settings(self):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        self._behavior.set_movement_enabled(s.value("behavior/movement_enabled", True, type=bool))
        self._behavior.set_drink_reminder_enabled(s.value("behavior/drink_reminder", False, type=bool))
        self._behavior.set_eye_rest_enabled(s.value("behavior/eye_rest", False, type=bool))
        interval = s.value("behavior/drink_interval", cfg.DRINK_REMINDER_INTERVAL, type=int)
        self._behavior.set_drink_interval(interval)

    def _save_behavior_settings(self):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        s.setValue("behavior/movement_enabled", self._behavior.is_movement_enabled())
        s.setValue("behavior/drink_reminder", self._behavior.is_drink_reminder_enabled())
        s.setValue("behavior/eye_rest", self._behavior.is_eye_rest_enabled())
        s.setValue("behavior/drink_interval", self._behavior.get_drink_interval())
        s.sync()

    # ── Activity Area Management ──────────────────────

    def _load_areas(self):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        raw = s.value("areas/list", "[]", type=str)
        try:
            self._activity_areas = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            self._activity_areas = []
        self._active_area_key = s.value("areas/active", "full", type=str)

    def _save_areas(self):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        s.setValue("areas/list", json.dumps(self._activity_areas, ensure_ascii=False))
        s.setValue("areas/active", self._active_area_key)

    def _apply_active_area(self):
        if self._active_area_key == "full":
            screen = QApplication.primaryScreen()
            if screen:
                self._behavior.set_screen_rect(screen.availableGeometry())
        else:
            for area in self._activity_areas:
                if area["name"] == self._active_area_key:
                    rect = QRect(area["x"], area["y"], area["w"], area["h"])
                    self._behavior.set_screen_rect(rect)
                    if not rect.contains(QPoint(int(self._fx), int(self._fy))):
                        cx = area["x"] + area["w"] // 2
                        cy = area["y"] + area["h"] // 2
                        self._fx, self._fy = float(cx), float(cy)
                        self.move(cx, cy)
                    return
            self._active_area_key = "full"
            self._save_areas()
            self._apply_active_area()

    def _apply_area(self, key):
        self._active_area_key = key
        self._save_areas()
        self._apply_active_area()

    def _start_area_selection(self):
        if self._area_selector is not None:
            self._area_selector.close()
            self._area_selector = None
        self._area_selector = AreaSelector()
        self._area_selector.area_selected.connect(self._on_area_selected)
        self._area_selector.selection_cancelled.connect(lambda: self._cleanup_selector())
        self._area_selector.show()

    def _on_area_selected(self, rect):
        name, ok = QInputDialog.getText(
            self, "Save Activity Area",
            f"Area: {rect.x()},{rect.y()}  {rect.width()}x{rect.height()}\nName this area:",
            text=f"Area{len(self._activity_areas) + 1}"
        )
        if ok and name.strip():
            name = name.strip()
            for area in self._activity_areas:
                if area["name"] == name:
                    QMessageBox.warning(self, "Duplicate Name", f"{name} already exists, please choose another name.")
                    self._cleanup_selector()
                    return
            self._activity_areas.append({
                "name": name, "x": rect.x(), "y": rect.y(),
                "w": rect.width(), "h": rect.height(),
            })
            self._save_areas()
            self._apply_area(name)
            self.say(f"Activity area set to\n{name}!", 3.0)
        self._cleanup_selector()

    def _delete_area(self, key):
        if key == "full":
            return
        reply = QMessageBox.question(
            self, "Delete Area", f"Are you sure you want to delete activity area {key}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self._activity_areas = [a for a in self._activity_areas if a["name"] != key]
        if self._active_area_key == key:
            self._active_area_key = "full"
        self._save_areas()
        self._apply_active_area()

    def _cleanup_selector(self):
        if self._area_selector is not None:
            self._area_selector.close()
            self._area_selector.deleteLater()
            self._area_selector = None

    # ── Heart Particles ───────────────────────────────

    def _update_hearts(self, dt_ms):
        now = time.time()
        dt = dt_ms / 1000.0
        survivors = []
        for p in self._heart_particles:
            p["y"] -= p["speed"] * dt * 30
            p["x"] += random.uniform(-0.3, 0.3) * dt * 30
            if now - p["spawn"] < p["life"]:
                survivors.append(p)
        self._heart_particles = survivors

    def _render_hearts(self, painter):
        for p in self._heart_particles:
            elapsed = time.time() - p["spawn"]
            alpha = max(0, min(255, int(255 * (1 - elapsed / p["life"]))))
            c = QColor(255, 80, 100, alpha)
            painter.setPen(Qt.NoPen)
            painter.setBrush(c)
            bx = int(self.width() // 2 - 10 + p["x"])
            by = int(5 * cfg.PIXEL_SCALE + p["y"])
            painter.fillRect(bx, by, 4, 4, c)

    # ── Countdown ─────────────────────────────────────

    def _show_countdown_dialog(self):
        minutes, ok = QInputDialog.getInt(
            self, "Set Countdown", "Enter countdown minutes:",
            value=5, min=1, max=180, step=1
        )
        if ok and minutes > 0:
            self._start_countdown(minutes * 60)

    def _start_countdown(self, seconds: int):
        if self._countdown is not None:
            self._countdown.stop()
            self._countdown.deleteLater()
            self._countdown = None
        bubble = CountdownBubble()
        bubble.start_countdown(seconds, self)
        self._countdown = bubble

    # ── Alarm System ──────────────────────────────────

    def _alarms_path(self):
        import os as _os
        return _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "alarms.json")

    def _load_alarms(self):
        try:
            with open(self._alarms_path(), "r", encoding="utf-8") as f:
                self._alarms = json.load(f)
            if self._alarms:
                self._next_alarm_id = max(a.get("id", 0) for a in self._alarms) + 1
        except (FileNotFoundError, json.JSONDecodeError):
            self._alarms = []

    def _save_alarms(self):
        with open(self._alarms_path(), "w", encoding="utf-8") as f:
            json.dump(self._alarms, f, ensure_ascii=False, indent=2)

    def _check_alarms(self):
        """Check if alarms should fire (triggered every 15 seconds)"""
        import datetime as _dt
        now = _dt.datetime.now()
        h, m = now.hour, now.minute
        wd = now.isoweekday()  # 1=Mon...7=Sun
        fired = False

        for alarm in self._alarms:
            if not alarm.get("enabled", True):
                continue
            if alarm["hour"] != h or alarm["minute"] != m:
                continue

            repeat = alarm.get("repeat", "once")
            if repeat == "daily":
                fired = True
            elif repeat == "weekly":
                if wd in alarm.get("days", []):
                    fired = True
            else:  # once
                fired = True
                alarm["enabled"] = False

            if fired:
                self._fire_alarm(alarm)
                fired = False

        if any(not a.get("enabled", True) and a.get("repeat") == "once" for a in self._alarms):
            self._save_alarms()

    def _fire_alarm(self, alarm):
        """Fire alarm: beep sound + bubble notification"""
        name = alarm.get("name", "Alarm")
        # Play ding sound
        try:
            import winsound
            winsound.Beep(1000, 300)
        except ImportError:
            QApplication.beep()
        self.say(f"⏰ {name}\nTime's up!", 6.0)

    def _show_alarm_manager(self):
        """Open alarm management dialog"""
        self._alarm_list_dialog()

    # ── Alarm Management Dialog ───────────────────────

    def _alarm_list_dialog(self):
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel,
            QPushButton, QListWidget, QListWidgetItem, QMessageBox,
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Alarm Manager")
        dlg.setWindowFlags(dlg.windowFlags() | Qt.Tool)
        dlg.setFixedSize(460, 400)
        dlg.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: #e0e0e0; border: 2px solid #555; }
            QLabel { color: #ccc; font-size: 14px; }
            QListWidget { background-color: #3a3a3a; color: #e0e0e0; border: 1px solid #666;
                border-radius: 3px; font-size: 13px; }
            QListWidget::item { padding: 6px 10px; }
            QListWidget::item:selected { background-color: #505050; }
            QPushButton { background-color: #505050; color: #e0e0e0; border: 1px solid #666;
                padding: 5px 14px; font-size: 13px; border-radius: 3px; }
            QPushButton:hover { background-color: #666; }
            QPushButton#btn_del { background-color: #6a2d2d; border-color: #c0392b; }
            QPushButton#btn_del:hover { background-color: #922b21; }
        """)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Alarm list (double-click to edit):"))

        lst = QListWidget()
        self._populate_alarm_list(lst)
        lst.itemDoubleClicked.connect(lambda item: self._alarm_edit_dialog(
            item.data(Qt.UserRole), dlg, lambda: self._populate_alarm_list(lst)
        ))
        layout.addWidget(lst)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("＋ New")
        btn_add.clicked.connect(lambda: self._alarm_edit_dialog(
            None, dlg, lambda: self._populate_alarm_list(lst)
        ))
        btn_row.addWidget(btn_add)

        btn_edit = QPushButton("✎ Edit")
        btn_edit.clicked.connect(lambda: (
            self._alarm_edit_dialog(
                lst.currentItem().data(Qt.UserRole) if lst.currentItem() else None,
                dlg, lambda: self._populate_alarm_list(lst)
            ) if lst.currentItem() else None
        ))
        btn_row.addWidget(btn_edit)

        btn_del = QPushButton("✕ Delete")
        btn_del.setObjectName("btn_del")
        btn_del.clicked.connect(lambda: self._delete_alarm(lst))
        btn_row.addWidget(btn_del)
        btn_row.addStretch()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        dlg.move(self.mapToGlobal(QPoint(self.width() + 8, 0)))
        dlg.exec_()

    def _populate_alarm_list(self, lst: 'QListWidget'):
        import datetime as _dt
        lst.clear()
        for alarm in self._alarms:
            name = alarm.get("name", "Alarm")
            h = alarm.get("hour", 0)
            m = alarm.get("minute", 0)
            enabled = alarm.get("enabled", True)
            repeat = alarm.get("repeat", "once")

            if repeat == "daily":
                repeat_text = "Daily"
            elif repeat == "weekly":
                wd_map = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
                days = alarm.get("days", [])
                if len(days) == 7:
                    repeat_text = "Daily"
                elif days == [1, 2, 3, 4, 5]:
                    repeat_text = "Weekdays"
                elif days == [6, 7]:
                    repeat_text = "Weekends"
                else:
                    repeat_text = "|".join(wd_map.get(d, "?") for d in sorted(days))
            else:
                repeat_text = "Once"

            icon = "☑" if enabled else "☐"
            label = f"{icon}  {name}    {h:02d}:{m:02d}    {repeat_text}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, alarm["id"])
            lst.addItem(item)

    def _delete_alarm(self, lst: 'QListWidget'):
        item = lst.currentItem()
        if item is None:
            return
        alarm_id = item.data(Qt.UserRole)
        from PyQt5.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Confirm Delete", "Are you sure you want to delete this alarm?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._alarms = [a for a in self._alarms if a.get("id") != alarm_id]
            self._save_alarms()
            self._populate_alarm_list(lst)

    def _alarm_edit_dialog(self, alarm_id, parent_dlg, refresh_callback):
        """New/Edit alarm dialog"""
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel,
            QPushButton, QLineEdit, QComboBox, QSpinBox, QCheckBox,
            QWidget, QMessageBox,
        )

        is_new = alarm_id is None
        alarm = None
        if not is_new:
            for a in self._alarms:
                if a.get("id") == alarm_id:
                    alarm = a
                    break
            if alarm is None:
                return

        dlg = QDialog(parent_dlg)
        dlg.setWindowTitle("New Alarm" if is_new else "Edit Alarm")
        dlg.setWindowFlags(dlg.windowFlags() | Qt.Tool)
        dlg.setFixedSize(380, 300)
        dlg.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: #e0e0e0; border: 2px solid #555; }
            QLabel { color: #ccc; font-size: 14px; }
            QLineEdit { background-color: #3a3a3a; color: #e0e0e0;
                border: 1px solid #666; padding: 4px 8px; font-size: 14px; border-radius: 3px; }
            QLineEdit:focus { border-color: #ffc800; }
            QComboBox { background-color: #3a3a3a; color: #e0e0e0;
                border: 1px solid #666; padding: 4px 8px; font-size: 14px; border-radius: 3px; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #3a3a3a; color: #e0e0e0;
                selection-background-color: #505050; }
            QSpinBox { background-color: #3a3a3a; color: #e0e0e0;
                border: 1px solid #666; padding: 4px; font-size: 14px; border-radius: 3px; }
            QCheckBox { color: #ccc; font-size: 13px; }
            QPushButton { background-color: #505050; color: #e0e0e0; border: 1px solid #666;
                padding: 5px 14px; font-size: 14px; border-radius: 3px; }
            QPushButton:hover { background-color: #666; }
        """)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)

        # Name
        layout.addWidget(QLabel("Name:"))
        edit_name = QLineEdit(alarm.get("name", "") if alarm else "")
        layout.addWidget(edit_name)

        # Time
        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Time:"))
        spn_h = QSpinBox()
        spn_h.setRange(0, 23)
        spn_h.setValue(alarm.get("hour", 8) if alarm else 8)
        spn_h.setSuffix(" h")
        time_row.addWidget(spn_h)
        spn_m = QSpinBox()
        spn_m.setRange(0, 59)
        spn_m.setValue(alarm.get("minute", 0) if alarm else 0)
        spn_m.setSuffix(" m")
        time_row.addWidget(spn_m)
        time_row.addStretch()
        layout.addLayout(time_row)

        # Repeat mode
        repeat_row = QHBoxLayout()
        repeat_row.addWidget(QLabel("Repeat:"))
        cmb_repeat = QComboBox()
        cmb_repeat.addItems(["Once", "Daily", "Weekly"])
        repeat_map = {"once": 0, "daily": 1, "weekly": 2}
        rev_repeat = {0: "once", 1: "daily", 2: "weekly"}
        cur_repeat = alarm.get("repeat", "once") if alarm else "once"
        cmb_repeat.setCurrentIndex(repeat_map.get(cur_repeat, 0))
        repeat_row.addWidget(cmb_repeat)
        repeat_row.addStretch()
        layout.addLayout(repeat_row)

        # Weekday selection (only shown for weekly)
        wd_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        wd_checks: list[QCheckBox] = []
        wd_widget = QWidget()
        wd_layout_top = QVBoxLayout(wd_widget)
        wd_layout_top.setContentsMargins(0, 0, 0, 0)
        wd_label = QLabel("Repeat days:")
        wd_layout_top.addWidget(wd_label)
        for row_start in (0, 4):
            wd_row = QHBoxLayout()
            for i in range(row_start, min(row_start + 4, 7)):
                cb = QCheckBox(wd_names[i])
                if alarm:
                    cb.setChecked(i + 1 in alarm.get("days", []))
                wd_checks.append(cb)
                wd_row.addWidget(cb)
            wd_row.addStretch()
            wd_layout_top.addLayout(wd_row)
        layout.addWidget(wd_widget)

        def _sync_weekdays():
            visible = cmb_repeat.currentIndex() == 2  # Weekly
            wd_widget.setVisible(visible)

        _sync_weekdays()
        cmb_repeat.currentIndexChanged.connect(lambda: _sync_weekdays())

        layout.addStretch()

        # OK/Cancel
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()

        def _on_ok():
            name = edit_name.text().strip()
            if not name:
                QMessageBox.warning(dlg, "Error", "Name cannot be empty.")
                return
            h = spn_h.value()
            m = spn_m.value()
            repeat = rev_repeat[cmb_repeat.currentIndex()]
            days = []
            if repeat == "weekly":
                for i, cb in enumerate(wd_checks):
                    if cb.isChecked():
                        days.append(i + 1)
                if not days:
                    QMessageBox.warning(dlg, "Error", "Please select at least one repeat day.")
                    return

            if is_new:
                new_alarm = {
                    "id": self._next_alarm_id,
                    "name": name,
                    "hour": h,
                    "minute": m,
                    "enabled": True,
                    "repeat": repeat,
                    "days": days,
                }
                self._next_alarm_id += 1
                self._alarms.append(new_alarm)
            else:
                alarm["name"] = name
                alarm["hour"] = h
                alarm["minute"] = m
                alarm["repeat"] = repeat
                alarm["days"] = days

            self._save_alarms()
            dlg.accept()
            refresh_callback()

        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(_on_ok)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(dlg.reject)
        bottom_row.addWidget(btn_ok)
        bottom_row.addWidget(btn_cancel)
        layout.addLayout(bottom_row)

        dlg.exec_()

    # ── Todo System ───────────────────────────────────

    def _load_todos(self):
        import os as _os
        import datetime as _dt
        todo_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), cfg.TODO_FILE)
        try:
            with open(todo_path, "r", encoding="utf-8") as f:
                items = json.loads(f.read())
        except (FileNotFoundError, json.JSONDecodeError):
            items = []

        today = _dt.date.today().isoformat()
        self._todo_items = [
            t for t in items
            if not t.get("done", False) or t.get("date", "") == today
        ]
        if len(self._todo_items) != len(items):
            self._save_todos()

    def _load_dialog_data(self):
        """Load dialog database (dialog_data.json), fall back to built-in defaults if file missing or malformed"""
        import os as _os
        data_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "dialog_data.json")
        try:
            with open(data_path, "r", encoding="utf-8") as f:
                self._dialog_data = json.loads(f.read())
        except (FileNotFoundError, json.JSONDecodeError):
            self._dialog_data = {"jokes": [], "facts": [], "compliments": []}

    def _save_todos(self):
        import os as _os
        todo_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), cfg.TODO_FILE)
        with open(todo_path, "w", encoding="utf-8") as f:
            json.dump(self._todo_items, f, ensure_ascii=False, indent=2)

    def _pending_todo_count(self) -> int:
        return sum(1 for t in self._todo_items if not t.get("done", False))

    def _close_todo_panel(self):
        if self._todo_panel is not None:
            self._todo_panel.close()
            self._todo_panel.deleteLater()
            self._todo_panel = None

    # ── Body Tracking: Data Persistence ───────────────

    def _load_body_settings(self):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        self._body_height = s.value("body/height", cfg.DEFAULT_HEIGHT, type=float)
        self._body_target_weight = s.value("body/target_weight", 0.0, type=float)
        self._body_start_weight = s.value("body/start_weight", 0.0, type=float)
        self._weigh_reminder_enabled = s.value("body/weigh_reminder_enabled", False, type=bool)
        self._weigh_reminder_time = s.value("body/weigh_reminder_time", cfg.DEFAULT_WEIGH_TIME, type=str)
        self._last_weigh_reminder_date = s.value("body/last_weigh_reminder_date", "", type=str)

    def _save_body_settings(self):
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        s.setValue("body/height", self._body_height)
        s.setValue("body/target_weight", self._body_target_weight)
        s.setValue("body/start_weight", self._body_start_weight)
        s.setValue("body/weigh_reminder_enabled", self._weigh_reminder_enabled)
        s.setValue("body/weigh_reminder_time", self._weigh_reminder_time)
        s.setValue("body/last_weigh_reminder_date", self._last_weigh_reminder_date)
        s.sync()

    def _load_body_records(self):
        import os as _os
        data_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), cfg.BODY_DATA_FILE)
        try:
            with open(data_path, "r", encoding="utf-8") as f:
                self._body_records = json.loads(f.read())
            self._body_records.sort(key=lambda r: r.get("date", ""))
        except (FileNotFoundError, json.JSONDecodeError):
            self._body_records = []

    def _save_body_records(self):
        import os as _os
        data_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), cfg.BODY_DATA_FILE)
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(self._body_records, f, ensure_ascii=False, indent=2)

    # ── Body Tracking: Calculation Helpers ────────────

    def _get_latest_weight(self):
        """Get the latest weight record, returns None if no records"""
        if not self._body_records:
            return None
        return self._body_records[-1]

    def _get_latest_weight_excluding(self, exclude_date):
        """Get the latest weight record excluding the specified date"""
        for r in reversed(self._body_records):
            if r.get("date") != exclude_date:
                return r
        return None

    def _calc_bmi(self):
        """Calculate BMI, returns None if height or weight missing"""
        if self._body_height <= 0:
            return None
        latest = self._get_latest_weight()
        if latest is None:
            return None
        h_m = self._body_height / 100.0
        return round(latest["weight"] / (h_m * h_m), 1)

    def _calc_progress(self):
        """Calculate goal completion percentage, returns None if no goal/start weight"""
        if self._body_start_weight <= 0 or self._body_target_weight <= 0:
            return None
        latest = self._get_latest_weight()
        if latest is None:
            return 0.0
        total = self._body_start_weight - self._body_target_weight
        if total <= 0:
            return 100.0
        done = self._body_start_weight - latest["weight"]
        return max(0.0, min(100.0, done / total * 100.0))

    # ── Body Tracking: Weight Recording & Feedback ────

    def _record_weight(self):
        """Pop up input dialog to record today's weight"""
        import datetime as _dt
        today = _dt.date.today().isoformat()
        existing = next((r for r in self._body_records if r.get("date") == today), None)
        default_val = str(existing["weight"]) if existing else ""

        text, ok = QInputDialog.getText(
            self, "Record Weight", "Enter today's weight (kg):\ne.g.: 72.5",
            text=default_val
        )
        if not ok or not text.strip():
            return
        try:
            new_weight = round(float(text.strip()), 1)
        except ValueError:
            self.say("Invalid format~\nPlease enter a number, e.g.: 72.5", 3.0)
            return

        prev_weight = self._get_latest_weight_excluding(today)
        prev_val = prev_weight["weight"] if prev_weight else None

        if existing:
            existing["weight"] = new_weight
        else:
            self._body_records.append({"date": today, "weight": new_weight})
        self._body_records.sort(key=lambda r: r.get("date", ""))

        if self._body_start_weight <= 0 and len(self._body_records) >= 1:
            self._body_start_weight = self._body_records[0]["weight"]
            self._save_body_settings()

        self._save_body_records()
        self._react_to_weight_change(new_weight, prev_val)

    def _react_to_weight_change(self, new_weight, prev_weight):
        """Give pet expression and bubble feedback based on weight change"""
        if prev_weight is None:
            self.say(f"Recorded~\nCurrent: {new_weight} kg\nFirst record, keep it up!", 4.0)
            return

        diff = new_weight - prev_weight
        abs_diff = abs(diff)

        if self._body_target_weight > 0 and new_weight <= self._body_target_weight:
            self._character.set_expression("surprised")
            self.say(
                f"Wow! Current: {new_weight} kg\n"
                f"{'Lighter' if diff < 0 else 'Heavier'} by {abs_diff:.1f} kg vs last time\n"
                "You reached your goal weight! Awesome!",
                6.0
            )
            QTimer.singleShot(6000, lambda: self._character.set_expression("idle"))
            return

        if diff < -0.3:
            self._character.set_expression("happy")
            if abs_diff >= 1.0:
                self.say(f"Weight dropped {abs_diff:.1f} kg!\nAmazing, keep it up!\nCurrent: {new_weight} kg", 5.0)
            else:
                self.say(f"Lighter by {abs_diff:.1f} kg~\nNice work!\nCurrent: {new_weight} kg", 4.0)
            QTimer.singleShot(4000, lambda: self._character.set_expression("idle"))
        elif diff > 0.3:
            self._character.set_expression("pout" if abs_diff < 1.0 else "sad")
            if abs_diff >= 1.0:
                self.say(f"Weight up by {abs_diff:.1f} kg...\nNo worries, keep going tomorrow!\nCurrent: {new_weight} kg", 5.0)
            else:
                self.say(f"Heavier by {abs_diff:.1f} kg~\nMaybe skip the late-night snack~\nCurrent: {new_weight} kg", 4.0)
            QTimer.singleShot(4000, lambda: self._character.set_expression("idle"))
        else:
            self._character.set_expression("idle")
            self.say(f"Weight is stable~\nCurrent: {new_weight} kg\nDoing great!", 4.0)

    # ── Body Tracking: Panel Display ──────────────────

    def _close_body_panel(self):
        if self._body_panel is not None:
            self._body_panel.close()
            self._body_panel.deleteLater()
            self._body_panel = None

    def _build_body_title_text(self):
        """Build panel title text (with BMI)"""
        import datetime as _dt
        bmi = self._calc_bmi()
        if bmi is None:
            bmi_str = "BMI: --"
        elif bmi < 18.5:
            bmi_str = f"BMI: {bmi} (Underweight)"
        elif bmi < 25:
            bmi_str = f"BMI: {bmi} (Normal)"
        elif bmi < 30:
            bmi_str = f"BMI: {bmi} (Overweight)"
        else:
            bmi_str = f"BMI: {bmi} (Obese)"
        records_count = len(self._body_records)
        return f"Body Tracking  |  {bmi_str}  |  {records_count} records"

    def _build_body_stats_widget(self):
        """Build today/yesterday comparison stats widget"""
        from PyQt5.QtWidgets import QLabel
        import datetime as _dt

        today_str = _dt.date.today().isoformat()
        latest = self._get_latest_weight()
        latest_weight = latest["weight"] if latest else None
        latest_date = latest["date"] if latest else None
        is_today = (latest_date == today_str)

        w = QLabel()
        w.setStyleSheet("border: none; color: #e0e0e0; font-size: 14px;")

        lines = []
        if latest_weight is None:
            lines.append("No weight records yet~\nClick the button below to record your first one!")
        elif is_today:
            lines.append(f"Today's weight: {latest_weight} kg")
            yesterday = self._get_latest_weight_excluding(today_str)
            if yesterday:
                yd = latest_weight - yesterday["weight"]
                arrow = "↓" if yd < 0 else ("↑" if yd > 0 else "→")
                lines.append(f"Yesterday: {yesterday['weight']} kg  {arrow}{abs(yd):.1f}")
        else:
            yesterday = self._get_latest_weight_excluding(today_str)
            if yesterday:
                yd = latest_weight - yesterday["weight"]
                arrow = "↓" if yd < 0 else ("↑" if yd > 0 else "→")
                lines.append(f"Latest: {latest_weight} kg ({latest_date})")
                lines.append(f"Previous: {yesterday['weight']} kg  {arrow}{abs(yd):.1f}")
            else:
                lines.append(f"Latest: {latest_weight} kg ({latest_date})")

        w.setText("\n".join(lines))
        return w

    def _build_body_progress_bar(self):
        """Build goal progress bar widget (custom QWidget drawing)"""
        from PyQt5.QtWidgets import QLabel

        progress = self._calc_progress()
        w = QLabel()
        w.setStyleSheet("border: none; color: #e0e0e0; font-size: 14px;")
        if progress is None:
            if self._body_start_weight <= 0:
                w.setText("Set a target weight to see progress")
            elif self._body_target_weight <= 0:
                w.setText("Set a target weight to see progress")
            else:
                w.setText("Record weight to see progress")
        else:
            start = self._body_start_weight
            target = self._body_target_weight
            current = self._get_latest_weight()["weight"]
            bar_len = 14
            filled = int(bar_len * progress / 100)
            bar = "█" * filled + "░" * (bar_len - filled)
            w.setText(
                f"Progress: {progress:.1f}%\n"
                f"{start} {bar} {target}\n"
                f"Lost {start - current:.1f} / Remaining {current - target:.1f} kg"
            )
        return w

    def _build_body_history_scroll(self, container_widget):
        """Build history scroll area, mount directly to container"""
        from PyQt5.QtWidgets import QScrollArea, QLabel, QVBoxLayout as _V, QWidget as _W
        import datetime as _dt

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(150)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #444; border-radius: 4px; background: #1e1e1e; }")

        inner = _W()
        inner.setStyleSheet("background: transparent; border: none;")
        inner_layout = _V(inner)
        inner_layout.setContentsMargins(6, 4, 6, 4)
        inner_layout.setSpacing(2)

        if not self._body_records:
            empty_label = QLabel("  No records yet")
            empty_label.setStyleSheet("border: none; color: #888; font-size: 13px;")
            inner_layout.addWidget(empty_label)
        else:
            today_str = _dt.date.today().isoformat()
            shown = 0
            for i in range(len(self._body_records) - 1, -1, -1):
                r = self._body_records[i]
                date_str = r.get("date", "")
                w = r.get("weight", 0)

                # Compare with previous day
                prev_r = self._body_records[i - 1] if i > 0 else None
                if prev_r:
                    chg = w - prev_r["weight"]
                    arrow = "↓" if chg < 0 else ("↑" if chg > 0 else "→")
                    line = f"  {date_str[-5:]}  {w:5.1f} kg  {arrow}{abs(chg):.1f}"
                else:
                    line = f"  {date_str[-5:]}  {w:5.1f} kg  ★First"

                label = QLabel(line)
                label.setStyleSheet("border: none; color: #ccc; font-size: 13px; font-family: Consolas, monospace;")
                inner_layout.addWidget(label)
                shown += 1
                if shown >= 14:
                    break

        inner_layout.addStretch()
        scroll.setWidget(inner)
        container_widget.layout().addWidget(scroll)

    def _show_body_panel(self):
        """Show body tracking panel (follows Todo panel pattern)"""
        from PyQt5.QtWidgets import (
            QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
        )

        self._body_panel_close_timer.stop()
        if self._body_panel is not None:
            self._body_panel.close()
            self._body_panel = None

        class _BodyPanel(QWidget):
            def __init__(self, parent_pet):
                super().__init__()
                self._pet = parent_pet
                self.setMouseTracking(True)

            def enterEvent(self, ev):
                self._pet._body_panel_close_timer.stop()

            def leaveEvent(self, ev):
                self._pet._body_panel_close_timer.start()

        panel = _BodyPanel(self)
        panel.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        panel.setAttribute(Qt.WA_ShowWithoutActivating)
        panel.setStyleSheet("""
            QWidget { background-color: #2b2b2b; color: #e0e0e0; border: 1px solid #555;
                      border-radius: 8px; font-size: 14px; }
            QPushButton { background-color: #3a3a3a; color: #e0e0e0; border: 1px solid #555;
                          padding: 4px 10px; border-radius: 3px; }
            QPushButton:hover { background-color: #505050; }
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Title
        title = QLabel(self._build_body_title_text())
        title.setStyleSheet("font-weight: bold; border: none; font-size: 15px; min-height: 24px;")
        layout.addWidget(title)

        # Today/Yesterday stats row
        stats = self._build_body_stats_widget()
        layout.addWidget(stats)

        # Progress bar
        progress = self._build_body_progress_bar()
        layout.addWidget(progress)

        # History area
        self._build_body_history_scroll(panel)

        # Button row
        btn_layout = QHBoxLayout()
        btn_record = QPushButton("Record Weight")
        btn_record.clicked.connect(self._record_weight)
        btn_target = QPushButton("Set Goal")
        btn_target.clicked.connect(self._show_body_target_dialog)
        btn_layout.addWidget(btn_record)
        btn_layout.addWidget(btn_target)
        layout.addLayout(btn_layout)

        panel.setLayout(layout)
        panel.adjustSize()
        panel.setMinimumWidth(cfg.BODY_PANEL_MIN_WIDTH)
        panel.move(self.mapToGlobal(QPoint(self.width() + 8, 0)))
        panel.show()
        self._body_panel = panel

    # ── Body Tracking: Settings Dialog ────────────────

    def _show_body_target_dialog(self):
        """Show body tracking target settings submenu (target weight/height/start weight)"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #2b2b2b; color: #e0e0e0; border: 1px solid #555; padding: 4px; }
            QMenu::item { padding: 6px 24px; border-radius: 3px; }
            QMenu::item:selected { background-color: #505050; }
        """)
        menu.addAction("Set Target Weight...").triggered.connect(lambda: self._set_body_target("weight"))
        menu.addAction("Set Height...").triggered.connect(lambda: self._set_body_target("height"))
        menu.addAction("Set Start Weight...").triggered.connect(lambda: self._set_body_target("start"))
        menu.exec_(self.mapToGlobal(QPoint(self.width() + 8, 0)))

    def _set_body_target(self, field):
        """Unified body tracking value setting entry"""
        labels = {
            "weight": ("Set Target Weight", "Enter target weight (kg):\ne.g.: 65.0"),
            "height": ("Set Height", "Enter height (cm):\ne.g.: 170"),
            "start": ("Set Start Weight", "Enter starting weight (kg):\ne.g.: 75.0"),
        }
        if field not in labels:
            return
        title, prompt = labels[field]
        defaults = {
            "weight": str(self._body_target_weight) if self._body_target_weight > 0 else "",
            "height": str(self._body_height) if self._body_height > 0 else "",
            "start": str(self._body_start_weight) if self._body_start_weight > 0 else "",
        }
        text, ok = QInputDialog.getText(self, title, prompt, text=defaults[field])
        if not ok or not text.strip():
            return
        try:
            val = round(float(text.strip()), 1)
            if val <= 0:
                self.say("Value must be greater than 0~", 2.0)
                return
        except ValueError:
            self.say("Invalid format~\nPlease enter a number", 3.0)
            return

        if field == "weight":
            self._body_target_weight = val
            self.say(f"Target weight set to {val} kg~\nYou can do it!", 4.0)
        elif field == "height":
            self._body_height = val
            bmi = self._calc_bmi()
            bmi_extra = f", current BMI: {bmi}" if bmi is not None else ""
            self.say(f"Height set to {val} cm{bmi_extra}~", 3.0)
        elif field == "start":
            self._body_start_weight = val
            self.say(f"Start weight set to {val} kg~\nProgress will be calculated from here!", 3.0)
        self._save_body_settings()

    # ── Body Tracking: Weigh-in Reminder ──────────────

    def _set_weigh_reminder_enabled(self, enabled):
        self._weigh_reminder_enabled = enabled
        if enabled:
            self._last_weigh_reminder_date = ""
            self._weigh_check_timer.start()
        else:
            self._weigh_check_timer.stop()
        self._save_body_settings()

    def _set_weigh_reminder_time(self, time_str):
        self._weigh_reminder_time = time_str
        self._last_weigh_reminder_date = ""
        self._save_body_settings()

    def _check_weigh_reminder(self):
        """Check every minute: whether current time matches reminder time and not yet reminded today"""
        if not self._weigh_reminder_enabled:
            return
        import datetime as _dt
        now = _dt.datetime.now()
        today = now.strftime("%Y-%m-%d")
        if self._last_weigh_reminder_date == today:
            return
        current_time = now.strftime("%H:%M")
        if current_time == self._weigh_reminder_time:
            self._on_weigh_reminder()

    def _on_weigh_reminder(self):
        """Weigh-in reminder triggered: check if already recorded today"""
        import datetime as _dt
        today = _dt.date.today().isoformat()
        has_record = any(r.get("date") == today for r in self._body_records)

        if has_record:
            self.say("Today's weight already recorded~\nKeep it up!", 3.0)
        else:
            # Calculate missed days
            days_missed = 0
            check_date = _dt.date.today() - _dt.timedelta(days=1)
            while days_missed < 30:
                found = any(r.get("date") == check_date.isoformat() for r in self._body_records)
                if found or not self._body_records:
                    break
                days_missed += 1
                check_date -= _dt.timedelta(days=1)

            if days_missed <= 0:
                self.say("Time to weigh in~\nSee what's changed today!", 5.0)
            elif days_missed <= 2:
                self._character.set_expression("sad")
                self.say(f"You haven't weighed in for {days_missed} days~\nDon't be lazy!", 5.0)
                QTimer.singleShot(4000, lambda: self._character.set_expression("idle"))
            else:
                self._character.set_expression("pout")
                self.say(f"No records for {days_missed} days!\nCome weigh in or I'll get mad!", 5.0)
                QTimer.singleShot(4000, lambda: self._character.set_expression("idle"))

        self._last_weigh_reminder_date = today
        self._save_body_settings()

    def _show_todo_panel(self):
        self._todo_close_timer.stop()
        if self._todo_panel is not None:
            self._todo_panel.close()
            self._todo_panel = None

        from PyQt5.QtWidgets import QVBoxLayout, QLabel, QCheckBox, QPushButton, QHBoxLayout, QScrollArea

        class _TodoPanel(QWidget):
            def __init__(self, parent_pet):
                super().__init__()
                self._pet = parent_pet
                self.setMouseTracking(True)

            def enterEvent(self, ev):
                self._pet._todo_close_timer.stop()

            def leaveEvent(self, ev):
                self._pet._todo_close_timer.start()

        panel = _TodoPanel(self)
        panel.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        panel.setAttribute(Qt.WA_ShowWithoutActivating)
        panel.setStyleSheet("""
            QWidget { background-color: #2b2b2b; color: #e0e0e0; border: 2px solid #555;
                      border-radius: 6px; font-size: 15px; }
            QCheckBox { color: #ddd; spacing: 8px; font-size: 15px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QPushButton { background: #444; border: 1px solid #666; padding: 4px 12px;
                          border-radius: 3px; color: #ddd; font-size: 15px; }
            QPushButton:hover { background: #666; }
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        title = QLabel(f"Todo ({self._pending_todo_count()})")
        title.setStyleSheet("font-weight: bold; border: none;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(200)
        scroll.setStyleSheet("border: 1px solid #444; background: #333;")
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("border: none; background: #333;")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(2)
        scroll_layout.setContentsMargins(4, 4, 4, 4)

        for i, item in enumerate(self._todo_items):
            row = QHBoxLayout()
            row.setSpacing(4)
            # Main text
            cb_text = item["text"]
            due = item.get("due_date", "")
            if due:
                try:
                    import datetime as _dt
                    d = _dt.datetime.strptime(due, "%Y-%m-%d").date()
                    delta = (d - _dt.date.today()).days
                    cb_text += f"  ({delta} days left)"
                except Exception:
                    pass
            cb = QCheckBox(cb_text)
            cb.blockSignals(True)
            cb.setChecked(item.get("done", False))
            cb.blockSignals(False)
            cb.toggled.connect(lambda checked, idx=i: self._toggle_todo(idx, checked))
            row.addWidget(cb, 1)
            btn_del = QPushButton("Delete")
            btn_del.setFixedSize(42, 24)
            btn_del.setStyleSheet(
                "QPushButton { background: #5a3030; border: 1px solid #774040;"
                " padding: 2px 6px; border-radius: 3px; color: #e0a0a0; font-size: 13px; }"
                "QPushButton:hover { background: #8b4040; color: #ffc0c0; }"
            )
            btn_del.clicked.connect(lambda checked, idx=i: self._delete_todo(idx))
            row.addWidget(btn_del)
            scroll_layout.addLayout(row)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # Clear completed button (only shown when there are completed items)
        done_count = sum(1 for t in self._todo_items if t.get("done", False))
        if done_count > 0:
            clear_row = QHBoxLayout()
            btn_clear = QPushButton(f"Clear Completed ({done_count})")
            btn_clear.setStyleSheet(
                "QPushButton { background: #444; border: 1px solid #666;"
                " padding: 5px 12px; border-radius: 3px; color: #aaa; font-size: 14px; }"
                "QPushButton:hover { background: #5a3030; color: #e0a0a0; border-color: #774040; }"
            )
            btn_clear.clicked.connect(self._clear_completed_todos)
            clear_row.addWidget(btn_clear)
            layout.addLayout(clear_row)

        add_row = QHBoxLayout()
        btn_add = QPushButton("+ New Todo...")
        btn_add.clicked.connect(self._add_todo_dialog)
        add_row.addWidget(btn_add)
        layout.addLayout(add_row)

        panel.setLayout(layout)
        panel.adjustSize()
        panel.setMinimumWidth(220)
        panel.move(self.mapToGlobal(QPoint(self.width() + 8, 0)))
        panel.show()
        self._todo_panel = panel

    def _add_todo_dialog(self):
        import datetime as _dt
        text, ok = QInputDialog.getText(self, "New Todo", "Enter todo item:")
        if ok and text.strip():
            self._todo_items.append({
                "text": text.strip(),
                "done": False,
                "date": _dt.date.today().isoformat(),
            })
            self._save_todos()
            self._show_todo_panel()

    def _toggle_todo(self, idx, checked):
        import datetime as _dt
        if 0 <= idx < len(self._todo_items):
            self._todo_items[idx]["done"] = checked
            if checked:
                self._todo_items[idx]["date"] = _dt.date.today().isoformat()
            self._save_todos()

    def _delete_todo(self, idx):
        """Delete a single todo item"""
        if 0 <= idx < len(self._todo_items):
            self._todo_items.pop(idx)
            self._save_todos()
            self._show_todo_panel()

    def _clear_completed_todos(self):
        """Batch clear all completed todos"""
        before = len(self._todo_items)
        self._todo_items = [t for t in self._todo_items if not t.get("done", False)]
        removed = before - len(self._todo_items)
        if removed > 0:
            self._save_todos()
            self._show_todo_panel()
            self.say(f"Cleared {removed} completed items~", 3.0)

    # ── AI Advanced Settings (Personality/History/Proactive Chat) ──

    def _load_ai_profile(self):
        """Load ai_settings.json, initialize with defaults if missing"""
        try:
            with open(cfg.AI_SETTINGS_FILE, "r", encoding="utf-8") as f:
                self._ai_profile = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        # Fill in missing fields
        self._ai_profile.setdefault("history_max", 5)
        self._ai_profile.setdefault("chat_history", [])
        self._ai_profile.setdefault("active_personality", "Energetic")
        if "personalities" not in self._ai_profile or not self._ai_profile["personalities"]:
            self._ai_profile["personalities"] = dict(cfg.DEFAULT_PERSONALITIES)
        # Ensure default personalities always exist
        for name, prompt in cfg.DEFAULT_PERSONALITIES.items():
            if name not in self._ai_profile["personalities"]:
                self._ai_profile["personalities"][name] = prompt
        self._ai_profile.setdefault("proactive_chat", False)
        self._ai_profile.setdefault("proactive_interval_min", cfg.PROACTIVE_CHAT_INTERVAL_MIN)
        self._ai_profile.setdefault("proactive_interval_max", cfg.PROACTIVE_CHAT_INTERVAL_MAX)
        self._ai_profile.setdefault("personality_expressions", {})
        # Ensure every personality has an expressions entry
        for name in self._ai_profile.get("personalities", {}):
            if name not in self._ai_profile["personality_expressions"]:
                self._ai_profile["personality_expressions"][name] = []

    def _save_ai_profile(self):
        """Save ai_settings.json"""
        with open(cfg.AI_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._ai_profile, f, ensure_ascii=False, indent=2)

    def _show_ai_profile_dialog(self):
        """AI advanced settings dialog — role switching / preset editing / conversation memory"""
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
            QPushButton, QComboBox, QSpinBox, QListWidget,
            QTextEdit, QMessageBox, QCheckBox, QScrollArea,
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("AI Advanced Settings")
        dlg.setWindowFlags(dlg.windowFlags() | Qt.Tool)
        dlg.setFixedSize(480, 620)
        dlg.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: #e0e0e0; border: 2px solid #555; }
            QLabel { color: #ccc; font-size: 14px; }
            QLineEdit, QComboBox, QSpinBox { background-color: #3a3a3a; color: #e0e0e0;
                border: 1px solid #666; padding: 4px 8px; font-size: 14px; border-radius: 3px; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #3a3a3a; color: #e0e0e0;
                selection-background-color: #505050; }
            QListWidget { background-color: #3a3a3a; color: #e0e0e0; border: 1px solid #666;
                border-radius: 3px; font-size: 14px; }
            QListWidget::item:selected { background-color: #505050; }
            QTextEdit { background-color: #3a3a3a; color: #e0e0e0; border: 1px solid #666;
                border-radius: 3px; font-size: 14px; }
            QPushButton { background-color: #505050; color: #e0e0e0; border: 1px solid #666;
                padding: 5px 14px; font-size: 14px; border-radius: 3px; }
            QPushButton:hover { background-color: #666; }
            QSpinBox { padding-right: 4px; }
        """)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)

        # ── Personality Switch ──
        layout.addWidget(QLabel("Personality:"))
        cmb_personality = QComboBox()
        cmb_personality.addItems(list(self._ai_profile["personalities"].keys()))
        current_personality = self._ai_profile.get("active_personality", "Energetic")
        cmb_personality.setCurrentText(current_personality)
        layout.addWidget(cmb_personality)

        # ── Preset Prompt Editing ──
        layout.addWidget(QLabel("Preset Prompt (edit after selecting personality):"))
        list_row = QHBoxLayout()
        lst_presets = QListWidget()
        lst_presets.setFixedWidth(100)
        lst_presets.addItems(list(self._ai_profile["personalities"].keys()))
        lst_presets.setCurrentRow(cmb_personality.currentIndex())
        list_row.addWidget(lst_presets)

        edit_prompt = QTextEdit()
        edit_prompt.setAcceptRichText(False)
        list_row.addWidget(edit_prompt)
        layout.addLayout(list_row)

        # Sync selected personality's prompt to editor
        def _load_preset_to_editor(name):
            prompt = self._ai_profile["personalities"].get(name, "")
            edit_prompt.setPlainText(prompt)

        _load_preset_to_editor(current_personality)

        lst_presets.currentTextChanged.connect(_load_preset_to_editor)

        # Add/Delete preset buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        def _add_preset():
            name, ok = QInputDialog.getText(dlg, "New Personality", "Enter new personality name:")
            if ok and name.strip():
                name = name.strip()
                if name in self._ai_profile["personalities"]:
                    QMessageBox.warning(dlg, "Duplicate", f"Personality \"{name}\" already exists.")
                    return
                self._ai_profile["personalities"][name] = "Edit your custom prompt here…"
                self._ai_profile.setdefault("personality_expressions", {})[name] = []
                lst_presets.addItem(name)
                cmb_personality.addItem(name)
                cmb_personality.setCurrentText(name)
                lst_presets.setCurrentRow(lst_presets.count() - 1)

        def _del_preset():
            name = lst_presets.currentItem().text() if lst_presets.currentItem() else ""
            if not name:
                return
            if name in cfg.DEFAULT_PERSONALITIES:
                QMessageBox.warning(dlg, "Protected", f"\"{name}\" is a system preset personality and cannot be deleted.")
                return
            reply = QMessageBox.question(dlg, "Confirm Delete", f"Are you sure you want to delete personality \"{name}\"?")
            if reply == QMessageBox.Yes:
                del self._ai_profile["personalities"][name]
                self._ai_profile.get("personality_expressions", {}).pop(name, None)
                row = lst_presets.currentRow()
                lst_presets.takeItem(row)
                idx = cmb_personality.findText(name)
                if idx >= 0:
                    cmb_personality.removeItem(idx)
                cmb_personality.setCurrentIndex(0)
                if lst_presets.count() > 0:
                    lst_presets.setCurrentRow(0)

        btn_add = QPushButton("+ New Personality")
        btn_add.clicked.connect(_add_preset)
        btn_row.addWidget(btn_add)

        btn_del = QPushButton("- Delete Current")
        btn_del.clicked.connect(_del_preset)
        btn_row.addWidget(btn_del)
        layout.addLayout(btn_row)

        # ── Chat Memory ──
        layout.addWidget(QLabel("Chat memory rounds (1-20):"))
        history_row = QHBoxLayout()
        spn_history = QSpinBox()
        spn_history.setRange(1, cfg.HISTORY_MAX_LIMIT)
        spn_history.setValue(self._ai_profile.get("history_max", 5))
        history_row.addWidget(spn_history)
        history_row.addStretch()

        btn_clear = QPushButton("Clear Chat History")
        btn_clear.clicked.connect(lambda: (
            self._ai_profile.update({"chat_history": []}),
            self._save_ai_profile(),
            self.say("Chat history cleared~", 2.0)
        ))
        history_row.addWidget(btn_clear)
        layout.addLayout(history_row)

        # ── Linked Expressions (randomly shown on AI reply) ──
        layout.addWidget(QLabel("Linked expressions (randomly shown on AI reply, 0-5):"))
        all_expr_names = self._character.expression_manager.get_names()
        expr_checkboxes: dict[str, QCheckBox] = {}

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(90)
        scroll_widget = QWidget()
        expr_grid = QVBoxLayout(scroll_widget)
        expr_grid.setSpacing(2)
        expr_grid.setContentsMargins(2, 2, 2, 2)

        def _build_expr_checkboxes():
            """Rebuild CheckBox layout (6 per row)"""
            # Clear old widgets
            while expr_grid.count():
                item = expr_grid.takeAt(0)
                if item.layout():
                    while item.layout().count():
                        child = item.layout().takeAt(0)
                        if child.widget():
                            child.widget().deleteLater()
                    item.layout().deleteLater()
            expr_checkboxes.clear()

            active = cmb_personality.currentText()
            linked = self._ai_profile.get("personality_expressions", {}).get(active, [])
            row_layout = None
            for i, ename in enumerate(all_expr_names):
                if i % 6 == 0:
                    row_layout = QHBoxLayout()
                    row_layout.setSpacing(2)
                    expr_grid.addLayout(row_layout)
                cb = QCheckBox(ename)
                cb.setChecked(ename in linked)
                cb.toggled.connect(lambda checked, n=ename: _on_expr_toggle(n, checked))
                expr_checkboxes[ename] = cb
                row_layout.addWidget(cb)
            if row_layout is not None:
                row_layout.addStretch()

        def _on_expr_toggle(name, checked):
            """Ensure at most 5 are checked"""
            active = cmb_personality.currentText()
            if checked:
                linked = self._ai_profile.setdefault("personality_expressions", {}).setdefault(active, [])
                if name not in linked:
                    if len(linked) >= 5:
                        cb = expr_checkboxes[name]
                        cb.blockSignals(True)
                        cb.setChecked(False)
                        cb.blockSignals(False)
                        return
                    linked.append(name)
            else:
                linked = self._ai_profile.get("personality_expressions", {}).get(active, [])
                if name in linked:
                    linked.remove(name)

        _build_expr_checkboxes()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # Sync checkboxes when switching personality
        def _sync_expr_checkboxes(name):
            for ename, cb in expr_checkboxes.items():
                linked = self._ai_profile.get("personality_expressions", {}).get(name, [])
                cb.blockSignals(True)
                cb.setChecked(ename in linked)
                cb.blockSignals(False)

        lst_presets.currentTextChanged.connect(lambda n: _sync_expr_checkboxes(n))

        layout.addStretch()

        # ── OK/Cancel ──
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()

        def _on_ok():
            # Save currently edited prompt
            cur_name = lst_presets.currentItem().text() if lst_presets.currentItem() else ""
            if cur_name:
                self._ai_profile["personalities"][cur_name] = edit_prompt.toPlainText()
            # Save other settings
            new_personality = cmb_personality.currentText()
            old_personality = self._ai_profile.get("active_personality", "")
            self._ai_profile["active_personality"] = new_personality
            self._ai_profile["history_max"] = spn_history.value()
            # Save expression associations (already written to personality_expressions in real-time via toggle signals)
            self._save_ai_profile()
            # Clear history when switching personality (avoid old personality tone contamination)
            if new_personality != old_personality:
                self._ai_profile["chat_history"] = []
                self._save_ai_profile()
            dlg.accept()
            self.say(f"AI settings saved~\nCurrent personality: {new_personality}", 3.0)

        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(_on_ok)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(dlg.reject)
        bottom_row.addWidget(btn_ok)
        bottom_row.addWidget(btn_cancel)
        layout.addLayout(bottom_row)

        dlg.move(self.mapToGlobal(QPoint(self.width() + 8, 0)))
        dlg.exec_()

    # ── Proactive Chat System ─────────────────────────

    def _start_proactive_timer(self):
        """Start proactive chat timer (single shot, rescheduled after each trigger)"""
        if not self._ai_profile.get("proactive_chat", False):
            return
        if self._proactive_timer is None:
            self._proactive_timer = QTimer(self)
            self._proactive_timer.setSingleShot(True)
            self._proactive_timer.timeout.connect(self._on_proactive_tick)
        self._schedule_proactive()

    def _stop_proactive_timer(self):
        if self._proactive_timer is not None:
            self._proactive_timer.stop()

    def _schedule_proactive(self):
        """Trigger next proactive chat after random interval"""
        if not self._ai_profile.get("proactive_chat", False):
            return
        min_interval = self._ai_profile.get("proactive_interval_min", cfg.PROACTIVE_CHAT_INTERVAL_MIN)
        max_interval = self._ai_profile.get("proactive_interval_max", cfg.PROACTIVE_CHAT_INTERVAL_MAX)
        mins = random.randint(min_interval, max_interval)
        self._proactive_timer.start(mins * 60 * 1000)

    def _set_custom_proactive_interval(self):
        """Custom proactive chat interval (minutes)"""
        cur_min = self._ai_profile.get("proactive_interval_min", cfg.PROACTIVE_CHAT_INTERVAL_MIN)
        cur_max = self._ai_profile.get("proactive_interval_max", cfg.PROACTIVE_CHAT_INTERVAL_MAX)
        text, ok = QInputDialog.getText(
            self, "Custom Proactive Chat Interval",
            "Enter interval range (minutes), format: min-max\ne.g. 10-30 means random 10~30 min between chats",
            text=f"{cur_min}-{cur_max}"
        )
        if ok and text.strip():
            parts = text.strip().split("-")
            if len(parts) == 2:
                try:
                    a = int(parts[0].strip())
                    b = int(parts[1].strip())
                    if a < 1:
                        a = 1
                    if b < a:
                        b = a
                    self._ai_profile.update({"proactive_chat": True, "proactive_interval_min": a, "proactive_interval_max": b})
                    self._save_ai_profile()
                    self._start_proactive_timer()
                    self.say(f"Proactive chat interval set to {a}-{b} min~", 2.0)
                except ValueError:
                    self.say("Wrong format~\nUse min-max format, e.g. 10-30", 3.0)

    def _on_proactive_tick(self):
        """Proactive chat: generate topic based on time+weather → call AI → bubble"""
        if self._game_mode.is_active():
            self._schedule_proactive()
            return
        if not self._ai_profile.get("proactive_chat", False):
            return
        if not self._has_ai_config():
            self._schedule_proactive()
            return
        prompt = self._build_proactive_prompt()
        if prompt:
            self._call_ai_api(prompt, save_to_history=False)
        self._schedule_proactive()

    def _build_proactive_prompt(self) -> str:
        """Generate proactive chat prompt based on time period and weather"""
        import datetime as _dt
        now = _dt.datetime.now()
        hour = now.hour
        weather = self._cached_weather
        weather_hint = f", weather {weather}" if weather else ""

        if 22 <= hour or hour < 6:
            topics = [
                "Remind the owner in a gentle, coaxing tone to rest early",
                "Yawn and ask why the owner isn't sleeping yet",
                "Say it's late, time to put down the phone",
            ]
        elif 6 <= hour < 9:
            topics = [
                "Cheerfully say good morning, encourage the owner to start a new day",
                "Ask how the owner slept last night",
                "Remind the owner to have breakfast",
            ]
        elif 9 <= hour < 12:
            topics = [
                "Ask what the owner is busy with, cheer them on",
                "Remind the owner to get up and stretch",
                "Say how fast the morning has gone by",
            ]
        elif 12 <= hour < 14:
            topics = [
                "Ask what the owner had for lunch",
                "Remind the owner to take a nap",
                "Say feeling sleepy after a full lunch",
            ]
        elif 14 <= hour < 18:
            topics = [
                "Cheer the owner on, keep working hard in the afternoon",
                "Remind the owner to drink some water",
                "Ask if work is going well today",
            ]
        elif 18 <= hour < 22:
            topics = [
                "Ask what delicious food the owner had for dinner",
                "Say the owner worked hard, time to relax",
                "Chat about evening plans",
            ]
        else:
            topics = ["Just chat casually with the owner"]

        topic = random.choice(topics)
        return (
            f"It's now {now.strftime('%H:%M')}{weather_hint}."
            f"Proactively {topic}. Say one natural sentence like a friend, don't read prefixes or sound like a manual."
        )

    # ── AI Chat ────────────────────────────────────────

    # Sensitive word filter list (rejects API call on match)
    _SENSITIVE_PATTERNS = [
        r'炸弹', r'枪支', r'毒品', r'自杀', r'杀人',
        r'色情', r'裸体', r'性爱', r'强奸',
        r'政治', r'革命', r'暴动', r'颠覆',
        r'黑客', r'破解', r'病毒', r'木马',
        r'洗钱', r'赌博', r'诈骗',
    ]

    def _filter_sensitive(self, text: str) -> bool:
        """Sensitive word filter, returns True if matched (rejected)"""
        import re
        for pattern in self._SENSITIVE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _load_ai_settings(self):
        """Load AI config from QSettings, auto-decrypt encrypted fields"""
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        raw_key = s.value("ai/api_key", "", type=str)
        self._ai_config = {
            "api_url": s.value("ai/api_url", "", type=str),
            "api_key": decrypt_value(raw_key),
            "model": s.value("ai/model", "deepseek-chat", type=str),
        }

    def _save_ai_settings(self):
        """Save AI config to QSettings, auto-encrypt sensitive fields"""
        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        for k, v in self._ai_config.items():
            if k == "api_key" and v:
                s.setValue(f"ai/{k}", encrypt_value(v))
            else:
                s.setValue(f"ai/{k}", v)
        s.sync()

    def _has_ai_config(self) -> bool:
        """Check if AI is configured (has URL and Key)"""
        return bool(self._ai_config.get("api_url") and self._ai_config.get("api_key"))

    def _show_ai_config_dialog(self):
        """AI configuration dialog"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout

        dlg = QDialog(self)
        dlg.setWindowTitle("AI Chat Configuration")
        dlg.setWindowFlags(dlg.windowFlags() | Qt.Tool)
        dlg.setFixedSize(400, 280)
        dlg.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: #e0e0e0; border: 2px solid #555; }
            QLabel { color: #ccc; font-size: 14px; }
            QLineEdit { background-color: #3a3a3a; color: #e0e0e0; border: 1px solid #666;
                        padding: 5px 8px; font-size: 15px; border-radius: 3px; }
            QLineEdit:focus { border-color: #ffc800; }
            QPushButton { background-color: #505050; color: #e0e0e0; border: 1px solid #666;
                          padding: 5px 16px; font-size: 14px; border-radius: 3px; }
            QPushButton:hover { background-color: #666; }
        """)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(8)

        # Security warning
        warn = QLabel("API Key will be saved encrypted (AES-128 machine-bound), decryptable only on this machine")
        warn.setStyleSheet("color: #ffc800; font-size: 13px; padding: 4px 8px;"
                           "background-color: #3a3020; border-radius: 3px;")
        warn.setWordWrap(True)
        layout.addWidget(warn)

        layout.addWidget(QLabel("API URL:"))
        edit_url = QLineEdit(self._ai_config.get("api_url", "https://api.deepseek.com/v1/chat/completions"))
        edit_url.setPlaceholderText("https://api.deepseek.com/v1/chat/completions")
        layout.addWidget(edit_url)

        layout.addWidget(QLabel("API Key:"))
        edit_key = QLineEdit(self._ai_config.get("api_key", ""))
        edit_key.setEchoMode(QLineEdit.Password)
        edit_key.setPlaceholderText("sk-...")
        layout.addWidget(edit_key)

        layout.addWidget(QLabel("Model name:"))
        edit_model = QLineEdit(self._ai_config.get("model", "deepseek-chat"))
        edit_model.setPlaceholderText("deepseek-chat")
        layout.addWidget(edit_model)

        btn_layout = QHBoxLayout()
        btn_test = QPushButton("Test Connection")
        btn_test.setStyleSheet(
            "QPushButton { background-color: #3a5030; border-color: #668; }"
            "QPushButton:hover { background-color: #4a6040; }"
        )
        btn_ok = QPushButton("OK")
        btn_cancel = QPushButton("Cancel")
        btn_layout.addWidget(btn_test)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        def on_test():
            url = edit_url.text().strip()
            key = edit_key.text().strip()
            model = edit_model.text().strip()
            if not url or not key:
                self.say("Please enter API URL and Key first~", 3.0)
                return
            self.say("Testing connection...", 2.0)
            self._call_ai_api_test(url, key, model)

        def on_ok():
            self._ai_config["api_url"] = edit_url.text().strip()
            self._ai_config["api_key"] = edit_key.text().strip()
            self._ai_config["model"] = edit_model.text().strip() or "deepseek-chat"
            self._save_ai_settings()
            dlg.accept()
            self.say("AI config saved~ Double-click menu to ask me!", 4.0)

        btn_test.clicked.connect(on_test)
        btn_ok.clicked.connect(on_ok)
        btn_cancel.clicked.connect(dlg.reject)

        dlg.move(self.mapToGlobal(QPoint(self.width() + 8, 0)))
        dlg.exec_()

    def _delete_ai_config(self):
        """Completely delete AI config (securely delete credentials)"""
        reply = QMessageBox.warning(
            self, "Delete AI Config",
            "Are you sure you want to delete all AI configuration?\n"
            "API Key and credentials will be permanently removed from local files. This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        s = QSettings(cfg.SETTINGS_PATH, QSettings.IniFormat)
        s.remove("ai/api_url")
        s.remove("ai/api_key")
        s.remove("ai/model")
        s.sync()
        self._ai_config = {"api_url": "", "api_key": "", "model": "deepseek-chat"}
        self.say("API config permanently deleted~", 3.0)

    def _ask_ai(self):
        """Open persistent chat dialog — input stays, closes only on cancel"""
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton,
        )
        from PyQt5.QtGui import QTextCursor

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Chat with {self._pet_name}")
        dlg.setWindowFlags(
            (Qt.Dialog | Qt.WindowStaysOnTopHint) & ~Qt.WindowContextHelpButtonHint
        )
        dlg.setMinimumSize(360, 400)
        dlg.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: #e0e0e0; border: 2px solid #555; }
            QTextEdit { background-color: #1e1e1e; color: #e0e0e0; border: 1px solid #555;
                        font-size: 15px; padding: 8px; border-radius: 4px; }
            QLineEdit { background-color: #3a3a3a; color: #e0e0e0; border: 1px solid #666;
                        padding: 6px 10px; font-size: 15px; border-radius: 4px; }
            QLineEdit:focus { border-color: #ffc800; }
            QPushButton { background-color: #505050; color: #e0e0e0; border: 1px solid #666;
                          padding: 6px 16px; font-size: 14px; border-radius: 3px; }
            QPushButton:hover { background-color: #666; }
        """)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(8)

        # Chat display area
        chat_display = QTextEdit()
        chat_display.setReadOnly(True)
        # Initially load existing history
        for msg in self._ai_profile.get("chat_history", []):
            prefix = f"{self._user_title}: " if msg["role"] == "user" else f"{self._pet_name}: "
            chat_display.append(f"{prefix}{msg['content']}")
        layout.addWidget(chat_display, stretch=1)

        # Input row
        input_row = QHBoxLayout()
        input_field = QLineEdit()
        input_field.setPlaceholderText("Enter a message, press Enter to send...")
        btn_send = QPushButton("Send")
        btn_send.setDefault(True)  # Enter key triggers send, not close dialog
        input_row.addWidget(input_field)
        input_row.addWidget(btn_send)
        layout.addLayout(input_row)

        # Bottom button row
        bottom_row = QHBoxLayout()
        btn_clear_hist = QPushButton("Clear History")
        btn_clear_hist.setAutoDefault(False)
        btn_clear_hist.clicked.connect(lambda: (
            self._ai_profile.update({"chat_history": []}),
            self._save_ai_profile(),
            chat_display.clear(),
        ))
        bottom_row.addWidget(btn_clear_hist)
        bottom_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setAutoDefault(False)  # Prevent stealing Enter key
        btn_close.setFixedWidth(80)
        bottom_row.addWidget(btn_close)
        layout.addLayout(bottom_row)

        waiting = [False]  # mutable for closure

        def _do_send():
            msg = input_field.text().strip()
            if not msg or waiting[0]:
                return
            if self._filter_sensitive(msg):
                chat_display.append(f"{self._pet_name}: Hehe, I don't know how to talk about that~")
                chat_display.append("")
                return

            input_field.clear()
            input_field.setEnabled(False)
            btn_send.setEnabled(False)
            waiting[0] = True
            chat_display.append(f"{self._user_title}：{msg}")
            chat_display.append("")
            # Thinking indicator (gray, cleared by rebuilding display on reply)
            cursor = chat_display.textCursor()
            cursor.movePosition(QTextCursor.End)
            fmt = cursor.charFormat()
            fmt.setForeground(QColor("#888888"))
            cursor.setCharFormat(fmt)
            cursor.insertText(f"  ⏳ {self._pet_name} is thinking...")
            fmt.setForeground(QColor("#e0e0e0"))
            cursor.setCharFormat(fmt)
            # Scroll to bottom
            scrollbar = chat_display.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

            def _on_reply(text):
                # Rebuild display from updated history (thinking indicator naturally disappears)
                chat_display.clear()
                for m in self._ai_profile.get("chat_history", []):
                    prefix = f"{self._user_title}: " if m["role"] == "user" else f"{self._pet_name}: "
                    chat_display.append(f"{prefix}{m['content']}")
                scrollbar = chat_display.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())
                input_field.setEnabled(True)
                btn_send.setEnabled(True)
                input_field.setFocus()
                waiting[0] = False

            self._chat_reply_callback = _on_reply
            self._call_ai_api(msg)

        input_field.returnPressed.connect(_do_send)
        btn_send.clicked.connect(_do_send)
        btn_close.clicked.connect(dlg.reject)

        # Position: don't block the pet
        dlg.move(self.mapToGlobal(QPoint(self.width() + 16, -20)))
        dlg.show()
        input_field.setFocus()
        dlg.exec_()

        # Cleanup
        self._chat_reply_callback = None

    def _get_env_context(self) -> str:
        """Build current environment context — date/time/weather, for AI to perceive the real world"""
        import datetime as _dt
        now = _dt.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        weekday = weekdays[now.weekday()]
        time_str = now.strftime("%H:%M")
        hour = now.hour
        if 6 <= hour < 12:
            period = "morning"
        elif 12 <= hour < 18:
            period = "afternoon"
        elif 18 <= hour < 22:
            period = "evening"
        else:
            period = "night"
        parts = [f"It's now {date_str} {weekday} {time_str} ({period})"]
        if self._cached_weather:
            parts.append(f"Weather: {self._cached_weather}")
        return ", ".join(parts) + "."

    def _get_personality_prompt(self) -> str:
        """Get current personality prompt, inject dynamic names"""
        name = self._ai_profile.get("active_personality", "Energetic")
        template = self._ai_profile.get("personalities", {}).get(
            name, cfg.DEFAULT_PERSONALITIES.get("Energetic", "")
        )
        return template.replace("{pet_name}", self._pet_name).replace("{user_title}", self._user_title)

    def _build_system_prompt(self) -> str:
        """Build system prompt — personality preset + behavior constraints + environment context"""
        personality = self._get_personality_prompt()
        env = self._get_env_context()
        return (
            f'{personality}\n'
            f'\n'
            f'HARD RULE: You are too small, the bubble can\'t hold long sentences — keep each reply strictly under 50 characters (punctuation counts). '
            f'Better one word less than one word more.\n'
            f'\n'
            f'You are good at: daily greetings, cheering up {self._user_title}, listening to complaints, sharing happy little things, casual chat, answering simple daily questions.\n'
            f'You avoid: overly professional/academic questions, complex reasoning, politics, violence, adult content and other sensitive topics. '
            f'When faced with these, tilt your head and play dumb, use different cute ways to brush them off.\n'
            f'\n'
            f'Now {self._user_title} is tapping your window, respond naturally, don\'t read rules, don\'t act like a manual.\n'
            f'\n'
            f'{env}'
        )

    def _call_ai_api(self, prompt: str, save_to_history: bool = True):
        """Worker thread calls AI API, result sent back to main thread via _ai_ready signal"""
        url = self._ai_config.get("api_url", "")
        key = self._ai_config.get("api_key", "")
        model = self._ai_config.get("model", "deepseek-chat")
        self._last_ai_prompt = prompt
        self._save_last_to_history = save_to_history

        def _fetch():
            import json as _json
            try:
                system_prompt = self._build_system_prompt()
                messages = [{"role": "system", "content": system_prompt}]
                # Inject chat history (only for user-initiated conversations)
                if save_to_history:
                    history = self._ai_profile.get("chat_history", [])
                    max_msgs = self._ai_profile.get("history_max", 5) * 2
                    messages.extend(history[-max_msgs:])
                messages.append({"role": "user", "content": prompt})

                body = _json.dumps({
                    "model": model,
                    "messages": messages,
                    "max_tokens": 50,
                    "temperature": 0.9,
                }).encode("utf-8")

                req = urllib.request.Request(url, data=body, headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}",
                })
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = _json.loads(resp.read().decode("utf-8"))
                    reply = data["choices"][0]["message"]["content"].strip()
                    # Safety net: if model still returns too long, truncate
                    if len(reply) > 120:
                        reply = reply[:117] + "..."
                    self._ai_ready.emit(reply)

            except urllib.error.HTTPError as e:
                code = e.code
                if code == 401:
                    self._ai_ready.emit("[401] API Key verification failed, please check in AI settings~")
                elif code == 404:
                    self._ai_ready.emit("[404] Model name might be wrong, try changing it in AI settings?")
                elif code == 429:
                    self._ai_ready.emit("[429] Hey, rate limited... wait a bit and try again~")
                elif code in (402, 403):
                    self._ai_ready.emit(f"[{code}] API quota insufficient or no permission~")
                else:
                    self._ai_ready.emit(f"[{code}] Server has a small issue, try again later?")
            except urllib.error.URLError:
                self._ai_ready.emit("[Timeout/Network] AI is a bit slow, timed out... try again?")
            except Exception as ex:
                self._ai_ready.emit(f"[Exception] Something unexpected: {ex}")

        threading.Thread(target=_fetch, daemon=True).start()

    def _call_ai_api_test(self, url: str, key: str, model: str):
        """Test connection: send a "hello" to verify API works"""
        def _fetch():
            import json as _json
            try:
                body = _json.dumps({
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Reply briefly in one sentence, no more than 20 characters."},
                        {"role": "user", "content": "Hello"},
                    ],
                    "max_tokens": 30,
                    "temperature": 0.7,
                }).encode("utf-8")

                req = urllib.request.Request(url, data=body, headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}",
                })
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = _json.loads(resp.read().decode("utf-8"))
                    reply = data["choices"][0]["message"]["content"].strip()
                    self._ai_ready.emit(f"[Test Success] {reply}")

            except urllib.error.HTTPError as e:
                if e.code == 401:
                    self._ai_ready.emit("[401] API Key verification failed, please check~")
                else:
                    self._ai_ready.emit(f"[{e.code}] Connection failed, please check config~")
            except urllib.error.URLError:
                self._ai_ready.emit("[Network] Cannot connect to API URL~")
            except Exception as ex:
                self._ai_ready.emit(f"[Exception] {ex}")

        threading.Thread(target=_fetch, daemon=True).start()

    def _apply_ai_expression(self):
        """Randomly pick a linked expression from current personality, show for 5s then revert to idle"""
        if self._ai_expr_timer is not None:
            self._ai_expr_timer.stop()
            self._ai_expr_timer = None

        personality_name = self._ai_profile.get("active_personality", "Energetic")
        linked = self._ai_profile.get("personality_expressions", {}).get(personality_name, [])
        if not linked:
            return

        expr = random.choice(linked)
        self._character.set_expression(expr)

        duration_ms = 5000
        self._ai_expr_timer = QTimer(self)
        self._ai_expr_timer.setSingleShot(True)
        self._ai_expr_timer.timeout.connect(lambda: self._character.set_expression("idle"))
        self._ai_expr_timer.start(duration_ms)

    def _on_ai_ready(self, text: str):
        """Main thread receives AI reply — route to dialog if open, otherwise bubble display"""
        is_error = text.startswith("[") and "]" in text[:10]
        is_test = text.startswith("[Test Success]")

        # AI expression linkage: randomly show linked expression on non-error/test messages
        if not is_error and not is_test:
            self._apply_ai_expression()

        # Write to history on user-initiated conversations (skip error/test messages)
        if self._save_last_to_history and self._last_ai_prompt and not is_error and not is_test:
            history = self._ai_profile.setdefault("chat_history", [])
            history.append({"role": "user", "content": self._last_ai_prompt})
            history.append({"role": "assistant", "content": text})
            max_msgs = self._ai_profile.get("history_max", 5) * 2
            if len(history) > max_msgs:
                self._ai_profile["chat_history"] = history[-max_msgs:]
            self._save_ai_profile()
            self._last_ai_prompt = ""

        # When chat dialog is active, route to both dialog and bubble
        if self._chat_reply_callback is not None:
            cb = self._chat_reply_callback
            self._chat_reply_callback = None
            cb(text)
            # Also show bubble when dialog is open, visible above character
            if not is_error and not is_test:
                self.say(text, 7.0)
            elif is_test:
                self.say(text, 6.0)
            elif is_error:
                self.say(text, 5.0)
            return

        # Otherwise just show bubble
        if is_test:
            self.say(text, 6.0)
        elif is_error:
            self.say(text, 5.0)
        else:
            self.say(text, 7.0)

    # ── Weather Fetch (background thread, avoid UI blocking) ──

    def _refresh_weather_cache(self):
        """Silently refresh weather cache (for AI context, failure doesn't affect existing cache)"""
        def _on_result(text):
            pass  # Cache already updated in _on_weather_ready
        self._get_weather_text(_on_result)

    def _get_weather_text(self, callback):
        """Fetch weather in a thread, safely deliver callback to main thread via pyqtSignal"""
        self._weather_callback = callback

        def _fetch():
            try:
                if self._city:
                    url = f"https://wttr.in/{quote(self._city)}?format=%l:+%C+%t&lang=zh"
                else:
                    url = "https://wttr.in?format=%l:+%C+%t&lang=zh"
                req = urllib.request.Request(url, headers={"User-Agent": "curl"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    result = resp.read().decode("utf-8").strip()
                    result = result.replace("+", " ")
                    # wttr.in may return °C or °F based on GeoIP, convert Fahrenheit to Celsius
                    result = self._normalize_temperature(result)
                    self._weather_ready.emit(result)
            except Exception:
                self._weather_ready.emit("")
        threading.Thread(target=_fetch, daemon=True).start()

    @staticmethod
    def _normalize_temperature(text):
        """wttr.in may return Fahrenheit (°F) based on GeoIP, detect and convert to Celsius"""
        import re
        match_f = re.search(r'([+-]?\d+)\s*°?\s*F', text)
        if match_f:
            f = float(match_f.group(1))
            c = round((f - 32) * 5 / 9)
            text = re.sub(r'[+-]?\d+\s*°?\s*F', f'{c}°C', text)
        return text

    def _on_weather_ready(self, text):
        """Main thread receives weather result, safely calls business callback"""
        if text:
            self._cached_weather = text  # Cache for AI context use
        if self._weather_callback:
            self._weather_callback(text)
            self._weather_callback = None

    # ── Reminder Response ──────────────────────────────

    def _on_drink_reminder(self):
        if self._game_mode.is_active():
            return
        self._character.set_expression("drink")
        self.say("Time to drink some water~\n(Right-click to postpone)", 6.0)
        QTimer.singleShot(5000, lambda: self._character.set_expression("idle"))

    def _on_eye_rest_reminder(self):
        if self._game_mode.is_active():
            return
        self._character.set_expression("eye_mask")
        self._eye_rest_overlay = True
        self.say("Look into the distance, blink your eyes~\n(20-20-20 rule)", 6.0)
        QTimer.singleShot(6000, lambda: self._character.set_expression("idle"))
        QTimer.singleShot(6000, lambda: setattr(self, '_eye_rest_overlay', False))

    # ── Hover Detection ───────────────────────────────

    def enterEvent(self, event):
        if not self._mouse_pressed:
            self._hover_timer.start()
        if self._body_panel is not None:
            self._body_panel_close_timer.stop()

    def leaveEvent(self, event):
        self._hover_timer.stop()
        self._todo_close_timer.start()
        if self._body_panel is not None:
            self._body_panel_close_timer.start()

    # ── Public Interface ──────────────────────────────

    def set_expression(self, name):
        self._set_expression(name)

    def say(self, text, duration=None):
        """Show speech bubble (supports \\n line breaks, custom display duration in seconds). Silent in game mode."""
        if self._game_mode.is_active():
            return
        if self._bubble is not None:
            self._bubble.hide()
            self._bubble.deleteLater()
            self._bubble = None
        bubble = SpeechBubble()
        bubble.show_text(text, self, duration)
        self._bubble = bubble

    def show_greeting(self):
        """Show greeting bubble (with weather and todo stats, weather fetched in background to avoid UI freeze)"""
        def _do_greet():
            def _on_weather(weather):
                parts = [self._behavior.get_period_greeting(self._user_title)]
                if weather:
                    parts.append(f"Weather: {weather}")
                pending = self._pending_todo_count()
                if pending > 0:
                    parts.append(f"You have {pending} pending todos~")
                self.say("\n".join(parts), 8.0)
                # Announce todo deadline reminders after greeting
                QTimer.singleShot(9000, self._broadcast_todo_deadlines)
            self._get_weather_text(_on_weather)
        QTimer.singleShot(600, _do_greet)

    def _broadcast_todo_deadlines(self):
        """Announce todos with due dates after startup (sorted by urgency)"""
        import datetime as _dt
        today = _dt.date.today()
        due_items = []
        for item in self._todo_items:
            due = item.get("due_date", "")
            if not due or item.get("done", False):
                continue
            try:
                d = _dt.datetime.strptime(due, "%Y-%m-%d").date()
                days = (d - today).days
                if days < 0:
                    continue  # Skip expired ones
                due_items.append((days, item["text"]))
            except Exception:
                continue
        if not due_items:
            return
        due_items.sort()
        lines = ["📋 Todo Reminders:"]
        for days, text in due_items[:5]:
            if days <= 3:
                icon = "🔴"
            elif days <= 7:
                icon = "🟡"
            else:
                icon = "🟢"
            lines.append(f"{icon} {text} {days} days left")
        self.say("\n".join(lines), 10.0)

    # ── Chat Response ─────────────────────────────────

    def _say_time(self):
        """Reply with current time"""
        import datetime as _dt
        now = _dt.datetime.now()
        time_str = now.strftime("%H:%M:%S")
        date_str = now.strftime("%Y-%m-%d")
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekday = weekdays[now.weekday()]
        period = self._behavior.get_time_period(now.hour)
        period_names = {"morning": "morning", "afternoon": "afternoon", "evening": "evening", "night": "night"}
        self.say(f"It's now {date_str} {weekday}\n{time_str}, {period_names[period]} time~", 6.0)

    def _say_weather(self):
        """Fetch weather asynchronously and reply"""
        self.say("Querying weather...", 2.0)

        def _on_weather(weather):
            if weather:
                self.say(f"Today's weather: {weather}", 6.0)
            else:
                self.say("Weather data fetch failed,\nmaybe a network issue~", 5.0)
        self._get_weather_text(_on_weather)

    def _say_todo_status(self):
        """Reply with todo status"""
        pending = self._pending_todo_count()
        total = len(self._todo_items)
        done = total - pending
        if total == 0:
            self.say("No todos today~\nTime to slack off!", 5.0)
        elif pending == 0:
            self.say(f"All {total} todos completed!\nAmazing~", 5.0)
        else:
            self.say(f"{pending} todos remaining\n({total} total, {done} completed)\nKeep going!", 5.0)

    def _say_joke(self):
        """Tell a random joke"""
        jokes = self._dialog_data.get("jokes", [])
        if jokes:
            joke = random.choice(jokes)
            self.say(joke, 8.0)
        else:
            self.say("The joke library is empty...\nThat itself is a joke.", 5.0)

    def _say_fact(self):
        """Say a random fun fact"""
        facts = self._dialog_data.get("facts", [])
        if facts:
            fact = random.choice(facts)
            self.say(fact, 8.0)
        else:
            self.say("The fun fact library is empty,\nbut 'vacuum' isn't really empty——\nQuantum fluctuations, anyone?", 5.0)

    def _say_compliment(self):
        """Give a random compliment"""
        compliments = self._dialog_data.get("compliments", [])
        if compliments:
            comp = random.choice(compliments)
            self.say(comp, 7.0)
        else:
            self.say("You're so great, I'm at a loss for words.\n(Add compliments in dialog_data.json)", 5.0)

    # ── Window Close ──────────────────────────────────

    def closeEvent(self, event):
        self._save_position()
        if self._bubble is not None:
            self._bubble.hide()
            self._bubble.deleteLater()
            self._bubble = None
        if self._countdown is not None:
            self._countdown.stop()
            self._countdown.deleteLater()
            self._countdown = None
        if self._todo_panel is not None:
            self._todo_panel.close()
            self._todo_panel = None
        if self._body_panel is not None:
            self._body_panel.close()
            self._body_panel.deleteLater()
            self._body_panel = None
        self._weigh_check_timer.stop()
        self._unregister_hotkey()
        for plugin in self._plugins:
            try:
                plugin.on_unload(self)
            except Exception:
                pass
        super().closeEvent(event)

"""Window Pin Manager — Add a pin button to each desktop window, click to toggle window always-on-top"""

import os
from PyQt5.QtCore import Qt, QTimer, QObject
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QWidget, QLabel, QApplication

import win32gui
import win32con
import win32process

# ── Constants ───────────────────────────────────────────────
POLL_INTERVAL = 500        # Window scan interval (milliseconds)
BTN_SIZE = 20              # Button size

# Position presets: offsets relative to window edges (button placed outside the window to avoid title bar overlap)
POSITION_PRESETS = {
    "top_left":      {"anchor": "top_left",      "dx": -BTN_SIZE - 2, "dy": -BTN_SIZE - 2},
    "top_center":    {"anchor": "top_center",    "dx": 0,             "dy": -BTN_SIZE - 2},
    "top_right":     {"anchor": "top_right",     "dx": 2,             "dy": -BTN_SIZE - 2},
    "bottom_left":   {"anchor": "bottom_left",   "dx": -BTN_SIZE - 2, "dy": 2},
    "bottom_center": {"anchor": "bottom_center", "dx": 0,             "dy": 2},
    "bottom_right":  {"anchor": "bottom_right",  "dx": 2,             "dy": 2},
}

# Excluded window titles
EXCLUDE_TITLES = (
    "", "Program Manager", "Microsoft Text Input Application",
    "Windows Shell Experience Host", "NVIDIA GeForce Overlay",
)

# Excluded window class names
EXCLUDE_CLASSES = (
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
    "Windows.UI.Core.CoreWindow", "ApplicationFrameWindow",
)

# Module-level singleton
_manager: 'WindowPinManager | None' = None


def get_manager():
    return _manager


class PinButton(QWidget):
    """Pin button — borderless mini window overlaid on the target window"""

    def __init__(self, hwnd, position_preset="top_right"):
        super().__init__()
        self._hwnd = hwnd
        self._pinned = self._check_topmost()
        self._preset = position_preset

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus |
            Qt.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(BTN_SIZE, BTN_SIZE)
        self.setCursor(Qt.PointingHandCursor)

        self._label = QLabel(self)
        self._label.setFixedSize(BTN_SIZE, BTN_SIZE)
        self._label.setAlignment(Qt.AlignCenter)
        font = QFont("Segoe UI Emoji", 10)
        self._label.setFont(font)
        self._update_icon()

    @property
    def hwnd(self):
        return self._hwnd

    @property
    def pinned(self):
        return self._pinned

    def set_preset(self, preset):
        self._preset = preset

    def _check_topmost(self):
        try:
            ex = win32gui.GetWindowLong(self._hwnd, win32con.GWL_EXSTYLE)
            return bool(ex & win32con.WS_EX_TOPMOST)
        except Exception:
            return False

    def _update_icon(self):
        self._label.setText("\U0001f9f7" if self._pinned else "\U0001f4cc")

    def mousePressEvent(self, event):
        self._pinned = not self._pinned
        self._update_icon()
        try:
            if self._pinned:
                win32gui.SetWindowPos(
                    self._hwnd, win32con.HWND_TOPMOST,
                    0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                )
            else:
                win32gui.SetWindowPos(
                    self._hwnd, win32con.HWND_NOTOPMOST,
                    0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                )
        except Exception:
            pass

    def update_position(self):
        """Update button position based on target window position and preset (auto-hide when minimized)"""
        try:
            if not win32gui.IsWindow(self._hwnd) or win32gui.IsIconic(self._hwnd):
                self.hide()
                return
        except Exception:
            self.hide()
            return
        try:
            rect = win32gui.GetWindowRect(self._hwnd)
            left, top, right, bottom = rect
            w = right - left
            h = bottom - top

            preset = POSITION_PRESETS.get(self._preset, POSITION_PRESETS["top_right"])
            anchor = preset["anchor"]
            dx, dy = preset["dx"], preset["dy"]

            if anchor == "top_left":
                ref_x, ref_y = left, top
            elif anchor == "top_center":
                ref_x, ref_y = left + w // 2 - BTN_SIZE // 2, top
            elif anchor == "top_right":
                ref_x, ref_y = right, top
            elif anchor == "bottom_left":
                ref_x, ref_y = left, bottom
            elif anchor == "bottom_center":
                ref_x, ref_y = left + w // 2 - BTN_SIZE // 2, bottom
            elif anchor == "bottom_right":
                ref_x, ref_y = right, bottom
            else:
                ref_x, ref_y = right, top

            self.move(ref_x + dx, ref_y + dy)

            # Set button z-order to be just above the target window (does not penetrate other windows)
            btn_hwnd = int(self.winId())
            win32gui.SetWindowPos(
                btn_hwnd, self._hwnd,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
            )

            if not self.isVisible():
                self.show()
        except Exception:
            self.hide()


class WindowPinManager(QObject):
    """Window pin manager"""

    def __init__(self):
        global _manager
        super().__init__()
        _manager = self

        from config import SETTINGS_PATH
        from PyQt5.QtCore import QSettings
        self._settings = QSettings(SETTINGS_PATH, QSettings.IniFormat)

        self._enabled = self._settings.value("pin/enabled", "true") == "true"
        self._position = self._settings.value("pin/position", "top_right")
        self._buttons = {}
        self._pinned_by_us = set()   # Windows we have pinned, to be restored on exit
        self._our_pid = os.getpid()
        self._our_hwnds = set()

        self._timer = QTimer()
        self._timer.setInterval(POLL_INTERVAL)
        self._timer.timeout.connect(self._poll)
        if self._enabled:
            self._timer.start()
            self._poll()

    @property
    def enabled(self):
        return self._enabled

    @property
    def position(self):
        return self._position

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self._settings.setValue("pin/enabled", str(enabled).lower())
        self._settings.sync()
        if enabled:
            self._timer.start()
            self._poll()
        else:
            self._timer.stop()
            self._clear_all_buttons()

    def set_position(self, position: str):
        self._position = position
        self._settings.setValue("pin/position", position)
        self._settings.sync()
        for btn in self._buttons.values():
            btn.set_preset(position)

    def show_settings(self, parent=None):
        """Show pin settings dialog"""
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QCheckBox,
            QPushButton, QLabel, QButtonGroup, QRadioButton
        )

        dlg = QDialog(parent)
        dlg.setWindowTitle("Window Pin Settings")
        dlg.setFixedSize(340, 280)
        dlg.setStyleSheet("""
            QDialog { background-color: #2b2b2b; }
            QLabel { color: #ccc; font-size: 12px; }
            QCheckBox { color: #ccc; font-size: 12px; }
            QRadioButton { color: #ccc; font-size: 12px; }
            QPushButton {
                background: #3c3c3c; color: #e0e0e0; border: 1px solid #555;
                padding: 6px 16px; border-radius: 4px;
            }
            QPushButton:hover { background: #4a4a4a; }
        """)

        layout = QVBoxLayout(dlg)

        # ── Toggle ──
        cb_enable = QCheckBox("Enable window pin button")
        cb_enable.setChecked(self._enabled)
        layout.addWidget(cb_enable)

        layout.addSpacing(8)

        # ── Position Presets ──
        layout.addWidget(QLabel("Button Position:"))

        pos_names = [
            ("top_left", "Top Left"), ("top_center", "Top Center"), ("top_right", "Top Right"),
            ("bottom_left", "Bottom Left"), ("bottom_center", "Bottom Center"), ("bottom_right", "Bottom Right"),
        ]

        pos_layouts = [QHBoxLayout(), QHBoxLayout()]
        for i, (key, label) in enumerate(pos_names):
            rb = QRadioButton(label)
            rb.setChecked(key == self._position)
            rb.key = key
            pos_layouts[i // 3].addWidget(rb)

        layout.addLayout(pos_layouts[0])
        layout.addLayout(pos_layouts[1])

        layout.addStretch()

        # ── Buttons ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(
            "background: #2980b9; color: white; font-weight: bold;"
        )
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        def on_ok():
            enabled = cb_enable.isChecked()
            # Find selected position
            new_pos = self._position
            for i, (key, _) in enumerate(pos_names):
                # Find corresponding radio button
                for pl in pos_layouts:
                    for j in range(pl.count()):
                        w = pl.itemAt(j).widget()
                        if w and hasattr(w, 'key') and w.key == key and w.isChecked():
                            new_pos = key

            if enabled != self._enabled:
                self.set_enabled(enabled)
            if new_pos != self._position:
                self.set_position(new_pos)
            dlg.accept()

        ok_btn.clicked.connect(on_ok)
        dlg.exec_()

    def stop(self):
        """Stop and restore windows we have pinned"""
        self._timer.stop()

        # Restore windows we have pinned
        for hwnd in list(self._pinned_by_us):
            try:
                if win32gui.IsWindow(hwnd):
                    ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                    if ex & win32con.WS_EX_TOPMOST:
                        win32gui.SetWindowPos(
                            hwnd, win32con.HWND_NOTOPMOST,
                            0, 0, 0, 0,
                            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                        )
            except Exception:
                pass
        self._pinned_by_us.clear()

        self._clear_all_buttons()

    def _clear_all_buttons(self):
        for btn in list(self._buttons.values()):
            try:
                btn.hide()
                btn.deleteLater()
            except Exception:
                pass
        self._buttons.clear()

    def _poll(self):
        if not self._enabled:
            return

        current_hwnds = set()
        self._our_hwnds = set()

        def callback(hwnd, _):
            current_hwnds.add(hwnd)
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid == self._our_pid:
                    self._our_hwnds.add(hwnd)
            except Exception:
                pass
            return True

        win32gui.EnumWindows(callback, None)

        for hwnd in current_hwnds:
            if hwnd in self._our_hwnds:
                continue
            if not self._should_pin(hwnd):
                # Window no longer qualifies (minimized, etc.), hide existing button
                if hwnd in self._buttons:
                    self._buttons[hwnd].hide()
                continue

            if hwnd in self._buttons:
                self._buttons[hwnd].update_position()
            else:
                btn = PinButton(hwnd, self._position)
                self._buttons[hwnd] = btn
                btn.update_position()

            # Track windows we have pinned
            if self._buttons[hwnd].pinned:
                self._pinned_by_us.add(hwnd)

        # Cleanup
        removed = []
        for hwnd, btn in self._buttons.items():
            if hwnd not in current_hwnds or not win32gui.IsWindow(hwnd):
                btn.hide()
                btn.deleteLater()
                removed.append(hwnd)
        for hwnd in removed:
            del self._buttons[hwnd]

    def _should_pin(self, hwnd):
        try:
            if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                return False
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            if title in EXCLUDE_TITLES:
                return False
            if any(kw in cls for kw in EXCLUDE_CLASSES):
                return False
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w < 150 or h < 100:
                return False
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            if not (style & win32con.WS_CAPTION):
                return False
            ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if ex & win32con.WS_EX_TOOLWINDOW:
                return False
            return True
        except Exception:
            return False

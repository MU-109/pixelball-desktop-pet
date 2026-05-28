"""Application management module — QApplication lifecycle, system tray, plugin loading"""

import sys
import os
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt5.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QAction,
)

import config as cfg
from pet_window import PetWindow
from plugin_base import PetPlugin

# Global singleton reference
_app_instance = None


def get_app():
    return _app_instance


class PetApp:
    """Desktop pet application manager — Singleton, manages QApplication and system tray"""

    def __init__(self, sys_argv=None):
        global _app_instance
        if _app_instance is not None:
            raise RuntimeError("PetApp is a singleton, use get_app() to get the instance")

        _app_instance = self
        self._qapp = QApplication(sys_argv or sys.argv)
        self._qapp.setQuitOnLastWindowClosed(False)
        self._pet: PetWindow | None = None
        self._tray: QSystemTrayIcon | None = None
        self._init_tray()

    @property
    def qapp(self):
        return self._qapp

    @property
    def pet(self):
        return self._pet

    # ── System Tray ──────────────────────────────────

    def _init_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        icon_pixmap = self._make_tray_icon()
        self._tray = QSystemTrayIcon(icon_pixmap, self._qapp)
        self._tray.setToolTip("Pixel Ball Desktop Pet")

        tray_menu = QMenu()
        act_show = tray_menu.addAction("Show Pet")
        act_show.triggered.connect(lambda: self._pet.show() if self._pet else None)
        act_hide = tray_menu.addAction("Hide Pet")
        act_hide.triggered.connect(lambda: self._pet.hide() if self._pet else None)
        tray_menu.addSeparator()

        # Passthrough mode toggle (when enabled, cannot right-click to exit; tray is the only way to recover)
        act_passthrough = tray_menu.addAction("Passthrough Mode")
        act_passthrough.setCheckable(True)
        act_passthrough.triggered.connect(
            lambda checked: self._pet.set_passthrough(checked) if self._pet else None
        )
        # Sync passthrough state each time tray menu opens
        tray_menu.aboutToShow.connect(
            lambda: act_passthrough.setChecked(
                self._pet._passthrough if self._pet else False
            )
        )

        tray_menu.addSeparator()

        # Game mode exit entry (only visible in game mode)
        act_exit_gm = tray_menu.addAction("Exit Game Mode")
        act_exit_gm.triggered.connect(
            lambda: self._pet._game_mode.exit() if self._pet and hasattr(self._pet, '_game_mode') else None
        )
        tray_menu.aboutToShow.connect(
            lambda: act_exit_gm.setVisible(
                self._pet._game_mode.is_active() if self._pet and hasattr(self._pet, '_game_mode') else False
            )
        )

        tray_menu.addSeparator()
        act_quit = tray_menu.addAction("Quit")
        act_quit.triggered.connect(self.quit)

        self._tray.setContextMenu(tray_menu)
        self._tray.show()

    @staticmethod
    def _make_tray_icon():
        """Generate 16x16 pixel yellow face tray icon"""
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, False)

        border_color = QColor(30, 30, 30)
        painter.setPen(border_color)
        painter.setBrush(border_color)
        painter.drawEllipse(0, 0, 15, 15)

        body_color = QColor(*cfg.BALL_BODY_COLOR)
        painter.setPen(body_color)
        painter.setBrush(body_color)
        painter.drawEllipse(1, 1, 13, 13)

        eye_color = QColor(*cfg.BALL_EYE_COLOR)
        painter.setPen(eye_color)
        painter.setBrush(eye_color)
        painter.drawRect(5, 5, 2, 3)
        painter.drawRect(9, 5, 2, 3)

        mouth_color = QColor(*cfg.BALL_MOUTH_COLOR)
        painter.setPen(mouth_color)
        painter.drawPoint(5, 10)
        painter.drawPoint(6, 11)
        painter.drawPoint(7, 11)
        painter.drawPoint(8, 11)
        painter.drawPoint(9, 10)
        painter.end()
        return QIcon(pixmap)

    # ── Pet Management ───────────────────────────────

    def spawn_pet(self, x=None, y=None):
        """Create pet instance, auto-load plugins"""
        if self._pet is not None:
            self._pet.close()
        self._pet = PetWindow()
        if x is not None and y is not None:
            self._pet.move_to(x, y)
        self._load_plugins()
        self._pet.show()
        return self._pet

    def _load_plugins(self):
        """Scan plugins/ directory, auto-load all PetPlugin subclasses"""
        plugins_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "plugins"
        )
        if not os.path.isdir(plugins_dir):
            return

        for fname in os.listdir(plugins_dir):
            if fname.startswith("_") or not fname.endswith(".py"):
                continue
            if fname == "__init__.py":
                continue
            try:
                mod_name = f"plugins.{fname[:-3]}"
                __import__(mod_name)
                mod = sys.modules.get(mod_name)
                if mod:
                    for attr_name in dir(mod):
                        attr = getattr(mod, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, PetPlugin)
                            and attr is not PetPlugin
                        ):
                            self._pet.load_plugin(attr())
            except Exception:
                pass

    def run(self):
        """Start Qt event loop"""
        if self._pet is None:
            self.spawn_pet()
        return self._qapp.exec_()

    def quit(self):
        """Quit application"""
        if self._pet is not None:
            self._pet.close()
            self._pet = None
        if self._tray:
            self._tray.hide()
        self._qapp.quit()

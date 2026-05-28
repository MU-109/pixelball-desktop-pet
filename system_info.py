"""System Info Plugin — IP/Model/WiFi/Ports/Env Vars/Cheat Sheet"""

import os
import re
import socket
import json
import platform
import subprocess
import urllib.request
import winreg
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QTextEdit,
    QWidget, QApplication, QInputDialog, QMessageBox,
)
from PyQt5.QtCore import QSettings
from config import SETTINGS_PATH


# ── Common Utilities ────────────────────────────────────────

def _copy_and_tell(pet, label, value):
    QApplication.clipboard().setText(str(value))
    if pet and hasattr(pet, 'say'):
        pet.say(f"{label}: {value}", 4.0)


# ── Info Collection ─────────────────────────────────────────

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "Unable to retrieve"


def get_public_ip():
    """Fetch asynchronously, returning result via callback"""
    def _fetch(callback):
        try:
            req = urllib.request.Request(
                "https://ipinfo.io/ip",
                headers={"User-Agent": "curl/7.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                ip = resp.read().decode().strip()
                callback(ip)
        except Exception:
            try:
                with urllib.request.urlopen("https://ifconfig.me/ip", timeout=5) as resp:
                    ip = resp.read().decode().strip()
                    callback(ip)
            except Exception:
                callback("Fetch failed")
    return _fetch


def get_wifi_ssid():
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, timeout=5,
            encoding="utf-8", errors="ignore"
        )
        for line in result.stdout.splitlines():
            if "SSID" in line and "BSSID" not in line:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    return parts[1].strip()
        return "Not connected to WiFi"
    except Exception:
        return "Unable to retrieve"


def get_computer_model():
    def _reg_query(key_path, value_name):
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            val, _ = winreg.QueryValueEx(key, value_name)
            winreg.CloseKey(key)
            return val
        except Exception:
            return None

    # Try multiple locations
    for path, name in [
        (r"HARDWARE\DESCRIPTION\System\BIOS", "SystemProductName"),
        (r"HARDWARE\DESCRIPTION\System\BIOS", "BaseBoardProduct"),
        (r"SOFTWARE\Microsoft\Windows\CurrentVersion\OEMInformation", "Model"),
    ]:
        v = _reg_query(path, name)
        if v and v.strip() and v.strip() != "System Product Name":
            return v.strip()

    # Brand + model concatenation
    mfr = _reg_query(r"HARDWARE\DESCRIPTION\System\BIOS", "SystemManufacturer") or ""
    prod = _reg_query(r"HARDWARE\DESCRIPTION\System\BIOS", "SystemProductName") or ""
    combined = f"{mfr} {prod}".strip()
    return combined if combined else "Unable to retrieve"


def get_cpu_model():
    cpu = platform.processor()
    # platform.processor() on Windows often returns unfriendly strings like "Intel64 Family..."
    if cpu and "Intel64 Family" not in cpu and "AMD64 Family" not in cpu:
        return cpu
    # Registry fallback (returns friendly names like "Intel Core i7-13700H")
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
        )
        name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        winreg.CloseKey(key)
        return name.strip()
    except Exception:
        return platform.processor() or "Unable to retrieve"


def get_gpu_model():
    try:
        result = subprocess.run(
            ["wmic", "path", "win32_VideoController", "get", "name"],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().splitlines()
        for line in lines:
            line = line.strip()
            if line and "Name" not in line:
                return line
    except Exception:
        pass
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode()
        return name
    except Exception:
        return "Unable to retrieve"


def get_system_version():
    return f"Windows {platform.version()} {platform.release()}"


def get_screen_info():
    from PyQt5.QtGui import QGuiApplication
    screen = QGuiApplication.primaryScreen()
    if screen:
        geom = screen.geometry()
        dpi = screen.logicalDotsPerInch()
        return f"{geom.width()}x{geom.height()}  {dpi:.0f} DPI"
    return "Unable to retrieve"


def get_uptime():
    try:
        import psutil
        sec = int(psutil.boot_time())
        boot = datetime.fromtimestamp(sec)
        now = datetime.now()
        delta = now - boot
        d = delta.days
        h, m = delta.seconds // 3600, (delta.seconds % 3600) // 60
        parts = []
        if d:
            parts.append(f"{d}d")
        if h:
            parts.append(f"{h}h")
        parts.append(f"{m}min")
        return f"{' '.join(parts)}  (Booted at {boot.strftime('%m-%d %H:%M')})"
    except Exception:
        return "Unable to retrieve"


# ── Panels ──────────────────────────────────────────────────

def show_full_panel(pet):
    dlg = QDialog(pet)
    dlg.setWindowTitle("System Info")
    dlg.setFixedSize(480, 420)
    dlg.setStyleSheet("""
        QDialog { background:#2b2b2b; }
        QTextEdit { background:#1e1e1e; color:#e0e0e0; border:1px solid #555;
            font-size:14px; padding:10px; border-radius:6px; font-family:"Microsoft YaHei",Consolas; }
    """)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)

    title = QLabel("System Info")
    title.setStyleSheet("color:#fff; font-size:16px; font-weight:bold;")
    layout.addWidget(title)

    te = QTextEdit()
    te.setReadOnly(True)
    info = "\n".join([
        f"Computer Model: {get_computer_model()}",
        f"System Version: {get_system_version()}",
        f"CPU: {get_cpu_model()}",
        f"GPU: {get_gpu_model()}",
        f"Screen: {get_screen_info()}",
        f"Local IP: {get_local_ip()}",
        f"WiFi: {get_wifi_ssid()}",
        f"Uptime: {get_uptime()}",
    ])
    te.setPlainText(info)
    layout.addWidget(te)

    close = QPushButton("Close")
    close.setStyleSheet(
        "background:#3c3c3c; color:#e0e0e0; border:1px solid #555;"
        "border-radius:6px; padding:10px 24px; font-size:14px;")
    close.clicked.connect(dlg.close)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    btn_row.addWidget(close)
    layout.addLayout(btn_row)

    dlg.exec_()


def show_port_checker(pet):
    dlg = QDialog(pet)
    dlg.setWindowTitle("Port Checker")
    dlg.setFixedSize(400, 220)
    dlg.setStyleSheet("""
        QDialog { background:#2b2b2b; }
        QLineEdit { background:#1e1e1e; color:#e0e0e0; border:1px solid #555;
            font-size:16px; padding:10px; border-radius:6px; }
        QLabel { color:#ccc; font-size:14px; }
    """)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)

    layout.addWidget(QLabel("Enter port number to check:"))

    row = QHBoxLayout()
    entry = QLineEdit()
    entry.setPlaceholderText("e.g. 8080")
    row.addWidget(entry)

    check_btn = QPushButton("Check")
    check_btn.setStyleSheet(
        "background:#2980b9; color:white; font-weight:bold; border:none;"
        "border-radius:6px; padding:10px 24px; font-size:14px;")
    row.addWidget(check_btn)
    layout.addLayout(row)

    result_label = QLabel("")
    result_label.setWordWrap(True)
    result_label.setStyleSheet("font-size:15px;")
    layout.addWidget(result_label)

    def do_check():
        port_str = entry.text().strip()
        if not port_str.isdigit():
            result_label.setText("Please enter a valid port number")
            return
        port = int(port_str)
        if port < 1 or port > 65535:
            result_label.setText("Port range is 1-65535")
            return

        # Check occupancy
        occupied = False
        proc_name = ""
        try:
            import psutil
            for conn in psutil.net_connections():
                if conn.laddr and conn.laddr.port == port:
                    occupied = True
                    if conn.pid:
                        try:
                            proc_name = psutil.Process(conn.pid).name()
                        except Exception:
                            pass
                    break
        except Exception:
            pass

        if occupied:
            extra = f" (Process: {proc_name})" if proc_name else ""
            result_label.setText(f"Port {port} is in use{extra}")
            result_label.setStyleSheet("color:#e74c3c; font-size:15px;")
        else:
            # Try to bind and confirm
            s = socket.socket()
            s.settimeout(0.5)
            try:
                s.bind(("", port))
                s.close()
                result_label.setText(f"Port {port} is available")
                result_label.setStyleSheet("color:#2ecc71; font-size:15px;")
            except Exception:
                result_label.setText(f"Port {port} is in use (system reserved)")
                result_label.setStyleSheet("color:#e74c3c; font-size:15px;")

    check_btn.clicked.connect(do_check)
    entry.returnPressed.connect(do_check)

    close = QPushButton("Close")
    close.setStyleSheet(
        "background:#3c3c3c; color:#e0e0e0; border:1px solid #555;"
        "border-radius:6px; padding:10px 24px; font-size:14px;")
    close.clicked.connect(dlg.close)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    btn_row.addWidget(close)
    layout.addLayout(btn_row)

    dlg.exec_()


def show_env_vars(pet):
    dlg = QDialog(pet)
    dlg.setWindowTitle("Environment Variables")
    dlg.setFixedSize(600, 420)
    dlg.setStyleSheet("""
        QDialog { background:#2b2b2b; }
        QLineEdit { background:#1e1e1e; color:#e0e0e0; border:1px solid #555;
            font-size:14px; padding:8px; border-radius:6px; }
        QListWidget { background:#1e1e1e; color:#e0e0e0; border:1px solid #444;
            border-radius:6px; font-size:13px; }
        QListWidget::item { padding:8px 10px; border-bottom:1px solid #333; }
    """)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)

    title = QLabel("Environment Variables")
    title.setStyleSheet("color:#fff; font-size:16px; font-weight:bold;")
    layout.addWidget(title)

    search = QLineEdit()
    search.setPlaceholderText("Search variable name or value...")
    layout.addWidget(search)

    lst = QListWidget()
    layout.addWidget(lst)

    env_items = sorted(os.environ.items())

    def refresh(filter_text=""):
        lst.clear()
        ft = filter_text.lower()
        for k, v in env_items:
            if ft and ft not in k.lower() and ft not in v.lower():
                continue
            display = f"{k}  =  {v}"
            lst.addItem(display)

    refresh()
    search.textChanged.connect(refresh)

    lst.itemDoubleClicked.connect(lambda item: (
        QApplication.clipboard().setText(item.text()),
        _copy_and_tell(pet, "Copied", item.text().split("=")[0].strip())
    ))

    hint = QLabel("Double-click an item to copy its value")
    hint.setStyleSheet("color:#999; font-size:12px;")
    layout.addWidget(hint)

    close = QPushButton("Close")
    close.setStyleSheet(
        "background:#3c3c3c; color:#e0e0e0; border:1px solid #555;"
        "border-radius:6px; padding:10px 24px; font-size:14px;")
    close.clicked.connect(dlg.close)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    btn_row.addWidget(close)
    layout.addLayout(btn_row)

    dlg.exec_()


# ── Cheat Sheet Management (Encrypted Storage) ──────────────

_CHEATSHEET_KEY = "cheatsheet/items"


def _load_cheats():
    from secure_store import decrypt_value
    s = QSettings(SETTINGS_PATH, QSettings.IniFormat)
    raw = s.value(_CHEATSHEET_KEY, "[]")
    try:
        items = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, list) else [])
    except Exception:
        items = []
    # Ensure items is an iterable list
    if not isinstance(items, list):
        items = []
    # Decrypt each entry
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            it["content"] = decrypt_value(it.get("content", ""))
        except Exception:
            pass
    return items


def _save_cheats(items):
    from secure_store import encrypt_value
    s = QSettings(SETTINGS_PATH, QSettings.IniFormat)
    # Deep copy and encrypt
    to_save = []
    for it in items:
        entry = dict(it)
        entry["content"] = encrypt_value(entry.get("content", ""))
        to_save.append(entry)
    # ensure_ascii=True avoids Chinese character encoding corruption in QSettings INI format
    s.setValue(_CHEATSHEET_KEY, json.dumps(to_save, ensure_ascii=True))
    s.sync()


def show_cheat_sheet(pet):
    """Cheat sheet management dialog — unified entry for view/copy/add/delete"""

    dlg = QDialog(pet)
    dlg.setWindowTitle("My Cheat Sheet")
    dlg.setFixedSize(420, 400)
    dlg.setStyleSheet("""
        QDialog { background:#2b2b2b; }
        QListWidget { background:#1e1e1e; color:#e0e0e0; border:1px solid #444;
            border-radius:6px; font-size:14px; }
        QListWidget::item { padding:10px 12px; border-bottom:1px solid #333; }
        QListWidget::item:selected { background:#3a5a8c; }
        QLineEdit, QTextEdit {
            background:#1e1e1e; color:#e0e0e0; border:1px solid #555;
            border-radius:6px; padding:10px 12px; font-size:14px;
        }
        QLineEdit:focus, QTextEdit:focus { border:1px solid #2980b9; }
    """)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)

    title = QLabel("My Cheat Sheet")
    title.setStyleSheet("color:#fff; font-size:16px; font-weight:bold;")
    layout.addWidget(title)

    # ── List ──
    lst = QListWidget()
    lst.setMaximumHeight(200)
    layout.addWidget(lst)

    # ── Action Button Row ──
    op_row = QHBoxLayout()
    op_row.setSpacing(8)

    btn_add = QPushButton("+ Add")
    btn_add.setStyleSheet(_btn_style("#27ae60", "#2ecc71"))
    btn_delete = QPushButton("x Delete")
    btn_delete.setStyleSheet(_btn_style("#c0392b", "#e74c3c"))
    btn_edit = QPushButton("Edit")
    btn_edit.setStyleSheet(_btn_style("#2980b9", "#3498db"))

    op_row.addWidget(btn_add)
    op_row.addWidget(btn_edit)
    op_row.addWidget(btn_delete)
    layout.addLayout(op_row)

    # ── Add/Edit Area (hidden by default) ──
    edit_widget = QWidget()
    edit_layout = QVBoxLayout(edit_widget)
    edit_layout.setContentsMargins(0, 0, 0, 0)
    edit_layout.setSpacing(6)

    name_input = QLineEdit()
    name_input.setPlaceholderText("Name (e.g., API Key)")
    content_input = QTextEdit()
    content_input.setPlaceholderText("Content (click list item to copy)")
    content_input.setMaximumHeight(80)
    content_input.setAcceptRichText(False)
    edit_layout.addWidget(name_input)
    edit_layout.addWidget(content_input)

    edit_btn_row = QHBoxLayout()
    edit_btn_row.setSpacing(8)
    btn_save = QPushButton("Save")
    btn_save.setStyleSheet(_btn_style("#27ae60", "#2ecc71"))
    btn_cancel = QPushButton("Cancel")
    btn_cancel.setStyleSheet(_btn_style("#555", "#777"))
    edit_btn_row.addStretch()
    edit_btn_row.addWidget(btn_cancel)
    edit_btn_row.addWidget(btn_save)
    edit_layout.addLayout(edit_btn_row)

    edit_widget.hide()
    layout.addWidget(edit_widget)

    layout.addStretch()

    # ── Bottom Bar ──
    bottom = QHBoxLayout()
    hint = QLabel()
    hint.setStyleSheet("color:#999; font-size:12px;")
    bottom.addWidget(hint)
    bottom.addStretch()
    btn_close = QPushButton("Close")
    btn_close.setStyleSheet(
        "background:#3c3c3c; color:#e0e0e0; border:1px solid #555;"
        "border-radius:6px; padding:8px 20px; font-size:14px;")
    btn_close.clicked.connect(dlg.accept)
    bottom.addWidget(btn_close)
    layout.addLayout(bottom)

    # ── Core function: reload from disk each time, data stored in QListWidgetItem.UserRole ──
    def _refresh():
        """Load from disk and refresh the list, data stored in item data to avoid stale closures"""
        cur = _load_cheats()
        lst.clear()
        for it in cur:
            item = QListWidgetItem(it.get("name", "???"))
            item.setData(Qt.UserRole, it)
            lst.addItem(item)
        if cur:
            lst.setCurrentRow(0)
        hint.setText(f"Total {len(cur)} items - Click item to copy content")

    _editing_index = [-1]

    def _show_edit(name="", content="", idx=-1):
        name_input.setText(name)
        content_input.setPlainText(content)
        _editing_index[0] = idx
        edit_widget.show()
        name_input.setFocus()

    def _hide_edit():
        name_input.clear()
        content_input.clear()
        _editing_index[0] = -1
        edit_widget.hide()

    # ── Click to copy — data always fetched fresh from item.UserRole ──
    def _on_item_clicked(item):
        data = item.data(Qt.UserRole)
        if not isinstance(data, dict):
            return
        content = data.get("content", "")
        name = data.get("name", "")
        # Copy content first, then show notification (don't overwrite clipboard)
        QApplication.clipboard().setText(content)
        if hasattr(pet, 'say'):
            pet.say(f"Copied: {name}", 4.0)

    lst.itemClicked.connect(_on_item_clicked)

    # ── Signals ──
    btn_add.clicked.connect(lambda: _show_edit())
    btn_cancel.clicked.connect(_hide_edit)

    btn_edit.clicked.connect(lambda: (
        _show_edit(
            lst.currentItem().data(Qt.UserRole).get("name", ""),
            lst.currentItem().data(Qt.UserRole).get("content", ""),
            lst.currentRow()
        ) if lst.currentItem() else None
    ))

    lst.itemDoubleClicked.connect(lambda: _show_edit(
        lst.currentItem().data(Qt.UserRole).get("name", ""),
        lst.currentItem().data(Qt.UserRole).get("content", ""),
        lst.currentRow()
    ) if lst.currentItem() else None)

    def _do_save():
        name = name_input.text().strip()
        content = content_input.toPlainText()
        if not name:
            return
        cur_items = _load_cheats()
        idx = _editing_index[0]
        if idx >= 0 and idx < len(cur_items):
            cur_items[idx] = {"name": name, "content": content}
        else:
            if len(cur_items) >= 20:
                if hasattr(pet, 'say'):
                    pet.say("Maximum 20 cheat sheet items", 3.0)
                return
            cur_items.append({"name": name, "content": content})
        _save_cheats(cur_items)
        _hide_edit()
        _refresh()
        if hasattr(pet, 'say'):
            pet.say(f"Cheat sheet saved: {name}", 3.0)

    btn_save.clicked.connect(_do_save)

    def _do_delete():
        idx = lst.currentRow()
        if idx < 0:
            return
        cur_items = _load_cheats()
        if idx >= len(cur_items):
            return
        name = cur_items[idx]["name"]
        cur_items.pop(idx)
        _save_cheats(cur_items)
        _hide_edit()
        _refresh()
        if hasattr(pet, 'say'):
            pet.say(f"Deleted: {name}", 2.0)

    btn_delete.clicked.connect(_do_delete)

    _refresh()
    dlg.exec_()


def _btn_style(bg, _hover_bg):
    """Button style template"""
    return (
        f"background:{bg}; color:#fff; border:none;"
        f"border-radius:6px; padding:8px 16px; font-size:13px;"
        f"font-weight:bold;"
    )

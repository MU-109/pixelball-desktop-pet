"""Utility tools — Clipboard history / Quick calculator / Color picker / Timestamp converter / Password generator / QR code"""

import secrets
import string
from datetime import datetime
from io import BytesIO

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTextEdit, QSpinBox, QCheckBox,
    QApplication, QListWidget, QListWidgetItem, QFileDialog,
)

# ── Global dark theme ─────────────────────────────────────
_STYLE = """
    QDialog, QWidget#ToolWin {
        background-color: #2b2b2b;
    }
    QLabel {
        color: #ccc;
        font-size: 14px;
    }
    QLabel#Title {
        font-size: 15px;
        font-weight: bold;
        color: #fff;
    }
    QLabel#Hint {
        color: #999;
        font-size: 12px;
    }
    QLabel#Result {
        color: #2ecc71;
        font-family: Consolas, "Microsoft YaHei";
        font-size: 16px;
        font-weight: bold;
    }
    QLabel#BigResult {
        color: #fff;
        font-family: Consolas, "Microsoft YaHei";
        font-size: 22px;
    }
    QLineEdit, QTextEdit, QSpinBox {
        background-color: #1e1e1e;
        color: #e0e0e0;
        border: 1px solid #555;
        border-radius: 6px;
        padding: 10px 12px;
        font-size: 15px;
        font-family: "Microsoft YaHei", Consolas;
        selection-background-color: #505050;
    }
    QLineEdit:focus, QTextEdit:focus {
        border: 1px solid #2980b9;
    }
    QSpinBox {
        padding: 8px 10px;
    }
    QCheckBox {
        color: #ccc;
        font-size: 14px;
        spacing: 8px;
    }
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
    }
    QListWidget {
        background-color: #1e1e1e;
        color: #e0e0e0;
        border: 1px solid #444;
        border-radius: 6px;
        font-size: 13px;
        padding: 4px;
        outline: none;
    }
    QListWidget::item {
        padding: 10px 12px;
        border-bottom: 1px solid #333;
    }
    QListWidget::item:hover {
        background-color: #3a3a3a;
    }
    QListWidget::item:selected {
        background-color: #505050;
    }
    QPushButton {
        background-color: #3c3c3c;
        color: #e0e0e0;
        border: 1px solid #555;
        border-radius: 6px;
        padding: 10px 24px;
        font-size: 14px;
    }
    QPushButton:hover {
        background-color: #4a4a4a;
    }
    QPushButton#Primary {
        background-color: #2980b9;
        color: white;
        font-weight: bold;
        border: none;
    }
    QPushButton#Primary:hover {
        background-color: #3498db;
    }
    QPushButton#Danger {
        background-color: #c0392b;
        color: white;
        border: none;
    }
    QPushButton#Danger:hover {
        background-color: #e74c3c;
    }
"""


def _dlg(parent, title, w, h):
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setFixedSize(w, h)
    dlg.setStyleSheet(_STYLE)
    return dlg


def _primary(text):
    b = QPushButton(text)
    b.setObjectName("Primary")
    return b


def _btn(text):
    return QPushButton(text)


def _btn_row(layout, *buttons):
    layout.addSpacing(12)
    row = QHBoxLayout()
    row.addStretch()
    for b in buttons:
        row.addWidget(b)
    layout.addLayout(row)


# ═══════════════════════════════════════════════════════════
# 1. Clipboard History
# ═══════════════════════════════════════════════════════════

_clipboard_history: list[str] = []
_clipboard_timer: QTimer | None = None
_MAX_HISTORY = 30


def _start_clipboard_watch():
    global _clipboard_timer
    if _clipboard_timer is not None:
        return
    _clipboard_timer = QTimer()
    _clipboard_timer.setInterval(300)
    _clipboard_timer.timeout.connect(_check_clipboard)
    _clipboard_timer.start()
    _check_clipboard()


def _check_clipboard():
    text = QApplication.clipboard().text().strip()
    if text and (not _clipboard_history or text != _clipboard_history[0]):
        _clipboard_history.insert(0, text)
        if len(_clipboard_history) > _MAX_HISTORY:
            _clipboard_history.pop()


def show_clipboard_history(pet):
    _start_clipboard_watch()
    dlg = _dlg(pet, "Clipboard History", 420, 380)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)

    title = QLabel("Clipboard History (Last 30 Items)")
    title.setObjectName("Title")
    layout.addWidget(title)

    hint = QLabel("Click an item to copy to clipboard")
    hint.setObjectName("Hint")
    layout.addWidget(hint)

    lst = QListWidget()
    for text in _clipboard_history:
        display = text.replace('\n', ' ').replace('\r', '')
        item = QListWidgetItem(
            display[:100] + ("..." if len(display) > 100 else ""))
        item.setToolTip(text)
        lst.addItem(item)
    lst.itemClicked.connect(
        lambda item: QApplication.clipboard().setText(
            item.toolTip() or item.text()))
    layout.addWidget(lst)

    btn_row = QHBoxLayout()
    clear_btn = QPushButton("Clear History")
    clear_btn.setObjectName("Danger")
    clear_btn.clicked.connect(
        lambda: (_clipboard_history.clear(), lst.clear()))
    btn_row.addWidget(clear_btn)
    btn_row.addStretch()
    close = _btn("Close")
    close.clicked.connect(dlg.close)
    btn_row.addWidget(close)
    layout.addLayout(btn_row)

    if pet:
        dlg.move(pet.pos().x() + pet.width() + 12, pet.pos().y())
    dlg.exec_()


# ═══════════════════════════════════════════════════════════
# 2. Quick Calculator
# ═══════════════════════════════════════════════════════════

_SAFE_GLOBALS = {
    "__builtins__": {},
    "abs": abs, "pow": pow, "round": round,
    "min": min, "max": max,
    "sin": __import__("math").sin, "cos": __import__("math").cos,
    "tan": __import__("math").tan, "pi": __import__("math").pi,
    "e": __import__("math").e, "log": __import__("math").log,
    "log10": __import__("math").log10, "ceil": __import__("math").ceil,
    "floor": __import__("math").floor, "sqrt": __import__("math").sqrt,
}
_ALLOWED_CHARS = set(
    "0123456789+-*/%(). e,**piEPIsincostanqrtlabcdfghjklmnouvwxyz"
    "ABSINCOSTANQRTLOGCEILFLOOROUNDMINMAXPW"
)


def show_calculator(pet):
    dlg = _dlg(pet, "Quick Calculator", 420, 200)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)

    title = QLabel("Quick Calculator")
    title.setObjectName("Title")
    layout.addWidget(title)

    hint = QLabel(
        "Supports: arithmetic / power(**) / brackets / sin cos tan / pi e / sqrt log")
    hint.setObjectName("Hint")
    hint.setWordWrap(True)
    layout.addWidget(hint)

    entry = QLineEdit()
    entry.setPlaceholderText("Enter expression, e.g.: 100 * (1 + 0.05) ** 3")
    entry.setStyleSheet("font-size: 20px; padding: 12px;")
    layout.addWidget(entry)
    entry.setFocus()

    def on_calc():
        expr = entry.text().strip()
        if not expr:
            return
        if not all(c in _ALLOWED_CHARS for c in expr.replace(" ", "")):
            if pet and hasattr(pet, 'say'):
                pet.say("Expression contains disallowed characters", 3.0)
            return
        try:
            result = eval(expr, _SAFE_GLOBALS, {})
            if isinstance(result, (int, float)):
                formatted = f"{result:,.6f}".rstrip('0').rstrip('.')
                text = f"{expr.replace(' ', '')} = {formatted}"
            else:
                text = f"{expr} = {result}"
            if pet and hasattr(pet, 'say'):
                pet.say(text, 6.0)
            dlg.accept()
        except Exception as e:
            if pet and hasattr(pet, 'say'):
                pet.say(f"Calculation error: {e}", 3.0)

    entry.returnPressed.connect(on_calc)

    calc = _primary("Calculate (Enter)")
    calc.clicked.connect(on_calc)
    cancel = _btn("Cancel")
    cancel.clicked.connect(dlg.reject)
    _btn_row(layout, calc, cancel)

    dlg.exec_()


# ═══════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════
# 4. Timestamp Converter
# ═══════════════════════════════════════════════════════════

def show_timestamp_converter(pet):
    dlg = _dlg(pet, "Timestamp Converter", 520, 340)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)

    title = QLabel("Timestamp ↔ Date Converter")
    title.setObjectName("Title")
    layout.addWidget(title)

    # ── Timestamp → Date ──
    sec1 = QVBoxLayout()
    sec1.setSpacing(6)
    sec1.addWidget(QLabel("Timestamp → Date"))

    row1 = QHBoxLayout()
    row1.setSpacing(8)
    ts_entry = QLineEdit()
    ts_entry.setPlaceholderText("Enter timestamp, e.g. 1716566400")
    ts_entry.setMinimumHeight(32)
    row1.addWidget(ts_entry)
    ts_btn = _primary("Convert")
    ts_btn.setFixedHeight(32)
    row1.addWidget(ts_btn)
    sec1.addLayout(row1)

    ts_bottom = QHBoxLayout()
    ts_bottom.setSpacing(8)
    ts_result = QLabel("")
    ts_result.setObjectName("Result")
    ts_result.setMinimumHeight(30)
    ts_result.setMaximumHeight(30)
    ts_bottom.addWidget(ts_result, 1)
    ts_copy = QPushButton("Copy")
    ts_copy.setFixedSize(50, 30)
    ts_copy.setVisible(False)
    ts_copy.setStyleSheet("font-size:12px; padding:2px 6px;")
    ts_bottom.addWidget(ts_copy)
    sec1.addLayout(ts_bottom)

    layout.addLayout(sec1)

    def ts_to_date():
        try:
            val = int(ts_entry.text().strip())
            if val > 1e12:
                val //= 1000
            dt = datetime.fromtimestamp(val)
            text = dt.strftime("%Y-%m-%d %H:%M:%S")
            ts_result.setText(text)
            ts_copy.setVisible(True)
            try:
                ts_copy.clicked.disconnect()
            except Exception:
                pass
            ts_copy.clicked.connect(lambda: QApplication.clipboard().setText(text))
        except Exception:
            ts_result.setText("Invalid format, please enter a numeric timestamp")
            ts_copy.setVisible(False)

    ts_btn.clicked.connect(ts_to_date)

    # ── Date → Timestamp ──
    layout.addSpacing(4)

    sec2 = QVBoxLayout()
    sec2.setSpacing(6)
    lbl2 = QLabel("Date → Timestamp")
    sec2.addWidget(lbl2)

    hint2 = QLabel("Supports various formats: 2024-5-24 / 2024/5/24 / 20061122124313 etc.")
    hint2.setObjectName("Hint")
    hint2.setMinimumHeight(20)
    hint2.setMaximumHeight(20)
    sec2.addWidget(hint2)

    row2 = QHBoxLayout()
    row2.setSpacing(8)
    date_entry = QLineEdit()
    date_entry.setPlaceholderText("Enter date in any format, e.g. 2024/5/24 14:30")
    date_entry.setMinimumHeight(32)
    row2.addWidget(date_entry)
    date_btn = _primary("Convert")
    date_btn.setFixedHeight(32)
    row2.addWidget(date_btn)
    sec2.addLayout(row2)

    date_bottom = QHBoxLayout()
    date_bottom.setSpacing(8)
    date_result = QLabel("")
    date_result.setObjectName("Result")
    date_result.setMinimumHeight(30)
    date_result.setMaximumHeight(30)
    date_bottom.addWidget(date_result, 1)
    date_copy = QPushButton("Copy")
    date_copy.setFixedSize(50, 30)
    date_copy.setVisible(False)
    date_copy.setStyleSheet("font-size:12px; padding:2px 6px;")
    date_bottom.addWidget(date_copy)
    sec2.addLayout(date_bottom)

    layout.addLayout(sec2)

    def date_to_ts():
        text = date_entry.text().strip()
        dt = _parse_date_flex(text)
        if dt is None:
            date_result.setText("Unrecognized, try: 2024/5/24 14:30:00")
            date_copy.setVisible(False)
            return
        result = str(int(dt.timestamp()))
        date_result.setText(result)
        date_copy.setVisible(True)
        try:
            date_copy.clicked.disconnect()
        except Exception:
            pass
        date_copy.clicked.connect(lambda: QApplication.clipboard().setText(result))

    date_btn.clicked.connect(date_to_ts)

    layout.addStretch()
    close = _btn("Close")
    close.clicked.connect(dlg.close)
    _btn_row(layout, close)

    dlg.exec_()


def _parse_date_flex(text: str):
    """Flexibly parse date string, return datetime or None"""
    import re
    text = text.strip()

    def mk(y, mo, d, h=0, mi=0, s=0):
        try:
            return datetime(int(y), int(mo), int(d), int(h), int(mi), int(s))
        except ValueError:
            return None

    # 20061122124313 → 14 digit pure number
    m = re.match(r'^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$', text)
    if m:
        return mk(*m.groups())

    # 20061122 → 8 digit pure number
    m = re.match(r'^(\d{4})(\d{2})(\d{2})$', text)
    if m:
        return mk(m.group(1), m.group(2), m.group(3))

    # Extract all numbers
    nums = re.findall(r'\d+', text)
    if not nums or int(nums[0]) < 1970 or int(nums[0]) > 2100:
        return None

    y = nums[0]
    mo = nums[1] if len(nums) > 1 else 1
    d = nums[2] if len(nums) > 2 else 1
    h = nums[3] if len(nums) > 3 else 0
    mi = nums[4] if len(nums) > 4 else 0
    s = nums[5] if len(nums) > 5 else 0
    return mk(y, mo, d, h, mi, s)


# ═══════════════════════════════════════════════════════════
# 5. Password Generator
# ═══════════════════════════════════════════════════════════

def show_password_generator(pet):
    dlg = _dlg(pet, "Password Generator", 440, 360)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)

    title = QLabel("Password Generator")
    title.setObjectName("Title")
    layout.addWidget(title)

    len_row = QHBoxLayout()
    len_row.addWidget(QLabel("Password length:"))
    len_spin = QSpinBox()
    len_spin.setRange(4, 64)
    len_spin.setValue(20)
    len_spin.setFixedWidth(80)
    len_row.addWidget(len_spin)
    len_row.addStretch()
    layout.addLayout(len_row)

    cb_upper = QCheckBox("Uppercase  A-Z")
    cb_upper.setChecked(True)
    layout.addWidget(cb_upper)

    cb_lower = QCheckBox("Lowercase  a-z")
    cb_lower.setChecked(True)
    layout.addWidget(cb_lower)

    cb_digit = QCheckBox("Digits  0-9")
    cb_digit.setChecked(True)
    layout.addWidget(cb_digit)

    cb_sym = QCheckBox("Symbols  !@#$%^&*")
    cb_sym.setChecked(True)
    layout.addWidget(cb_sym)

    result_entry = QLineEdit()
    result_entry.setReadOnly(True)
    result_entry.setStyleSheet(
        "font-size: 20px; padding: 14px; font-family: Consolas;")
    layout.addWidget(result_entry)

    def generate():
        chars = ""
        if cb_upper.isChecked():
            chars += string.ascii_uppercase
        if cb_lower.isChecked():
            chars += string.ascii_lowercase
        if cb_digit.isChecked():
            chars += string.digits
        if cb_sym.isChecked():
            chars += "!@#$%^&*()-_=+[]{}|;:,.<>?"
        if not chars:
            result_entry.setText("Please select at least one character set")
            return
        pwd = ''.join(secrets.choice(chars) for _ in range(len_spin.value()))
        result_entry.setText(pwd)
        QApplication.clipboard().setText(pwd)

    generate()

    gen = _primary("Generate & Copy")
    gen.clicked.connect(generate)
    close = _btn("Close")
    close.clicked.connect(dlg.close)
    _btn_row(layout, gen, close)

    dlg.exec_()


# ═══════════════════════════════════════════════════════════
# 6. QR Code Generator
# ═══════════════════════════════════════════════════════════

def show_qr_generator(pet):
    dlg = _dlg(pet, "QR Code Generator", 460, 470)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)

    title = QLabel("QR Code Generator")
    title.setObjectName("Title")
    layout.addWidget(title)

    hint = QLabel("Enter URL or any text, click generate")
    hint.setObjectName("Hint")
    layout.addWidget(hint)

    te = QTextEdit()
    te.setMaximumHeight(70)
    te.setPlaceholderText("https://example.com")
    layout.addWidget(te)

    img_label = QLabel()
    img_label.setAlignment(Qt.AlignCenter)
    img_label.setMinimumSize(220, 220)
    img_label.setMaximumSize(240, 240)
    img_label.setStyleSheet(
        "border: 1px solid #555; border-radius: 6px; background: white;")

    img_holder = QHBoxLayout()
    img_holder.addStretch()
    img_holder.addWidget(img_label)
    img_holder.addStretch()
    layout.addLayout(img_holder)

    def generate():
        text = te.toPlainText().strip()
        if not text:
            return
        try:
            import qrcode
            qr = qrcode.QRCode(version=None, box_size=10, border=2)
            qr.add_data(text)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            img.save(buf, "PNG")
            pm = QPixmap()
            pm.loadFromData(buf.getvalue())
            img_label.setPixmap(pm.scaled(
                220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:
            img_label.setText(f"  Generation failed\n  {e}")

    gen = _primary("Generate")
    gen.clicked.connect(generate)

    save_btn = QPushButton("Save Image")
    save_btn.setStyleSheet(
        "background:#3c3c3c; color:#e0e0e0; border:1px solid #555;"
        "border-radius:6px; padding:10px 20px; font-size:14px;")

    def save_qr():
        pm = img_label.pixmap()
        if pm:
            path, _ = QFileDialog.getSaveFileName(
                dlg, "Save QR Code", "qrcode.png", "PNG (*.png)")
            if path:
                pm.save(path)

    save_btn.clicked.connect(save_qr)

    close = _btn("Close")
    close.clicked.connect(dlg.close)
    _btn_row(layout, gen, save_btn, close)

    dlg.exec_()


# ═══════════════════════════════════════════════════════════
# 7. Text Statistics
# ═══════════════════════════════════════════════════════════



def show_text_stats(pet):
    dlg = _dlg(pet, "Text Statistics", 460, 420)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(8)

    title = QLabel("Text Statistics")
    title.setObjectName("Title")
    layout.addWidget(title)

    te = QTextEdit()
    te.setPlaceholderText("Paste or type text here...")
    te.setMaximumHeight(100)
    layout.addWidget(te)

    stats_widget = QWidget()
    stats_widget.setStyleSheet(
        "background:#1e1e1e; border-radius:6px;")
    sl = QVBoxLayout(stats_widget)
    sl.setContentsMargins(12, 12, 12, 12)
    sl.setSpacing(4)

    vals = {}
    for label in ("Total Characters", "Chinese Characters", "English Words",
                  "Digits", "Punctuation", "Lines", "Bytes (UTF-8)"):
        r = QHBoxLayout()
        r.setSpacing(8)
        lbl = QLabel(label)
        lbl.setFixedHeight(24)
        lbl.setStyleSheet("color:#999; font-size:13px; border:none;")
        r.addWidget(lbl, 0)
        val = QLabel("0")
        val.setFixedHeight(24)
        val.setStyleSheet(
            "color:#fff; font-size:15px; font-weight:bold;"
            "font-family:Consolas; border:none;")
        val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        r.addWidget(val, 1)
        sl.addLayout(r)
        vals[label] = val
    layout.addWidget(stats_widget)

    import re
    def update_stats():
        text = te.toPlainText()
        if not text:
            for v in vals.values():
                v.setText("0")
            return
        vals["Total Characters"].setText(str(len(text)))
        vals["Chinese Characters"].setText(str(len(re.findall(r'[一-鿿]', text))))
        vals["English Words"].setText(str(len(re.findall(r'[a-zA-Z]+', text))))
        vals["Digits"].setText(str(len(re.findall(r'\d', text))))
        import string as _string
        _punct = _string.punctuation + '，。！？、；：""''（）【】《》'
        vals["Punctuation"].setText(str(sum(1 for c in text if c in _punct)))
        vals["Lines"].setText(str(
            text.count('\n') + (1 if text and not text.endswith('\n') else 0)))
        vals["Bytes (UTF-8)"].setText(str(len(text.encode('utf-8'))))

    te.textChanged.connect(update_stats)

    close = _btn("Close")
    close.clicked.connect(dlg.close)
    _btn_row(layout, close)

    dlg.exec_()


# ═══════════════════════════════════════════════════════════
# 8. Countdown Days
# ═══════════════════════════════════════════════════════════

def show_countdown(pet):
    from PyQt5.QtCore import QSettings
    from config import SETTINGS_PATH
    import json as _json

    dlg = _dlg(pet, "Countdown Days", 480, 440)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)

    title = QLabel("Countdown Days")
    title.setObjectName("Title")
    layout.addWidget(title)

    # ── Input area ──
    row1 = QHBoxLayout()
    row1.setSpacing(8)
    name_entry = QLineEdit()
    name_entry.setPlaceholderText("Event name, e.g.: Exam")
    row1.addWidget(name_entry, 2)
    date_entry = QLineEdit()
    date_entry.setPlaceholderText("Date (any format accepted)")
    row1.addWidget(date_entry, 2)
    calc_btn = _primary("Calculate")
    row1.addWidget(calc_btn)
    layout.addLayout(row1)

    # ── Calculation result ──
    result_widget = QWidget()
    result_widget.setStyleSheet(
        "background:#1e1e1e; border-radius:6px;")
    result_widget.setVisible(False)
    result_layout = QVBoxLayout(result_widget)
    result_layout.setContentsMargins(14, 14, 14, 14)
    result_layout.setSpacing(6)

    result_name = QLabel("")
    result_name.setMinimumHeight(22)
    result_name.setStyleSheet("color:#ccc; font-size:14px; border:none;")
    result_layout.addWidget(result_name)

    result_days = QLabel("")
    result_days.setMinimumHeight(36)
    result_days.setStyleSheet(
        "color:#fff; font-size:26px; font-weight:bold;"
        "font-family:Consolas; border:none;")
    result_layout.addWidget(result_days)

    result_date = QLabel("")
    result_date.setMinimumHeight(20)
    result_date.setStyleSheet("color:#888; font-size:13px; border:none;")
    result_layout.addWidget(result_date)
    layout.addWidget(result_widget)

    # ── Saved list ──
    lst_label = QLabel("Saved countdowns:")
    lst_label.setStyleSheet("color:#999; font-size:12px; border:none;")
    layout.addWidget(lst_label)

    lst = QListWidget()
    lst.setMaximumHeight(140)
    lst.setStyleSheet(
        "QListWidget { background:#1e1e1e; border:1px solid #444; border-radius:6px;"
        "font-size:13px; padding:4px; }"
        "QListWidget::item { padding:8px 10px; border-bottom:1px solid #333; }")
    layout.addWidget(lst)

    s = QSettings(SETTINGS_PATH, QSettings.IniFormat)
    saved = s.value("countdown/items", "[]")
    try:
        items = _json.loads(saved) if isinstance(saved, str) else saved
    except Exception:
        items = []

    def normalize_date(ds):
        dt = _parse_date_flex(ds)
        return dt.strftime("%Y-%m-%d") if dt else None

    _last_result = {}   # Most recent calculation result

    def refresh_list():
        lst.clear()
        today = datetime.now().date()
        for it in items:
            try:
                d = datetime.strptime(it["date"], "%Y-%m-%d").date()
                delta = (d - today).days
                tag = f"{delta} days left" if delta > 0 else ("Today!" if delta == 0 else f"{-delta} days ago")
            except Exception:
                tag = "?"
            lst.addItem(f"{it['name']}  |  {it['date']}  |  {tag}")

    refresh_list()

    def do_calc():
        name = name_entry.text().strip()
        ds = date_entry.text().strip()
        if not name or not ds:
            return
        normalized = normalize_date(ds)
        if not normalized:
            result_name.setText("⚠ Date format not recognized")
            result_days.setText("")
            result_date.setText("")
            result_widget.setVisible(True)
            return
        # Calculate days
        today = datetime.now().date()
        d = datetime.strptime(normalized, "%Y-%m-%d").date()
        delta = (d - today).days
        if delta > 0:
            days_text = f"{delta} days left"
        elif delta == 0:
            days_text = "It's today!"
        else:
            days_text = f"{-delta} days ago"

        result_name.setText(name)
        result_days.setText(days_text)
        result_date.setText(f"Target date: {normalized}")
        result_widget.setVisible(True)

        # Save to list
        items.append({"name": name, "date": normalized})
        s.setValue("countdown/items", _json.dumps(items, ensure_ascii=False))
        s.sync()
        _last_result["name"] = name
        _last_result["date"] = normalized
        refresh_list()
        name_entry.clear()
        date_entry.clear()

    calc_btn.clicked.connect(do_calc)

    # ── Button row ──
    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)
    clear_btn = QPushButton("Clear All")
    clear_btn.setObjectName("Danger")
    clear_btn.clicked.connect(lambda: (
        items.clear(),
        s.setValue("countdown/items", "[]"),
        s.sync(),
        refresh_list(),
        result_widget.setVisible(False)
    ))
    btn_row.addWidget(clear_btn)
    btn_row.addStretch()

    def add_to_todo():
        # Prefer most recent calculation result, otherwise use selected list item
        name = _last_result.get("name", "")
        date_str = _last_result.get("date", "")
        if not name:
            row = lst.currentRow()
            if row < 0 or row >= len(items):
                return
            it = items[row]
            name = it["name"]
            date_str = it["date"]
        if pet and hasattr(pet, '_todo_items'):
            todo = {
                "text": name,
                "done": False,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "due_date": date_str,
            }
            pet._todo_items.append(todo)
            pet._save_todos()
            if hasattr(pet, 'say'):
                pet.say(f"Added to todo: {name}\nDue {date_str}", 3.0)
            _last_result.clear()
            result_widget.setVisible(False)

    todo_btn = QPushButton("Add to Todo")
    todo_btn.setStyleSheet(
        "background:#27ae60; color:white; font-weight:bold; border:none;"
        "border-radius:6px; padding:10px 20px; font-size:14px;")
    todo_btn.clicked.connect(add_to_todo)
    btn_row.addWidget(todo_btn)
    close = _btn("Close")
    close.clicked.connect(dlg.close)
    btn_row.addWidget(close)
    layout.addLayout(btn_row)

    dlg.exec_()


# ═══════════════════════════════════════════════════════════
# 9. Noise Meter
# ═══════════════════════════════════════════════════════════

def show_noise_meter(pet):
    import math

    dlg = _dlg(pet, "Noise Meter", 380, 220)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)

    title = QLabel("Ambient Noise")
    title.setObjectName("Title")
    layout.addWidget(title)

    bar_bg = QWidget()
    bar_bg.setFixedHeight(36)
    bar_bg.setStyleSheet(
        "background:#1e1e1e; border:1px solid #444; border-radius:8px;")
    bar_lo = QHBoxLayout(bar_bg)
    bar_lo.setContentsMargins(0, 0, 0, 0)
    bar_fill = QWidget()
    bar_fill.setFixedHeight(36)
    bar_fill.setStyleSheet("background:#2ecc71; border-radius:8px;")
    bar_lo.addWidget(bar_fill)
    bar_lo.addStretch()
    layout.addWidget(bar_bg)

    val_row = QHBoxLayout()
    db_label = QLabel("-- dB")
    db_label.setStyleSheet(
        "color:#fff; font-size:28px; font-weight:bold;"
        "font-family:Consolas; border:none;")
    val_row.addWidget(db_label)
    val_row.addStretch()
    level_label = QLabel("Waiting")
    level_label.setStyleSheet("color:#999; font-size:15px; border:none;")
    val_row.addWidget(level_label)
    layout.addLayout(val_row)

    running = [False]

    def update_bar(rms_val):
        db_val = 20 * math.log10(max(rms_val, 0.00001) / 0.00002)
        db_val = max(0, min(db_val, 100))
        db_label.setText(f"{db_val:.0f} dB")
        bar_fill.setFixedWidth(int(db_val / 100 * 330))
        if db_val < 40:
            bar_fill.setStyleSheet("background:#2ecc71; border-radius:8px;")
            level_label.setText("Quiet")
            level_label.setStyleSheet("color:#2ecc71; font-size:15px; border:none;")
        elif db_val < 60:
            bar_fill.setStyleSheet("background:#f39c12; border-radius:8px;")
            level_label.setText("Normal")
            level_label.setStyleSheet("color:#f39c12; font-size:15px; border:none;")
        else:
            bar_fill.setStyleSheet("background:#e74c3c; border-radius:8px;")
            level_label.setText("Noisy")
            level_label.setStyleSheet("color:#e74c3c; font-size:15px; border:none;")

        if running[0]:
            QTimer.singleShot(500, _poll)

    def _poll():
        try:
            import sounddevice as sd
            import numpy as np
            buf = sd.rec(int(16000 * 0.5), samplerate=16000, channels=1,
                         dtype='float32', blocking=True)
            rms = float(np.sqrt(np.mean(buf ** 2)))
            update_bar(rms)
        except Exception:
            if running[0]:
                QTimer.singleShot(500, _poll)

    def toggle():
        if running[0]:
            running[0] = False
            start_btn.setText("Start Monitoring")
            start_btn.setObjectName("Primary")
            start_btn.setStyleSheet(
                "QPushButton#Primary { background:#2980b9; color:white;"
                "font-weight:bold; border:none; border-radius:6px;"
                "padding:10px 20px; font-size:14px; }")
        else:
            running[0] = True
            start_btn.setText("Stop")
            start_btn.setObjectName("Danger")
            start_btn.setStyleSheet(
                "QPushButton#Danger { background:#c0392b; color:white;"
                "font-weight:bold; border:none; border-radius:6px;"
                "padding:10px 20px; font-size:14px; }")
            _poll()

    QTimer.singleShot(300, _poll)

    start_btn = _primary("Start Monitoring")
    start_btn.clicked.connect(toggle)
    close = _btn("Close")
    close.clicked.connect(lambda: (running.__setitem__(0, False), dlg.close()))
    _btn_row(layout, start_btn, close)

    dlg.finished.connect(lambda: running.__setitem__(0, False))
    dlg.exec_()


# ═══════════════════════════════════════════════════════════
# 10. Stopwatch
# ═══════════════════════════════════════════════════════════

def show_stopwatch(pet):
    import time as _time

    dlg = _dlg(pet, "Stopwatch", 360, 320)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)

    title = QLabel("Stopwatch")
    title.setObjectName("Title")
    layout.addWidget(title)

    # Large time display
    time_label = QLabel("00:00.00")
    time_label.setAlignment(Qt.AlignCenter)
    time_label.setStyleSheet(
        "color:#fff; font-size:48px; font-weight:bold;"
        "font-family:Consolas, monospace; border:none;"
        "padding:10px 0;")
    layout.addWidget(time_label)

    # Lap records list
    laps_list = QListWidget()
    laps_list.setMaximumHeight(120)
    laps_list.setStyleSheet(
        "QListWidget { background:#1e1e1e; border:1px solid #444;"
        "border-radius:6px; font-size:13px; }"
        "QListWidget::item { padding:6px 10px; color:#aaa; }")
    layout.addWidget(laps_list)

    state = {"running": False, "elapsed": 0.0, "start_time": 0.0,
             "laps": [], "timer": None}

    def fmt(sec):
        m = int(sec // 60)
        s = sec % 60
        return f"{m:02d}:{s:05.2f}"

    def update_display():
        if state["running"]:
            state["elapsed"] = _time.time() - state["start_time"]
        time_label.setText(fmt(state["elapsed"]))

    def _tick():
        if state["running"]:
            update_display()
            QTimer.singleShot(30, _tick)

    def start_stop():
        if state["running"]:
            state["elapsed"] = _time.time() - state["start_time"]
            state["running"] = False
            start_btn.setText("Resume")
        else:
            state["start_time"] = _time.time() - state["elapsed"]
            state["running"] = True
            start_btn.setText("Pause")
            _tick()
        update_display()

    def reset():
        state["running"] = False
        state["elapsed"] = 0.0
        state["laps"].clear()
        laps_list.clear()
        start_btn.setText("Start")
        update_display()

    def lap():
        if not state["running"] and state["elapsed"] == 0:
            return
        current = state["elapsed"] if not state["running"] else _time.time() - state["start_time"]
        prev = state["laps"][-1][1] if state["laps"] else 0.0
        split = current - prev
        state["laps"].append((current, current))
        n = len(state["laps"])
        laps_list.insertItem(0, f"#{n}  Split {fmt(current)}  Interval {fmt(split)}")

    # Buttons
    btn_top = QHBoxLayout()
    btn_top.setSpacing(8)
    start_btn = _primary("Start")
    start_btn.clicked.connect(start_stop)
    lap_btn = QPushButton("Lap")
    lap_btn.clicked.connect(lap)
    reset_btn = QPushButton("Reset")
    reset_btn.setObjectName("Danger")
    reset_btn.clicked.connect(reset)
    btn_top.addWidget(start_btn)
    btn_top.addWidget(lap_btn)
    btn_top.addWidget(reset_btn)
    layout.addLayout(btn_top)

    close = _btn("Close")
    close.clicked.connect(lambda: (reset(), dlg.close()))
    _btn_row(layout, close)

    dlg.exec_()

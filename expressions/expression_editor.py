"""Expression Editor — Pixel art canvas + management dialog"""

from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QFont, QPixmap, QImage,
)
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QColorDialog, QSizePolicy,
)

from .expression_manager import PROTECTED_NAMES

GRID = 16
CELL_PX = 20          # Pixel size per cell on canvas
PREVIEW_SCALE = 4     # Preview scale (16*4=64px)


class PixelCanvas(QWidget):
    """16x16 pixel grid canvas, supports mouse click/drag drawing"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid = [[None for _ in range(GRID)] for _ in range(GRID)]
        self._current_color = (255, 200, 0)  # Default yellow
        self._drawing = False
        self._erasing = False
        w = GRID * CELL_PX
        self.setFixedSize(w, w)
        self.setMouseTracking(True)

    def set_grid(self, grid: list):
        """Load an existing grid"""
        self._grid = [[None for _ in range(GRID)] for _ in range(GRID)]
        for y in range(min(GRID, len(grid))):
            row = grid[y]
            for x in range(min(GRID, len(row) if row else 0)):
                px = row[x]
                if px is not None:
                    if isinstance(px, (list, tuple)) and len(px) == 3:
                        self._grid[y][x] = tuple(int(c) for c in px)
        self.update()

    def get_grid(self) -> list:
        """Return the current 16x16 grid (deep copy)"""
        return [list(row) for row in self._grid]

    def set_color(self, rgb: tuple):
        self._current_color = tuple(int(c) for c in rgb)

    def get_color(self) -> tuple:
        return self._current_color

    def clear_all(self):
        self._grid = [[None for _ in range(GRID)] for _ in range(GRID)]
        self.update()

    def fill_all(self):
        for y in range(GRID):
            for x in range(GRID):
                self._grid[y][x] = self._current_color
        self.update()

    # ── Mouse Interaction ──────────────────────────────────

    def _pixel_at(self, pos):
        x = pos.x() // CELL_PX
        y = pos.y() // CELL_PX
        if 0 <= x < GRID and 0 <= y < GRID:
            return x, y
        return None, None

    def mousePressEvent(self, event):
        x, y = self._pixel_at(event.pos())
        if x is None:
            return
        if event.button() == Qt.LeftButton:
            self._drawing = True
            self._grid[y][x] = self._current_color
        elif event.button() == Qt.RightButton:
            self._erasing = True
            self._grid[y][x] = None
        self.update()

    def mouseMoveEvent(self, event):
        x, y = self._pixel_at(event.pos())
        if x is None:
            return
        if self._drawing:
            self._grid[y][x] = self._current_color
            self.update()
        elif self._erasing:
            self._grid[y][x] = None
            self.update()

    def mouseReleaseEvent(self, event):
        self._drawing = False
        self._erasing = False

    # ── Rendering ──────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # Background
        painter.fillRect(self.rect(), QColor(55, 55, 60))

        # Grid lines
        line_pen = QPen(QColor(75, 75, 80))
        line_pen.setWidth(1)
        painter.setPen(line_pen)
        for i in range(GRID + 1):
            pos = i * CELL_PX
            painter.drawLine(pos, 0, pos, GRID * CELL_PX)
            painter.drawLine(0, pos, GRID * CELL_PX, pos)

        # Pixel blocks
        for y in range(GRID):
            for x in range(GRID):
                color = self._grid[y][x]
                if color is not None:
                    painter.fillRect(
                        x * CELL_PX + 1, y * CELL_PX + 1,
                        CELL_PX - 1, CELL_PX - 1,
                        QColor(*color)
                    )

        painter.end()


# ── Preset Color Palette ────────────────────────────────────

PRESET_COLORS = [
    (255, 200, 0),     # Yellow (face)
    (30, 30, 30),      # Black (eyes/mouth/outline)
    (255, 255, 255),   # White (eye whites/teeth)
    (255, 100, 100),   # Red (tongue/blush)
    (100, 180, 255),   # Blue (sweat drops/bubbles/ice)
    (255, 150, 150),   # Pink (flush)
    (130, 70, 180),    # Purple (question mark)
    (220, 60, 60),     # Dark red (red cross/veins)
    (150, 210, 255),   # Light blue (cold/ice crystals)
    (255, 80, 130),    # Pink hat
    (255, 220, 100),   # Gold (pom-pom)
    (160, 160, 160),   # Gray (whiskers)
    (210, 190, 60),    # Golden eye (cat pupil)
    (220, 220, 240),   # White-blue (ice pack)
    (240, 100, 100),   # Tongue red
    (180, 220, 255),   # Light blue (drool)
]


class ExpressionEditorDialog(QDialog):
    """Expression manager dialog — list + canvas + palette + preview + CRUD"""

    def __init__(self, character, parent=None):
        super().__init__(parent)
        self._character = character
        self._manager = character.expression_manager
        self._dirty = False      # Whether there are unsaved changes
        self._editing_name = ""  # Currently editing expression name

        self._build_ui()
        self._load_list()

        # Default to first item selected
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
            self._on_select(0)

    def _build_ui(self):
        self.setWindowTitle("Expression Manager")
        self.setWindowFlags(self.windowFlags() | Qt.Tool)
        self.setFixedSize(720, 570)
        self.setStyleSheet("""
            QDialog { background: #2b2b2b; color: #e0e0e0; }
            QListWidget {
                background: #1e1e1e; color: #e0e0e0; border: 1px solid #444;
                font-size: 13px; padding: 4px;
            }
            QListWidget::item { padding: 4px 8px; }
            QListWidget::item:selected { background: #3a6ea5; }
            QLineEdit {
                background: #3a3a3a; color: #e0e0e0; border: 1px solid #555;
                padding: 4px 8px; font-size: 13px;
            }
            QLineEdit:focus { border-color: #ffc800; }
            QPushButton {
                background: #3a3a3a; color: #e0e0e0; border: 1px solid #555;
                padding: 5px 14px; font-size: 13px; border-radius: 3px;
            }
            QPushButton:hover { background: #4a4a4a; border-color: #ffc800; }
            QPushButton:pressed { background: #2a2a2a; }
            QPushButton#btn_save { background: #2d6a4f; border-color: #40916c; }
            QPushButton#btn_save:hover { background: #40916c; }
            QPushButton#btn_del { background: #6a2d2d; border-color: #c0392b; }
            QPushButton#btn_del:hover { background: #922b21; }
            QLabel { color: #c0c0c0; font-size: 12px; }
        """)

        main_layout = QHBoxLayout(self)

        # ── Left: Expression List ───────────────────────────
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Expressions (drag to reorder)"))
        self._list = QListWidget()
        self._list.setDragDropMode(self._list.InternalMove)
        self._list.setFixedWidth(150)
        self._list.currentRowChanged.connect(self._on_select)
        left_layout.addWidget(self._list)

        # Sort buttons
        sort_layout = QHBoxLayout()
        btn_up = QPushButton("▲")
        btn_up.setFixedWidth(32)
        btn_up.clicked.connect(self._move_up)
        btn_dn = QPushButton("▼")
        btn_dn.setFixedWidth(32)
        btn_dn.clicked.connect(self._move_down)
        sort_layout.addWidget(btn_up)
        sort_layout.addWidget(btn_dn)
        sort_layout.addStretch()
        left_layout.addLayout(sort_layout)
        main_layout.addLayout(left_layout)

        # ── Right: Canvas + Controls ────────────────────────
        right_layout = QVBoxLayout()

        # Top: Canvas + Preview + Palette
        top_area = QHBoxLayout()

        # Canvas
        self._canvas = PixelCanvas()
        top_area.addWidget(self._canvas)

        # Preview + Palette
        side_layout = QVBoxLayout()

        # Preview
        side_layout.addWidget(QLabel("Preview (64x64)"))
        self._preview = QLabel()
        self._preview.setFixedSize(72, 72)
        self._preview.setStyleSheet("background: #1e1e1e; border: 1px solid #444;")
        self._preview.setAlignment(Qt.AlignCenter)
        side_layout.addWidget(self._preview)

        # Palette
        side_layout.addWidget(QLabel("Palette"))
        palette_widget = QWidget()
        palette_layout = QHBoxLayout(palette_widget)
        palette_layout.setContentsMargins(0, 0, 0, 0)
        palette_layout.setSpacing(2)

        # Two columns of preset colors
        col_layouts = [QVBoxLayout(), QVBoxLayout()]
        for i, color in enumerate(PRESET_COLORS):
            btn = QPushButton()
            btn.setFixedSize(22, 22)
            btn.setStyleSheet(
                f"background: rgb({color[0]},{color[1]},{color[2]}); "
                "border: 1px solid #555; border-radius: 2px;"
            )
            btn.clicked.connect(lambda checked, c=color: self._pick_preset(c))
            col_layouts[i % 2].addWidget(btn)

        for cl in col_layouts:
            palette_layout.addLayout(cl)

        # Current color + color picker
        cur_color_layout = QVBoxLayout()
        self._cur_color_btn = QPushButton()
        self._cur_color_btn.setFixedSize(30, 30)
        self._update_color_btn()
        self._cur_color_btn.clicked.connect(self._pick_custom)
        cur_color_layout.addWidget(self._cur_color_btn)
        cur_color_layout.addStretch()
        palette_layout.addLayout(cur_color_layout)

        side_layout.addWidget(palette_widget)

        # Fill / Clear
        tool_layout = QHBoxLayout()
        btn_fill = QPushButton("Fill All")
        btn_fill.clicked.connect(lambda: self._canvas.fill_all())
        btn_clear = QPushButton("Clear Canvas")
        btn_clear.clicked.connect(lambda: self._canvas.clear_all())
        tool_layout.addWidget(btn_fill)
        tool_layout.addWidget(btn_clear)
        side_layout.addLayout(tool_layout)

        side_layout.addStretch()
        top_area.addLayout(side_layout)
        right_layout.addLayout(top_area)

        # ── Bottom: Name + Action Buttons ───────────────────
        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(QLabel("Expression Name:"))
        self._name_input = QLineEdit()
        self._name_input.setFixedWidth(160)
        self._name_input.textChanged.connect(self._on_name_changed)
        bottom_layout.addWidget(self._name_input)
        bottom_layout.addStretch()

        btn_new = QPushButton("New")
        btn_new.clicked.connect(self._new_expression)
        bottom_layout.addWidget(btn_new)

        self._btn_save = QPushButton("Save")
        self._btn_save.setObjectName("btn_save")
        self._btn_save.clicked.connect(self._save_current)
        bottom_layout.addWidget(self._btn_save)

        btn_rename = QPushButton("Rename")
        btn_rename.clicked.connect(self._rename_current)
        bottom_layout.addWidget(btn_rename)

        self._btn_del = QPushButton("Delete")
        self._btn_del.setObjectName("btn_del")
        self._btn_del.clicked.connect(self._delete_current)
        bottom_layout.addWidget(self._btn_del)

        right_layout.addLayout(bottom_layout)

        # Second row: Import/Export + Close
        io_layout = QHBoxLayout()
        io_layout.addStretch()
        btn_export = QPushButton("Export Skin Pack")
        btn_export.clicked.connect(self._export_pack)
        io_layout.addWidget(btn_export)
        btn_import = QPushButton("Import Skin Pack")
        btn_import.clicked.connect(self._import_pack)
        io_layout.addWidget(btn_import)
        io_layout.addSpacing(16)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self._close)
        io_layout.addWidget(btn_close)
        right_layout.addLayout(io_layout)
        main_layout.addLayout(right_layout)

    # ── List Operations ──────────────────────────────────────

    def _load_list(self):
        """Load expression list from manager, protected expressions marked with [Lock]"""
        self._list.blockSignals(True)
        self._list.clear()
        for name in self._manager.get_names():
            label = f" {name} [Lock]" if name in PROTECTED_NAMES else f"   {name}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, name)
            self._list.addItem(item)
        self._list.blockSignals(False)

    def _on_select(self, row: int):
        """Select an expression in the list -> load onto canvas"""
        if row < 0:
            return
        # Prompt if there are unsaved changes
        if self._dirty and self._editing_name:
            self._ask_save_before_switch(row)
            return

        name = self._list.item(row).data(Qt.UserRole)
        self._editing_name = name
        self._name_input.blockSignals(True)
        self._name_input.setText(name)
        self._name_input.blockSignals(False)

        # Protected expressions: disable rename input and delete button, canvas still editable
        is_protected = name in PROTECTED_NAMES
        self._name_input.setEnabled(not is_protected)
        self._btn_del.setEnabled(not is_protected)

        grid = self._manager.get_grid(name)
        if grid:
            self._canvas.set_grid(grid)
        self._dirty = False
        self._update_preview()

    def _on_name_changed(self, text: str):
        self._dirty = True

    def _ask_save_before_switch(self, target_row: int):
        """Ask whether to save before switching"""
        reply = QMessageBox.question(
            self, "Unsaved Changes",
            f"\"{self._editing_name}\" has unsaved changes.\nSave before switching?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if reply == QMessageBox.Save:
            self._save_current()
            self._list.setCurrentRow(target_row)
        elif reply == QMessageBox.Discard:
            self._dirty = False
            self._list.setCurrentRow(target_row)
        # Cancel -> do nothing

    # ── Preview Update ──────────────────────────────────────

    def _update_preview(self):
        """Render the current canvas as a 64x64 QPixmap preview"""
        grid = self._canvas.get_grid()
        img = QImage(GRID, GRID, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        for y in range(GRID):
            for x in range(GRID):
                color = grid[y][x]
                if color is not None:
                    img.setPixelColor(x, y, QColor(*color))
        pixmap = QPixmap.fromImage(img).scaled(
            GRID * PREVIEW_SCALE, GRID * PREVIEW_SCALE,
            Qt.KeepAspectRatio, Qt.FastTransformation,
        )
        self._preview.setPixmap(pixmap)

    # ── Palette ───────────────────────────────────────────────

    def _pick_preset(self, color: tuple):
        self._canvas.set_color(color)
        self._update_color_btn()

    def _pick_custom(self):
        c = QColorDialog.getColor(
            QColor(*self._canvas.get_color()), self, "Choose Color",
        )
        if c.isValid():
            rgb = (c.red(), c.green(), c.blue())
            self._canvas.set_color(rgb)
            self._update_color_btn()

    def _update_color_btn(self):
        c = self._canvas.get_color()
        self._cur_color_btn.setStyleSheet(
            f"background: rgb({c[0]},{c[1]},{c[2]}); "
            "border: 2px solid #ffc800; border-radius: 3px;"
        )

    # ── CRUD Operations ─────────────────────────────────────

    def _new_expression(self):
        """Create new expression: clear canvas + default name"""
        if self._dirty:
            reply = QMessageBox.question(
                self, "Unsaved", "Current expression has unsaved changes. Discard?",
                QMessageBox.Discard | QMessageBox.Cancel,
            )
            if reply != QMessageBox.Discard:
                return

        # Find a non-conflicting default name
        existing = set(self._manager.get_names())
        base = "new_expr"
        name = base
        idx = 1
        while name in existing:
            name = f"{base}{idx}"
            idx += 1

        self._canvas.clear_all()
        self._editing_name = name
        self._dirty = True
        self._name_input.blockSignals(True)
        self._name_input.setText(name)
        self._name_input.blockSignals(False)
        self._update_preview()

    def _save_current(self):
        """Save current canvas to ExpressionManager"""
        if not self._editing_name:
            return
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Expression name cannot be empty.")
            return

        grid = self._canvas.get_grid()

        # If it's a new name or a rename
        if name != self._editing_name:
            if self._manager.exists(name) and name != self._editing_name:
                QMessageBox.warning(self, "Error", f"Name \"{name}\" already exists.")
                return
            if self._manager.exists(self._editing_name):
                # Rename
                self._manager.rename(self._editing_name, name)
            else:
                # Create new
                self._manager.create(name, grid)
        else:
            self._manager.save(name, grid)

        self._editing_name = name
        self._dirty = False
        self._load_list()

        # Re-select
        for i in range(self._list.count()):
            if self._list.item(i).text() == name:
                self._list.setCurrentRow(i)
                break

    def _rename_current(self):
        """Rename the current expression"""
        if not self._editing_name:
            return
        new_name, ok = QLineEdit.getText(
            self, "Rename", "New name:", text=self._editing_name,
        )
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()
        if new_name == self._editing_name:
            return
        if self._manager.exists(new_name):
            QMessageBox.warning(self, "Error", f"Name \"{new_name}\" already exists.")
            return
        if self._manager.rename(self._editing_name, new_name):
            self._editing_name = new_name
            self._name_input.blockSignals(True)
            self._name_input.setText(new_name)
            self._name_input.blockSignals(False)
            self._dirty = False
            self._load_list()
            for i in range(self._list.count()):
                if self._list.item(i).text() == new_name:
                    self._list.setCurrentRow(i)
                    break

    def _delete_current(self):
        """Delete the current expression"""
        if not self._editing_name or self._manager.count() <= 1:
            QMessageBox.warning(self, "Cannot Delete", "At least one expression must be kept.")
            return
        reply = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete expression \"{self._editing_name}\"?\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        if self._manager.delete(self._editing_name):
            self._dirty = False
            self._editing_name = ""
            self._load_list()
            if self._list.count() > 0:
                self._list.setCurrentRow(0)

    # ── Sorting ───────────────────────────────────────────────

    def _move_up(self):
        row = self._list.currentRow()
        if row <= 0:
            return
        name = self._list.item(row).text()
        if self._manager.move_up(name):
            self._load_list()
            self._list.setCurrentRow(row - 1)

    def _move_down(self):
        row = self._list.currentRow()
        if row < 0 or row >= self._list.count() - 1:
            return
        name = self._list.item(row).text()
        if self._manager.move_down(name):
            self._load_list()
            self._list.setCurrentRow(row + 1)

    # ── Import / Export Skin Pack ───────────────────────────

    def _export_pack(self):
        from PyQt5.QtWidgets import QFileDialog
        import os, zipfile, datetime

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Skin Pack",
            os.path.join(os.path.expanduser("~"), "Desktop", "face_skin_pack.petpack"),
            "Skin Pack (*.petpack)",
        )
        if not path:
            return

        expr_dir = self._manager._dir
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in os.listdir(expr_dir):
                if fname.endswith(".json"):
                    zf.write(os.path.join(expr_dir, fname), fname)
            # Also write manifest
            manifest = os.path.join(expr_dir, "manifest.json")
            if os.path.isfile(manifest):
                zf.write(manifest, "manifest.json")

        QMessageBox.information(self, "Export Successful", f"Skin pack saved to:\n{path}")

    def _import_pack(self):
        from PyQt5.QtWidgets import QFileDialog
        import os, zipfile, tempfile, shutil

        path, _ = QFileDialog.getOpenFileName(
            self, "Import Skin Pack", "", "Skin Pack (*.petpack);;All Files (*)",
        )
        if not path:
            return

        # Preview pack contents
        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = [n for n in zf.namelist() if n.endswith(".json") and n != "manifest.json"]
        except zipfile.BadZipFile:
            QMessageBox.warning(self, "Error", "Invalid skin pack file.")
            return

        # Check for conflicts
        existing = set(self._manager.get_names())
        conflicts = [n.replace(".json", "") for n in names if n.replace(".json", "") in existing]
        conflict_protected = [n for n in conflicts if n in PROTECTED_NAMES]
        conflict_normal = [n for n in conflicts if n not in PROTECTED_NAMES]

        preview_lines = [f"Pack contains {len(names)} expressions:"]
        for n in names:
            ename = n.replace(".json", "")
            tag = ""
            if ename in PROTECTED_NAMES:
                tag = " [System protected, will skip]"
            elif ename in existing:
                tag = " [Will overwrite]"
            else:
                tag = " [New]"
            preview_lines.append(f"  {ename}{tag}")

        msg = "\n".join(preview_lines)
        msg += "\n\nConfirm import?"
        reply = QMessageBox.question(self, "Import Preview", msg, QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        # Extract to temp directory then copy
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(tmpdir)
            expr_dir = self._manager._dir
            for fname in names:
                ename = fname.replace(".json", "")
                if ename in PROTECTED_NAMES:
                    continue  # Skip protected expressions
                src = os.path.join(tmpdir, fname)
                dst = os.path.join(expr_dir, fname)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)

        # Reload manager
        self._manager = self._character.expression_manager
        # Re-initialize manager
        from .expression_manager import ExpressionManager
        new_mgr = ExpressionManager()
        self._manager._names = new_mgr._names
        self._manager._grids = new_mgr._grids
        self._manager._save_manifest()
        self._load_list()
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

        QMessageBox.information(self, "Import Complete", f"Successfully imported {len(names) - len(conflict_protected)} expressions.")

    # ── Close ───────────────────────────────────────────────

    def _close(self):
        if self._dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                f"\"{self._editing_name}\" has unsaved changes.\nSave before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Cancel:
                return
            if reply == QMessageBox.Save:
                self._save_current()
        self.accept()

    def closeEvent(self, event):
        """Auto-save order after drag reordering"""
        new_order = []
        for i in range(self._list.count()):
            new_order.append(self._list.item(i).text())
        self._manager.set_order(new_order)
        super().closeEvent(event)

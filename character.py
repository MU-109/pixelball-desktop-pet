"""Pixel character rendering — 16x16 pixel grid, loaded from ExpressionManager, rendered with QPainter.fillRect scaled up"""

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QColor, QPainter
import config as cfg
from expressions import ExpressionManager


class PixelBall(QObject):
    """Pixel yellow-face character — 16x16 grid, all expressions managed by ExpressionManager"""

    expression_changed = pyqtSignal(str)
    GRID = cfg.PIXEL_SIZE

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expr_manager = ExpressionManager()
        self._expressions: dict[str, list] = {}
        self._current_expr = "idle"
        self._scale = cfg.PIXEL_SCALE

        # First run: export expressions from legacy procedural methods to JSON
        if self._expr_manager.count() == 0:
            self._migrate_legacy()
        self._load_expressions()

    def _migrate_legacy(self):
        """One-time migration: generate all expressions using old _build_* methods and export as JSON files"""
        from expressions._legacy_builder import build_all
        build_all(self)
        self._expr_manager.export_from_pixelball(self)

    def _load_expressions(self):
        """Load all expressions from ExpressionManager into memory cache"""
        self._expressions.clear()
        for name in self._expr_manager.get_names():
            grid = self._expr_manager.get_grid(name)
            if grid is not None:
                self._expressions[name] = grid
        # Fallback: at least one empty grid
        if not self._expressions:
            self._expressions["idle"] = [[None] * self.GRID for _ in range(self.GRID)]
            self._expr_manager.create("idle", self._expressions["idle"])
        # Ensure current expression is valid
        if self._current_expr not in self._expressions:
            names = self._expr_manager.get_names()
            self._current_expr = names[0] if names else "idle"

    def refresh_from_disk(self):
        """Called after UI editing, reload all expressions from disk and refresh current expression"""
        self._expr_manager = ExpressionManager()
        self._load_expressions()

    @property
    def expression_manager(self):
        return self._expr_manager

    # ── Public interface ──────────────────────────────────────

    def set_expression(self, name):
        if name in self._expressions and name != self._current_expr:
            self._current_expr = name
            self.expression_changed.emit(name)

    def get_expression(self):
        return self._current_expr

    def get_current_grid(self):
        return self._expressions.get(self._current_expr, self._expressions.get("idle"))

    def get_grid_for(self, name):
        return self._expressions.get(name)

    def register_custom_expression(self, name, grid):
        """Register a custom 16x16 expression (save to memory and persist to disk)"""
        if len(grid) == self.GRID and len(grid[0]) == self.GRID:
            self._expressions[name] = grid
            self._expr_manager.create(name, grid)
            return True
        return False

    def render(self, painter: QPainter, offset_x=0, offset_y=0, scale=None):
        """Render current expression"""
        if scale is None:
            scale = self._scale
        grid = self.get_current_grid()
        if grid is None:
            return
        for y in range(self.GRID):
            for x in range(self.GRID):
                color = grid[y][x]
                if color is not None:
                    painter.fillRect(
                        offset_x + x * scale, offset_y + y * scale,
                        scale, scale, QColor(*color)
                    )

    def render_expression(self, painter, name, offset_x=0, offset_y=0, scale=None):
        """Render specified expression (does not change current state)"""
        if scale is None:
            scale = self._scale
        grid = self._expressions.get(name, self._expressions.get("idle"))
        if grid is None:
            return
        for y in range(self.GRID):
            for x in range(self.GRID):
                color = grid[y][x]
                if color is not None:
                    painter.fillRect(
                        offset_x + x * scale, offset_y + y * scale,
                        scale, scale, QColor(*color)
                    )

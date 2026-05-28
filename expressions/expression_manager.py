"""Expression manager — manages loading, saving, CRUD and ordering of all expressions in the expressions/ directory"""

import json
import os

MANIFEST_FILE = "manifest.json"

# System-bound expressions — cannot be deleted or renamed (but pixels can be edited)
PROTECTED_NAMES = {
    "idle", "happy", "sad", "sleepy", "surprised",
    "pout", "dizzy", "drink", "eye_mask",
}


class ExpressionManager:
    """Manages JSON files for all expressions in the expressions/ directory"""

    def __init__(self, expressions_dir: str = None):
        if expressions_dir is None:
            expressions_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "expressions",
            )
        self._dir = expressions_dir
        self._grids: dict[str, list] = {}  # name -> 16x16 grid
        self._names: list[str] = []        # Ordered expression name list
        os.makedirs(self._dir, exist_ok=True)

        # Try loading from JSON; if directory is empty, export from PixelBall
        if not self._load_manifest():
            # First run, will be populated later by export_from_pixelball
            pass
        else:
            self._load_all_grids()

    # ── Query ────────────────────────────────────────────

    def get_names(self) -> list[str]:
        """Return ordered list of expression names"""
        return list(self._names)

    def get_grid(self, name: str):
        """Return 16x16 grid for the specified expression, returns None if not found"""
        return self._grids.get(name)

    def exists(self, name: str) -> bool:
        return name in self._grids

    def count(self) -> int:
        return len(self._names)

    # ── CRUD ────────────────────────────────────────────

    def create(self, name: str, grid: list) -> bool:
        """Create new expression JSON and append to end of manifest"""
        if self.exists(name) or not name.strip():
            return False
        self._grids[name] = grid
        self._names.append(name)
        self._save_json(name, grid)
        self._save_manifest()
        return True

    def save(self, name: str, grid: list) -> bool:
        """Overwrite existing expression"""
        if not self.exists(name):
            return self.create(name, grid)
        self._grids[name] = grid
        self._save_json(name, grid)
        return True

    def rename(self, old_name: str, new_name: str) -> bool:
        """Rename expression (protected expressions cannot be renamed)"""
        if old_name in PROTECTED_NAMES:
            return False
        if old_name not in self._grids or not new_name.strip():
            return False
        if old_name == new_name:
            return True
        if new_name in self._grids:
            return False

        # Save new file
        grid = self._grids[old_name]
        self._save_json(new_name, grid)
        # Delete old file
        old_path = self._json_path(old_name)
        try:
            os.remove(old_path)
        except OSError:
            pass
        # Update memory
        self._grids[new_name] = grid
        del self._grids[old_name]
        idx = self._names.index(old_name)
        self._names[idx] = new_name
        self._save_manifest()
        return True

    def delete(self, name: str) -> bool:
        """Delete expression (protected expressions cannot be deleted, minimum 1 must remain)"""
        if name in PROTECTED_NAMES:
            return False
        if name not in self._grids or self.count() <= 1:
            return False
        # Delete JSON file
        try:
            os.remove(self._json_path(name))
        except OSError:
            pass
        del self._grids[name]
        self._names.remove(name)
        self._save_manifest()
        return True

    # ── Ordering ────────────────────────────────────────────

    def move_to(self, name: str, new_index: int) -> bool:
        """Move specified expression to a new position (index is the new absolute position)"""
        if name not in self._names:
            return False
        old_index = self._names.index(name)
        if old_index == new_index:
            return True
        self._names.pop(old_index)
        # If original position is before new position, adjust index after removal
        if old_index < new_index:
            new_index -= 1
        new_index = max(0, min(new_index, len(self._names)))
        self._names.insert(new_index, name)
        self._save_manifest()
        return True

    def move_up(self, name: str) -> bool:
        """Move up one position"""
        if name not in self._names:
            return False
        idx = self._names.index(name)
        if idx <= 0:
            return False
        return self.move_to(name, idx - 1)

    def move_down(self, name: str) -> bool:
        """Move down one position"""
        if name not in self._names:
            return False
        idx = self._names.index(name)
        if idx >= len(self._names) - 1:
            return False
        return self.move_to(name, idx + 1)

    def set_order(self, names: list[str]) -> bool:
        """Completely overwrite ordering with a new list (for saving after QListWidget drag-and-drop)"""
        if set(names) != set(self._names):
            return False
        self._names = list(names)
        self._save_manifest()
        return True

    # ── Import / Export ──────────────────────────────────────

    def export_from_pixelball(self, pixelball) -> bool:
        """Export all expression grids from old PixelBall instance to JSON (one-time migration)
        Only executes when expressions/ directory is empty.
        """
        if self._names:
            return False  # Data already exists, skip

        # Need to import PixelBall to call its build methods
        # pixelball is already passed by caller, its self._expressions is populated
        for name, grid in pixelball._expressions.items():
            self._names.append(name)
            self._grids[name] = grid
            self._save_json(name, grid)
        self._save_manifest()
        return True

    # ── Internal methods ─────────────────────────────────────

    def _json_path(self, name: str) -> str:
        safe = name.replace("/", "_").replace("\\", "_")
        return os.path.join(self._dir, f"{safe}.json")

    def _manifest_path(self) -> str:
        return os.path.join(self._dir, MANIFEST_FILE)

    def _load_manifest(self) -> bool:
        """Load manifest.json, returns success status"""
        mp = self._manifest_path()
        if not os.path.isfile(mp):
            return False
        try:
            with open(mp, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._names = data.get("expressions", [])
            return True
        except (json.JSONDecodeError, KeyError):
            return False

    def _save_manifest(self):
        with open(self._manifest_path(), "w", encoding="utf-8") as f:
            json.dump({"version": 1, "expressions": self._names}, f, ensure_ascii=False, indent=2)

    def _load_all_grids(self):
        """Load all expression JSON files in manifest order"""
        self._grids.clear()
        for name in self._names:
            grid = self._load_json(name)
            if grid is not None:
                self._grids[name] = grid

    def _load_json(self, name: str):
        """Load a single expression's 16x16 grid from JSON file"""
        jp = self._json_path(name)
        if not os.path.isfile(jp):
            return None
        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("grid")
        except (json.JSONDecodeError, KeyError):
            return None

    def _save_json(self, name: str, grid: list):
        """Write a single expression to JSON file"""
        # Convert tuples to lists for JSON serialization
        serializable = []
        for row in grid:
            new_row = []
            for px in row:
                if px is None:
                    new_row.append(None)
                elif isinstance(px, (list, tuple)):
                    new_row.append([int(c) for c in px])
                else:
                    new_row.append(None)
            serializable.append(new_row)

        with open(self._json_path(name), "w", encoding="utf-8") as f:
            json.dump({"name": name, "grid": serializable}, f, ensure_ascii=False, indent=2)

"""Expression migration builder — one-time export of legacy procedural expressions to JSON
Only used when expressions/ directory is empty; no longer needed after migration.
"""

import math
import config as cfg

GRID = cfg.PIXEL_SIZE
FACE_CX = 7.5
FACE_CY = 7.5
FACE_OUTER_R = 7.5
FACE_INNER_R = 6.5
FACE_BORDER = (30, 30, 30)

# Complete list of all known legacy expressions (independent of config.py, for migration tool use only)
LEGACY_EXPRESSIONS = [
    "idle", "happy", "sad", "sleepy", "surprised", "blink",
    "pout", "dizzy", "drink", "eye_mask",
    "angry", "nervous", "satisfied", "pleading", "thinking",
    "sick", "overheat", "cold", "deep_sleep", "quiet",
    "cool", "birthday", "ghost", "cat_face", "furious",
]


def build_all(pixelball):
    """Generate all expression grids from old _build_* methods, populate pixelball._expressions"""
    builder = _Builder()
    for name in LEGACY_EXPRESSIONS:
        method = getattr(builder, f"_build_{name}", None)
        pixelball._expressions[name] = method() if method else builder._build_idle()


class _Builder:
    """Internal builder — contains all grid utility and expression build methods"""

    def __init__(self):
        self._body_color = cfg.BALL_BODY_COLOR
        self._eye_color = cfg.BALL_EYE_COLOR
        self._mouth_color = cfg.BALL_MOUTH_COLOR

    @staticmethod
    def _blank():
        return [[None for _ in range(GRID)] for _ in range(GRID)]

    @staticmethod
    def _dist(x, y, cx, cy):
        return math.sqrt((x - cx) ** 2 + (y - cy) ** 2)

    @staticmethod
    def _set_px(g, x, y, color):
        if 0 <= x < GRID and 0 <= y < GRID:
            g[y][x] = color

    @staticmethod
    def _fill_rect(g, x, y, w, h, color):
        for dy in range(h):
            for dx in range(w):
                _Builder._set_px(g, x + dx, y + dy, color)

    def _base_face(self):
        g = self._blank()
        for y in range(GRID):
            for x in range(GRID):
                d = self._dist(x + 0.5, y + 0.5, FACE_CX, FACE_CY)
                if d <= FACE_INNER_R:
                    g[y][x] = self._body_color
                elif d <= FACE_OUTER_R:
                    g[y][x] = FACE_BORDER
        return g

    # ── idle ──────────────────────────────────────────
    def _build_idle(self):
        g = self._base_face()
        self._fill_rect(g, 4, 5, 2, 3, self._eye_color)
        self._fill_rect(g, 10, 5, 2, 3, self._eye_color)
        self._set_px(g, 5, 10, self._mouth_color)
        self._set_px(g, 6, 11, self._mouth_color)
        self._set_px(g, 7, 11, self._mouth_color)
        self._set_px(g, 8, 11, self._mouth_color)
        self._set_px(g, 9, 11, self._mouth_color)
        self._set_px(g, 10, 10, self._mouth_color)
        return g

    # ── happy ─────────────────────────────────────────
    def _build_happy(self):
        g = self._base_face()
        self._set_px(g, 3, 7, self._eye_color)
        self._set_px(g, 4, 6, self._eye_color)
        self._set_px(g, 5, 6, self._eye_color)
        self._set_px(g, 6, 7, self._eye_color)
        self._set_px(g, 9, 7, self._eye_color)
        self._set_px(g, 10, 6, self._eye_color)
        self._set_px(g, 11, 6, self._eye_color)
        self._set_px(g, 12, 7, self._eye_color)
        self._set_px(g, 5, 10, self._mouth_color)
        self._set_px(g, 6, 11, self._mouth_color)
        self._set_px(g, 7, 11, self._mouth_color)
        self._set_px(g, 8, 11, self._mouth_color)
        self._set_px(g, 9, 11, self._mouth_color)
        self._set_px(g, 10, 10, self._mouth_color)
        return g

    # ── sad ───────────────────────────────────────────
    def _build_sad(self):
        g = self._base_face()
        self._fill_rect(g, 4, 5, 2, 3, self._eye_color)
        self._fill_rect(g, 10, 5, 2, 3, self._eye_color)
        self._set_px(g, 5, 11, self._mouth_color)
        self._set_px(g, 6, 10, self._mouth_color)
        self._set_px(g, 7, 10, self._mouth_color)
        self._set_px(g, 8, 10, self._mouth_color)
        self._set_px(g, 9, 10, self._mouth_color)
        self._set_px(g, 10, 11, self._mouth_color)
        return g

    # ── sleepy ────────────────────────────────────────
    def _build_sleepy(self):
        g = self._base_face()
        self._fill_rect(g, 4, 7, 2, 1, self._eye_color)
        self._fill_rect(g, 10, 7, 2, 1, self._eye_color)
        self._fill_rect(g, 7, 10, 2, 2, self._mouth_color)
        return g

    # ── surprised ─────────────────────────────────────
    def _build_surprised(self):
        g = self._base_face()
        self._set_px(g, 4, 5, self._eye_color); self._set_px(g, 5, 5, self._eye_color)
        self._set_px(g, 6, 5, self._eye_color)
        self._set_px(g, 4, 6, self._eye_color); self._set_px(g, 5, 6, (255,255,255))
        self._set_px(g, 6, 6, self._eye_color)
        self._set_px(g, 4, 7, self._eye_color); self._set_px(g, 5, 7, self._eye_color)
        self._set_px(g, 6, 7, self._eye_color)
        self._set_px(g, 9, 5, self._eye_color); self._set_px(g, 10, 5, self._eye_color)
        self._set_px(g, 11, 5, self._eye_color)
        self._set_px(g, 9, 6, self._eye_color); self._set_px(g, 10, 6, (255,255,255))
        self._set_px(g, 11, 6, self._eye_color)
        self._set_px(g, 9, 7, self._eye_color); self._set_px(g, 10, 7, self._eye_color)
        self._set_px(g, 11, 7, self._eye_color)
        self._fill_rect(g, 6, 10, 4, 1, self._mouth_color)
        return g

    # ── blink ─────────────────────────────────────────
    def _build_blink(self):
        g = self._base_face()
        self._fill_rect(g, 4, 5, 2, 3, self._eye_color)
        self._fill_rect(g, 10, 7, 2, 1, self._eye_color)
        self._set_px(g, 5, 10, self._mouth_color)
        self._set_px(g, 6, 11, self._mouth_color)
        self._set_px(g, 7, 11, self._mouth_color)
        self._set_px(g, 8, 11, self._mouth_color)
        self._set_px(g, 9, 11, self._mouth_color)
        self._set_px(g, 10, 10, self._mouth_color)
        return g

    # ── pout ──────────────────────────────────────────
    def _build_pout(self):
        g = self._base_face()
        self._fill_rect(g, 4, 5, 2, 2, self._eye_color)
        self._fill_rect(g, 10, 5, 2, 2, self._eye_color)
        self._set_px(g, 5, 11, self._mouth_color)
        self._set_px(g, 6, 10, self._mouth_color)
        self._set_px(g, 7, 11, self._mouth_color)
        self._set_px(g, 8, 10, self._mouth_color)
        self._set_px(g, 9, 11, self._mouth_color)
        self._set_px(g, 10, 10, self._mouth_color)
        return g

    # ── dizzy ─────────────────────────────────────────
    def _build_dizzy(self):
        g = self._base_face()
        self._set_px(g, 3, 5, self._eye_color); self._set_px(g, 5, 5, self._eye_color)
        self._set_px(g, 4, 6, self._eye_color)
        self._set_px(g, 3, 7, self._eye_color); self._set_px(g, 5, 7, self._eye_color)
        self._set_px(g, 10, 5, self._eye_color); self._set_px(g, 12, 5, self._eye_color)
        self._set_px(g, 11, 6, self._eye_color)
        self._set_px(g, 10, 7, self._eye_color); self._set_px(g, 12, 7, self._eye_color)
        self._fill_rect(g, 7, 10, 2, 1, self._mouth_color)
        return g

    # ── drink ─────────────────────────────────────────
    def _build_drink(self):
        g = self._base_face()
        self._fill_rect(g, 3, 6, 3, 1, self._eye_color)
        self._fill_rect(g, 10, 6, 3, 1, self._eye_color)
        self._set_px(g, 5, 10, self._mouth_color)
        self._set_px(g, 6, 11, self._mouth_color)
        self._set_px(g, 7, 11, self._mouth_color)
        self._set_px(g, 8, 11, self._mouth_color)
        self._set_px(g, 9, 11, self._mouth_color)
        self._set_px(g, 10, 10, self._mouth_color)
        cup = (100, 180, 255)
        self._fill_rect(g, 10, 12, 3, 2, cup)
        self._set_px(g, 13, 12, cup)
        return g

    # ── eye_mask ──────────────────────────────────────
    def _build_eye_mask(self):
        g = self._base_face()
        self._fill_rect(g, 2, 4, 12, 5, self._eye_color)
        for px in (3, 5, 7, 9, 11, 12):
            self._set_px(g, px, 6, (100, 100, 100))
        self._fill_rect(g, 7, 10, 2, 2, self._mouth_color)
        return g

    # ── angry ─────────────────────────────────────────
    def _build_angry(self):
        g = self._base_face()
        self._set_px(g, 3, 3, self._eye_color); self._set_px(g, 4, 2, self._eye_color)
        self._set_px(g, 5, 3, self._eye_color)
        self._set_px(g, 10, 3, self._eye_color); self._set_px(g, 11, 2, self._eye_color)
        self._set_px(g, 12, 3, self._eye_color)
        self._fill_rect(g, 4, 5, 2, 2, self._eye_color)
        self._fill_rect(g, 10, 5, 2, 2, self._eye_color)
        self._set_px(g, 5, 11, self._mouth_color); self._set_px(g, 6, 10, self._mouth_color)
        self._set_px(g, 7, 10, self._mouth_color); self._set_px(g, 8, 10, self._mouth_color)
        self._set_px(g, 9, 10, self._mouth_color); self._set_px(g, 10, 11, self._mouth_color)
        return g

    # ── nervous ───────────────────────────────────────
    def _build_nervous(self):
        g = self._base_face()
        self._set_px(g, 5, 6, self._eye_color); self._set_px(g, 10, 6, self._eye_color)
        self._set_px(g, 5, 10, self._mouth_color); self._set_px(g, 6, 11, self._mouth_color)
        self._set_px(g, 7, 10, self._mouth_color); self._set_px(g, 8, 11, self._mouth_color)
        self._set_px(g, 9, 10, self._mouth_color)
        sweat = (100, 180, 255)
        self._set_px(g, 13, 2, sweat); self._set_px(g, 12, 3, sweat)
        self._set_px(g, 13, 3, sweat); self._set_px(g, 13, 4, sweat)
        return g

    # ── satisfied ─────────────────────────────────────
    def _build_satisfied(self):
        g = self._base_face()
        self._set_px(g, 3, 6, self._eye_color); self._set_px(g, 4, 5, self._eye_color)
        self._set_px(g, 5, 6, self._eye_color)
        self._set_px(g, 10, 6, self._eye_color); self._set_px(g, 11, 5, self._eye_color)
        self._set_px(g, 12, 6, self._eye_color)
        self._fill_rect(g, 7, 10, 2, 1, self._mouth_color)
        blush = (255, 150, 150)
        self._fill_rect(g, 2, 8, 2, 2, blush); self._fill_rect(g, 12, 8, 2, 2, blush)
        return g

    # ── pleading ──────────────────────────────────────
    def _build_pleading(self):
        g = self._base_face()
        self._set_px(g, 3, 3, self._eye_color); self._set_px(g, 4, 4, self._eye_color)
        self._set_px(g, 11, 4, self._eye_color); self._set_px(g, 12, 3, self._eye_color)
        white = (255, 255, 255)
        self._fill_rect(g, 4, 5, 3, 3, self._eye_color)
        self._set_px(g, 5, 6, white)
        self._fill_rect(g, 10, 5, 3, 3, self._eye_color)
        self._set_px(g, 11, 6, white)
        self._fill_rect(g, 6, 11, 4, 1, self._mouth_color)
        return g

    # ── thinking ──────────────────────────────────────
    def _build_thinking(self):
        g = self._base_face()
        self._fill_rect(g, 4, 5, 2, 3, self._eye_color)
        self._set_px(g, 10, 6, self._eye_color)
        self._set_px(g, 6, 10, self._mouth_color); self._set_px(g, 7, 11, self._mouth_color)
        self._set_px(g, 8, 10, self._mouth_color)
        qc = (130, 70, 180)
        self._set_px(g, 8, 0, qc); self._set_px(g, 9, 0, qc)
        self._set_px(g, 8, 1, qc); self._set_px(g, 8, 2, qc)
        self._set_px(g, 9, 3, qc); self._set_px(g, 9, 4, qc)
        return g

    # ── sick ──────────────────────────────────────────
    def _build_sick(self):
        g = self._base_face()
        self._fill_rect(g, 4, 6, 2, 1, self._eye_color)
        self._fill_rect(g, 10, 6, 2, 1, self._eye_color)
        self._set_px(g, 5, 10, self._mouth_color); self._set_px(g, 6, 11, self._mouth_color)
        self._set_px(g, 7, 10, self._mouth_color); self._set_px(g, 8, 11, self._mouth_color)
        self._set_px(g, 9, 10, self._mouth_color)
        ice_pack = (220, 220, 240)
        self._fill_rect(g, 5, 0, 6, 2, ice_pack)
        self._set_px(g, 4, 1, ice_pack); self._set_px(g, 11, 1, ice_pack)
        red = (220, 60, 60)
        self._set_px(g, 7, 0, red); self._set_px(g, 8, 0, red); self._set_px(g, 7, 1, red)
        return g

    # ── overheat ──────────────────────────────────────
    def _build_overheat(self):
        g = self._base_face()
        for px, py in [(4,5),(6,5),(5,6),(4,7),(6,7)]:
            self._set_px(g, px, py, self._eye_color)
        for px, py in [(9,5),(11,5),(10,6),(9,7),(11,7)]:
            self._set_px(g, px, py, self._eye_color)
        self._fill_rect(g, 6, 10, 4, 2, self._mouth_color)
        red_tint = (255, 100, 80)
        self._set_px(g, 3, 8, red_tint); self._set_px(g, 12, 8, red_tint)
        self._set_px(g, 2, 9, red_tint); self._set_px(g, 13, 9, red_tint)
        return g

    # ── cold ──────────────────────────────────────────
    def _build_cold(self):
        g = self._base_face()
        self._fill_rect(g, 4, 5, 2, 1, self._eye_color)
        self._fill_rect(g, 10, 5, 2, 1, self._eye_color)
        self._set_px(g, 5, 10, self._mouth_color); self._set_px(g, 6, 9, self._mouth_color)
        self._set_px(g, 7, 10, self._mouth_color); self._set_px(g, 8, 9, self._mouth_color)
        self._set_px(g, 9, 10, self._mouth_color); self._set_px(g, 10, 9, self._mouth_color)
        ice = (150, 210, 255)
        self._set_px(g, 1, 3, ice); self._set_px(g, 2, 3, ice); self._set_px(g, 1, 5, ice)
        self._set_px(g, 14, 2, ice); self._set_px(g, 13, 3, ice)
        return g

    # ── deep_sleep ────────────────────────────────────
    def _build_deep_sleep(self):
        g = self._base_face()
        self._fill_rect(g, 4, 7, 2, 1, self._eye_color)
        self._fill_rect(g, 10, 7, 2, 1, self._eye_color)
        self._fill_rect(g, 7, 10, 2, 3, self._mouth_color)
        bubble = (150, 200, 255)
        self._fill_rect(g, 10, 2, 3, 3, bubble)
        self._set_px(g, 13, 3, bubble); self._set_px(g, 13, 4, bubble)
        drool = (180, 220, 255)
        self._set_px(g, 5, 13, drool); self._set_px(g, 5, 14, drool)
        self._set_px(g, 6, 13, drool)
        return g

    # ── quiet ─────────────────────────────────────────
    def _build_quiet(self):
        g = self._base_face()
        self._set_px(g, 3, 6, self._eye_color); self._set_px(g, 4, 5, self._eye_color)
        self._set_px(g, 5, 6, self._eye_color)
        self._set_px(g, 10, 6, self._eye_color); self._set_px(g, 11, 5, self._eye_color)
        self._set_px(g, 12, 6, self._eye_color)
        self._fill_rect(g, 6, 10, 4, 1, self._mouth_color)
        return g

    # ── cool ──────────────────────────────────────────
    def _build_cool(self):
        g = self._base_face()
        shades = (25, 25, 25)
        self._fill_rect(g, 3, 5, 10, 3, shades)
        self._set_px(g, 4, 5, (80, 80, 80)); self._set_px(g, 10, 5, (80, 80, 80))
        self._set_px(g, 5, 10, self._mouth_color); self._set_px(g, 6, 11, self._mouth_color)
        self._set_px(g, 7, 11, self._mouth_color); self._set_px(g, 8, 11, self._mouth_color)
        self._set_px(g, 9, 11, self._mouth_color); self._set_px(g, 10, 10, self._mouth_color)
        return g

    # ── birthday ──────────────────────────────────────
    def _build_birthday(self):
        g = self._base_face()
        hat = (255, 80, 130)
        self._fill_rect(g, 5, 0, 6, 1, hat); self._fill_rect(g, 6, 1, 4, 1, hat)
        self._fill_rect(g, 7, 2, 2, 1, hat)
        pompom = (255, 220, 100)
        self._set_px(g, 6, 0, pompom); self._set_px(g, 10, 0, pompom)
        self._set_px(g, 7, 1, pompom)
        self._fill_rect(g, 4, 3, 8, 1, hat)
        self._set_px(g, 3, 6, self._eye_color); self._set_px(g, 4, 5, self._eye_color)
        self._set_px(g, 5, 6, self._eye_color)
        self._set_px(g, 10, 6, self._eye_color); self._set_px(g, 11, 5, self._eye_color)
        self._set_px(g, 12, 6, self._eye_color)
        self._set_px(g, 5, 10, self._mouth_color); self._set_px(g, 6, 11, self._mouth_color)
        self._set_px(g, 7, 11, self._mouth_color); self._set_px(g, 8, 11, self._mouth_color)
        self._set_px(g, 9, 11, self._mouth_color); self._set_px(g, 10, 10, self._mouth_color)
        return g

    # ── ghost ─────────────────────────────────────────
    def _build_ghost(self):
        g = self._base_face()
        self._fill_rect(g, 5, 5, 1, 2, self._eye_color)
        self._fill_rect(g, 10, 5, 1, 2, self._eye_color)
        self._fill_rect(g, 5, 10, 6, 2, self._mouth_color)
        tongue = (240, 100, 100)
        self._fill_rect(g, 7, 12, 2, 2, tongue)
        self._set_px(g, 6, 13, tongue)
        return g

    # ── cat_face ──────────────────────────────────────
    def _build_cat_face(self):
        g = self._base_face()
        gold = (210, 190, 60)
        self._fill_rect(g, 4, 5, 3, 3, gold); self._fill_rect(g, 10, 5, 3, 3, gold)
        self._fill_rect(g, 5, 5, 1, 3, self._eye_color)
        self._fill_rect(g, 11, 5, 1, 3, self._eye_color)
        self._set_px(g, 4, 9, self._mouth_color); self._set_px(g, 5, 10, self._mouth_color)
        self._set_px(g, 7, 10, self._mouth_color); self._set_px(g, 9, 10, self._mouth_color)
        self._set_px(g, 10, 10, self._mouth_color); self._set_px(g, 11, 9, self._mouth_color)
        self._set_px(g, 8, 10, self._mouth_color); self._set_px(g, 6, 10, self._mouth_color)
        whisk = (160, 160, 160)
        self._fill_rect(g, 1, 8, 2, 1, whisk); self._fill_rect(g, 1, 10, 2, 1, whisk)
        self._fill_rect(g, 13, 8, 2, 1, whisk); self._fill_rect(g, 13, 10, 2, 1, whisk)
        return g

    # ── furious ───────────────────────────────────────
    def _build_furious(self):
        g = self._base_face()
        vein = (210, 30, 30)
        self._set_px(g, 7, 0, vein); self._set_px(g, 8, 0, vein); self._set_px(g, 9, 0, vein)
        self._set_px(g, 8, 1, vein); self._set_px(g, 7, 2, vein); self._set_px(g, 9, 2, vein)
        self._fill_rect(g, 3, 2, 3, 1, self._eye_color)
        self._fill_rect(g, 10, 2, 3, 1, self._eye_color)
        self._set_px(g, 4, 3, self._eye_color); self._set_px(g, 11, 3, self._eye_color)
        self._fill_rect(g, 3, 5, 3, 2, self._eye_color)
        self._fill_rect(g, 10, 5, 3, 2, self._eye_color)
        self._fill_rect(g, 5, 10, 6, 2, self._mouth_color)
        tooth = (255, 255, 255)
        self._set_px(g, 6, 10, tooth); self._set_px(g, 7, 10, tooth)
        self._set_px(g, 8, 10, tooth); self._set_px(g, 9, 10, tooth)
        return g

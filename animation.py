"""Animation engine — time-based easing animations, independent of frame rate"""

import math
import time

def _clamp(t):
    """Clamp to [0, 1]"""
    return max(0.0, min(1.0, t))


def linear(t):       return _clamp(t)
def ease_in_quad(t): return _clamp(t * t)
def ease_out_quad(t):return _clamp(1 - (1 - t) ** 2)
def ease_in_out_quad(t):
    t = _clamp(t)
    return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2

def ease_out_bounce(t):
    t = _clamp(t)
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    elif t < 2 / d1:
        t -= 1.5 / d1; return n1 * t * t + 0.75
    elif t < 2.5 / d1:
        t -= 2.25 / d1; return n1 * t * t + 0.9375
    else:
        t -= 2.625 / d1; return n1 * t * t + 0.984375

def ease_out_elastic(t):
    t = _clamp(t)
    if t == 0 or t == 1:
        return t
    return math.pow(2, -10 * t) * math.sin((t - 0.075) * (2 * math.pi) / 0.3) + 1


EASING = {
    "linear": linear,
    "ease_in": ease_in_quad,
    "ease_out": ease_out_quad,
    "ease_in_out": ease_in_out_quad,
    "bounce": ease_out_bounce,
    "elastic": ease_out_elastic,
}


class AnimState:
    """Runtime state for a single animation"""
    __slots__ = ("start_time", "duration", "easing", "from_val", "to_val", "done")

    def __init__(self, duration, easing, from_val, to_val):
        self.start_time = time.time()
        self.duration = duration
        self.easing = easing
        self.from_val = from_val
        self.to_val = to_val
        self.done = False

    def progress(self):
        elapsed = time.time() - self.start_time
        # Prevent system time rollback from causing negative values
        if elapsed < 0:
            elapsed = 0
        t = min(elapsed / self.duration, 1.0) if self.duration > 0 else 1.0
        return self.easing(t)

    def current_value(self):
        p = self.progress()
        if p >= 1.0:
            self.done = True
            return self.to_val
        if isinstance(self.from_val, (tuple, list)):
            return tuple(
                self.from_val[i] + (self.to_val[i] - self.from_val[i]) * p
                for i in range(len(self.from_val))
            )
        return self.from_val + (self.to_val - self.from_val) * p


class AnimationEngine:
    """Animation engine — manages three-channel concurrent animations for movement/scale/bounce"""

    def __init__(self):
        self._move_anim: AnimState | None = None
        self._scale_anim: AnimState | None = None
        self._bounce_anim: AnimState | None = None

    def add_move(self, from_pos, to_pos, duration=1.0, easing="ease_out"):
        easing_fn = EASING.get(easing, ease_out_quad)
        self._move_anim = AnimState(duration, easing_fn, from_pos, to_pos)

    def add_scale(self, from_scale, to_scale, duration=0.3, easing="ease_out"):
        easing_fn = EASING.get(easing, ease_out_quad)
        self._scale_anim = AnimState(duration, easing_fn, from_scale, to_scale)

    def add_bounce(self, intensity=1.0, duration=0.5):
        self._bounce_anim = AnimState(duration, ease_out_bounce, intensity * 30, 0)

    def add_jump(self, height=80, duration=0.8):
        self._bounce_anim = AnimState(duration, ease_out_quad, height, 0)

    def tick(self):
        """Advance all animations by one frame, returns (move_target, scale_val, bounce_offset)"""
        move_target = None
        sc = 0.0
        bo = 0.0

        if self._move_anim and not self._move_anim.done:
            val = self._move_anim.current_value()
            move_target = (val[0], val[1])

        if self._scale_anim and not self._scale_anim.done:
            sc = self._scale_anim.current_value()

        if self._bounce_anim and not self._bounce_anim.done:
            bo = self._bounce_anim.current_value()

        return move_target, sc, bo

    def has_running(self):
        return (
            (self._move_anim and not self._move_anim.done)
            or (self._scale_anim and not self._scale_anim.done)
            or (self._bounce_anim and not self._bounce_anim.done)
        )

    def clear_all(self):
        self._move_anim = None
        self._scale_anim = None
        self._bounce_anim = None

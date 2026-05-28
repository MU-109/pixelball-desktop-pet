"""Behavior system — weighted random state machine + reminder timer

State machine: IDLE ↔ WALK / BOUNCE / JUMP / SLEEP
Manually switched walk/sleep automatically returns to idle after about 10 minutes.
"""

import math
import random
import time
import datetime
from PyQt5.QtCore import QObject, pyqtSignal
import config as cfg


class BehaviorAI(QObject):
    """Pet behavior AI — state machine driven autonomous behavior + time-aware weights + reminder system"""

    action_changed = pyqtSignal(str, dict)
    expression_changed = pyqtSignal(str)
    reminder_drink = pyqtSignal()
    reminder_eye_rest = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "idle"
        self._state_timer = 0.0
        self._state_duration = 0.0
        self._screen_rect = None
        self._sleep_start = 0.0
        self._breath_offset = 0.0
        self._walk_dir = (1.0, 0.0)
        self._walk_speed = 0.0
        self._manual_mode = False
        self._custom_handlers = {}
        self._facing_right = True
        self._last_action_time = time.time()
        self._randomize_duration()

        # Instance-level behavior weights (not read from global BEHAVIOR_WEIGHTS to avoid period switching from polluting global config)
        self._behavior_weights = dict(cfg.BEHAVIOR_WEIGHTS)

        # Time period detection (check every 5 minutes)
        self._last_period_check = 0.0
        self._current_period = self.get_time_period()
        self._apply_period_weights()

        # Toggle states
        self._movement_enabled = True
        self._drink_reminder_enabled = False
        self._drink_interval = cfg.DRINK_REMINDER_INTERVAL * 60
        self._drink_timer = 0.0
        self._eye_rest_enabled = False
        self._eye_rest_timer = 0.0

    def set_screen_rect(self, rect):
        self._screen_rect = rect

    def _randomize_duration(self):
        self._state_duration = random.uniform(
            cfg.BEHAVIOR_INTERVAL_MIN, cfg.BEHAVIOR_INTERVAL_MAX
        )

    def _pick_action(self):
        """Weighted random selection of next action, excluding walk when movement is disabled"""
        actions = list(self._behavior_weights.keys())
        weights = list(self._behavior_weights.values())
        if not self._movement_enabled:
            filtered = [(a, w) for a, w in zip(actions, weights) if a != "walk"]
            if filtered:
                actions, weights = zip(*filtered)
        return random.choices(actions, weights=weights, k=1)[0]

    def _random_walk_dir(self):
        angle = random.uniform(0, 2 * math.pi)
        return (math.cos(angle), math.sin(angle))

    def _generate_move_params(self):
        distance = cfg.WALK_SPEED * random.uniform(1.5, 3.0)
        angle = random.uniform(0, 2 * math.pi)
        return {"dx": math.cos(angle) * distance, "dy": math.sin(angle) * distance}

    def _face_center(self, cur_x, cur_y):
        """Face screen center — used when bouncing off walls"""
        if self._screen_rect is None:
            return (1.0, 0.0)
        cx = self._screen_rect.x() + self._screen_rect.width() / 2
        cy = self._screen_rect.y() + self._screen_rect.height() / 2
        dx = cx - cur_x
        dy = cy - cur_y
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1:
            return self._random_walk_dir()
        return (dx / length, dy / length)

    def transition_to(self, new_state, params=None):
        old_state = self._state
        self._state = new_state
        self._state_timer = 0.0

        action_params = params or {}
        is_manual = action_params.pop("manual", False)
        self._manual_mode = is_manual

        if new_state == "idle":
            self.expression_changed.emit("idle")
            self._randomize_duration()
            action_params["duration"] = self._state_duration
            self._walk_speed = 0.0

        elif new_state == "walk":
            self.expression_changed.emit("happy")
            if is_manual:
                self._state_duration = cfg.MANUAL_WALK_DURATION
                self._walk_speed = cfg.WALK_SPEED_SLOW
                self._walk_dir = self._random_walk_dir()
                action_params["manual"] = True
                action_params["duration"] = 0
            else:
                self._randomize_duration()
                self._walk_speed = cfg.WALK_SPEED
                act = self._generate_move_params()
                self._walk_dir = (
                    math.copysign(1.0, act["dx"]) if act["dx"] != 0 else 1.0,
                    0.0,
                )
                action_params = act
                action_params["duration"] = random.uniform(1.5, 3.0)

        elif new_state == "bounce":
            self.expression_changed.emit("happy")
            self._randomize_duration()
            action_params = {"intensity": random.uniform(0.5, 1.5)}
            self._walk_speed = 0.0

        elif new_state == "jump":
            self.expression_changed.emit("surprised")
            self._randomize_duration()
            action_params = {"height": random.uniform(50, 120)}
            self._walk_speed = 0.0

        elif new_state == "sleep":
            self.expression_changed.emit("sleepy")
            self._sleep_start = time.time()
            if is_manual:
                self._state_duration = cfg.MANUAL_SLEEP_DURATION
            else:
                self._state_duration = random.uniform(
                    cfg.SLEEP_DURATION_MIN, cfg.SLEEP_DURATION_MAX
                )
            action_params["duration"] = self._state_duration
            action_params["manual"] = is_manual
            self._walk_speed = 0.0

        self._last_action_time = time.time()
        self.action_changed.emit(new_state, action_params)

    def transition_to_idle(self):
        self.transition_to("idle")

    def on_click(self):
        """Click response: sleep→wake, non-idle→switch to idle, idle→handled by PetWindow for head pat"""
        if self._state == "sleep":
            self.transition_to("idle")
        elif self._state != "idle":
            self.transition_to("idle")

    def on_double_click(self):
        pass

    def update(self, delta_ms, pet_x=None, pet_y=None):
        """Update behavior state every frame

        Returns:
            (dx, dy): movement delta in walk manual mode, otherwise (0, 0)
        """
        dt = delta_ms / 1000.0
        # Prevent state machine anomalies from time jumps after system sleep resume
        dt = min(dt, 1.0)
        self._state_timer += dt

        # Check period change every 5 minutes
        self._last_period_check += dt
        if self._last_period_check >= 300:
            self._last_period_check = 0.0
            new_period = self.get_time_period()
            if new_period != self._current_period:
                self._current_period = new_period
                self._apply_period_weights()

        move_dx, move_dy = 0.0, 0.0

        # Reminder timers
        if self._drink_reminder_enabled:
            self._drink_timer += dt
            if self._drink_timer >= self._drink_interval:
                self._drink_timer = 0.0
                self.reminder_drink.emit()

        if self._eye_rest_enabled:
            self._eye_rest_timer += dt
            if self._eye_rest_timer >= cfg.EYE_REST_INTERVAL * 60:
                self._eye_rest_timer = 0.0
                self.reminder_eye_rest.emit()

        # Breath animation (continuous)
        self._breath_offset = math.sin(time.time() * 2.0) * 3

        # Walk manual mode: slow movement + wall bounce + random direction change
        if self._state == "walk" and self._manual_mode:
            if not self._movement_enabled:
                return (0.0, 0.0)
            if self._state_timer >= self._state_duration:
                self.transition_to_idle()
                return (0.0, 0.0)

            if pet_x is not None and pet_y is not None and self._screen_rect is not None:
                ww, wh = cfg.WINDOW_WIDTH, cfg.WINDOW_HEIGHT
                left = self._screen_rect.x()
                top = self._screen_rect.y()
                right = self._screen_rect.x() + self._screen_rect.width() - ww
                bottom = self._screen_rect.y() + self._screen_rect.height() - wh

                hit = False
                if pet_x <= left and self._walk_dir[0] < 0:
                    hit = True
                elif pet_x >= right and self._walk_dir[0] > 0:
                    hit = True
                if pet_y <= top and self._walk_dir[1] < 0:
                    hit = True
                elif pet_y >= bottom and self._walk_dir[1] > 0:
                    hit = True

                if hit:
                    self._walk_dir = self._face_center(pet_x, pet_y)
                elif random.random() < cfg.WALK_DIRECTION_CHANGE_CHANCE * dt:
                    self._walk_dir = self._random_walk_dir()

            move_dx = self._walk_dir[0] * self._walk_speed * dt
            move_dy = self._walk_dir[1] * self._walk_speed * dt
            return (move_dx, move_dy)

        # walk auto mode
        if self._state == "walk" and not self._manual_mode:
            if self._state_timer >= self._state_duration:
                self.transition_to_idle()
            return (0.0, 0.0)

        # bounce / jump timeout check
        if self._state in ("bounce", "jump"):
            if self._state_timer >= self._state_duration:
                self.transition_to_idle()
                self._state_timer = random.uniform(0, 1.5)

        # idle timeout → pick next action
        if self._state == "idle" and self._state_timer >= self._state_duration:
            action = self._pick_action()
            self.transition_to(action)

        # sleep timeout check
        elif self._state == "sleep":
            if self._manual_mode:
                if self._state_timer >= self._state_duration:
                    self.transition_to_idle()
            elif time.time() - self._sleep_start >= self._state_duration:
                self.transition_to_idle()

        # Update facing direction
        if self._state == "walk":
            if self._walk_dir[0] > 0.01:
                self._facing_right = True
            elif self._walk_dir[0] < -0.01:
                self._facing_right = False

        return (move_dx, move_dy)

    def get_state(self):
        return self._state

    def get_breath_offset(self):
        return self._breath_offset if self._state in ("idle", "sleep") else 0.0

    def get_facing_right(self):
        return self._facing_right

    @staticmethod
    def get_time_period(hour=None):
        if hour is None:
            hour = datetime.datetime.now().hour
        if cfg.MORNING_START <= hour < cfg.AFTERNOON_START:
            return "morning"
        elif cfg.AFTERNOON_START <= hour < cfg.EVENING_START:
            return "afternoon"
        elif cfg.EVENING_START <= hour < cfg.NIGHT_START:
            return "evening"
        else:
            return "night"

    @staticmethod
    def get_period_greeting(user_title="Master"):
        now = datetime.datetime.now()
        time_str = now.strftime("%H:%M")
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekday = weekdays[now.weekday()]
        period = BehaviorAI.get_time_period(now.hour)
        greeting_map = {
            "morning": "Good morning",
            "afternoon": "Good afternoon",
            "evening": "Good evening",
            "night": "It's late, rest early",
        }
        return f"It's now {time_str}, {weekday}.\n{user_title}, {greeting_map[period]}!"

    def _apply_period_weights(self):
        """Update instance-level behavior weights based on current time period"""
        period = self.get_time_period()
        weights = cfg.PERIOD_WEIGHTS.get(period)
        if weights:
            self._behavior_weights.update(weights)

    # ── Toggle control ─────────────────────────────────────

    def set_movement_enabled(self, enabled: bool):
        self._movement_enabled = enabled

    def is_movement_enabled(self) -> bool:
        return self._movement_enabled

    def set_drink_reminder_enabled(self, enabled: bool):
        self._drink_reminder_enabled = enabled
        if enabled:
            self._drink_timer = 0.0

    def is_drink_reminder_enabled(self) -> bool:
        return self._drink_reminder_enabled

    def set_drink_interval(self, minutes: int):
        self._drink_interval = minutes * 60
        self._drink_timer = 0.0

    def get_drink_interval(self) -> int:
        return self._drink_interval // 60

    def postpone_drink(self):
        self._drink_timer = max(0, self._drink_interval - cfg.DRINK_POSTPONE_MINUTES * 60)

    def set_eye_rest_enabled(self, enabled: bool):
        self._eye_rest_enabled = enabled
        if enabled:
            self._eye_rest_timer = 0.0

    def is_eye_rest_enabled(self) -> bool:
        return self._eye_rest_enabled

    def add_custom_action(self, name, weight, handler):
        self._behavior_weights[name] = weight
        self._custom_handlers[name] = handler

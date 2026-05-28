"""Global configuration constants for desktop pet"""

# Window settings
WINDOW_WIDTH = 100
WINDOW_HEIGHT = 100
WINDOW_OPACITY = 1.0

# Pixel ball settings (scaled down to 1/4)
PIXEL_SIZE = 16           # Logical pixel size (16x16)
PIXEL_SCALE = 4           # Render scale factor (16*4 = 64px actual render)
BALL_BODY_COLOR = (255, 200, 0)       # Face main color (pure yellow face)
BALL_EYE_COLOR = (30, 30, 30)         # Eye color (pure black)
BALL_MOUTH_COLOR = (30, 30, 30)       # Mouth color (pure black)

# Color constants (used by tray icon, etc.)
# Action list
ACTIONS = ["idle", "walk", "bounce", "sleep", "jump"]

# Behavior weights (percentage)
BEHAVIOR_WEIGHTS = {
    "idle": 40,
    "walk": 30,
    "bounce": 15,
    "sleep": 10,
    "jump": 5,
}

# Behavior interval (seconds)
BEHAVIOR_INTERVAL_MIN = 3.0
BEHAVIOR_INTERVAL_MAX = 8.0

# Animation settings
FPS = 60
WALK_SPEED = 80           # Walk speed (pixels/sec)
JUMP_HEIGHT = 100         # Jump height
BOUNCE_HEIGHT = 30        # Bounce height

# Sleep settings
SLEEP_DURATION_MIN = 5.0  # Min sleep duration (seconds)
SLEEP_DURATION_MAX = 15.0 # Max sleep duration (seconds)

# Manual switch duration (seconds)
MANUAL_WALK_DURATION = 600    # 10 minutes
MANUAL_SLEEP_DURATION = 600   # 10 minutes

# Walk parameters
WALK_SPEED_SLOW = 25          # pixels/sec (manual walk slow speed)
WALK_DIRECTION_CHANGE_CHANCE = 0.03  # 3% chance per second to change direction

# Settings file (local INI, saved in project directory)

import os
_SETTINGS_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(_SETTINGS_DIR, "pet_settings.ini")

# ── Time period definitions ──────────────────────────
# Used to adjust behavior weights and greetings
MORNING_START = 6        # Morning 6:00
AFTERNOON_START = 12     # Afternoon 12:00
EVENING_START = 18       # Evening 18:00
NIGHT_START = 22         # Night 22:00

# Period behavior weights (idle, walk, bounce, sleep, jump)
PERIOD_WEIGHTS = {
    "morning":   {"idle": 35, "walk": 35, "bounce": 15, "sleep": 5,  "jump": 10},
    "afternoon": {"idle": 30, "walk": 35, "bounce": 20, "sleep": 5,  "jump": 10},
    "evening":   {"idle": 45, "walk": 25, "bounce": 10, "sleep": 15, "jump": 5},
    "night":     {"idle": 30, "walk": 15, "bounce": 5,  "sleep": 40, "jump": 10},
}

# ── Bubble dialog settings ──────────────────────────
BUBBLE_DURATION = 5.0        # Default bubble display duration (seconds)
BUBBLE_PADDING_H = 12        # Bubble horizontal padding
BUBBLE_PADDING_V = 8         # Bubble vertical padding
BUBBLE_FONT_SIZE = 11         # Bubble font size
BUBBLE_MAX_WIDTH = 280       # Bubble max width (auto wrap)
BUBBLE_POINTER_H = 6         # Bubble pointer triangle height

# ── Reminder settings ───────────────────────────────
DRINK_REMINDER_INTERVAL = 45    # Default drink reminder interval (minutes)
EYE_REST_INTERVAL = 20          # Eye rest interval (minutes, 20-20-20 rule)
DRINK_POSTPONE_MINUTES = 5      # Postpone drink reminder (minutes)

# ── Todo settings ───────────────────────────────────
TODO_FILE = "pet_todos.json"    # Todo data file name (same directory)
TODO_HOVER_DELAY = 1000         # Hover delay to show Todo (milliseconds)

# ── Body monitoring settings ────────────────────────
BODY_DATA_FILE = "pet_body_data.json"   # Body weight record file name (same directory)
BODY_PANEL_MIN_WIDTH = 240              # Body monitoring panel min width
BODY_PANEL_CLOSE_DELAY = 400            # Leave-close delay (milliseconds)
DEFAULT_HEIGHT = 170.0                  # Default height (cm)
DEFAULT_WEIGH_TIME = "08:00"            # Default weigh-in reminder time

# ── Default names ──────────────────────────────────
DEFAULT_PET_NAME = "Little Yellow"
DEFAULT_USER_TITLE = "Master"

# ── AI settings file ────────────────────────────────
AI_SETTINGS_FILE = os.path.join(_SETTINGS_DIR, "ai_settings.json")

# Preset personalities (for role switching), {pet_name} {user_title} replaced at runtime
DEFAULT_PERSONALITIES = {
    "Energetic": (
        'You are "{pet_name}", an energetic pixel yellow face living on {user_title}\'s desktop.\n'
        "Personality: Vibrant, optimistic and cheerful, speaking as warmly as a little sun.\n"
        "Likes to use 'Ya~', 'Ehehe!', 'Awoo!' as interjections, {user_title}'s ray of sunshine."
    ),
    "Gentle": (
        'You are "{pet_name}", a gentle and caring pixel yellow face living on {user_title}\'s desktop.\n'
        "Personality: Empathetic, soft-spoken, using the softest tone to say the warmest words.\n"
        "Likes to use 'Ne~', 'Meow.', 'Okay~' as interjections, {user_title}'s little comfort."
    ),
    "Rigorous": (
        'You are "{pet_name}", a rigorous and serious pixel yellow face living on {user_title}\'s desktop.\n'
        "Personality: Clear logic, concise speech, talking like a little professor while staying cute.\n"
        "Likes to use 'Hmm.', 'Makes sense.', 'Let me think...' as interjections, {user_title}'s reliable little assistant."
    ),
}

# Proactive chat interval range (minutes)
PROACTIVE_CHAT_INTERVAL_MIN = 15
PROACTIVE_CHAT_INTERVAL_MAX = 60

# Max conversation history rounds
HISTORY_MAX_LIMIT = 20

# ── Screenshot hotkey ───────────────────────────────
DEFAULT_SCREENSHOT_HOTKEY = '<ctrl_r>+<f12>'

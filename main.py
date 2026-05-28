"""Pixel Ball Desktop Pet — Entry module

Launch methods:
    python main.py                 # Normal mode (console visible)
    pythonw main.py                # Launch without console
    python main.py --passthrough   # Passthrough mode (read-only display)
"""

import sys
import os
import argparse

# When launched with pythonw.exe, redirect stdout/stderr to prevent print from triggering a console window
if sys.executable.endswith("pythonw.exe"):
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')

# Pre-import faster_whisper (must be done before QApplication is created)
# onnxruntime C extension initialization conflicts with Qt event loop; importing after Qt causes segfault
try:
    import faster_whisper  # noqa: F401
except Exception:
    pass

from pet_app import PetApp


def parse_args():
    parser = argparse.ArgumentParser(description="Pixel Ball Desktop Pet")
    parser.add_argument(
        "--passthrough", action="store_true",
        help="Passthrough mode (read-only display, no mouse response)"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    app = PetApp(sys.argv)
    pet = app.spawn_pet()

    if args.passthrough:
        pet.set_passthrough(True)

    pet.show_greeting()

    # Start window pin manager
    from window_pin import WindowPinManager
    _pin_manager = WindowPinManager()
    app.qapp.aboutToQuit.connect(_pin_manager.stop)

    print("Pixel Ball desktop pet started. Right-click menu to switch expressions/actions, drag to move, system tray to exit.")
    sys.exit(app.run())


if __name__ == "__main__":
    main()

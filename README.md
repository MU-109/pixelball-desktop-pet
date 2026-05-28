PixelBall Desktop Pet
<img width="84" height="84" alt="image" src="https://github.com/user-attachments/assets/a61cad84-22da-4aec-8d9f-59bcd3f845be" />

A cute pixel-style desktop pet, built with Python + PyQt5. A 16x16 pixel ball character that can walk, jump, nap, and interact with you on your desktop.

A fun toy project, no longer actively maintained. Feel free to fork and mod!

Features

Basic Interaction

- Left-click: Bounce + happy expression; pop the bubble to wake when napping
- Double-click: Quick chat menu (time, weather, AI chat, jokes, tools, etc.)
- Drag: Move the pet anywhere on the desktop
- Right-click menu: Full feature menu
- Hover for 1 second: Show Todo list panel
- Drag text: Select text and drag onto the pet -> Bing search

Smart Behavior (Time-Aware)

- Morning 6:00-12:00: Active (walk 35%, sleep only 5%)
- Afternoon 12:00-18:00: Most active (bounce 20%, walk 35%)
- Evening 18:00-22:00: Calming down (idle 45%, sleep 15%)
- Late night 22:00-6:00: Sleepy (sleep 40%, walk only 15%)

Advanced Features

- 25 pixel expressions -- edit on a 16x16 pixel canvas, supports importing/exporting skin packs
- AI Chat -- Integrated with DeepSeek API, supports 4 preset personalities (Energetic/Gentle/Serious/Cat)
- Speech-to-Text -- based on faster-whisper, offline real-time recognition with floating display
- Screenshot OCR -- take a screenshot, right-click to recognize text, supports Chinese and English
- Window Pin -- adds a pin button to desktop windows for one-click pinning
- Utility Tools -- Clipboard history, calculator, countdown, timestamp, password generator, QR code, text statistics, noise meter
- System Info -- Local IP, public IP, WiFi name, CPU, GPU, port detection
- Game Mode -- Keyboard stats, performance monitoring panel
- Timed Reminders -- Drink water, eye rest, weigh-in reminder, alarm clock
- Todo Management -- supports due dates, auto-announce on startup
- Plugin System -- Extensible architecture based on abstract base classes

Quick Start

Prerequisites

- Windows 10/11
- Python 3.10+

Installation & Running

1. Clone the repository

   git clone https://github.com/MU-109/pixelball-desktop-pet.git
   cd pixelball-desktop-pet

2. Install dependencies

   pip install -r requirements.txt

3. (Optional) Copy the configuration template

   copy pet_settings.example.ini pet_settings.ini

4. Launch

   python main.py

   Passthrough mode (read-only display, no mouse interaction):

   python main.py --passthrough

Optional Modules

- Speech-to-Text: requires additional installation of faster-whisper + model files, run python download_model.py to download
- OCR: Requires Tesseract portable version, place it in the tesseract-portable directory
- GPU Monitoring: NVIDIA GPUs require additional installation of nvidia-ml-py

Tech Stack

- Language: Python 3.10+
- GUI Framework: PyQt5
- Rendering: QPainter pixel-by-pixel drawing (16x16 -> 64px)
- Animation: Time-based easing system (6 easing functions, frame-rate independent)
- Behavior AI: Time-aware weighted random state machine
- Encrypted Storage: Fernet AES-128 + PBKDF2 key derivation
- Speech Recognition: faster-whisper base model (offline)
- OCR: Tesseract + pytesseract

Project Structure

    main.py                 Entry point
    pet_app.py              App management (QApplication, system tray, plugin loading)
    pet_window.py           Core hub (rendering, interaction, particles, bubbles, AI, alarm)
    character.py            Pixel ball character rendering
    animation.py            Animation engine
    behavior.py             Behavior AI (state machine + timed reminders)
    config.py               Global configuration constants
    plugin_base.py          Plugin abstract base class
    secure_store.py         API key encrypted storage
    voice_to_text.py        Speech-to-text (mic -> faster-whisper -> floating window)
    ocr_tool.py             OCR tool
    window_pin.py           Window pin manager
    utility_tools.py        Utility tools (8 tools)
    system_info.py          System info collection
    download_model.py       faster-whisper model download
    game_mode.py            Game mode management
    plugins                 Plugins directory
    expressions             Expression system (JSON data + manager + pixel editor)

Configuration Files

The program automatically generates the following files on first run:

    pet_settings.ini        Main config (position, behavior, AI API, hotkeys, etc.)
    ai_settings.json        AI personality presets and chat history
    dialog_data.json        Dialog corpus (jokes, facts, compliments)
    alarms.json             Alarm data
    pet_todos.json          Todos
    stats.json              Keyboard/mouse stats
    pet_body_data.json      Weight records

AI Chat Configuration

1. Right-click the pet -> AI Settings -> Configure API
2. Enter DeepSeek API URL and API Key (or any OpenAI-compatible service)
3. The API Key is encrypted and stored using AES-128

Get a DeepSeek API Key: platform.deepseek.com

Custom Expressions

Right-click the pet -> Switch Expression -> Manage Expressions -> Open the 16x16 pixel canvas editor, draw and save. Also supports importing/exporting .petpack skin packs.

Writing Plugins

Create a .py file in the plugins directory, inheriting from PetPlugin:

    from plugin_base import PetPlugin

    class MyPlugin(PetPlugin):
        name = "My Plugin"
        version = "1.0.0"
        description = "Custom feature"

        def on_load(self, pet):
            print("Plugin loaded")

        def on_unload(self, pet):
            print("Plugin unloaded")

        def on_click(self, event):
            pet.set_expression("happy")

Known Limitations

- Windows only (extensive win32 API usage)
- Speech-to-text requires downloading model files (~150MB)
- OCR requires Tesseract portable (not included in the repository)

License

MIT License -- see LICENSE file for details

If you've made an interesting desktop pet too, feel free to share it with me! Even though it's no longer maintained, seeing other people's mods makes me happy :)

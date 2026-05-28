"""Plugin base class — all plugins must inherit PetPlugin, place .py files in plugins/ for auto-loading"""

from abc import ABC, abstractmethod


class PetPlugin(ABC):
    """Desktop pet plugin base class — must implement on_load / on_unload, 7 optional hooks"""

    name: str = "base_plugin"
    version: str = "0.1.0"
    description: str = ""

    def __init__(self):
        self._pet = None
        self._enabled = False

    @property
    def pet(self):
        return self._pet

    @abstractmethod
    def on_load(self, pet):
        """Called when plugin is loaded, pet is PetWindow instance"""
        ...

    @abstractmethod
    def on_unload(self, pet):
        """Called when plugin is unloaded"""
        ...

    # Optional hooks
    def on_click(self, event): pass
    def on_double_click(self, event): pass
    def on_tick(self, delta_ms): pass
    def on_expression_changed(self, expression_name): pass
    def on_action_changed(self, action_name): pass

    def context_menu_entries(self):
        """Returns list of right-click menu extension items [(label, callback), ...]"""
        return []

    def on_enable(self):
        self._enabled = True

    def on_disable(self):
        self._enabled = False

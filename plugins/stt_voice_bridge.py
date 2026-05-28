"""Speech-to-text bridge plugin — integrate voice_to_text module into desktop pet menu system"""

from plugin_base import PetPlugin


class STTVoiceBridge(PetPlugin):
    """Speech-to-text plugin bridge, provides right-click/double-click menu entry (microphone only)"""

    name = "Voice to Text"
    version = "1.0.0"
    description = "Real-time microphone speech-to-text, offline recognition, follows floating window display"

    def on_load(self, pet):
        from voice_to_text import VoiceToTextManager
        self._mgr = VoiceToTextManager(pet)

    def on_unload(self, pet):
        if hasattr(self, '_mgr'):
            self._mgr.stop()

    def context_menu_entries(self):
        """Right-click menu items"""
        if not hasattr(self, '_mgr'):
            return []
        mgr = self._mgr
        return [
            ("🎤 Start Recognition", mgr.start),
            ("⏹ Stop Recognition", mgr.stop),
            ("⚙ Settings...", mgr.show_settings),
        ]

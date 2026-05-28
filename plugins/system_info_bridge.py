"""System info bridge plugin"""

from plugin_base import PetPlugin


class SystemInfoBridge(PetPlugin):

    name = "System Info"
    version = "1.0.0"
    description = "IP/Model/WiFi/Ports/Environment variables/Encrypted cheat sheet"

    def on_load(self, pet):
        self._pet = pet

    def on_unload(self, pet):
        pass

    def context_menu_entries(self):
        from system_info import (
            get_local_ip, get_public_ip, get_wifi_ssid,
            get_computer_model, get_cpu_model, get_gpu_model,
            show_full_panel, show_port_checker, show_env_vars,
            show_cheat_sheet, _copy_and_tell,
        )
        pet = self._pet

        def _copy(label, getter):
            val = getter()
            _copy_and_tell(pet, label, val)

        def _copy_public_ip():
            def _done(ip):
                _copy_and_tell(pet, "Public IP", ip)
            get_public_ip()(_done)

        return [
            ("View Full Info Panel", lambda: show_full_panel(pet)),
            (None, None),  # Separator
            ("Copy Local IP", lambda: _copy("Local IP", get_local_ip)),
            ("Copy Public IP", _copy_public_ip),
            ("Copy Current WiFi SSID", lambda: _copy("WiFi", get_wifi_ssid)),
            ("Copy Computer Model", lambda: _copy("Computer Model", get_computer_model)),
            ("Copy CPU Model", lambda: _copy("CPU", get_cpu_model)),
            ("Copy GPU Model", lambda: _copy("GPU", get_gpu_model)),
            (None, None),
            ("Port Checker...", lambda: show_port_checker(pet)),
            ("View Environment Variables", lambda: show_env_vars(pet)),
            (None, None),
            ("My Cheat Sheet...", lambda: show_cheat_sheet(pet)),
        ]

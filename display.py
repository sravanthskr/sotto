"""
display.py - screen brightness and exact master volume.

Brightness uses WMI (works on most laptops / built-in panels; desktop monitors often
refuse it, which we report honestly). Volume uses the Windows Core Audio API via pycaw.
"""

import subprocess

_CREATE_NO_WINDOW = 0x08000000


def _powershell(script):
    return subprocess.run(["powershell", "-NoProfile", "-Command", script],
                          capture_output=True, text=True, creationflags=_CREATE_NO_WINDOW)


# ---------------------------------------------------------------------------
# Brightness
# ---------------------------------------------------------------------------
def get_brightness():
    r = _powershell("(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness)"
                    ".CurrentBrightness")
    out = (r.stdout or "").strip()
    return int(out) if out.isdigit() else None


def set_brightness(percent):
    p = max(0, min(100, int(percent)))
    r = _powershell("(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
                    f").WmiSetBrightness(1,{p})")
    if r.returncode == 0 and not (r.stderr or "").strip():
        return f"Brightness set to {p}%."
    return "Error: this display doesn't allow brightness control (common for desktop monitors)."


# ---------------------------------------------------------------------------
# Volume (Windows Core Audio via pycaw)
# ---------------------------------------------------------------------------
def _endpoint():
    from pycaw.pycaw import AudioUtilities
    device = AudioUtilities.GetSpeakers()
    # newer pycaw exposes EndpointVolume directly
    if hasattr(device, "EndpointVolume"):
        return device.EndpointVolume
    # older pycaw: activate the interface manually
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import IAudioEndpointVolume
    interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def get_volume():
    try:
        return int(round(_endpoint().GetMasterVolumeLevelScalar() * 100))
    except Exception:
        return None


def set_volume(percent):
    p = max(0, min(100, int(percent)))
    try:
        _endpoint().SetMasterVolumeLevelScalar(p / 100.0, None)
        return f"Volume set to {p}%."
    except Exception as e:
        return f"Error: couldn't set the volume ({e})."

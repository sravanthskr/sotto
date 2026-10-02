"""
sysauth.py - Verify the current user with the Windows sign-in.

Recovery path for a forgotten Sotto voice lock:
  "Forgot passphrase?" -> verify with Windows Hello / PIN / password
  -> remove the lock or set a new passphrase. Nothing is ever deleted.

No third-party dependencies:
  * Windows Hello runs through PowerShell's WinRT bridge.
  * The password fallback uses the standard Windows credentials dialog
    (CredUI) and validates against the local Windows logon.

Public API:
  verify_windows_identity(reason)  -> {"ok": bool, "method": str, "detail": str}
  hello_available()                -> "Available" | "DeviceNotPresent" | ...
"""

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import tempfile

# ---------------------------------------------------------------------------
# Windows Hello (UserConsentVerifier) via PowerShell + WinRT
# ---------------------------------------------------------------------------

_PS_TEMPLATE = r'''
$ErrorActionPreference = 'Stop'
[void][Windows.Security.Credentials.UI.UserConsentVerifier,Windows.Security.Credentials.UI,ContentType=WindowsRuntime]
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]
function AwaitOp($op, $type) {
  $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
  $t.Wait(-1) | Out-Null
  return $t.Result
}
'''

_PS_VERIFY = _PS_TEMPLATE + r'''
$msg = 'Verify it''s you to reset the Sotto voice lock'
$res = AwaitOp ([Windows.Security.Credentials.UI.UserConsentVerifier]::RequestVerificationAsync($msg)) ([Windows.Security.Credentials.UI.UserConsentVerificationResult])
Write-Output $res.ToString()
'''

_PS_CHECK = _PS_TEMPLATE + r'''
$res = AwaitOp ([Windows.Security.Credentials.UI.UserConsentVerifier]::CheckAvailabilityAsync()) ([Windows.Security.Credentials.UI.UserConsentVerifierAvailability])
Write-Output $res.ToString()
'''


def _run_ps(script):
    """Run a PowerShell snippet hidden; return its last stdout line (or "")."""
    path = None
    try:
        fd, path = tempfile.mkstemp(suffix=".ps1", prefix="sotto_sysauth_")
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(script)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        p = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path],
            capture_output=True, text=True, timeout=240, creationflags=flags,
        )
        out = [ln.strip() for ln in (p.stdout or "").splitlines() if ln.strip()]
        return out[-1] if out else ""
    except Exception:
        return ""
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def hello_available():
    """Check (without showing UI) whether Windows Hello is ready."""
    return _run_ps(_PS_CHECK) or "Unknown"


def _try_windows_hello():
    res = _run_ps(_PS_VERIFY)
    mapping = {
        "Verified": "verified",
        "DeviceNotPresent": "unavailable",
        "NotConfiguredForUser": "unavailable",
        "DisabledByPolicy": "unavailable",
        "DeviceBusy": "failed",
        "RetriesExhausted": "failed",
        "Canceled": "canceled",
    }
    return mapping.get(res, "unavailable")


# ---------------------------------------------------------------------------
# Windows password fallback (CredUI + local logon validation)
# ---------------------------------------------------------------------------

class _CREDUI_INFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("hwndParent", wt.HWND),
        ("pszMessageText", wt.LPCWSTR),
        ("pszCaptionText", wt.LPCWSTR),
        ("hbmBanner", wt.HBITMAP),
    ]


def _cred_ui_verify():
    credui = ctypes.WinDLL("credui", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    CREDUIWIN_GENERIC = 0x1
    CREDUIWIN_ENUMERATE_CURRENT_USER = 0x200
    LOGON32_LOGON_NETWORK = 3
    LOGON32_PROVIDER_DEFAULT = 0
    ERROR_CANCELLED = 1223

    info = _CREDUI_INFOW()
    info.cbSize = ctypes.sizeof(_CREDUI_INFOW)
    info.pszCaptionText = "Sotto - Reset voice lock"
    info.pszMessageText = ("Confirm your Windows account to reset the "
                           "forgotten voice lock. Nothing is deleted.")

    auth_pkg = wt.DWORD(0)
    out_buf = ctypes.c_void_p()
    out_size = wt.DWORD(0)
    save = wt.BOOL(False)

    credui.CredUIPromptForWindowsCredentialsW.restype = wt.DWORD
    rc = credui.CredUIPromptForWindowsCredentialsW(
        ctypes.byref(info), 0, ctypes.byref(auth_pkg),
        None, 0, ctypes.byref(out_buf), ctypes.byref(out_size),
        ctypes.byref(save),
        CREDUIWIN_GENERIC | CREDUIWIN_ENUMERATE_CURRENT_USER,
    )
    if rc == ERROR_CANCELLED:
        return {"ok": False, "method": "password", "detail": "Verification was canceled."}
    if rc != 0:
        return {"ok": False, "method": "password",
                "detail": "The Windows credentials dialog failed (%d)." % rc}

    try:
        credui.CredUnPackAuthenticationBufferW.restype = wt.BOOL
        uname = ctypes.create_unicode_buffer(514)
        un_len = wt.DWORD(514)
        domain = ctypes.create_unicode_buffer(514)
        dn_len = wt.DWORD(514)
        pwd = ctypes.create_unicode_buffer(514)
        pn_len = wt.DWORD(514)
        unpacked = credui.CredUnPackAuthenticationBufferW(
            0, out_buf, out_size,
            uname, ctypes.byref(un_len),
            domain, ctypes.byref(dn_len),
            pwd, ctypes.byref(pn_len),
        )
        if not unpacked:
            return {"ok": False, "method": "password",
                    "detail": "Could not read the entered credentials."}

        token = wt.HANDLE()
        advapi.LogonUserW.restype = wt.BOOL
        ok = advapi.LogonUserW(uname, domain, pwd,
                               LOGON32_LOGON_NETWORK,
                               LOGON32_PROVIDER_DEFAULT,
                               ctypes.byref(token))
        if ok:
            kernel.CloseHandle(token)
            return {"ok": True, "method": "windows-password"}
        err = ctypes.get_last_error()
        if err == 1326:
            return {"ok": False, "method": "password",
                    "detail": "That Windows password was not accepted."}
        return {"ok": False, "method": "password",
                "detail": "Windows could not verify this account (code %d)." % err}
    finally:
        try:
            credui.CredFree(out_buf)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def verify_windows_identity(reason="Reset the Sotto voice lock"):
    """Ask Windows to verify the current user. Returns a small result dict."""
    hello = _try_windows_hello()
    if hello == "verified":
        return {"ok": True, "method": "windows-hello", "detail": ""}
    if hello == "canceled":
        return {"ok": False, "method": "windows-hello", "detail": "Verification was canceled."}
    if hello == "unavailable":
        return _cred_ui_verify()
    res = _cred_ui_verify()
    if res.get("ok"):
        return res
    return {"ok": False, "method": "windows-hello",
            "detail": res.get("detail") or "Windows sign-in was not completed."}


if __name__ == "__main__":
    print("Hello availability:", hello_available())
    out = verify_windows_identity()
    print("Verification result:", out)
"""Reused Windows DPAPI / ACL primitives from the original source snapshot.
Only error naming was decoupled from the retired Provider control plane.
Windows execution requires validation on the actual operator account.
"""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import subprocess
from typing import Callable
class ProviderConfigError(RuntimeError): pass

class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class WindowsDpapiProtector:
    _CRYPTPROTECT_UI_FORBIDDEN = 0x1

    def protect(self, secret: bytes) -> bytes:
        return self._crypt(secret, protect=True)

    def unprotect(self, ciphertext: bytes) -> bytes:
        return self._crypt(ciphertext, protect=False)

    def _crypt(self, content: bytes, *, protect: bool) -> bytes:
        if sys.platform != "win32":
            raise ProviderConfigError("Windows DPAPI is unavailable")
        if not content:
            raise ProviderConfigError("DPAPI input must not be empty")

        input_buffer = (ctypes.c_ubyte * len(content)).from_buffer_copy(content)
        input_blob = _DataBlob(len(content), input_buffer)
        output_blob = _DataBlob()
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            wintypes.LPCWSTR,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p

        try:
            operation = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
            succeeded = operation(
                ctypes.byref(input_blob),
                None,
                None,
                None,
                None,
                self._CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(output_blob),
            )
            if not succeeded:
                raise ProviderConfigError("Windows DPAPI operation failed")
            result = ctypes.string_at(output_blob.pbData, output_blob.cbData)
            return bytes(result)
        finally:
            ctypes.memset(input_buffer, 0, len(content))
            if output_blob.pbData:
                if not protect:
                    ctypes.memset(output_blob.pbData, 0, output_blob.cbData)
                kernel32.LocalFree(output_blob.pbData)


CommandRunner = Callable[[list[str]], tuple[int, str]]


def _run_command(arguments: list[str]) -> tuple[int, str]:
    completed = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    return completed.returncode, completed.stdout


class WindowsDirectoryHardener:
    def __init__(self, *, runner: CommandRunner = _run_command) -> None:
        self._runner = runner

    def harden(self, path: Path) -> None:
        identity_status, identity_output = self._runner(["whoami"])
        identity = identity_output.strip()
        if (
            identity_status != 0
            or not identity
            or any(character.isspace() for character in identity)
        ):
            raise ProviderConfigError("current Windows identity could not be resolved")
        status, _output = self._runner(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"{identity}:(OI)(CI)(F)",
                "*S-1-5-18:(OI)(CI)(F)",
            ]
        )
        if status != 0:
            raise ProviderConfigError("permission hardening failed")



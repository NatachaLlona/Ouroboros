"""Interactive credentials and restricted persistent Compose secret files."""
import os
import re
import subprocess
import sys
from pathlib import Path

from app.config import PROJECT_ROOT, save_config
from app.database import DatabaseError


def validate_name(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value):
        raise DatabaseError(f"{field} must contain 1-63 lowercase letters, digits, or underscores and must not start with a digit")
    return value


def read_password(prompt="Master database password: "):
    """Read one asterisk per character without echoing the actual password."""
    if not sys.stdin.isatty():
        raise DatabaseError("Credentials require an interactive terminal; run python start.py in the VS Code terminal")
    print(prompt, end="", flush=True)
    characters = []
    try:
        if os.name == "nt":
            import msvcrt
            def read():
                char = msvcrt.getwch()
                if char in ("\x00", "\xe0"):
                    msvcrt.getwch()
                    return ""
                return char
            return _read_masked(read, characters)
        import termios
        import tty
        fd = sys.stdin.fileno()
        original = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return _read_masked(lambda: sys.stdin.read(1), characters)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, original)
    finally:
        characters.clear()
        print(flush=True)


def _read_masked(read, characters):
    while True:
        char = read()
        if char in ("\x03", "\x1b", "\x04"):
            raise KeyboardInterrupt
        if char in ("\r", "\n"):
            if not characters:
                raise DatabaseError("Password must not be empty")
            return "".join(characters)
        if char in ("\b", "\x7f"):
            if characters:
                characters.pop()
                print("\b \b", end="", flush=True)
        elif char and char.isprintable():
            characters.append(char)
            print("*", end="", flush=True)


def prompt_credentials(config, root=PROJECT_ROOT):
    if not sys.stdin.isatty():
        raise DatabaseError("Credentials require an interactive terminal; run python start.py in the VS Code terminal")
    database = config["database"]
    if database["name"].strip():
        answer = input(f"Configured database: {database['name']}. Keep this database? [Y/n]: ").strip().lower()
        if answer not in ("", "y", "yes", "n", "no"):
            raise DatabaseError("Enter yes or no when choosing the database")
        if answer in ("n", "no"):
            database["name"] = input("Database name: ").strip()
    else:
        database["name"] = input("Database name: ").strip()
    validate_name(database["name"], "database.name")
    if database["user"].strip():
        answer = input(f"Configured master user: {database['user']}. Use this user? [Y/n]: ").strip().lower()
        if answer not in ("", "y", "yes", "n", "no"):
            raise DatabaseError("Enter yes or no when choosing the master user")
        if answer in ("n", "no"):
            database["user"] = input("Master database user: ").strip()
    else:
        database["user"] = input("Master database user: ").strip()
    validate_name(database["user"], "database.user")
    if not config.get("auth", {}).get("password_hash"):
        save_config(config, root)
    return read_password()


def write_secret(password, root=PROJECT_ROOT, filename="postgres_password"):
    """Restrict the directory before writing a persistent secret, including on Windows."""
    directory = Path(root) / ".secrets"
    if not re.fullmatch(r"[a-z_]+", filename):
        raise DatabaseError("Invalid secret filename")
    path = directory / filename
    try:
        if directory.is_symlink() or path.is_symlink():
            raise OSError("Symbolic links are not allowed for secrets")
        directory.mkdir(mode=0o700, exist_ok=True)
        if os.name == "nt":
            import csv
            import ctypes
            from ctypes import wintypes
            result = subprocess.run(["whoami.exe", "/user", "/fo", "csv", "/nh"],
                                    check=True, capture_output=True, timeout=15, shell=False)
            sid = next(csv.reader([result.stdout.decode().strip()]))[1]
            if not re.fullmatch(r"S-1-[0-9-]+", sid):
                raise OSError("Unable to resolve current Windows user")
            advapi = ctypes.WinDLL("advapi32", use_last_error=True)
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
            convert.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
            convert.restype = wintypes.BOOL
            apply = advapi.SetFileSecurityW
            apply.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
            apply.restype = wintypes.BOOL
            kernel.LocalFree.argtypes = [ctypes.c_void_p]
            kernel.LocalFree.restype = ctypes.c_void_p
            for target, inheritance in ((directory, "OICI"), (path, "")):
                if not target.exists():
                    continue
                descriptor = ctypes.c_void_p()
                if not convert(f"D:P(A;{inheritance};FA;;;{sid})", 1, ctypes.byref(descriptor), None):
                    raise ctypes.WinError(ctypes.get_last_error())
                try:
                    # Apply only the protected DACL; no audit privilege is required.
                    if not apply(str(target.resolve()), 0x80000004, descriptor):
                        raise ctypes.WinError(ctypes.get_last_error())
                finally:
                    kernel.LocalFree(descriptor)
        else:
            directory.chmod(0o700)
            if path.exists():
                path.chmod(0o600)
        # Keep the initialization secret unchanged on subsequent attempts, even if
        # the newly entered connection password is wrong. No password rotation occurs.
        if path.exists():
            return path
        with path.open("x", encoding="utf-8", newline="") as target:
            if os.name != "nt":
                os.fchmod(target.fileno(), 0o600)
            target.write(password)
        return path
    except (OSError, subprocess.SubprocessError):
        raise DatabaseError("Unable to create the restricted secret file; check filesystem permissions") from None

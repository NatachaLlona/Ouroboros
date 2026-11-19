"""Non-echoing human bootstrap and OS-protected SQL initialization secret."""
import getpass
import os
from pathlib import Path
import re
import subprocess
import sys
import warnings

from database.settings import ConfigurationError


def validate_password(password):
    if not (8 <= len(password) <= 16 and re.search('[A-Z]', password)
            and re.search('[a-z]', password) and re.search('[0-9]', password)
            and any(not char.isalnum() and not char.isspace() for char in password)
            and all(char.isprintable() and not char.isspace() for char in password)):
        raise ConfigurationError('App Password and PostgreSQL Master Password each require 8-16 characters, uppercase, lowercase, number and special character; no whitespace')


def _read_masked(read, stream):
    """Read non-echoing characters and render only editing feedback."""
    characters = []
    try:
        while True:
            char = read()
            if char in ('\r', '\n'):
                return ''.join(characters)
            if char in ('\x03', '\x04', '\x1b'):
                raise KeyboardInterrupt
            if char in ('\b', '\x7f'):
                if characters:
                    characters.pop()
                    stream.write('\b \b')
                    stream.flush()
            elif char and char.isprintable():
                characters.append(char)
                stream.write('*')
                stream.flush()
    finally:
        characters.clear()
        stream.write('\n')
        stream.flush()


def _windows_reader():
    """Use the non-echoing console API in PowerShell and VS Code ConPTY."""
    import ctypes
    from ctypes import wintypes
    import msvcrt
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetConsoleMode.restype = wintypes.BOOL
    mode = wintypes.DWORD()
    if not kernel.GetConsoleMode(kernel.GetStdHandle(-10), ctypes.byref(mode)):
        return None

    def read():
        char = msvcrt.getwch()
        if char in ('\x00', '\xe0'):
            msvcrt.getwch()  # Consume special keys without adding password characters.
            return ''
        if '\ud800' <= char <= '\udbff':
            low = msvcrt.getwch()
            if '\udc00' <= low <= '\udfff':
                return chr(0x10000 + ((ord(char)-0xd800) << 10) + ord(low)-0xdc00)
            return ''
        return char
    return read


def _read_hidden(prompt):
    """Never allow getpass to fall back to input with visible echo."""
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            return getpass.getpass(prompt)
        except getpass.GetPassWarning:
            raise ConfigurationError('A terminal with echo disabled is required') from None


def read_password(prompt):
    """Shared masked App Password/PostgreSQL Master Password entry."""
    if not sys.stdin.isatty():
        raise ConfigurationError('First startup requires an interactive terminal')
    if not sys.stdout.isatty():
        return _read_hidden(prompt)
    if os.name == 'nt':
        try:
            read = _windows_reader()
        except (OSError, ImportError):
            read = None
        if read is None:
            return _read_hidden(prompt)
        sys.stdout.write(prompt)
        sys.stdout.flush()
        return _read_masked(read, sys.stdout)
    try:
        import termios
        descriptor = sys.stdin.fileno()
        original = termios.tcgetattr(descriptor)
        masked = termios.tcgetattr(descriptor)
        masked[3] &= ~(termios.ECHO | termios.ICANON)
        masked[6][termios.VMIN] = 1
        masked[6][termios.VTIME] = 0
        termios.tcsetattr(descriptor, termios.TCSADRAIN, masked)
    except (ImportError, OSError, ValueError):
        return _read_hidden(prompt)
    try:
        sys.stdout.write(prompt)
        sys.stdout.flush()
        return _read_masked(lambda: sys.stdin.read(1) or '\x04', sys.stdout)
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, original)


def prompt_password(label):
    password = read_password(label+': ')
    validate_password(password)
    if password != read_password('Confirm '+label+': '):
        raise ConfigurationError(label+' confirmation differs')
    return password


def protect(path, directory=False):
    if path.is_symlink():
        raise ConfigurationError('Secret paths must not be symbolic links')
    if os.name == 'nt':
        import csv
        import ctypes
        from ctypes import wintypes
        result = subprocess.run(['whoami.exe','/user','/fo','csv','/nh'], check=True, capture_output=True, timeout=15)
        sid = next(csv.reader([result.stdout.decode().strip()]))[1]
        if not re.fullmatch(r'S-1-[0-9-]+',sid):
            raise ConfigurationError('Cannot resolve secret owner')
        advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(wintypes.DWORD)]
        convert.restype = wintypes.BOOL
        apply = advapi.SetFileSecurityW
        apply.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,ctypes.c_void_p]
        apply.restype = wintypes.BOOL
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        descriptor = ctypes.c_void_p()
        inheritance = 'OICI' if directory else ''
        if not convert(f'D:P(A;{inheritance};FA;;;{sid})',1,ctypes.byref(descriptor),None):
            raise ConfigurationError('Cannot protect secret permissions')
        try:
            if not apply(str(path.resolve()),0x80000004,descriptor):
                raise ConfigurationError('Cannot protect secret permissions')
        finally:
            kernel.LocalFree(descriptor)
    else:
        path.chmod(0o700 if directory else 0o600)


def sql_secret(root, relative):
    path = Path(root)/relative
    if path.parent.is_symlink() or path.is_symlink():
        raise ConfigurationError('Secret paths must not be symbolic links')
    path.parent.mkdir(mode=0o700, exist_ok=True)
    protect(path.parent, True)
    if not path.exists():
        password = prompt_password('New PostgreSQL Master Password')
        with path.open('x', encoding='utf-8', newline='') as output:
            if os.name != 'nt':
                os.fchmod(output.fileno(), 0o600)
            output.write(password)
    protect(path)
    return path

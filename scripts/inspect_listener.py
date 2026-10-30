"""Identify only the local API listener without printing arbitrary launch secrets."""
import json
from pathlib import Path
import re
import subprocess
import os
import struct

ROOT = Path(__file__).resolve().parents[1]


def process_directory(process_id):
    """Read only the Windows x64 process-parameter CurrentDirectory string.

    No environment, heap, authentication state or memory scan is performed.
    Unsupported architecture/access returns unavailable rather than guessing.
    """
    if os.name != 'nt':
        return None
    import ctypes
    from ctypes import wintypes
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        return None
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    native = ctypes.WinDLL('ntdll')
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    kernel.ReadProcessMemory.restype = wintypes.BOOL
    kernel.IsWow64Process.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    native.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)]
    native.NtQueryInformationProcess.restype = wintypes.LONG
    handle = kernel.OpenProcess(0x0400 | 0x0010, False, process_id)
    if not handle:
        return None
    try:
        wow = wintypes.BOOL()
        if not kernel.IsWow64Process(handle, ctypes.byref(wow)) or wow.value:
            return None
        basic = (ctypes.c_void_p * 6)()
        size = wintypes.ULONG()
        if native.NtQueryInformationProcess(handle, 0, ctypes.byref(basic), ctypes.sizeof(basic), ctypes.byref(size)) < 0:
            return None
        def read(address, count):
            buffer = ctypes.create_string_buffer(count)
            copied = ctypes.c_size_t()
            if not address or not kernel.ReadProcessMemory(handle, ctypes.c_void_p(address), buffer, count, ctypes.byref(copied)) or copied.value != count:
                raise OSError('Directory metadata unavailable')
            return buffer.raw
        parameters = int.from_bytes(read(basic[1] + 0x20, 8), 'little')
        length, maximum, pointer = struct.unpack('<HH4xQ', read(parameters + 0x38, 16))
        if not 0 < length <= maximum <= 65534 or length % 2:
            return None
        directory = read(pointer, length).decode('utf-16-le')
        return directory if re.fullmatch(r'[A-Za-z]:\\[^\x00-\x1f]*', directory) else None
    except (OSError, ValueError, UnicodeError, struct.error):
        return None
    finally:
        kernel.CloseHandle(handle)


def main():
    """Read process identity; never stop/restart a process or load credentials."""
    listing = subprocess.run(['netstat','-ano','-p','tcp'],capture_output=True,text=True,timeout=15,check=True)
    identities = []
    for line in listing.stdout.splitlines():
        parts = line.split()
        if len(parts) == 5 and parts[1].endswith(':6969') and parts[3] == 'LISTENING' and parts[4].isdecimal():
            identities.append(int(parts[4]))
    for process_id in sorted(set(identities)):
        command = ['powershell','-NoProfile','-Command',
            f'Get-CimInstance Win32_Process -Filter "ProcessId={process_id}" | Select-Object ExecutablePath,CommandLine,CreationDate,ParentProcessId | ConvertTo-Json -Compress']
        result = subprocess.run(command,capture_output=True,text=True,timeout=30,check=True)
        process = json.loads(result.stdout)
        executable, launch = process.get('ExecutablePath') or '', process.get('CommandLine') or ''
        local = bool(executable) and Path(executable).resolve().is_relative_to(ROOT / '.venv')
        # Only a recognized plain Python + start.py invocation may be shown.
        # Arbitrary arguments could contain credentials, so never echo them.
        normalized = launch.strip()
        if executable:
            normalized = re.sub(r'^"?' + re.escape(executable) + r'"?\s*','',normalized,flags=re.IGNORECASE)
        script = normalized.strip('"')
        expected = script in ('start.py',str(ROOT / 'start.py'))
        pair = re.fullmatch(r'\s*(?:"([^"]+)"|(\S+))\s+(?:"([^"]+)"|(\S+))\s*', launch)
        if pair:
            interpreter = pair[1] or pair[2]
            entry = pair[3] or pair[4]
            workspace_launch = Path(interpreter).is_absolute() and Path(interpreter).resolve().is_relative_to(ROOT / '.venv')
            if entry in ('start.py',str(ROOT / 'start.py')) and workspace_launch:
                local, expected = True, True
        directory = process_directory(process_id)
        project_confirmed = local and expected and (directory is not None and Path(directory).resolve() == ROOT or script == str(ROOT / 'start.py'))
        print(json.dumps(dict(pid=process_id,executable=executable,
            launch='python start.py (no additional arguments)' if expected else 'Unrecognized arguments omitted',
            command_line=launch if expected else 'Unrecognized arguments omitted',
            working_directory=directory,project_directory=str(ROOT) if project_confirmed else None,
            creation_date=process.get('CreationDate'),parent_pid=process.get('ParentProcessId'),
            workspace_executable=local,ouroboros_launch_confirmed=project_confirmed)))
    if not identities:
        print('No TCP listener on port 6969')


if __name__ == '__main__':
    try:
        main()
    except (subprocess.SubprocessError,OSError,ValueError):
        print('Listener identity inspection unavailable; no process was stopped or restarted')
        raise SystemExit(1) from None

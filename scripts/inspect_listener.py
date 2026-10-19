"""Identify only the local API listener without printing arbitrary launch secrets."""
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


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
            f'Get-CimInstance Win32_Process -Filter "ProcessId={process_id}" | Select-Object ExecutablePath,CommandLine | ConvertTo-Json -Compress']
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
        print(json.dumps(dict(pid=process_id,executable=executable,
            launch='python start.py (no additional arguments)' if expected else 'Unrecognized arguments omitted',
            workspace_executable=local,ouroboros_launch_confirmed=local and expected)))
    if not identities:
        print('No TCP listener on port 6969')


if __name__ == '__main__':
    try:
        main()
    except (subprocess.SubprocessError,OSError,ValueError):
        print('Listener identity inspection unavailable; no process was stopped or restarted')
        raise SystemExit(1) from None

"""Der Windows-Prüfstarter muss alte Startprotokolle erhalten."""
import os
from pathlib import Path
import subprocess
import time

import pytest


@pytest.mark.skipif(os.name != 'nt', reason='Windows-Prüfstarter')
def test_probe_launcher_uses_unique_logs_and_quoted_script_path(tmp_path):
    root = Path(__file__).resolve().parents[1]
    probe = tmp_path/'Prüfung mit Leerzeichen (1).py'
    probe.write_text("print('PROBE_OK', flush=True)\n", encoding='utf-8')
    logs = []
    for _ in range(2):
        completed = subprocess.run([
            'powershell.exe', '-NoProfile', '-File',
            str(root/'tools/launch_refactor_probe.ps1'), '-ProbeScript', str(probe),
        ], capture_output=True, text=True, timeout=30)
        assert completed.returncode == 0, completed.stderr
        directory = next(line.split(': ', 1)[1] for line in completed.stdout.splitlines()
                         if line.startswith('Startprotokolle: '))
        log = Path(directory)/'stdout.log'
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if log.exists() and 'PROBE_OK' in log.read_text(encoding='utf-8'):
                break
            time.sleep(0.05)
        assert log.read_text(encoding='utf-8').strip() == 'PROBE_OK'
        logs.append(log)
    assert logs[0] != logs[1]
    assert logs[0].read_text(encoding='utf-8').strip() == 'PROBE_OK'

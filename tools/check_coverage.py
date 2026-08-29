"""
Zeigt Coverage-Bericht fuer die wichtigsten Module.
Laeuft OHNE xdist um Coverage korrekt zu messen.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

result = subprocess.run(
    [
        sys.executable, "-m", "pytest", "tests/",
        "-q", "--no-header",
        "-o", "addopts=",
        "--cov=hpg_core",
        "--cov=main",
        "--cov-report=term-missing:skip-covered",
        "--cov-fail-under=70",
        "--no-cov-on-fail",
        "-m", "not slow",
    ],
    cwd=ROOT,
    capture_output=True,
    text=True,
    timeout=300,
)
# Nur Coverage-Tabelle ausgeben
output = result.stdout + result.stderr
lines = output.split("\n")
in_table = False
for line in lines:
    if "Name" in line and "Stmts" in line:
        in_table = True
    if in_table:
        print(line)
    if in_table and ("TOTAL" in line or "---" in line and "+" in line):
        if "TOTAL" in line:
            break
print("\nReturn code:", result.returncode)
if not in_table:
    print(output)
raise SystemExit(result.returncode)

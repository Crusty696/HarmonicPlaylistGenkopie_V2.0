"""
Zeigt Coverage-Bericht fuer die wichtigsten Module.
Laeuft OHNE xdist um Coverage korrekt zu messen.
"""
import subprocess, sys

result = subprocess.run(
    [
        sys.executable, "-m", "pytest", "tests/",
        "-q", "--no-header",
        "--cov=hpg_core",
        "--cov-report=term-missing:skip-covered",
        "--no-cov-on-fail",
        "-p", "no:xdist",
        "--timeout=120",
    ],
    cwd=r"C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main",
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

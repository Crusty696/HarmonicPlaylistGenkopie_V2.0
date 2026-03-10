"""Validiert alle Agent-Dateien in .claude/agents/ auf korrektes YAML-Frontmatter."""
import os, sys
try:
  import yaml
except ImportError:
  print("FEHLER: PyYAML nicht installiert. pip install pyyaml")
  sys.exit(1)

agents_dir = os.path.join(
  os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
  '.claude', 'agents'
)

errors = []
ok = []

for fname in sorted(os.listdir(agents_dir)):
  if not fname.endswith('.md'):
    continue
  fpath = os.path.join(agents_dir, fname)
  with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

  if not content.startswith('---'):
    errors.append(f"FAIL   {fname:35s} | Kein YAML-Frontmatter")
    continue

  parts = content.split('---', 2)
  if len(parts) < 3:
    errors.append(f"FAIL   {fname:35s} | Frontmatter nicht geschlossen")
    continue

  try:
    meta = yaml.safe_load(parts[1])
  except yaml.YAMLError as e:
    errors.append(f"FAIL   {fname:35s} | YAML-Fehler: {e}")
    continue

  body = parts[2].strip()
  checks = []

  name = meta.get('name', '')
  if not name or len(name) < 3 or len(name) > 50:
    checks.append(f"name ungueltig ({len(name)} chars)")

  desc = meta.get('description', '')
  if not desc or len(desc) < 50:
    checks.append(f"description zu kurz ({len(desc)} chars)")

  if '<example>' not in desc:
    checks.append("keine <example> Bloecke")

  model = meta.get('model', '')
  if model not in ('inherit', 'opus', 'sonnet', 'haiku'):
    checks.append(f"model ungueltig: {model}")

  color = meta.get('color', '')
  valid_colors = ['red', 'orange', 'yellow', 'green', 'blue', 'cyan', 'purple', 'magenta', 'white']
  if color not in valid_colors:
    checks.append(f"color ungueltig: {color}")

  tools = meta.get('tools', [])
  if not tools:
    checks.append("keine tools definiert")

  if len(body) < 50:
    checks.append(f"body zu kurz ({len(body)} chars)")

  join_str = ", ".join(checks)
  if checks:
    errors.append(f"WARN   {fname:35s} | {join_str}")
  else:
    ok.append(
      f"OK     {fname:35s} name={name:30s} model={model} "
      f"color={color:7s} desc={len(desc)}ch body={len(body)}ch tools={tools}"
    )

for line in ok:
  print(line)
for line in errors:
  print(line)

total = len(ok) + len(errors)
print(f"\n=== {len(ok)}/{total} OK, {len(errors)} Probleme ===")
sys.exit(1 if errors else 0)

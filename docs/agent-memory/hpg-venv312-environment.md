---
name: hpg-venv312-environment
description: "HPG braucht venv312 (Python 3.12) — altes venv/ ist Python 3.14 mit kaputtem numpy, numba braucht <3.13"
metadata: 
  node_type: memory
  type: project
  originSessionId: 996087b8-444a-4673-b80a-77294a78c37b
---

Für HPG immer `.\venv312\Scripts\python.exe` nutzen (Projekt-Root). Erstellt 2026-07-16 aus `C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe` + requirements.txt + pytest/pytest-xdist/pytest-cov/pytest-qt.

**Why:** Altes `venv/` ist Python 3.14.6 mit numpy 1.26.4 für älteres Python gebaut → ImportError `numpy.core._multiarray_umath`. numba (librosa-Dependency) braucht Python <3.13. Das war der "Blocker" aus AUDIT_REPORT.md.

**How to apply:** Tests: `& '.\venv312\Scripts\python.exe' -m pytest tests/ --no-cov -q -p no:cacheprovider`. Baseline 2026-07-16: 1433 passed. build.bat findet Python312 selbst (repariert). Siehe auch Projekt-Skills [[hpg-debugging]] in .claude/skills/.

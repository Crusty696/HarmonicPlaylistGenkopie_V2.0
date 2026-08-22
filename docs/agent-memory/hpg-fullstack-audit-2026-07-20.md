---
name: hpg-fullstack-audit-2026-07-20
description: "Full-Stack-Audit 2026-07-20 alle 7 Findings gefixt — Suite 1320 grün, CACHE_VERSION 18, Scoring-Kontext zentralisiert"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7a768d28-20fe-43d3-9919-b330a425f734
---

Am 2026-07-20 den Full-Stack-Audit-Bericht `FULLSTACK_AUDIT_HPG_2026-07-20.md` (7 Findings: 4 HIGH, 1 MEDIUM, 2 LOW) autonom komplett abgearbeitet. Endstand: **Suite 1320 grün** (245s, venv312), Headless-GUI-Smoke grün, `CACHE_VERSION = 18`.

Fixes:
- **HPG-001** (Scoring-Kontext-Drift): `resolve_scoring_context(mode, advanced_params)` in playlist.py neu — liefert die Scoring-Teilmenge (`SCORING_PARAMETERS = {harmonic_strictness, allow_experimental}`) der gewählten Strategie. Durchgereicht via neuen Parameter `scoring_context=` in `compute_transition_recommendations` + `calculate_playlist_quality`, und via `**self.scoring_context`/`self.current_scoring_context` in ALLE `calculate_enhanced_compatibility`-Aufrufe in main.py (Tabelle, Reorder, Drag-Drop-Recalc, Preview). Panel + MainWindow halten den Kontext. Strategien ohne strictness (Warm-Up etc.) → leerer Kontext → Sort und Anzeige einheitlich Default.
- **HPG-002** (AI-Provenienz): `has_valid_provenance()` in ai_engine.py; `calculate_ai_compatibility_bonus` gibt 0.0 ohne gültige aktuelle `_provenance` (provider/model/prompt_version/schema_version). Lazy-Import von ai_engine in playlist.py (requests-frei im Core-Scoring).
- **HPG-003** (AI-Worker-Abbruch): `ollama_pull(model, cancel_check=None)` mit Popen-Poll-Loop + terminate; alle AI-Worker (Detect/Test/Pull) prüfen `isInterruptionRequested()` vor Signal-Emit.
- **HPG-004** (Preview-Worker): `TransitionRenderWorker` verwaltet Executor manuell, `_terminate_executor()` killt Child bei Timeout/Cancel; Worker in closeEvent-Lifecycle aufgenommen.
- **HPG-005/006/007**: Doku-Sync (PRODUCTION_STATUS/README auf v18, 8 Strategien, 1317+ Tests, Py3.12.1), `AI_MODELS_AVAILABLE` gelöscht, `tools/_inspect_cache.py` von Shelve→SQLite read-only, `requests==2.34.2` in requirements.txt, no-op `pass` in main.py `__main__` entfernt.

**Why:** Vollständige Produktionsreife war das Ziel — die 4 HIGH mussten vor Release gefixt sein.

**Produktionsreife voll verifiziert (echte Ausführung, nicht nur Suite):** Coverage-Gate 76.39% (≥70, `-n auto`); E2E-Pipeline synthetisches Audio→ParallelAnalyzer→4 Strategien→M3U8+Rekordbox-XML-Export; 3 Transition-Typen rendern valides Audio; HPG-004-Terminate killt Child in 1.5s statt 30s-Block; Headless-GUI-Boot+closeEvent; **shippable EXE per PyInstaller (HPG.spec) neu gebaut (159 MB), startet offscreen ohne Crash** (scipy/numba-Freeze-Bugs weg). Commit bd85c68.

**How to apply:** Scoring läuft jetzt über EINEN Kontext — bei neuen Score-Anzeigen in main.py IMMER `scoring_context` mitgeben, sonst kehrt der Drift zurück. EXE ist gitignored (Artefakt); nach main.py/hpg_core-Änderungen `pyinstaller --clean --noconfirm HPG.spec` neu bauen. Siehe [[hpg-audit-2026-07-17]], [[hpg-venv312-environment]]. CACHE_VERSION-Stand ist 18 (nicht 14).

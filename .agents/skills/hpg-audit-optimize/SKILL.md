---
name: hpg-audit-optimize
description: Use when auditing, reviewing, cleaning up or optimizing the HPG codebase — Code-Review, toter oder doppelter Code, Doku-Widersprueche, Produktionsreife-Check, oder wenn ein Audit-Bericht aus docs/ gegen den aktuellen Stand abgeglichen werden soll.
---

# HPG Audit & Optimize

## Regel Null

**Statusdokumente sind Hypothesen, der Code ist die Wahrheit.** Dieses Repo
enthaelt sechs Audit-/Fixlog-Markdowns, deren Befunde grossteils erledigt
sind. Wer sie als offene Punkte behandelt, auditiert die Vergangenheit.

Vor jedem Audit: `git log --oneline -10`, `git status --short`, dann die
Behauptung im Code pruefen.

## Verifizierter Ist-Stand (2026-08-14, selbst gemessen)

| Fakt | Wert |
|---|---|
| Version | 3.7.2 |
| Testsuite | **1395 passed**, 26 warnings, ~162 s |
| Coverage | **75,28 %**, Gate 70 % erfuellt |
| `CACHE_VERSION` | **28**, `hpg_cache_v28.db` |
| Strategien | **8** (`STRATEGIES`, playlist.py:1864) |
| `main.py` | rund 4930 Zeilen |
| Kanonische Genres | **9** |
| Python | 3.12.10 in `venv312` |
| Worker-Cap | 4 (`PARALLEL_AUTO_MAX_WORKERS`) |

## Belegte Doku-Widersprueche

| Behauptung | Fundort | Realitaet |
|---|---|---|
| "main.py ~1600 Zeilen" | `CLAUDE.md`, `AGENTS.md` | 4868 |
| 10-11 Strategien, alte Namen | `docs/QUICK_START.txt` | 8, `STRATEGY_ALIASES` haelt Altnamen gueltig |
| `ui/main_window.py`, `GUI/`-Ordner | `docs/QUICK_START.txt` | existiert nicht, alles in `main.py` |
| veraltete Testzahlen | AGENT_HANDOFF, alte Fixlogs | real 1395 (2026-08-14) |
| "Build blockiert", `security.py`-Duplikat | alte Audit-Berichte | erledigt, Datei existiert nicht mehr |

`AUDIT_SKILL-TEAM_2026-07-24.md`, `FULLSTACK_AUDIT_HPG_2026-07-20.md` und die
`FIXLOG_*`-Dateien sind ausdruecklich **Snapshots**.

## Wo Fehler in diesem Projekt real entstehen

Nach Auswertung beider Voll-Audits, in dieser Reihenfolge:

1. **Qt-Worker-Lebenszyklus** — `finished` ueberschrieben, Cleanup am falschen
   Signal, verwaiste Worker ohne Source-Guard. Skill `hpg-qt-gui`.
2. **Ein Anker, ein Gitter** — Mixpoints und Sektionen auf verschiedenen
   Rastern, Off-Grid-Werte aus Fallback-Pfaden. Skill
   `hpg-mixpoint-engineering`.
3. **Cache maskiert Fixes** — `CACHE_VERSION` nicht gebumpt. Skill
   `hpg-cache-persistence`.
4. **Zwei Pfade, ein Fix** — Fast-Path und Voll-Path divergieren. Skill
   `hpg-audio-analysis`.
5. **UI verspricht, was der Code nicht liefert** — Parameter, die validiert,
   aber nie zugestellt werden.
6. **Skript meldet Erfolg ohne Wirkung** — Batch-Wrapper. Skill
   `hpg-release-build`.

## Aktuell offene, belegte Punkte

**Uncommittete Arbeitskopie** (Stand 2026-08-14): `main.py`, `hpg_core/theme.py`,
`tests/test_run_lifecycle.py`, `tests/test_theme.py`, `Start.bat`,
`build_installer.bat`, `requirements.txt`. Die Doku behauptet einen sauberen
Abschlusszustand — das stimmt nicht. Suite ist mit diesen Aenderungen gruen.

**Erledigt 2026-08-14:** die verwaisten `theme.RISK_*`-Konstanten wurden
entfernt, ebenso `caching._quarantine_cache_row`, `caching._is_confirmed_corrupt`,
`ErrorReporter.clear_errors` und `RekordboxImporter._time_to_seconds`. Die
doppelte Versionsquelle ist konsolidiert: `hpg_core/__init__.py` leitet
`__version__` aus `app_metadata.APP_VERSION` ab, ein Test haelt beides synchron.

## Audit-Vorgehen

1. Ist-Stand messen: Suite laufen lassen, `CACHE_VERSION` lesen, `git status`.
2. Behauptung waehlen, Code-Stelle zitieren, **ausfuehren** wo moeglich.
   Scoring- und Playlist-Befunde lassen sich direkt mit einem kleinen
   Python-Aufruf belegen statt vermuten.
3. Toten Code per Grep gegen **alle** Konsumenten pruefen, `tests/`
   eingeschlossen — ein Symbol, das nur Tests nutzen, ist tot, aber sein Test
   auch.
4. Doppelten Code nicht "reparieren", sondern konsolidieren: es gibt zentrale
   Helfer (`models.seconds_per_bar`, `quantize_to_grid`, `effective_bpm_diff`,
   `get_camelot_components`, `resolve_transition_mix_points`,
   `resolve_scoring_context`, `theme.COLORS`). Neue Inline-Kopie = Befund.
5. Fix, dann Volllauf plus die passende Verify-Suite. Bei geaendertem
   Analyse-Output `CACHE_VERSION` bumpen.
6. Findings mit Schweregrad, Codestelle und **reproduzierbarem** Fehlfall
   melden. "Sieht falsch aus" ist kein Finding.

## Grenzen ehrlich benennen

Gruene Tests beweisen **keine** musikalische Qualitaet. Interne Scores sind
keine Ground Truth. Aussagen ueber Uebergangsqualitaet brauchen den
Blindtest-Pfad (`tools/prepare_dj_blind_test.py`) oder eine Hoersession —
das steht so auch im `docs/DATA_AND_VALIDATION_CONTRACT.md`.

## Common Mistakes

- Alte Audit-Markdowns als To-do-Liste lesen.
- Toten Code entfernen und die zugehoerigen Tests stehen lassen.
- Optimieren ohne Messung (`tests/performance_fixtures.py`,
  `benchmark_rekordbox.py`, `tools/validation_run.py`).
- Mehrere kritische Module in einem Rutsch aendern.

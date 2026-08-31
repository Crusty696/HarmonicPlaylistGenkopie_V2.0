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

## Aktueller Abschlussbeleg (2026-08-31, selbst gemessen)

Der lokale Standardlauf mit explizitem isoliertem Windows-Basetemp
bestand **3537 Tests** und erreichte **85,85 % Coverage**. GitHub Actions auf
Commit `3c59dc8` bestand zusätzlich 3522
Standardtests; 46 Slow-Tests waren dort explizit abgewählt.

## Historischer Volltest-Snapshot (2026-08-25)

| Fakt | Wert |
|---|---|
| Version | 3.7.2 |
| Testsuite | **2035 passed**, 25 Warnungen (Abschlusslauf) |
| Coverage | **81,65 %**, Gate 70 % erfuellt |
| `CACHE_VERSION` | **37**, `hpg_cache_v37.db` |
| Strategien | **8** (`STRATEGIES`) |
| `main.py` | **5811 Zeilen** |
| Kanonische Genres | **9** |
| Python | 3.12.10 in `venv312` |
| Worker-Cap | 4 (`PARALLEL_AUTO_MAX_WORKERS`) |

Die Werte in dieser Tabelle sind historische Bestandteile des
Volltest-Snapshots vom 2026-08-25. Der aktuelle Code steht seit 2026-08-26 auf
`CACHE_VERSION = 44` und verwendet `hpg_cache_v44.db`.

## Belegte Doku-Widersprueche

| Fruehere Behauptung | Ehemaliger Fundort | Status 2026-08-25 |
|---|---|---|
| `main.py` mit 1600/4944/5351/5752 Zeilen | Statusdokus/Skills | korrigiert; volatile Zeilenzahl wird nicht mehr festgeschrieben |
| 10-11 Strategien, alte Namen | `docs/QUICK_START.txt` | korrigiert; 8, Aliase bleiben gueltig |
| `ui/main_window.py`, `GUI/`-Ordner | `docs/QUICK_START.txt` | korrigiert; alles in `main.py` |
| veraltete Testzahlen | alte Handoffs/Fixlogs | historische Snapshots; aktueller lokaler Abschlussbeleg 3537 |
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

## Worktree-Hinweis

**Historischer Snapshot 2026-08-14:** `main.py`, `hpg_core/theme.py`,
`tests/test_run_lifecycle.py`, `tests/test_theme.py`, `Start.bat`,
`build_installer.bat`, `requirements.txt`. Die Doku behauptet einen sauberen
Abschlusszustand — das stimmt nicht. Suite ist mit diesen Aenderungen gruen.

**Aktuell 2026-08-25:** Der gemessene Stand ist eine uncommittete
Arbeitskopie. Vor Freigabe oder Commit deshalb `git status --short` neu lesen.

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

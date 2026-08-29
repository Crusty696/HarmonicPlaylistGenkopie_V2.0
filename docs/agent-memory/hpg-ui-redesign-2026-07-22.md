---
name: hpg-ui-redesign-2026-07-22
description: GUI-Redesign Ink Navy Gold — Theme + Camelot-Rad-Widget + Deck-Wellenform in echter App (commits f77e719/c9f5982/db705b6)
metadata: 
  node_type: memory
  type: project
  originSessionId: 7a768d28-20fe-43d3-9919-b330a425f734
  modified: 2026-07-22T03:09:03.149Z
---

Am 2026-07-22 GUI-Redesign der echten PyQt6-App begonnen und die drei größten Elemente umgesetzt (User-Wahl: voller Struktur-Umbau, Farbschema **Ink Navy Gold**, erst alles dann testen).

**Farbschema Ink Navy Gold** (in Prototyp abgestimmt, dann theme.py): Ground Navy `#0c1430` (kräftig), Akzent Gold `#d6ac44` (satt, Hue 43°), Sekundär Stahlblau `#6f8fc4`, gedämpfte Status/Genre/Phase-Farben (kein Neon). NICHT die 4 ersten Neon-Konzepte, NICHT die späteren gedämpften Steel/Brass — User wählte explizit „Ink Navy Gold" und ließ Navy kräftiger + Gold satter machen (Hue unverändert).

**Umgesetzt (committed + gepusht, EXE gebaut):**
- `f77e719` theme.py: COLORS/GENRE_COLORS/RISK_STYLES/PHASE_COLORS/TRANSITION_TYPE_COLORS auf Navy-Gold. Globales QSS recoloriert damit ALLE Standard-Widgets automatisch.
- `c9f5982` main.py: `CamelotWheelWidget(QWidget, paintEvent)` im AnalyticsPanel (Quality-Reiter) — A/B-Rad 24 Keys gedämpftes Spektrum, Set-Pfad mit Reihenfolge-Badges, Kantenfarbe nach `calculate_enhanced_compatibility` (grün/amber/rot), BPM-Clash = rote gestrichelte Kante. `set_analytics(quality, playlist, bpm_tolerance)`.
- `db705b6` main.py: `WaveformWidget` (Deck) im TransitionPreviewWidget — Peak-Hüllkurve aus gerendertem Clip via soundfile, Crossfade-Region gold, Playhead. Segment-Labels von hartkodiert Blau/Lila/Grün auf Theme-Tokens.

Verifiziert: Suite 1319 grün, Headless-Paint (Rad + Waveform als PNG geprüft — sehen gut aus), EXE baut + startet offscreen.

**Noch offen (User-Go):** Junction-Deltas (Key±/BPM±/Energie±) in Playlist-Tabelle, Font-System (Sans-UI + Mono-Daten statt überall Mono), Feinschliff einzelner Panel-Layouts (mattes Analyzer-Layout).

**Vorschau-Artefakt** (claude.ai): Voll-Prototyp aller 5 Reiter mit Farbschema-Umschalter — Struktur/Elemente dort abgestimmt bevor in PyQt umgesetzt.

**Why:** User will die App visuell modernisieren (weg vom Neon-DAW-Look).

**How to apply:** theme.py `COLORS` ist der zentrale Farb-Treiber. Neue Custom-Widgets (Rad/Waveform) lesen COLORS-Tokens → automatisch theme-konform. Siehe [[hpg-chirurgie-audit-2026-07-21]]. ACHTUNG 2026-07-22: parallele Bug-Hunt-Session ließ 14 uncommittete Dateien im Working Tree (analysis/dj_brain/playlist/exporters + tests) — NICHT meine, „2 Funde offen".

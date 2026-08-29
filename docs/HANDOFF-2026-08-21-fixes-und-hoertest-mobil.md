# Handoff 2026-08-21 (Nacht) — Hoertest mobil, Renderer-Pegel, Set-Timeline, Altlasten

Fortsetzung von `HANDOFF-2026-08-21-scoring-an.md`. Regel bleibt: Statusdokumente
sind Hypothesen, der Code ist die Wahrheit.

## Hoertest

1. **Feste Blende fuer alle Clips** (`5d1d8ad`): `tools/rate_transitions.py`
   rendert jetzt jedes Paar mit `HOERTEST_TRANSITION_TYPE = "pro_eq_swap"`
   (3-Band-EQ, kein Echo/Cut/Sweep). Vorher lief `predict_transition_type`
   je Paar, der Effekt variierte von Clip zu Clip und ging als nicht erfasste
   Stoergroesse in die Note ein. **Alle Altnoten verworfen** (43 Psy + 46
   Misch), Sicherung in `Music\HPG-Hoertest-Sicherung\*_vor_eqfest_20260821.csv`.
   Alle 280 Clips neu gerendert (120 Psy, 160 Misch), 0 Fehler.
2. **Mobiler Ordner** `C:\Users\david\Music\HPG-Hoertest-Mobil\` (2,6 GB):
   `hoertest_server.py` (nur Stdlib), `Psytrance\` (Port 8766), `Mischsatz\`
   (Port 8765), `Start.bat` (findet Python 3, startet beide Server, oeffnet
   Browser, idempotent), `Stop.bat`, `LIESMICH.txt`. Noten landen sofort in
   `<Satz>\bewertung.csv`; Rueckgabe = nur diese beiden Dateien. Der Nutzer
   kopiert den Ordner selbst auf den Stick (F:). **Achtung:** PC-Saetze und
   Mobil-Ordner sind getrennte Kopien — nur an einem Ort bewerten.
3. Ziel je Satz: mindestens 40 Noten >= 4 UND 40 Noten <= 3
   (`MIN_EREIGNISSE_JE_MERKMAL = 10` x 4 Merkmale, beide Klassen).
4. **Offen:** die nach `5a6861e` (Renderer-Pegel, unten) noch nicht neu
   gerenderten Hoertest-Clips. Entscheidung des Nutzers, ob erneut rendern
   (bisher 13 Noten im Mischsatz seit dem EQ-Render).

## Fixes (Reihenfolge vom Nutzer bestaetigt: 5 -> 3 -> 6 -> 7 -> 1+2 -> 4)

- **#5 Renderer-Pegel** (`5a6861e`): `_rms_normalize` bekommt `reference`
  (Solo-Teil: Vorlauf nur A, Nachlauf nur B); Block steht hinter dem
  Beat-Alignment. Messung vorher an 280 Clips: Vorlauf/Blende/Nachlauf im
  Median gleich laut (Hypothese "Vorlauf systematisch lauter" widerlegt),
  aber Pegelsprung Vorlauf->Nachlauf bis +8/-13 dB RMS, LUFS der Solo-Teile
  bis 10 dB auseinander; nach dem Fix LUFS-Differenz <= 0.3 dB an den 7
  schlimmsten Paaren. **Betrifft auch die App-Preview** (`from_plan`, 30/30 s).
  Skill `hpg-transition-render` (Abschnitt Pegel) nachgezogen. Punkt 3 des
  Handoffs "blende-und-hoertest" ist damit beantwortet.
- **#3 Set-Timeline** (`e946080`): `_calculate_timeline_entries` rechnet
  Set-Laenge aus Mix-In..Mix-Out (erster Track ab 0, letzter bis Ende, B
  startet an mix_in_b wenn A mix_out_a erreicht, Eintraege ueberlappen um
  overlap). Fallbacks ohne Plan aus `_resolve_mix_points`. Regression:
  10 x 450 s, Mix-In 60 / Mix-Out 360 -> 52,5 statt 70,5 min.
- **#6 Altlasten** (`b5aa8a5`): `tools/dj_report.py` geloescht (0
  Referenzen); `hpg_core/__init__.py` ohne Re-Exporte (Paket-Import zieht kein
  librosa mehr); drei identische Genre-Resolver in `playlist.py`
  (calculate_enhanced_compatibility, predict_transition_type,
  _sort_context_flow) -> `_resolve_track_genre`. **Bewusst belassen:**
  `get_key` (Test-Seam, 22 Vorkommen in tests/), `calculate_lufs` (6 Tests),
  `bars_to_seconds`, `get_format_info`, `BARS_PER_PHRASE`, Track-Felder
  `avg_mids/avg_highs/danceability/lufs_*` (Entfernen = CACHE_VERSION-Bump).
  Varianten der Genre-Aufloesung bei playlist.py:1154 ("" statt "Unknown")
  und :1675 (ohne ID3-Fallback) sind abweichend und unangetastet.
- **#7 Doku** (der Commit, der diese Datei anlegt): CLAUDE.md (5351 Zeilen,
  1792 Tests, vier fehlende Module), `hpg-orientation` alle 14 Zeilenrefs
  nachgemessen. Noch veraltet (eigener Anlass):
  `docs/PLAYLIST_ALGORITHMEN_ERKLAERUNG.md` ("10 Strategien") und
  `HANDOFF-2026-08-20-groove-scoring.md:189` ("Flag auf False").

## Mixpunkte — Befund, kein Fix (#1/#2 offen)

- Der Nutzer hat klargestellt: **wo gemischt wird, ist pro Track individuell,
  pro Paar gibt es mehrere gute Moeglichkeiten. Keine Einheitsregel bauen,
  Kandidaten anbieten.** (Memory `hpg-mixpunkte-individuell-cues-phrasen`.)
- Messung an 280 Paaren: laut Analyzer-Sektionen liegt kein Mix-In vor dem
  Intro-Ende und kein Mix-Out nach dem Outro-Start — der Guard haelt. Aber
  der Analyzer raet Intro/Outro viel zu kurz (Psy: Intro-Ende Median 28 s,
  Outro 22 s), deshalb hoert der Nutzer "Mixpunkt im Intro".
- Alle 77 Psy-Tracks haben 6-11 Rekordbox-Cues, fast alle unbenannt, gesetzt
  auf Chorus/Drop-Starts. HPG-Heuristik (`analysis.py` ~1672): Cue 2 = Mix-In,
  letzter Cue = Mix-Out. Mix-In trifft Cue 2 in 93/120 Paaren; Mix-Out liegt
  Median 21 s VOR dem letzten Cue (floor-Quantisierung eine Phrase frueher),
  die Blende laeuft dann ueber den Cue.
- Rekordbox-Phrasen (PSSI: Intro/Up/Chorus/Down/Outro) liegen in
  `D:\PIONEER\Master\share\PIONEER\USBANLZ\<AnalysisDataPath>\ANLZ0000.EXT`
  (4844 Dateien), `pyrekordbox.anlz.AnlzFile.parse_file` liest sie,
  `AnalysisDataPath` aus master.db. HPG liest aus ANLZ nur PQTZ (Beatgrid).
- Naechster Schritt (Design mit dem Nutzer): PSSI-Phrasen + Cues als
  Kandidatenmenge pro Paar; Phrasengitter aus PSSI statt Schaetzung.
  CACHE_VERSION-Bump, Neuanalyse der 231 Tracks.

## #4 Melodic Techno — offen

Braucht Hoertest-Noten; `GENRE_TRANSITION_TOLERANCES` ist je Genre ein eigener
Dict, ein abweichender Eintrag braucht keine neue Mechanik.

## Server

PC: `tools/hoertest_server.py --dir Music\HPG-Psytrance --port 8766` und
`--dir Music\HPG-Hoertest --port 8765` (laufen am Sessionende).

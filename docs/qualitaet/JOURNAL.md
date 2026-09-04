# Qualitaets-Journal

Fortlaufende Schleife: Fehler, toten Code, doppelten Code und gebrochene
Zusammenhaenge finden, belegen, beheben, beweisen. Ein Eintrag je Runde.

## Regeln der Schleife

1. **Finden** — read-only, mit Beleg (Datei:Zeile), nie aus einem Statusdokument.
2. **Pruefen** — jeder Befund wird selbst nachgemessen. Ein Subagenten-Bericht
   ist eine Hypothese, kein Beleg.
3. **Bauen** — erst wenn der Befund steht und die Wirkung auf alle Aufrufer
   geklaert ist. Kleinste Aenderung, die das Problem loest.
4. **Beweisen** — Regressionstest, der VOR der Korrektur rot ist, plus volle
   Suite. Ohne roten Vorher-Lauf gilt der Test als wirkungslos.
5. **Tor** — `hpg-waechter` an Tor 1 (Vorhaben) und Tor 2 (Diff). Bei
   ZURUECKGEWIESEN wird nachgebessert, nicht committet.
6. **Dokumentieren** — Runde hier eintragen: was gefunden, was belegt, was
   verworfen, was offen.

## Offene Posten (aus HANDOFF.md und laufenden Pruefungen)

- V-012: Parameter existiert, die GUI reicht ihn nicht durch.
- V-010: `transition_metrics_from_candidate` meldet perfekte Passung bei
  BPM 0.0; erreichbar aus `tools/rate_transitions.py` und
  `tools/audit_candidate_set.py`.
- V-015: offen als P3.
- ~~Doku-Drift in `.agents`~~ -- GESTRICHEN am 2026-09-04, selbst nachgeprueft
  und WIDERLEGT: `hpg-mixpoint-engineering` nennt nirgends CACHE_VERSION 42,
  sondern 34 als historischen Bump und verweist fuer den aktuellen Wert
  ausdruecklich auf `[hpg_core/caching.py]`. `hpg-audio-analysis` enthaelt
  ueberhaupt keine Zeilenangabe. Beide Behauptungen stammten ungeprueft aus
  einem aelteren Handoff -- genau die Fehlerklasse, gegen die dieses Journal
  gebaut ist.
- `analysis.py`-Lauf koennte unter der neuen Merge-Regel neu gemerged werden
  (braucht einen Baum am Audit-Commit).
- Vor dem naechsten `--apply` gegen den echten Vault: Trockenlauf lesen. Die
  Aenderung an `evidence_markdown` beruehrt jede bestehende Notiz.

## Runden

### Runde 0 — 2026-09-04 — C2/C3 Datenverlust am Wissensspeicher

Gefunden: der Vault-Sync loeschte alles ausserhalb von `## Nutzerkommentar`,
obwohl die GENERATED-Marker nur den Block dazwischen versprechen; und
`learnings.json` wurde ersetzt statt vereinigt, wodurch Wissen frueherer
Laeufe verschwand.

Tor 2 zuerst ZURUECKGEWIESEN — neun Befunde, zwei davon hoch: `tags` im
Blockstil zerstoerte das gesamte Frontmatter, und der vereinigte, ungepruefte
Bestand floss in die Renderer und brach dort mit KeyError statt mit einer
Meldung ab. Beide behoben, dazu CRLF-Notizen, doppelte Marker, die
Ueberschrift bei Bestandsnotizen und die Quellenpruefung je Learning statt je
Learning-ID.

Status: Nachbesserung liegt an Tor 2.

### Runde 1 — 2026-09-04 — Bestandsaufnahme toter und doppelter Code

Zwei read-only Aufklaerer ueber `hpg_core/`, `main.py`, `tools/`. Beide haben
ihre Detektoren an synthetischen Faellen gegengeprueft und ausdruecklich
gemeldet, wonach sie gesucht und NICHTS gefunden haben. Nachgemessen habe ich
selbst; ein Punkt hielt der Nachmessung nicht stand.

**Selbst bestaetigt, zur Behebung vorgemerkt:**

- **D1 (hoch)** `transition_renderer.py:326-330`: sobald `tempo_ratio` gesetzt
  ist, wird die Half/Double-Erkennung darueber (`:307-318`) wirkungslos --
  `raw_rate = 1.0 / tempo_ratio` ignoriert `target_bpm_b`. `from_plan`
  (`:161`) setzt `tempo_ratio` IMMER und `strict_beat_sync=True`;
  `playlist.py:2601` berechnet es als rohes `upcoming.bpm / current.bpm`, ohne
  Half/Double. Fuer A=140, B=70 (`effective_bpm_diff` -> `(0.0, "half")`,
  passiert also jedes Gate) ergibt das `raw_rate = 2.0`, Clamp auf 1.08,
  `BeatSyncError` -- kein Preview. `tools/rate_transitions.py:1493` baut den
  Spec OHNE `tempo_ratio` und rendert denselben Uebergang sauber. Die App kann
  damit einen Paartyp nicht abspielen, den ihr eigenes Scoring ausdruecklich
  unterstuetzt (`BPM_HALF_DOUBLE_ENABLED = True`,
  `BPM_HALF_DOUBLE_PENALTY = 0.85`, `PAAR_HALF_DOUBLE_MAX_BARS = 16`).
- **D2 (hoch)** `config.py:197` `TRANSITION_FEATURES_ENABLED = True` hat keinen
  einzigen Leser -- der einzige weitere Treffer im Code ist ein Kommentar in
  `tests/test_scoring_contract.py:163`. `playlist.py` berechnet die
  Uebergangs-Merkmale bedingungslos. Der dokumentierte A/B-Vergleich fuer den
  Hoertest ist damit nicht durchfuehrbar.
- **D3 (mittel)** `config.py:56` `LUFS_REFERENCE = -18.0` hat keinen Leser; der
  einzige weitere Treffer ist eine Docstring-Zeile in `analysis.py:586`.
  `transition_renderer.py:128` normalisiert gegen fest verdrahtete `-14.0`.
  Zwei Dokumentationsstellen nennen also einen Wert, mit dem nichts rechnet.
- **D4 (mittel)** `playlist.py:3391` `_immutable_metrics_from_candidate` ist
  ohne Aufrufer, ebenso `playlist.py:3462` `legacy_transition_metrics`,
  waehrend die Schwesterfunktion `legacy_transition_recommendations` in
  `main.py` lebt.

**Nachgemessen und VERWORFEN:** Der Bericht behauptete,
`_immutable_metrics_from_candidate` wuerde beim Aufruf mit `NameError`
scheitern, weil `metrics` ungebunden sei. Der Code liest an diesen Stellen
`legacy.structure_match` und `legacy.energy_delta`. Die Funktion ist tot,
aber sie ist lauffaehig. Beispiel dafuer, warum ein Subagenten-Bericht eine
Hypothese bleibt.

**Weiter zu pruefen, noch nicht selbst nachgemessen:** Rundungs-Divergenz
zwischen `dj_brain.seconds_to_bars` (rundet) und `analysis.py:2060/2571`
(`int()`, trunkiert); zwei Begriffe von "Genre dieses Tracks"
(`_resolve_track_genre` mit ID3-Fallback gegen `dj_brain` ohne); gegensaetzliche
Outro-Deckel in `playlist._outro_overlap_limit` (`None` = keine Grenze) und
`pair_candidates.blend_bars_options` (`[]` = unmoeglich); verschieden lange
Analysefenster in beiden Analysepfaden (360 s gegen 600 s).

Nichts davon ist gebaut. Erst Tor 1 je Befund, dann Umsetzung.

**Nachtrag Runde 1 — selbst nachgemessen:**

- **D5 (niedrig)** `dj_brain.py:252-253` liefert die Mix-Takte ueber
  `seconds_to_bars`, das rundet. `analysis.py:2060-2061` (Fast-Path) und
  `:2571-2572` (Vollpfad) ueberschreiben den Rueckgabewert sofort mit
  `int(mix_point / seconds_per_bar)`, also Trunkierung. Die Berechnung aus
  `dj_brain` wird damit verworfen. Bei `bpm=120`, `mix_out_point=99.0 s` sind
  das `49` im Cache gegen `50` in der Anzeige (`main.py:319` rundet wieder).
  Der gespeicherte Wert dient laut `main.py:322` nur noch als Fallback bei
  `bpm <= 0`, der Schaden bleibt also bei einer Taktangabe in Cache und
  Export. Kein Audio-Effekt: massgeblich sind die Sekundenwerte.
- **D6 (mittel, Entscheidung noetig)** Zwei Begriffe von "Genre dieses
  Tracks" in derselben Schleife. `playlist.py:2242-2244` bildet `has_dj_data`
  allein aus `detected_genre`; alles andere geht ueber
  `_resolve_track_genre` (`playlist.py:613-624`), das auf das ID3-Genre
  zurueckfaellt. Ein Track mit `detected_genre = "Unknown"` und ID3
  `"Deep House"` wird von der Kandidatenbewertung mit Deep-House-Toleranzen
  behandelt, waehrend der DJ-Brain-Zweig ihn als unbekannt ueberspringt.
  Hier NICHT selbstaendig aendern: das verschiebt Scoring-Ergebnisse. Erst
  vorlegen, wie bei V-004.
- **D7 (mittel)** Gegensaetzliche Antwort auf dieselbe Frage. Reicht der Raum
  bis zum Outro nicht fuer `MIN_TRANSITION_BARS`, gibt
  `playlist._outro_overlap_limit` (`playlist.py:1938-1939`) `None` zurueck,
  und `None` heisst dort "keine Grenze" -- der Legacy-Pfad blendet dann bis
  zum 64-Sekunden-Deckel weiter, mitten ins Outro. `blend_bars_options`
  (`pair_candidates.py:612-619`) gibt im selben Fall `[]` zurueck, also
  "Kandidat unmoeglich". Genau die Paare, die der Kandidatenpfad als zu eng
  verwirft, behandelt der Fallback-Pfad am groesszuegigsten.
- **D8 (mittel)** Beide Analysepfade messen die Track-Merkmale ueber
  verschieden lange Fenster: Fast-Path `librosa.load(..., duration=360)`
  (`analysis.py:1907`), Vollpfad `duration=600` (`analysis.py:2290`), danach
  in beiden dieselben Aufrufe fuer `calculate_energy`,
  `analyze_frequency_bands` und `compute_groove_fields`. Ein 480 s langer
  Track bekommt damit je nach Vorhandensein von Rekordbox-Metadaten
  verschiedene `energy`- und `avg_*`-Werte, und die fliessen ueber
  `transition_features` ins Scoring. Fuer Struktur und Outro gibt es mit
  `LIBROSA_TAIL_DURATION` eine Kompensation, fuer die Merkmale nicht. Der
  RAM-Grund der Fensterlaengen ist in `config.py:158-166` dokumentiert, die
  Pfadabhaengigkeit der Merkmale nicht.

### Runde 2 — 2026-09-04 — D1, D3, D4 gebaut

**D1 behoben.** `transition_renderer.py`: `raw_rate` kommt jetzt immer aus
`spec.bpm_a / target_bpm_b`. `tempo_ratio` bleibt, was es laut
`validate_transition_clip_spec` immer war -- der Vertragsabgleich zwischen
Plan und Spec --, und das steht jetzt als Kommentar daneben, damit die
naechste Aufraeumrunde es nicht als tot loescht. Die Log-Zeile behauptet bei
Rate 1.0 keine Tempoanpassung mehr.

Regressionstest `TestHalfDoubleRate`: misst die an `time_stretch` uebergebene
Rate, nicht das Ausbleiben eines Fehlers. Gegen den alten Code rot mit
"benoetigt Rate 2.000, erlaubt 0.92-1.08" -- also aus dem richtigen Grund.
Das zweite Paar (128/124) belegt, dass die Aenderung fuer alles ausser
Half/Double ein No-Op ist.

GRENZEN, die diese Korrektur NICHT abdeckt:
- Der Preview entsteht jetzt, aber ob er im TAKT sitzt, ist damit nicht
  belegt. `bar_sec_b` (`transition_renderer.py:420-422`) und der Vorlauf
  (`:292`) messen B's Phase gegen einen 70-BPM-Takt, `_align_beat_phase`
  bekommt aber `bpm=spec.bpm_a` = 140. B's Takt 1 landet damit auf irgendeinem
  Downbeat von A, nicht zwingend am Phrasenanfang. Offener Posten.
- Die Half/Double-Erkennung nutzt die relative Toleranz `bpm_a * 0.04`, die
  Gates dagegen absolute 2.0 BPM. Sie greift also erst ab `bpm_a > 50`.

**D3 behoben.** `LUFS_REFERENCE` samt ihrer beiden Kommentarzeilen entfernt.
Der Docstring in `analysis.py` nennt jetzt KEINEN Zahlenwert mehr: die
`-14.0` aus `transition_renderer.py:128` sind ein RMS-Ziel des Preview-
Renderers und nicht dasselbe wie ein LUFS-Wert -- sie dort einzusetzen haette
eine falsche Behauptung durch die naechste ersetzt. Die Gain-Angleichung
arbeitet rein relativ (`dj_brain._gain_advice` gegen `GAIN_DIFF_SHOW_DB` und
`GAIN_DIFF_WARN_DB`), einen absoluten Referenzpegel gibt es nicht. Beide
`hpg-audio-analysis`-Spiegel nachgezogen; `docs/HANDOFF-*` und `docs/plans/*`
bleiben als historische Dokumente unveraendert.

**D4 behoben.** `_immutable_metrics_from_candidate` und
`legacy_transition_metrics` entfernt. Letztere ist ein oeffentlicher Name --
ein nicht eingechecktes Skript ausserhalb des Repos wuerde nach der Loeschung
mit ImportError brechen. `legacy_transition_recommendations`,
`legacy_transition_metrics_for_snapshot`, `ImmutableMetricsSnapshot` und
`CandidateSnapshot.from_pair_candidate` bleiben, alle vier haben Aufrufer.

Suite nach D1/D3/D4: 3804 gruen -- Zwischenstand, gemessen VOR den vier
spaeter ergaenzten Tests am Audit-Werkzeug. Endstand dieser Runde: 3811.

**D2 praezisiert (2026-09-04, selbst nachgemessen):** Der Schalter war NIE
die Ursache. `playlist.py:888-891` berechnet `groove`, `bass`, `timbre` und
`mood` bedingungslos und uebergibt sie an `combine_weighted`. Was am
2026-08-21 wirklich umgestellt wurde, sind die GEWICHTE -- der Schalter stand
schon vorher wirkungslos herum. Damit ist auch der Gedaechtniseintrag
"TRANSITION_FEATURES_ENABLED seit 21.08. AN" irrefuehrend: das Setzen auf
True hat nichts bewirkt.

`docs/status_audit_2026-08-27/E_persistenz_infra.md:185` hat den Befund
bereits gemeldet ("kein Import nirgends"). Er wurde nicht behoben -- ein
Beleg dafuer, dass ein Statusdokument ohne Schleife folgenlos bleibt.

Zwei Wege, ENTSCHEIDUNG DES NUTZERS noetig:
1. Schalter loeschen, Doku und Gedaechtnis korrigieren. Aendert kein
   Verhalten. Der dokumentierte A/B-Vergleich bleibt unmoeglich -- er war es
   immer, denn der Schalter hat nie etwas geschaltet. A/B ginge stattdessen
   ueber das Groove-Gewicht 0.
2. Schalter tatsaechlich anschliessen. Bei `True` bit-identisch zu heute,
   erst `False` wuerde etwas aendern. Mehr Verzweigung im Scoring-Pfad.

Meine Neigung: Weg 1. Weg 2 baut eine zweite Wahrheit neben die Gewichte.
Nicht gebaut, wartet auf Entscheidung.

### Runde 3 — 2026-09-04 — Auflagen aus beiden Tor-2-Urteilen

Beide Aenderungssaetze standen auf MIT AUFLAGEN. Dreizehn Befunde, davon vier
mittel. Die vier gewichtigen, alle selbst nachgemessen:

- **Die Marker-Entschaerfung lag nur um das Zitat.** `impact`, `claim`,
  `rule` und `path` werden ebenso roh interpoliert und sind auf keine Zeile
  beschraenkt. Ein Audit ueber dieses Modul haette die Markerzeile ueber die
  Auswirkung einschleusen koennen. Jetzt liegt die Entschaerfung um den
  ganzen Block UND um die Ueberschrift, die ausserhalb der Marker steht.
- **Bei Rate 1.0 lief `time_stretch` trotzdem** -- ein voller
  Phase-Vocoder-Roundtrip mit Rekonstruktionsartefakten auf Material, das
  unveraendert bleiben soll, waehrend die neue Log-Zeile "Kein Time-Stretching
  noetig" behauptete. Der Aufruf wird jetzt uebersprungen. Der Test misst
  entsprechend, dass NICHT gerufen wurde, und belegt ueber das Log, dass der
  Zweig ueberhaupt erreicht wurde -- sonst waere er auch bei einem frueheren
  Abbruch gruen.
- **`_titel_aktualisieren` benutzte weiter den Fence-Automaten**, den ich fuer
  die Markererkennung aus gutem Grund entfernt hatte. Ein nicht geschlossener
  Codeblock oberhalb haette den Titel dauerhaft eingefroren, ohne Hinweis.
  Jetzt zaehlt nur die erste nicht leere Zeile.
- **Das BOM ging bei jedem Sync verloren.** Der ausdruecklich byteerhaltende
  Pfad hielt sein Versprechen nicht.

Dazu: der Hinweis auf eine entschaerfte Markerzeile steht jetzt IN der Notiz
(vorher nur in der Skill-Doku -- im Vault stand ein als woertlich
ausgewiesenes Zitat, das an einer Stelle nicht woertlich war); der
`schema_version`-Kommentar widersprach dem Code und nannte die Grenze nicht,
dass `veritas.command_init` der Laufdatei ohnehin immer die neueste Version
aufstempelt; der fuenfte Konfliktgrund "Notiz ohne lesbares Frontmatter"
fehlte in der Doku, ebenso der noetige Einmal-Handgriff fuer Altnotizen aus
der Zeit vor der Entschaerfung.

EIN TEST WURDE GEAENDERT, nicht nur ergaenzt:
`test_titel_im_codeblock_wird_nicht_fuer_die_ueberschrift_gehalten` sicherte
zu, dass der Titel trotz eines Codeblocks darueber nachgezogen wird. Mit der
neuen, einfacheren Regel wird er dort bewusst eingefroren. Der Kern des Tests
-- das Zitat bleibt unangetastet -- gilt unveraendert und wird weiter geprueft.

Gegenprobe ueber beide Saetze: fuenf Tests rot beim Rueckbau. Suite 3811 gruen.

### Runde 4 — 2026-09-04 — ZURUECKGEWIESEN, Ursache tiefer als gedacht

Der Wächter fand einen Fehler, den ich selbst eingebaut hatte: die
Marker-Entschaerfung lag im Neuanlage-Pfad, im Aktualisierungs-Pfad bekam
`_titel_aktualisieren` den ROHEN Claim. Nachgestellt: Lauf 1 sauber, Lauf 2
wuchs auf zwei Startmarker, Lauf 3 blockierte dauerhaft mit "mehrfache
VERITAS-Marker" — an einer Notiz, die das Werkzeug selbst geschrieben hatte.
Alle bisherigen Entschaerfungs-Tests starteten mit einer leeren Notiz und
konnten das nicht sehen.

URSACHE der Ursache: die Ueberschrift war ueberhaupt mehrzeilig. `claim` ist
auf eine Zeile nicht beschraenkt, und eine mehrzeilige Ueberschrift laesst
sich zeilenweise nicht stabil ersetzen — die Notiz waere auch OHNE Markerzeile
bei jedem Lauf gewachsen. Der Titel wird jetzt zusammengezogen und zusaetzlich
entschaerft. Beide Pfade speisen sich aus demselben Wert.

Handwerklicher Fehler dahinter, der Erwaehnung verdient: ein Skript brach an
einer Assertion ab, BEVOR es schrieb. Zwei von drei Aenderungen hatte ich
ueber ein anderes Werkzeug nachgezogen, die dritte nicht — und nicht
nachgeprueft. Dieselbe Escaping-Klasse ist in dieser Sitzung mehrfach
aufgetreten. Konsequenz: nach jedem Skript, das mehrere Stellen aendert, das
Ergebnis pruefen statt der Rueckmeldung zu vertrauen.

Weiter behoben: der Docstring von `_marker_positionen` verwies auf den alten
Funktionsnamen; `_frontmatter_teile` streifte mit `lstrip` beliebig viele BOMs
ab, schrieb aber nur eines zurueck; beide Skill-Spiegel beschrieben noch den
entfernten Fence-Automaten; drei Zeilenangaben in diesem Journal zeigten auf
den Stand VOR dem Diff; eine Zusicherung im Renderer-Test konnte nie rot
werden, weil sie auf einen Text prueft, der nur in der Exception steht, nicht
im Log.

Suite 3813 gruen. Auf Empfehlung des Waechters gehen die beiden Saetze als
ZWEI Commits ins Repo, gleiche Reihenfolge, gleicher Inhalt.

### Runde 5 — 2026-09-04 — dieselbe Fehlerklasse eine Ebene tiefer

Erneut ZURUECKGEWIESEN, Teil B war sauber. Der Befund: die Entschaerfung
deckte Rumpf und Ueberschrift, aber nicht das FRONTMATTER. `category` wird roh
in `kategorie:` UND in `tags:` interpoliert und ist auf keine Zeile
beschraenkt -- `veritas.py` prueft es nur als nichtleeren String, anders als
`severity` und `confidence` mit geschlossenem Vokabular.

Selbst nachgemessen ueber vier Laeufe: Startmarker 2, 3, 4, 5, Notizlaenge
651/686/721/756. Und schlimmer als der Vorgaenger: es wird KEIN Konflikt
gemeldet, weil `_marker_positionen` nur den Rumpf liest. `--apply` haette fuer
immer mit einer Differenz geendet, ohne dass irgendwo steht warum. Zwei
weitere Varianten derselben Klasse: eine `---`-Zeile in einem Wert schneidet
das Frontmatter ab, schlichte Mehrzeiligkeit laesst die Notiz um 13 Byte je
Lauf wachsen.

Behoben an der Wurzel: `_einzeilig` zieht JEDEN generierten
Frontmatter-Wert und die Ueberschrift auf eine Zeile und entschaerft die
Markerzeichenfolgen. Nach vier Laeufen: 663/663/663/663 -- stabil ab Lauf 1,
fuer alle drei Varianten. Test als `parametrize` ueber genau diese drei.

**Widerruf einer frueheren Entscheidung:** Der Waechter hatte die Zeile
`- Claim:` im generierten Block einmal als unbeauftragt beanstandet, ich hatte
sie entfernt. Sie kommt zurueck -- mit anderer Begruendung: seit der Titel
zusammengezogen wird, stuende der volle Wortlaut eines mehrzeiligen Claims
sonst nirgends mehr in der Notiz.

**Zwei eigene Journal-Behauptungen widerrufen.** Die "Doku-Drift in .agents"
(CACHE_VERSION 42; falsche Zeile in `hpg-audio-analysis`) habe ich
nachgeprueft: beide sind FALSCH. Der Skill nennt 34 als historischen Bump und
verweist fuer den aktuellen Wert auf `[hpg_core/caching.py]`; der andere
enthaelt ueberhaupt keine Zeilenangabe. Ich hatte sie ungeprueft aus einem
aelteren Handoff uebernommen -- genau die Fehlerklasse, gegen die dieses
Journal gebaut ist. Dazu vier Zeilenangaben korrigiert, die nach dem Diff
nicht mehr stimmten, und einen offenen Posten gestrichen, der in derselben
Datei 150 Zeilen weiter als erledigt gemeldet war.

**Nachtrag zur Offenlegung der Testaenderungen:** ausser dem geaenderten
Titel-Test wurde `test_nutzerkommentar_ueberlebt_ein_zitat_des_eigenen_markers`
ERSATZLOS GELOESCHT -- er prueft die entfernte `user_comment`. Die Zusicherung
tragen jetzt `test_text_hinter_dem_endmarker_bleibt_erhalten` und
`test_markerzeile_im_zitat_wird_entschaerft`.

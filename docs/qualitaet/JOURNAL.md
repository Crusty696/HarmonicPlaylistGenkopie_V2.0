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
  das `49` im Cache gegen `50` in der Anzeige (`main.py:320` rundet wieder).
  Der gespeicherte Wert dient laut `main.py:317-320` als Fallback in ZWEI
  Faellen: `sek < 0` und `bpm <= 0`, der Schaden bleibt also bei einer Taktangabe im Cache.
  Die Exporter lesen die Felder NICHT (2026-09-04 nachgemessen). Kein Audio-Effekt: massgeblich sind die Sekundenwerte.
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
  RAM-Grund der Fensterlaengen ist in `config.py:162-167` dokumentiert, die
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

### Runde 6 — 2026-09-04 — beide Saetze committet

`3bdaa77` (D1/D3/D4) und `3551c04` (C2/C3). Sieben Tor-2-Durchgaenge fuer den
Audit-Teil, jeder mit mindestens einem Befund, der bei der Nachbesserung des
vorigen entstanden war. Die Kette lohnt es, festzuhalten:

1. `BESTAETIGT` war strukturell unerreichbar (Prosa-Gleichheit).
2. Der Sync loeschte alles ausserhalb des Nutzerkommentars.
3. Meine Marker-Zaehlung hielt die eigene Notiz fuer doppelt erzeugt.
4. Die Fence-Zaehlung dagegen haengte an fremdem Nutzertext.
5. Die Entschaerfung lag nur um das Zitat, nicht um Auswirkung und Titel.
6. Der Titel war mehrzeilig -- die Notiz waere auch ohne Marker gewachsen.
7. Das Frontmatter blieb ganz aussen vor, und dort meldet die Erkennung
   nicht einmal einen Konflikt.
8. Und zuletzt: "hinter dem Ende ist Nutzerterritorium" hatte ich nur nach
   hinten umgesetzt, nicht nach vorn.

Muster: jede Korrektur, die eine Zeichenkette ZAEHLT statt sie an der Quelle
unmoeglich zu machen, hat eine neue Luecke aufgemacht. Erst die Regel "was
ausserhalb der Marker landet, wird einzeilig und markerfrei erzeugt" hat die
Klasse geschlossen.

Zweites Muster, das mich mehrfach erwischt hat: ein Skript, das mehrere
Stellen aendert, bricht an einer Assertion ab, BEVOR es schreibt -- und ich
habe der Rueckmeldung geglaubt statt dem Ergebnis. Einmal hat genau das einen
Fehler durchgelassen, den der Waechter dann fand.

## Offen, wartet auf Entscheidung oder Umsetzung

- **D9 (neu, 2026-09-04)** `config.py` behauptet im Kommentar zur
  Ladefenster-Begrenzung "Rekordbox Fast-Path: ... daher reichen 120s fuer
  Energy/Genre", waehrend `LIBROSA_FAST_PATH_DURATION` auf 360 steht.
  Gefunden beim Korrigieren einer Zeilenangabe. Gehoert zu D8, wird dort
  miterledigt -- nicht in den D2/D6-Commit gezogen.

- ~~**D2** Schalter `TRANSITION_FEATURES_ENABLED`~~ -- ERLEDIGT Runde 9.
- ~~**D5** Trunkierung ueberschreibt die gerundeten Mix-Takte~~ -- ERLEDIGT,
  commit 8ca0e21.
- ~~**D6** Zwei Begriffe von "Genre dieses Tracks"~~ -- ERLEDIGT Runde 9,
  entschieden: dokumentieren statt angleichen.
- ~~**D7** `_outro_overlap_limit` gibt `None` = "keine Grenze"~~ -- ERLEDIGT
  Runde 10: latente Divergenz, im App-Pfad unerreichbar. Entscheidung
  2026-09-04: Verhalten unveraendert, Docstring richtiggestellt, Test nagelt
  die Unerreichbarkeit fest.
- **D8** Beide Analysepfade messen die Merkmale ueber verschieden lange
  Fenster (360 s gegen 600 s).
- Half/Double: der Preview entsteht, die Taktlage ist ungemessen.
- Vor dem naechsten `--apply` gegen den echten Vault: Trockenlauf lesen. Der
  neue Sync fasst jede Bestandsnotiz an.

### Runde 7 — 2026-09-04 — D5 und D7 nachgemessen

**D5 praezisiert.** Die Neuberechnung der Mix-Takte nach
`_apply_manual_mixpoint_cues` ist RICHTIG und bleibt -- manuelle Cues koennen
die Punkte verschieben. Der Defekt ist allein die Rundungsart: `int()` gegen
`seconds_to_bars`. Bei `bpm=120`, `mix_out_point=99.0` stehen 49 im Cache und
50 in der Anzeige.

Beim Messen ein ZWEITER, latenter Fehler gefunden, der ohne Guard aus dem
Fix eine echte Regression gemacht haette: `MIX_POINT_UNSET = -1.0`. Ein
naiver Wechsel auf `seconds_to_bars` liefert

    bpm 120 -> int() 0, round()  0    gleich
    bpm 174 -> int() 0, round() -1    <-- Psytrance/DnB-Kerntempo
    bpm 240 -> beide -1

und `caching.py:688` verlangt nichtnegative Takte. Der Fix braucht deshalb
zwingend `if mix_point >= 0 else 0`. Der heutige `int()`-Pfad ist ab 240 BPM
ebenfalls betroffen, praktisch aber unerreichbar. Liegt an Tor 1, samt der
Frage nach einem CACHE_VERSION-Bump.

**D7 exakt nachgerechnet.** A: 140 BPM, Dauer 330 s, Outro ab 300 s, Mix-Out
290 s. Takt = 1,7143 s, Kopfraum = 10,05 s, Mindestblende
(`MIN_TRANSITION_BARS = 8`) = 13,71 s.

- `blend_bars_options`: `max_bars = 5 < 8` -> `[]`, also kein Kandidat.
- `_outro_overlap_limit`: Kopfraum unter der Mindestblende -> `None`, und
  `None` heisst dort "KEINE Grenze". Rechnerisch klemmte der Legacy-Pfad dann
  auf `min(64, 330-290) = 40 s`, davon 30 s im Outro.
  **WIDERRUFEN in Runde 10**: dieser Weg ist im App-Pfad unerreichbar, die
  Wirkung tritt nicht ein. Siehe dort.

Dieselbe Frage, zwei gegensaetzliche Antworten, und die groesszuegigere
gewinnt ausgerechnet dort, wo der andere Pfad "unmoeglich" sagt. Die Ursache
ist, dass `None` drei verschiedene Dinge bedeutet: "kein Outro vorhanden",
"nicht berechenbar" und "zu eng". Nur der dritte Fall ist falsch behandelt.

NICHT selbstaendig gebaut: die Korrektur aendert, was der Nutzer HOERT --
statt 40 s Blende ein harter Schnitt oder ein verworfener Uebergang. Das ist
eine Entscheidung wie bei V-004 und D6.

**D5 behoben.** `seconds_to_bars` statt `int()`, mit `if mix_point >= 0 else 0`.
Der Import fehlte (`NameError` beim ersten Track), die lokale
`seconds_per_bar` ist damit tot und mit entfernt.

ENTSCHEIDUNG CACHE_VERSION: **kein Bump.** Belegt: `mix_in_bars`/`mix_out_bars`
werden zwar persistiert (`caching.py:216`) und validiert (`:688`), aber
ausserhalb von `analysis.py` von KEINEM Konsumenten gelesen -- die Exporter
enthalten kein Vorkommen, Scoring und Kandidaten ebenso wenig. Einziger Leser
ist `main.py:317-320`, und der rechnet aus den Sekundenwerten neu; der
gespeicherte Wert greift nur bei `sek < 0` (dort vor wie nach der Aenderung
0) und bei `bpm <= 0` (dort existiert kein analysierter Mixpunkt). Ein Bump
zwaenge die gesamte Bibliothek zur Neuanalyse, ohne dass ein Wert sichtbar
falsch werden koennte. Die Projektregel "Analysewerte aendern sich -> Bump"
wird hier bewusst und begruendet nicht angewendet.

VERWORFEN: `docs/archive/ARBEITSPLAN_2026-07-26.md:44` (R8/B8) forderte
`seconds_to_bars(..., floor)` UEBERALL. Nie umgesetzt -- beide lebenden
Aufrufer nutzen `round`. Projektsemantik fuer Mix-Takte ist ab jetzt
ausdruecklich `round`: die Mixpunkte sind phrasenquantisiert, und ein
Rundungsrest von Millisekunden unter der Taktgrenze machte mit `floor` aus
Takt 50 eine 49 -- dieselbe Fehlerklasse wie der dokumentierte
3-ms-Phrasenfehler.

FOLGENLOS, aber genannt: `seconds_to_bars` faengt `bpm <= 0` selbst ab, wo
die alte Division `ZeroDivisionError` geworfen haette. Im Vollpfad ist das
unerreichbar -- `analysis.py:2384` faellt bei `bpm_value <= 0` auf
`DEFAULT_BPM` zurueck (`:2392` Verdopplung, `:2399` Halbierung halten den Wert
positiv).

Beide Tests laufen ueber BEIDE Analysepfade. Ein Test nur fuer den Fast-Path
ist die haeufigste Fehlerquelle dieses Projekts, und die beiden geaenderten
Stellen liegen 500 Zeilen auseinander -- der Vollpfad haette sich still
zurueckbauen lassen. Gegenprobe deshalb einzeln je Pfad: Fast-Path
zurueckgebaut -> ein Fall rot; Vollpfad zurueckgebaut -> ein Fall rot.

Der Rundungstest berechnet die Mixpunkte aus der im Pfad gueltigen BPM
(Bruchteil fest 0,6), weil er sonst vom erzeugten Audio abhinge -- mein
erster Entwurf blieb bei zurueckgebauter Trunkierung zufaellig gruen. Im
Vollpfad schaetzt librosa die BPM, ein fester Sekundenwert waere dort
wirkungslos gewesen.

Der Sentinel-Test faengt ausdruecklich NICHT den alten `int()`-Pfad -- der
lieferte hier 0 --, sondern die Regression, die der Wechsel auf `round` ohne
Guard erzeugt haette. Das steht so im Docstring, damit niemand daraus einen
Altfehler liest.

### Runde 8 — 2026-09-04 — D8 nachgemessen

Beide Analysepfade rechnen dieselben Merkmalsfunktionen ueber das komplette
geladene Signal -- nur ist das Fenster verschieden lang: Fast-Path
`duration=LIBROSA_FAST_PATH_DURATION` (360 s), Vollpfad
`duration=LIBROSA_MAX_DURATION` (600 s). Betroffen sind `calculate_energy`,
`calculate_brightness`, `analyze_frequency_bands` und `compute_groove_fields`.

Gemessen an einem konstruierten Signal von 480 s Dauer, dessen letztes Drittel
leiser ist (typischer Outro-Verlauf). Reproduktion: Sinus 110 Hz plus 3 kHz
bei 22050 Hz, `sig[int(360*sr):] *= 0.25`, dann `calculate_energy` und
`analyze_frequency_bands` je auf die ersten 360 s und auf die vollen 480 s:

    energy   Fast-Path (360 s) = 100.0   Vollpfad (480 s) = 90.0   Delta 10.0

Die Frequenzbaender blieben in dieser Probe gleich, weil sie normierte
Verhaeltnisse sind; bei anderem Material koennen auch sie auseinanderlaufen.

TRAGWEITE groesser als zunaechst notiert: 360 s sind SECHS MINUTEN. Ein
Grossteil der Psytrance- und DnB-Tracks dieser Bibliothek ist laenger. Ein
einzelner Track laeuft immer nur durch EINEN Pfad -- die Inkonsistenz
entsteht also nicht am selben Track, sondern ZWISCHEN Tracks: ob ein Track
ueber 360 oder ueber 600 Sekunden gemessen wird, haengt allein daran, ob
Rekordbox-Metadaten vorliegen. Genau diese Werte vergleicht das Scoring
anschliessend miteinander.

Der RAM-Grund der beiden Fensterlaengen ist in `config.py:162-167`
dokumentiert. Dass die Trackmerkmale dadurch pfadabhaengig werden, steht
nirgends. Fuer Struktur und Outro gibt es mit `LIBROSA_TAIL_DURATION` eine
Kompensation, fuer die Merkmale nicht.

NICHT gebaut: jede Angleichung aendert Analysewerte, verschiebt damit das
Scoring und verlangt einen CACHE_VERSION-Bump. Entscheidung des Nutzers.

### Runde 9 — 2026-09-04 — D2 und D6 erledigt

Der Nutzer hat am 2026-09-04 entschieden: D2 "Schalter loeschen und Doku
richtigstellen", D6 "nur dokumentieren", D7 "angleichen, harter Schnitt",
D8 "Cache-Matrizen beschneiden". D2 und D6 sind damit ERLEDIGT und stehen
nicht mehr unter den offenen Posten.

**D2 behoben.** `TRANSITION_FEATURES_ENABLED` ist entfernt. Kein Verhalten
aendert sich -- die Konstante hatte nachweislich keinen Leser.

Zwei Dinge, die der Waechter an Tor 1 gefunden hat und ohne die der Fix
Schaden angerichtet haette:

1. Der zu loeschende Kommentarblock enthielt die EINZIGE zutreffende
   Beschreibung von `GENRE_WEIGHT_WITH_DJ_BRAIN` und
   `GENRE_WEIGHT_WITHOUT_DJ_BRAIN` -- dass sie im Acht-Faktoren-Pfad nur noch
   als VERHAELTNIS wirken (`playlist.py`: `weights["genre"] *=
   GENRE_WEIGHT_WITHOUT_DJ_BRAIN / GENRE_WEIGHT_WITH_DJ_BRAIN`). Die
   Kommentare an den Definitionen selbst behaupteten dagegen Absolutwerte und
   waren falsch. Ein blosses Loeschen haette richtige Doku entfernt und
   falsche stehen lassen. Der Text ist jetzt an die Definitionen verschoben.
2. `docs/agent-memory/` ist laut `docs/AGENT_HANDOFF.md` nur eine KOPIE. Das
   Gedaechtnis, das ein Agent tatsaechlich laedt, liegt ausserhalb des
   Repositorys und trug dieselben drei falschen Aussagen. Beide Orte sind
   nachgezogen; ein Abgleichskript existiert nicht.

Ausdruecklich NICHT erledigt: der A/B-Vergleich fuer den Hoertest fehlt
weiterhin. Er war nie moeglich -- der Schalter hat nie etwas geschaltet.
Machbar waere er ueber das Groove-Gewicht 0. Das ist kein Teil dieser
Aenderung.

**D6 dokumentiert, nicht geaendert.** Der Kommentar an `has_dj_data` nennt
jetzt den GRUND, nicht nur den Unterschied: `generate_dj_recommendation`
loest das Genre intern ebenfalls nur aus `detected_genre` auf. Das Gate
spiegelt also seinen Aufgerufenen und ist nicht willkuerlich. Ohne diesen
Hinweis haette ein spaeterer Agent es allein hier auf `_resolve_track_genre`
umgestellt -- dann liefe DJ-Brain mit dem `DEFAULT_MIX_PROFILE`, und das
Ergebnis waere schlechter als heute. Die ausfuehrliche Fassung steht in
`hpg-genres` (beide Spiegel), nicht in `hpg-playlist-scoring`: dort steht
bereits die verwandte Truthy-"Unknown"-Regel.

Der Kommentarverweis in `tests/test_scoring_contract.py` nennt jetzt die
Gewichtsumstellung statt der geloeschten Konstante. Die Assertion darunter
ist unveraendert.

### Runde 10 — 2026-09-04 — D7 WIDERRUFEN und richtiggestellt

Der Waechter hat an Tor 1 zwei Dinge gefunden, die meine D7-Darstellung
kippen. Beide selbst nachgeprueft, beide treffen zu.

**1. Die 40-Sekunden-Blende ins Outro ist im App-Pfad NICHT erreichbar.**
Meine Behauptung in Runde 7 ("der Legacy-Pfad klemmt auf 40 s, davon 30 s im
Outro") ist unbelegt. Der Code verwirft ein Paar schon vorher:
`compute_transition_recommendations` (`playlist.py:2421-2426`) bricht bei
`not kandidaten` ab -- genau der Zustand, den `blend_bars_options -> []`
erzeugt. Und wenn Kandidaten da sind, kommt `current_mix_out` aus dem
Kandidaten (`playlist.py:2525`), dessen Kopfraum per Konstruktion mindestens
`MIN_TRANSITION_BARS` betraegt: `blend_bars_options` nimmt nur Laengen
`b >= MIN_TRANSITION_BARS` und `b <= max_bars`, und `max_bars` folgt
demselben `_outro_deckel` wie `_outro_overlap_limit`. Der abweichende Zweig
ist damit im einzigen Produktivaufruf tot.

Die Divergenz ist real, aber LATENT: sie beisst erst, wenn jemand den
Kandidatenpfad aendert. Genau die Fehlerklasse, die ich anderen Berichten
vorwerfe -- Wirkung behauptet, wo nur eine Moeglichkeit besteht.

**2. `0.0` ergibt keinen harten Schnitt.** Ein Overlap von 0 faellt in
`playlist.py:2576-2583` durch `not 0.0 < overlap` und der Uebergang wird per
`continue` KOMPLETT VERWORFEN, mit `logger.error("ungueltiger Overlap")`. Es
entstuende also keine Blende der Laenge Null, sondern gar keine Empfehlung,
kein Plan, kein Preview fuer dieses Paar. Der Nutzer hat am 2026-09-04
"Angleichen: harter Schnitt" gewaehlt -- auf Grundlage meiner Beschreibung
"Du hoerst an diesen Stellen einen harten Schnitt". Diese Beschreibung war
falsch. Die Entscheidung wird deshalb neu vorgelegt.

**3. Ein bestehender Test haelt die heutige Entscheidung fest.**
`tests/test_transition_recommendations.py` `test_kurzer_kopfraum_wird_nicht_gekuerzt`
mit dem Docstring "Unter 8 Takten lieber ins Outro laufen als harter Schnitt".
Und `git show 1ebaa96` (2026-08-21) nennt die Entscheidung woertlich -- aber
OHNE eigene Messung fuer diesen Fall. Die dort zitierten Zahlen (109 von 160
Blenden liefen ins Outro) betreffen den anderen Fall. Fuer die Haeufigkeit
des D7-Falls gibt es nur eine indirekte Obergrenze: "Outro-Verletzungen
109 -> 18", und diese 18 verteilen sich auf ALLE VIER `None`-Zweige.

Nichts gebaut. Wartet auf die neue Entscheidung.

**D7 erledigt (Entscheidung 2026-09-04: Verhalten lassen, absichern).**
Kein Verhalten geaendert. Die Docstring von `_outro_overlap_limit` nennt jetzt
die Divergenz, ihren Grund und warum sie heute folgenlos ist -- samt der
Feststellung, dass `0.0` KEIN harter Schnitt waere, sondern den Uebergang
verwirft.

Neu `test_divergenz_zum_kandidatenpfad_bleibt_unerreichbar`: er prueft ueber
fuenf Mix-Out-Werte, dass es zu JEDEM Kandidaten auch eine Outro-Grenze gibt.
Gegenprobe gefahren -- die Mindestblende im Kandidatenpfad auf 1 Takt
gelockert, und der Test faellt mit "Kandidat bei mix_out=290.0 vorhanden,
aber keine Outro-Grenze -- die Divergenz ist erreichbar geworden". Damit wird
aus einem stillen Widerspruch ein lauter, sobald jemand den Kandidatenpfad
anfasst.

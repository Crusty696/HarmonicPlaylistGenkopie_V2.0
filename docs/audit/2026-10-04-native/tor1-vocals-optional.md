## Pruefvertrag

- tor: TOR 1
- auftrag: Vocals als optionale Information behandeln; ausschließlich ihre Pflichtprüfung aus raw_ok entfernen. Gemeinsamen Ranking-Vertrag für App, CLI und Audit erhalten.
- akzeptanzkriterien: Unbekannte Vocals auf einer oder beiden Seiten erzeugen kein quellmessung_fehlt:vocals und verhindern allein keine Rangfähigkeit; None bleibt None; bestehender beidseitiger Vocal-Clash-Abzug von 0,06 bleibt unverändert; alle zehn Faktoren und sämtliche übrigen Mess-, BPM-, Grid-, Kick-, Coverage- und Score-Gates bleiben unverändert.
- erlaubte_dateien: hpg_core/pair_candidates.py, tests/test_pair_candidates.py; zusätzliche Manifestpolicy-Dateien ausschließlich bei belegter Notwendigkeit. Die Prüfung ergibt hierfür keine notwendige Änderung.
- verbotene_dateien: Analyse, Cache-Persistenz, GUI, Renderer, Fit-Algorithmik und andere Scoring-Bereiche; Originalaudio, Datenbanken, Coverage, private und Claude-Artefakte sowie bestehender E-Worktree. Keine Änderungen durch diesen Prüfer.
- referenzen: hpg_core/pair_candidates.py:378, hpg_core/pair_candidates.py:326, hpg_core/pair_candidates.py:857, hpg_core/pair_candidates.py:1133, tests/test_pair_candidates.py:420, tools/rate_transitions.py:775, tools/audit_candidate_set.py:274
- invarianten: Keine Umdeutung unbekannter Messungen zu False; keine duplizierte Ranking-Algorithmik; keine Abschwächung anderer Gates; kein Analyse-Output- oder Cache-Schemawechsel; alte Manifest-/Audit-Bindungen niemals auf einen neuen Build umetikettieren.
- testbelege: Geplant: unbekannte Vocals links, rechts und beidseitig; None-Erhaltung und tatsächliche Rangfähigkeit bei sonst vollständig gültigen Messungen; unveränderter Vocal-Clash-Abzug; Ablehnung fehlender anderer Pflichtmessungen. Laufender Parent-Volltest prüft die bisherige Policy; nach Umsetzung ist ein neuer Abschlusslauf erforderlich. Keine Tests durch diesen Prüfer.

## Urteil

DURCHGEWUNKEN

## Vertragspruefung

- [OBSERVATION] Die Pflichtprüfung existiert tatsächlich. Git-Blame ordnet die beiden Vocals-Zeilen Commit b2f574dd vom 27.08.2026 zu.
- [INTENTION] Nur diesen Eintrag entfernen. Vocals sind kein elfter Pflichtfaktor: Die zehn Faktoren werden unabhängig davon weiterhin geprüft.
- [OBSERVATION] Der bestehende Score-Abzug bleibt bei beidseitig aktiven Vocals erhalten. None löst diesen Abzug nicht aus und muss nicht ersetzt werden.
- [OBSERVATION] App, CLI und Replay-Audit verwenden dieselbe rank_pair_candidates-Funktion. Keine Adapterkopie notwendig.
- Kein Manifestformat-Bump oder zusätzliches Gate-Versionsfeld erforderlich: Der vorhandene Build-Digest umfasst pair_candidates.py automatisch. Die Änderung erzeugt somit eine andere Build-Identität; bestehende Kandidatenmanifeste werden vom Audit und von der Fit-Bindungsprüfung zurückgewiesen. Neu vorbereiten, nicht alte Reports oder Manifeste umschreiben.
- Kein CACHE_VERSION-Bump erforderlich: Das Vorhaben verändert ausschließlich die Zulassung bereits gemessener Kandidaten, nicht Analysewerte, Messsemantik oder Persistenzschema.
- Meldepflichtige Teständerung: Der bisherige gemeinsame Test für unbekannte Kick- und Vocal-Messung muss aufgeteilt werden. Kick bleibt sperrend; die Vocal-Erwartung wird aufgrund der ausdrücklichen Nutzerentscheidung geändert und entsprechend im Test begründet.
- Umsetzung erst nach Ende des laufenden Parent-Volltests. Dieses Urteil ist eine Vorhabenfreigabe, keine TOR2-, Test-, Build- oder Release-Abnahme. Die spätere Commit-Whitelist muss die beiden zusätzlichen Pfade ausdrücklich aufnehmen.

## Belegmatrix

- Pruefpunkt: Entfernbare Vocals-Pflichtprüfung ist vorhanden | Beleg: hpg_core/pair_candidates.py:378 | Ergebnis: erfuellt
- Pruefpunkt: Zehn Pflichtfaktoren bleiben unabhängig geprüft | Beleg: hpg_core/pair_candidates.py:326 | Ergebnis: erfuellt
- Pruefpunkt: Kick-Pflichtmessung bleibt separat erhalten | Beleg: hpg_core/pair_candidates.py:360 | Ergebnis: erfuellt
- Pruefpunkt: Bestehender Vocal-Clash-Abzug bleibt unangetastet | Beleg: hpg_core/pair_candidates.py:857 | Ergebnis: erfuellt
- Pruefpunkt: Unbekannte Vocal-Messung besitzt bereits None-Semantik | Beleg: hpg_core/mix_candidates.py:85 | Ergebnis: erfuellt
- Pruefpunkt: Ranking verwendet den gemeinsamen Qualitätsvertrag | Beleg: hpg_core/pair_candidates.py:1133 | Ergebnis: erfuellt
- Pruefpunkt: App verwendet dieselbe Ranking-Funktion | Beleg: hpg_core/playlist.py:706 | Ergebnis: erfuellt
- Pruefpunkt: CLI verwendet dieselbe Ranking-Funktion | Beleg: tools/rate_transitions.py:886 | Ergebnis: erfuellt
- Pruefpunkt: Replay-Audit verwendet dieselbe Ranking-Funktion | Beleg: tools/audit_candidate_set.py:561 | Ergebnis: erfuellt
- Pruefpunkt: Build-Fingerprint umfasst Core-Pythonquellen automatisch | Beleg: tools/rate_transitions.py:779 | Ergebnis: erfuellt
- Pruefpunkt: Audit lehnt abweichende Build-Identität ab | Beleg: tools/audit_candidate_set.py:274 | Ergebnis: erfuellt
- Pruefpunkt: Fit-Bindung lehnt abweichende Build-Identität ab | Beleg: tools/rate_transitions.py:3473 | Ergebnis: erfuellt
- Pruefpunkt: Bisherige Vocal-Sperrerwartung ist gezielt anzupassen | Beleg: tests/test_pair_candidates.py:420 | Ergebnis: erfuellt
- Pruefpunkt: Bestehende Regression sichert den Abzug von 0,06 | Beleg: tests/test_pair_candidates.py:497 | Ergebnis: erfuellt

## Befunde

- keine

## Nicht geprueft

- keine

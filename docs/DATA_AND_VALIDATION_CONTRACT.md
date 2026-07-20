# Daten- und Validierungsvertrag

Stand: 2026-07-20 · Produktversion 3.7.0

Die Audioanalyse ist der deterministische Kern. Das lokale LLM ist standardmäßig deaktiviert und ergänzt nach ausdrücklichem Opt-in ausschließlich Mood-, Subgenre-, Beschreibung- und advisory Mixpoint-Daten. Es hört kein Audio. KI-Daten werden nur mit passender Provider-, Modell-, Prompt- und Schema-Provenienz wiederverwendet.

Strukturwerte tragen eine explizite Analyse-Coverage. Mix-out-Cues dürfen nur exportiert werden, wenn das Trackende tatsächlich analysiert wurde. LUFS wird separat über das vollständige native Mehrkanalsignal berechnet oder mit einem expliziten Skip-Status versehen.

`bass_intensity`, `avg_mids`, `avg_highs`, `brightness`, `vocal_instrumental`, `danceability` und `mfcc_fingerprint` sind derzeit Diagnose- bzw. Klassifikationsfeatures, nicht eigenständige Transition-Objectives. `genre_source` ist Provenienz. `timbre_fingerprint` ist der aktive Texture-Similarity-Input. Der beobachtete Wert `bass_intensity=100` ist ohne unabhängig gelabeltes Korpus kein Beweis für korrekte Kalibrierung.

Interne Playlist-Scores sind keine musikalische Ground Truth. Der Validator kann BPM, Key und Dateinamen-Genre gegen vorhandene Labels prüfen. Für Sections und Mixpoints sind kuratierte Zeitlabels nötig; für Übergänge zusätzlich ein verblindetes A/B-Hörprotokoll. Aussagen wie „sample-genau“ gelten nur für die technische Übereinstimmung eines erzeugten `TransitionPlan` mit Renderer-Samplegrenzen, nicht für musikalische Optimalität.

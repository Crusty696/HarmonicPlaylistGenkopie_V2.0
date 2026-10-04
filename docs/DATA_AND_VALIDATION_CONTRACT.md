# Daten- und Validierungsvertrag

Vertragsgrundlage vom 20.07.2026; Merkmalsbeschreibung am 04.10.2026 korrigiert.
Die Aussagen sind Anforderungen; aktuelle Laufzeitnachweise separat pruefen.

Die Audioanalyse ist der deterministische Kern. Das lokale LLM ist standardmäßig deaktiviert und ergänzt nach ausdrücklichem Opt-in ausschließlich Mood-, Subgenre-, Beschreibung- und advisory Mixpoint-Daten. Es hört kein Audio. KI-Daten werden nur mit passender Provider-, Modell-, Prompt- und Schema-Provenienz wiederverwendet.

Strukturwerte tragen eine explizite Analyse-Coverage. Mix-out-Cues dürfen nur exportiert werden, wenn das Trackende tatsächlich analysiert wurde. LUFS wird separat über das vollständige native Mehrkanalsignal berechnet oder mit einem expliziten Skip-Status versehen.

Die Rolle eines Merkmals muss am jeweiligen Verbraucher geprueft werden.
`transition_features.mood_match` verarbeitet `brightness`; lokale Kandidaten
nutzen in `pair_candidates._teil_timbre` auch `avg_mids_lokal` und
`avg_highs_lokal`, in `_teil_mood` lokale Helligkeit. Die fruehere pauschale
Einordnung als reine Diagnosewerte ist deshalb entfernt. Ein beobachteter
Maximalwert ohne unabhaengig gelabeltes Korpus beweist keine Kalibrierung.

Interne Playlist-Scores sind keine musikalische Ground Truth. Der Validator kann BPM, Key und Dateinamen-Genre gegen vorhandene Labels prüfen. Für Sections und Mixpoints sind kuratierte Zeitlabels nötig; für Übergänge zusätzlich ein verblindetes A/B-Hörprotokoll. Aussagen wie „sample-genau“ gelten nur für die technische Übereinstimmung eines erzeugten `TransitionPlan` mit Renderer-Samplegrenzen, nicht für musikalische Optimalität.

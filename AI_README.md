# Optionale lokale KI-Metadaten

Die GUI initialisiert die optionale KI mit ausgeschaltetem Kontrollkaestchen
(main.py: ai_enabled_checkbox). Konfigurierte Vorauswahl in hpg_core/config.py:

```python
AI_PROVIDER = "LM Studio"
AI_MODEL = "granite-4.0-h-tiny"
AI_MAX_TOKENS = 400
AI_TIMEOUT = 120.0
```

Quellenabgleich am 04.10.2026; die Werte beweisen weder einen laufenden Server
noch lokale Modellverfuegbarkeit. Fuer konkrete Providerstarts und Antworten
hpg_core/ai_launcher.py und hpg_core/ai_engine.py sowie Laufzeitlogs pruefen.

Der [Datenvertrag](docs/DATA_AND_VALIDATION_CONTRACT.md) trennt optionale
Metadaten von Audioanalyse und musikalischen Qualitaetsnachweisen.
Historische Modellbenchmarks und Hardwareempfehlungen wurden aus dieser
Anleitung entfernt. Sie sind keine aktuellen Messungen oder Empfehlungen.
[Quellen und Beweisgrenzen](docs/PROJECT_KNOWLEDGE.md).

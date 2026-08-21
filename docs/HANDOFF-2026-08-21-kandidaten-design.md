# Handoff 2026-08-21 (Abend): Mixpunkt-Kandidaten — Design genehmigt

Vorheriger Stand: `docs/HANDOFF-2026-08-21-fixes-und-hoertest-mobil.md`.

## Was passiert ist

- Vier parallele Suchen (Code, Repo-Docs/Archive, Brain-Vault, Skills/Memory)
  haben alle je besprochenen Uebergangs-/Mixpunkt-Kriterien mit Quelle und
  Status gesammelt. 44 Punkte fehlten im ersten Design-Entwurf; der Katalog
  steht als Anhang A in der Spec.
- Der Nutzer hat die Spec
  `docs/superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md`
  abschnittsweise genehmigt (1 Datenmodell, 2 Paarung/Bewertung, 3 Hoertest,
  4 App) mit der Auflage: **genau so umsetzen, alles fertig bauen bis zum
  letzten Teil, keine Abweichung, 100 % ehrlich, keine Annahmen.**
- Skill `hpg-mixpoint-engineering` (beide Spiegel) verweist auf das Design.

## Naechster Schritt

Implementierungsplan nach `docs/superpowers/plans/` (writing-plans), dann
Umsetzung in dieser Reihenfolge: Abschnitt 1 (PSSI-Leser, `MixCandidate`,
lokale Messwerte, Cache 34) → 2 (Paar-Bewertung) → 3 (Hoertest-Modus
Kandidaten) → 4 (App). Waechter an beiden Toren je Schritt.

## Offen (unveraendert)

- App-BPM-Default 3.0 → 2.0 (Teil von Abschnitt 4)
- #4 Melodic Techno: wartet auf Noten
- `docs/PLAYLIST_ALGORITHMEN_ERKLAERUNG.md` ("10 Strategien") und
  `HANDOFF-2026-08-20-groove-scoring.md:189` veraltet
- Mobiler Hoertest-Ordner: Nutzer kopiert selbst auf USB

## Server

`tools/hoertest_server.py --dir Music\HPG-Psytrance --port 8766` und
`--dir Music\HPG-Hoertest --port 8765` laufen.

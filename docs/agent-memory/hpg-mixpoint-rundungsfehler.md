---
name: hpg-mixpoint-rundungsfehler
description: "Aus \"Mix-Out liegt vor dem Outro\" folgt NICHT, in welcher Sektion er sitzt — mit Messwerten aus 200 Tracks"
metadata: 
  node_type: memory
  type: project
  originSessionId: 602c084c-5127-4b2b-b848-63a0fe84aba7
  modified: 2026-08-20T01:13:54.719Z
---

Zwei Befunde zur Mixpunkt-Logik, beide an 200 analysierten Tracks gemessen und
beide gegen die Intuition:

**1. Rundungsrauschen verschob Mixpunkte um eine ganze Phrase.**
Sektionsgrenzen kommen gerundet aus der Analyse. Lag eine Grenze 3 ms hinter
einem Rasterpunkt, sprang `ceil` auf die naechste Phrase — 27 s bei 16-Bar-
Phrasen, vom Intro-Ende mitten in den Drop. Zwei volle Tracks liefen dann 32 s
uebereinander. Kein Test war rot; David hoerte es beim ersten Clip.
Behoben ueber `QUANTIZE_TOLERANCE_SEC = 0.05` in `models.py` (Commit
`839ba41`), CACHE_VERSION 30 -> 31.

**2. Aus Invariante 4 folgt nicht, wo der Mix-Out sitzt.**
`max_mix_out = min(outro_start, ...)` ist eine **Obergrenze**, keine
Gleichsetzung. Gemessen: der Mix-Out liegt im Median **76 s vor dem Outro**.
Die letzte Main/Drop-Sektion enthaelt ihn in nur **12 %** der Faelle; in 170
von 200 beginnt sie erst im Median 47 s **nach** dem Mix-Out. Die Abkuerzung
"letzte Nicht-Intro-Sektion" trifft in 169 von 200 das Outro.

Wer die Sektion an einem Mixpunkt braucht, nimmt `section_dict_at_time`
(`dj_brain.py`) und raet nicht ueber Labels.

**Geklaert 2026-08-23** (Messung `hpg_cache_v34.db`, 231 Tracks): kein
`mix_in_point` liegt vor `_get_intro_end_from_sections` (0 von 231, Toleranz
0.05 s); die frueher gezaehlten "Mix-In in einer Intro-Sektion" (jetzt 54)
sitzen alle hoechstens 0.005 s vor dem Intro-Ende — `section_dict_at_time` ordnet
`start <= t < end` zu, ein Rundungsrest unter dem Intro-Ende traegt das Label
"intro". Invariante 5 ist eingehalten; auch 0 von 1829 Mix-In-Kandidaten
liegen vor dem Intro-Ende. Der alte Befund "57 von 200" stammt aus einer anderen
Stichprobe/einem aelteren Cache und ist nicht reproduziert. Kein Codeaenderungsbedarf.

Siehe auch [[hpg-groove-scoring-2026-08-20]].

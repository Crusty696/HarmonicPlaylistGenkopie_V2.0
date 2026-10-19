"""
SQLite-based caching module for multi-process audio analysis

Provides cross-platform thread-safe and process-safe SQLite caching with WAL
(Write-Ahead Logging) mode enabled for optimal concurrent read/write operations.
"""

import sqlite3
import json
import os
import hashlib
import logging
import math
import shutil
import sys
import time
import numpy as np
from contextlib import contextmanager
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from .downbeat import (
    DOWNBEAT_RELIABLE_MIN, EXACT_BEAT_SYNC_TOLERANCE_SECONDS,
    REFERENCE_BEATGRID_CONFIDENCE,
)
from .mix_candidates import MixCandidate, SCHEMA_PRIORITAET
from .models import (
    BEATGRID_SOURCES, BEATGRID_STATUSES, Track, is_supported_phrase_unit,
)
from .config import MIX_POINT_UNSET

logger = logging.getLogger(__name__)

# v17: Key-Confidence (Essentia-Muster strength+margin) + LUFS-Loudness
# (EBU R128 via pyloudnorm/DeMan) 2026-07-17 — neue Track-Felder
# key_confidence und lufs werden bei der Analyse gefuellt
# AUDIT-FIX Welle 1 (2026-07-24): Version-Bump 18 -> 19 — die gecachten
# Mix-Punkte/Downbeats stammen aus der fehlerhaften Logik (N1/B7/B4/B5/B1/N10)
# und muessen neu berechnet werden.
# AUDIT-FEATURE A1 (2026-07-26): 19 -> 20 — neue Felder first_phrase/
# phrase_confidence; Mix-Punkte sind jetzt phrasen-verankert und muessen
# fuer alle Tracks neu berechnet werden.
# Analyse-/Quantisierungsvertrag geaendert: ungerundete Mixpunkte und
# gemessene Phrase-Units/erweiterte Novelty.
# AUDIT-FIX 2026-07-26: Mixpoints verwenden -1.0 als "nicht gesetzt";
# 0.0 bleibt ein gueltiger Zeitpunkt.
# AUDIT-FIX 2026-08-14: 24 -> 25. Drei Analysewerte aendern sich messbar und
# muessen neu berechnet werden:
#   - LUFS: die blockweise Messung lieferte fuer 24 von 52 Tracks NaN
#     ("lufs_status": "invalid", lufs 0.0), weil die Blockzahl aufgerundet
#     wurde und der letzte 400-ms-Block nicht mehr ins Signal passte.
#   - bass_intensity: die Skala endete bei einem Bass-Anteil von 0.5 und
#     klemmte real gemessene 0.78-0.89 auf konstant 100 (ein einziger
#     distinkter Wert ueber die ganze Bibliothek).
#   - bpm: ID3-Tags werden jetzt gegen das Audio auf Halftime/Doubletime und
#     2/3-Fehltagging geprueft; betroffene Tracks aendern BPM, Genre und
#     phrase_unit.
# AUDIT-FIX 2026-08-14 (Runde 2): 25 -> 26. Die Downbeat-Schaetzung wurde an
# zwei Stellen korrigiert: die Taktlaenge kam aus einem hop-gerasterten
# Median (-2,5 % Bias, der linear mit der Tracklaenge wuchs — bis 4,2 s
# Ankerfehler bei 330 s), und ein inkommensurables librosa-Beatraster
# (11 von 34 Tracks) lieferte Takte einer fremden Metrik. Folge:
# first_downbeat aendert sich auf 34/34 gemessenen Tracks,
# downbeat_confidence faellt bei 11/34 auf 0.0, phrase_anchor und die
# Sektions-Startzeiten verschieben sich — und damit die Mixpunkte.
# AUDIT-FIX 2026-08-14 (Runde 3): 26 -> 27. Die Downbeat-Feinausrichtung
# rastete auf den staerksten Bass-Onset-FRAME (46-ms-Hopraster) und lag
# dadurch ueber 35 Referenztracks konsistent +116 ms zu spaet (Gruppen-
# laufzeit des Onset-Detektors). Ersetzt durch nullphasigen Tiefpass +
# beat-synchrone Faltung: Sub-Beat-Fehler 117 ms -> 16 ms Median.
# Zusaetzlich ist die Konfidenz-Skala neu normiert (der alte 2/3-Deckel
# war ein Artefakt der Vote-Normierung, 1.0 bleibt Rekordbox vorbehalten).
# first_downbeat UND downbeat_confidence aendern sich auf jedem selbst
# geschaetzten Track; phrase_anchor, Sektionsgrenzen und Mixpunkte folgen.
# AUDIT-FIX 2026-08-14 (Runde 4): 27 -> 28. Das Phrasen-Voting faltet jetzt
# auf die GEMESSENE Periode, bevor es bewertet. Grund: Psytrance/Trance
# sind die einzigen Genres mit phrase_unit=16, viele Tracks haben real
# aber eine 8-Bar-Periode. Dann sammeln zwei Bins (p und p+8) dieselbe
# echte Phrasengrenze, die Margin bricht zusammen — und zwar umso mehr,
# je klarer die Struktur ist. Gefaltet wird nur bei zirkularer
# Selbstkorrelation >= 0.70 (kalibriert: echte 16-Bar-Tracks max 0.60,
# erkannte 8-Bar-Tracks min 0.78).
# Geaendert: first_phrase, phrase_confidence und darueber phrase_anchor,
# sections sowie alle Mixpunkte.
# AUDIT-FIX 2026-08-15: 28 -> 29. Context-/Genre-Flow, Transition-Typ und
# abgeleitete Camelot-Werte wurden korrigiert. Damit alte Genre-/Mixpoint-
# Ausgaben die neuen Verträge nicht maskieren, wird ein neuer Cache genutzt.
# FEATURE 2026-08-19: 29 -> 30. Neue Groove-Features (groove_pattern,
# bass_pattern, syncopation, sub_energy, bass_punch) auf Track. Alte Rows
# kennen diese Felder nicht, ein neuer Cache erzwingt Neuanalyse statt
# stiller Default-Werte.
# FIX 2026-08-20: 30 -> 31. quantize_to_grid arbeitet in "ceil"/"floor" jetzt
# mit QUANTIZE_TOLERANCE_SEC Spielraum. Sektionsgrenzen kommen gerundet aus
# der Analyse; lag eine Grenze 3 ms hinter einem Rasterpunkt, schob `ceil`
# den Mix-In eine GANZE Phrase weiter (gemessen: 82,29 s -> 109,72 s, also
# vom Intro-Ende mitten in den Drop). Alle gecachten Mixpunkte sind damit
# neu zu berechnen.
# FEATURE 2026-08-20: 31 -> 32. Zwei Aenderungen an gecachten Inhalten:
# Das Groove-Muster wird jetzt nur noch ueber Sektionen mit Beat (main,
# drop) gefaltet, und die Sektionen tragen zusaetzlich sub_energy und
# bass_punch fuer den Nahtstellen-Vergleich des Bassdrucks. Alte Zeilen
# kennen die Sektions-Schluessel nicht und halten Muster aus dem gesamten
# Fenster — sie wuerden stille Altwerte liefern, die neu berechnete Tracks
# still anders bewerten als gecachte.
# FIX 2026-08-20: 32 -> 33. Der Intro-Guard greift jetzt auch in der
# Rekordbox-Cue-Uebernahme (analysis.py, `cue_in_verwerfen`). Gecachte
# mix_in_point-Werte aus dem Heuristik-Zweig koennen im Intro liegen —
# gemessen 24 von 231 Tracks, bis 56,5 s tief. Ohne Bump behalten sie ihren
# falschen Wert, weil der Cache-Key nur an Pfad und Rekordbox-Signatur haengt
# und es keine selektive Invalidierung gibt.
# FEATURE 2026-08-21: 33 -> 34. Kandidatenfelder phrases/cue_points/
# phrase_grid/mix_in_candidates/mix_out_candidates auf Track, Cue-Heuristik
# entfernt. Alte Zeilen kennen die Felder nicht und lieferten leere Listen,
# obwohl eine Neuanalyse Kandidaten haette; ein neuer Cache erzwingt sie.
# FEATURE 2026-08-25: persistierter Beatgrid-Pruefstatus und vollstaendige
# Rekordbox-PQTZ-Signatur. Alte Rows kennen die Messwerte nicht; zudem muss die
# korrigierte Sekundenbehandlung der flachen pyrekordbox-Tagform neu einlesen.
# Der Status ist Diagnose, kein Track-Ausschluss: die reale Kick-Synchronitaet
# wird beim Rendern direkt am Audio korrigiert und geprueft.
# FEATURE 2026-08-25: 36 -> 37. Unbekannte lokale Kick-, Vocal- und
# Strukturmessungen bleiben None statt als False zu gelten; alte Kandidaten
# duerfen den strengeren lokalen Paarvertrag deshalb nicht wiederverwenden.
# FIX 2026-08-26: 37 -> 38. BPM-lose Rekordbox-Eintraege behalten nach der
# Librosa-Tempoermittlung validierte RB-Keys, Cues und PSSI-Phrasen. Die
# Rekordbox-Signatur umfasst jetzt ebenfalls die abgeleiteten PSSI-Phrasen;
# alte Analysezeilen duerfen diese neuen Metadaten nicht maskieren.
# FIX 2026-08-26: 38 -> 39. Cache-Schreibvorgaenge erstellen jetzt einen tief
# losgeloesten Snapshot und normalisieren nicht-endliche Kandidatenmesswerte
# feldabhaengig. Fast-Path und BPM-loser Vollpfad bestimmen PSSI-Phrasenenden
# jetzt mit der echten endlichen Dateidauer. Der parameterlose Signaturpfad
# verwendet weiterhin die positive Rekordbox-Dauer oder 0.0; getrennte
# dauerabhaengige Memo-Keys verhindern gegenseitige Vergiftung. Nicht-endliche
# Dauerwerte werden nie selbst Teil eines Memo-Keys. Alte v38-Zeilen koennen
# die strengere Kandidatenvalidierung, None-/Vektor-Semantik und den
# PSSI-Vertrag nicht verlaesslich erfuellen.
# FIX 2026-08-26: 39 -> 40. Die framegenaue Audiodauer ist im Rekordbox-
# Fast-Path jetzt autoritativ; ganzzahlig gekuerzte Rekordbox-Dauern duerfen
# gueltige Cues nicht mehr hinter das Trackende verschieben. Cues werden vor
# Kandidatenbildung und Persistenz strikt gegen die echte Dateidauer geprueft.
# Alte v39-Zeilen enthalten sonst abweichende Dauern und Cue-/Kandidatenwerte.
# FIX 2026-08-26: 40 -> 41. Die ID3-BPM-Faktorpruefung erkennt jetzt auch
# 3/4- und 4/3-Fehltaggings. Korrekturen sind strikt an ein bekanntes
# kanonisches ID3-Genre gebunden; der widerspruechliche genreuebergreifende
# Union-Fallback ist entfernt. Alte v40-Zeilen koennen dadurch falsche BPM,
# Phrasenraster, Mixpunkte und Kandidaten enthalten. Derselbe v41-Vertrag liest
# AIFF-Metadaten feldweise aus Easy-Tags und rohen TPE1/TIT2/TCON-Frames;
# dadurch bleiben Artist, Titel und kanonisches ID3-Genre erhalten.
# FIX 2026-08-26: 41 -> 42. Manuelle Rekordbox-Cues duerfen die harten
# Strukturgrenzen weder bei Track-Mixpunkten noch bei persistierten Kandidaten
# und Paaren uebersteuern. Alte v41-Zeilen koennen Mix-In im Intro, Mix-Out im
# Outro oder Blenden hinter dem Outro-Start enthalten.
# FIX 2026-08-27: 42 -> 43. Mehrdeutige Audio-Keys werden vollstaendig
# geleert; Rekordbox-Beatgrids brauchen fuer Persistenz/Export wieder den
# verifizierten Referenzvertrag. PSSI-Grenzen und KI-Metadaten werden strikt
# validiert, damit keine falschen Erfolgsdaten wiederverwendet werden.
# FIX 2026-08-27: 43 -> 44. Mixpunkte ohne erfuellbares Phrasenraster bleiben
# jetzt explizit ungesetzt statt auf einen Bar-Anker auszuweichen. Alte
# v43-Zeilen koennen weiterhin solche semantisch ungueltigen Fallback-Werte
# enthalten und duerfen den strengeren Mixpoint-Vertrag nicht maskieren.
# FIX 2026-09-04: 44 -> 45. Acht Track-Merkmale werden jetzt in BEIDEN
# Analysepfaden ueber ein gemeinsames 360-s-Fenster gemessen (D8); alte
# v44-Zeilen enthalten Werte, die davon abhaengen, ob Rekordbox-Metadaten
# vorlagen.
# FIX 2026-10-04: 45 -> 46. Diagnosezweige und lokale Gridfenster werden
# explizit gespeichert. Alte Records enthalten keine belegten Fehlerursachen.
# FIX 2026-10-13: 46 -> 47. Begrenzter Downbeat-Retry mit unabhaengiger
# Drei-Fenster-Pruefung; alte Analyseergebnisse enthalten diesen Versuch nicht.
# FIX 2026-10-13: 47 -> 48. Physische Beatnummern statt Tracker-Arraypositionen
# bewahren die Taktphase bei fehlenden oder doppelten Beat-Zuordnungen.
# FIX 2026-10-13: 48 -> 49. Die Vollpfad-Struktur verwendet wie alle
# Rasterkonsumenten die BPM-Taktlaenge statt eines hopgerasterten Medians.
# FIX 2026-10-13: 49 -> 50. Downbeat-Merkmale werden bei eindeutiger
# Beatzuordnung auf derselben Fold-Phase wie der abschliessende Anker gemessen.
# FIX 2026-10-13: 50 -> 51. Vollstaendige Beat-Energiefenster mit anteiligen
# Rand-Samples vermeiden kuenstliche Downbeat-Akzente aus Teilfenstern.
# FIX 2026-10-13: 51 -> 52. Audio-Feintempo im Vollpfad nach separater
# Drei-Fenster-Pruefung; alte Analysen enthalten diese Korrektur nicht.
# Version 53: versionierte Cue-Rohdiagnostik und Modell-/Preprocess-Cacheidentität.
# Version 54: Beat-Modellkandidaten, Schema 2 und gemeinsame neuronale Quellidentität.
# Version 55: audio-bestätigte neuronale Taktanker und getrennte Referenzdiagnosen.
# Version 56: audio-bestätigte neuronale Tempoentscheidung in beiden Analysepfaden.
# Version 57: identitätsgebundene Cue-Rohscores beeinflussen die PSSI-Kandidatenkappung.
# Version 58: nur exakt zugeordnete Rekordbox-Pfade liefern Metadaten;
# fruehere Basename-Treffer muessen ohne fremde BPM/Keys/Cues neu analysiert werden.
# Version 59: widerspruechliche Fold-/Trackerzuordnungen liefern keinen Downbeat.
# Version 60: Mixpunkte und Kandidaten ohne belastbare Taktphase werden nicht ausgegeben.
# Version 61: abgeleitete Rasterwerte verlangen bestaetigte Beatgridphase.
# Version 62: Track.phrase_anchor faellt bei unbestaetigtem Raster nicht mehr
# auf den rohen first_downbeat zurueck, damit Downstream kein Raster erfindet.
# Version 63: ANLZ-Beatticks validieren die lokale Phase je Audiofenster statt
# den ersten Rekordbox-Anker ueber den ganzen Track konstant fortzuschreiben.
# Version 64: Diagnose unterscheidet einen konsistenten Beatphasen-Offset von
# wechselnder Phase; Sync-Status und Freigabegates bleiben unveraendert.
# Version 65: eine verifizierte DSP-Baseline wird bei schwacher Phrase durch
# vorhandene Audio-Beatmodelle geprueft; der Phrasenwert folgt dem gewaehlten Anker.
# Version 66: der Fixed-BPM-Retrygrund bleibt neben dem primaeren Downbeatgrund sichtbar.
# Version 67: Diagnose-Schema v4 kennzeichnet exakten Rekordbox-Pfad vs. Laufwerks-Rebind.
# Version 68: Schema v5 speichert einen rein diagnostischen Modellkandidaten fuer
# die PQTZ-Taktpositionsrotation; aktive Rekordbox-Anker und Freigaben bleiben gleich.
# Version 69: Audio-Voting und Vollgridprüfung protokollieren den Kandidaten,
# ohne den aktiven Rekordbox-Anker oder bestehende Freigaben zu ersetzen.
# Version 70: eine gemessene Nichtnull-Taktrotation sperrt PSSI/Phrasenraster,
# Mixpunkte, Paar-Kandidaten, Takt-1-Rendererphase und Cue-/Beatgrid-Export.
# Version 71: PSSI/PQTZ-Phrasen werden nur aus eindeutig zugeordneten
# ANLZ-Dateigruppen gebildet; alte Phrase-/Mix-Ergebnisse duerfen nicht bleiben.
# Version 72: Bei schwacher Phrasenphase kann die Audio-Novelty-Messung im
# bestaetigten Beatgrid die Genre-Prior-Phrasenlaenge ersetzen.
# Version 73: Track speichert die Herkunft der effektiven Phrasenlaenge.
# Version 74: Track speichert den besten Novelty-Kandidaten, Rohscore und Margin.
# Version 77: neuronaler Taktanker benoetigt dieselben drei bestaetigten
# Version 78: Nur audio-bestaetigte Modell-Taktrotationen duerfen Rekordbox-
# Takt-1 ersetzen; sie bleiben Audioherkunft und erhalten keine RB-Sync-Freigabe.
# Version 79: Ein erkannter konstanter Rekordbox-Grid-Offset wird als
# reference_constant_offset in der persistierten Taktpositionsdiagnose abgelegt;
# der Befund korrigiert weder Grid noch Anker und gibt keine Sync-Freigabe.
# Version 80: Bei konstantem Grid-Offset vergleicht die Taktpositionsdiagnose
# Modellbeats gegen zeitlich phasenprojizierte PQTZ-Ticks. Ein Rotationstreffer
# bleibt Kandidat, sperrt vorsorglich PSSI/Mixausgaben und korrigiert nichts.
# Version 81: Ein versatzbereinigter Rotationstreffer darf nur mit drei
# disjunkten Zusatzfenstern je Modell, separater Audiophasenbestätigung und
# verifiziertem Grid als Audioanker übernommen werden.
# Quellfenster je Modell; gespeicherter Kandidat und Mindestkonfidenz muessen
# dem Resolver entsprechen. Phrase-Novelty braucht Grid/Downbeat; Schema v6
# behaelt die vorhandene Sperre fuer gemessene Taktrotationen.
# Cache 86: reine Offsetkorrektur ohne Rotation wird verworfen, wenn sie den
# Anker ueber eine Bar-Grenze wickeln und so Phrasenphase verschieben muesste.
# Cache 87: die wirksame Phrase-Unit steuert bereits die interne Mix-In/Out-
# Kandidatenquantisierung, nicht nur das abschliessende gemeinsame Phrasenraster.
# Cache 88: neuronales Tempo-Kandidatentempo ist der Median aller sechs
# konsistenten Modellfenster, nicht das erste Modell-/Fensterergebnis.
# Cache 89: persistierter Tempoentscheid mit Status, Grund und Modellwerten.
# Cache 90: die sechs einzelnen Tempo-Modellwerte bleiben mit Fensterherkunft erhalten.
# v92: Verifizierte PSSI-Intervalle bestimmen gedeckte Strukturgrenzen;
# lokale Sektionsenergie und davon abhängige Mixpunkte müssen neu entstehen.
# v93: nativer Phrasenvertrag mit eigener Provenienz und Strukturgrenzen.
# v94: bekannte Tonarten an nativen Generator binden; Schema-7-Taktsperre beachten.
# v95: native Schlussgrenze statt künstlicher Verlängerung bis Dateiende.
# v96: lokale Stemkurven und normalisierte Embeddings samt Herkunft/Coverage.
# v97: interner Tracker-Lag darf bei erhaltener Beatidentitaet schwanken.
# v98: lokaler Drei-Fenster-Retry nach langem Tracker-Drift, Gesamtgrid unveraendert.
# v99: interner Trackerdrift nutzt separat bestaetigtes Audio-Raster vor Takt-Voting.
# v115: MP3-Analyse-, LUFS-, Beat- und Tail-Fenster verwenden gemeinsame Reader-Herkunft.
# v116: MP3-Zusatzmerkmale duerfen die MP3-Dauertoleranz nutzen und brauchen Reader-Provenienz.
# v117: native Phrasengrenzen referenzieren das bestaetigte native Audio-Beatgrid.
# v118: Analysefenster fuer MP3/WAV/AIFF/FLAC verwenden den gemeinsamen Reader.
# v119: weitere Rekordbox-Container/Codec-Endungen nutzen den gemeinsamen Readerpfad.
# v120: Zusatzmerkmale und native Phrasen validieren die erweiterten Decoderquellen.
# v121: native Ankerpfade tolerieren Tracks ohne importiertes Referenzgrid.
# v122: Mixkandidaten, LUFS und native Phasenfenster teilen den Audioformatreader.
# v123: nicht erkannte Mehrkanalcontainer bleiben beim bisherigen HPG-Downmix.
# v124: Stem-/Embedding-Fingerprints und Payloads binden den Audio-Readervertrag.
# v125: Embedding-Payloads erfassen Provider nach möglichem Laufzeit-Fallback.
# v126: native Beatwrapper erhalten den float32-Fensterstart nach Windows-ABI.
# v129: Cache weist native Phrasensnapshots zurueck, deren gerundeter
# Millisekunden-Offset eine volle Beatperiode erreicht; das wuerde die
# gespeicherte Taktposition ohne Rotation auf den Folgebeat verschieben.
# v130: Native Beat-Snapshots enthalten bei langen Quellen segmentierte
# Modellabdeckung; alte Einfenster-Payloads erfuellen diesen Vertrag nicht.
# v131: native Beat-Snapshots enthalten die ctime-basierte Quellidentitaet.
# v132: unverglichene Rekordbox-Taktpositionen bleiben Kandidaten und dürfen
# nicht als verifizierter Bar-1-Anker für Rendering oder Mixausrichtung gelten.
# v133: native Reader-Payloads trennen Quell-/Ausgabekanäle; Mehrkanalquellen
# nutzen begrenzten Mono-Downmix für Beat-, Phrasen- und Zusatzmerkmale.
# v134: Messdiagnosen speichern den Status und Grund der nativen Rasterannahme.
# v135: Audio-bestaetigte Taktphasen duerfen einen widersprechenden externen
# Beatindex als Kandidat pruefen; nur disjunkte Fenster und Gesamtgrid uebernehmen.
# v136: Auch nach nativer Gridbestaetigung muss die Audio-Taktphase die
# Zuverlaessigkeitsschwelle bestehen, bevor Phrasen-/Mixanker freigegeben werden.
# v139: Alle unterstützten Analyseformate laufen im Hauptpfad durch denselben
# begrenzten Reader; Mehrkanalquellen nutzen dessen festgelegten Mono-Downmix.
# v140: Lokale Kandidatenfenster nutzen denselben Reader auch hinter 20 Minuten;
# ein fehlgeschlagener Reader wird nicht still durch einen zweiten Decoder ersetzt.
# v141: Lokale LUFS-Messungen nutzen den gemeinsamen Reader auch nach 20 Minuten.
# v145: Mixkandidaten und gepaarte Mixpunkte verlangen freigegebene Phrasenphase;
# native Kandidatenphrasen allein überschreiben keinen fehlenden Takt-1-Anker.
# v146: MP3-Dauer stammt aus demselben Reader wie Analyse und Preview;
# alte Track-Enden und davon abgeleitete Phrasen-/Mixwerte werden neu berechnet.
# v147: Analysepfade sperren Genre- und Cue-Mixpunkte bei nicht freigegebener
# Phrasenphase, nicht nur bei expliziter Modellrotationssperre.
# v148: PSSI-, Cue- und native Phrasegrenzen gelangen nur mit freigegebener
# Phrasephase in die Struktur; alte abgeleitete Sektionen werden neu berechnet.
# v149: Cache-Validierung verlangt für PSSI und native Phrasen dieselbe
# freigegebene Takt-/Phrasephase wie die Analysepfade.
# v150: Native FLAC/MP4/AAC-Readerausgabe und Reader-Provenienzvertrag.
# v151: AAC-Sperre, Metadaten-Kanalauflösung und Codec-Fallback ändern Reader-/Beat-Eingaben.
# v152: Nativer Grenzwrapper meldet die aktive Mono-/Stereo-Kanalzahl auch beim HPG-Readerfallback.
# v153: Readervertrag v22 aendert Analyse-Eingaenge; alte Cachezeilen muessen neu analysiert werden.
# v154: Der Anchor-Resolver verarbeitet bestaetigte konstante Rekordbox-Offsets
# auch ohne beat_windows im Audiozweig; betroffene Downbeat-/Phrasen-/Mixwerte
# werden neu berechnet statt aus dem alten Resolver-Cache weiterverwendet.
# v155: Reader v23 sperrt WAV/AIFF auf Mono/Stereo bei fehlendem nativem Reader;
# Mehrkanal bleibt kontrolliert beim HPG-Decoder.
# v156: Reader v24 erlaubt den HPG-Fallback fuer WAV/AIFF, wenn das native
# Abbild nicht geladen werden kann und noch kein nativer Decoder existiert.
# v157: Reader v25 nutzt fuer bekannte Mehrkanal-Optionalcodecs vor dem nativen
# Open den HPG-Mono-Downmix statt einen unfreigebbaren nativen Decoder zu oeffnen.
# v158: Boundary v4 validiert den vom nativen Wrapper weitergereichten FloatMatrix-Zeiger.
# v159: Optionaler nativer Codec-Fehler fällt im isolierten Worker auf HPG-Reader zurück.
# v160: Audioembedding wird nur noch einmal in embedding_analysis gespeichert.
# v161: Bei nativer Analyse werden bei konstantem Rekordbox-Phasenversatz oder
# Taktlabelsprung getrennte Modellfenster gesammelt; betroffene abgeleitete
# Anker-/Phrasen-/Mixwerte werden neu berechnet.
# v162: Sektionsmerkmale langer Tracks werden auch aus dem analysierten Tail-Audio ermittelt.
# v163: Unbenannte Rekordbox-Marker bleiben Mixkandidaten mit eigener
# Provenienz und eigener Rangklasse; alte Auto-Cue-Zuordnungen verfallen.
# v164: Modell8-Langtrack-Coverage darf getrennte 60-s-Fenster abbilden;
# jedes Fenster wird einzeln gegen die durchgehende Modell7-Folge bestätigt.
# v165: Native Phrasen nutzen bei spaetem erstem Grid-Treffer einen
# phasenerhaltenden Eingabeoffset innerhalb der ersten Beatperiode.
# v166: Variable lange native Beatgrids werden nicht mehr am globalen
# Konstanttempo verworfen; HPG-FFmpeg ist Teil des gebundenen Readerpfads.
# v167: AAC wird mit der nativen Rekordbox-Factory dekodiert.
# v168: Native Phraseninitialisierung übergibt wie der Rekordbox-Caller die
# Sample-Rate auch im sechsten Zahlenargument statt der HPG-Taktposition.
# v169: Der native Phrasen-Snapshot bindet die drei konfigurierbaren Rohflags;
# Cache und Modellfingerprint trennen unterschiedliche Generatoraufrufe.
# v170: Cue-Modellbewertungen werden auch an freigegebene native Phrasen
# gebunden und dürfen deren Kandidaten bei der bestehenden Kappung ordnen.
# v171: Cue-Diagnostik bindet Scores an die Audiodatei, benennt den
# Phrase-Regressor unabhängig von PSSI/native Herkunft und priorisiert
# bestätigte PSSI-Grenzen in der Struktur.
# v172: Native Phrasenflags verlangen jetzt die rekonstruierte Kopplung
# zwischen Flag 2 und 3; ungültige alte Snapshots werden verworfen.
# v173: Nativen ersten Downbeat über die Rekordbox-Tabelle in die HPG-
# Taktposition übersetzen; alte Phrasenfreigaben/-ablehnungen nicht übernehmen.
# v174: Der native Initialisierer erhält den ersten Downbeat statt einer
# wiederholten Sample-Rate; Phrasenvertrag v8 bindet den tatsächlichen Aufruf.
# v175: Nativer ALAC-Reader mit eigener Herkunft und verlustfreier Dauertoleranz.
# v176: Nativer Beatwrapper erhält den Fensterstart als INT32-Sampleindex.
# v177: Nach Ankerentscheidung nur das tatsächlich gewählte native Grid weiterreichen.
CACHE_VERSION = 177
_CACHE_FILE_OVERRIDE = os.environ.get("HPG_CACHE_FILE", "").strip()


def _default_cache_file() -> str:
    """Liefert einen CWD-unabhaengigen Cachepfad im Benutzerprofil."""
    configured_dir = os.environ.get("HPG_CACHE_DIR", "").strip()
    if configured_dir:
        base_dir = Path(configured_dir).expanduser().resolve()
    else:
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        base_dir = (
            Path(local_app_data).expanduser().resolve() / "HPG"
            if local_app_data
            else (Path.home() / ".hpg").resolve()
        )
    return str((base_dir / f"hpg_cache_v{CACHE_VERSION}.db").resolve())


def _resolve_cache_file(override: str) -> str:
    """Bindet auch relative Overrides einmalig an einen absoluten Pfad."""
    return (
        str(Path(override).expanduser().resolve())
        if override
        else _default_cache_file()
    )


CACHE_FILE = _resolve_cache_file(_CACHE_FILE_OVERRIDE)
LOCK_FILE = os.path.splitext(CACHE_FILE)[0] + ".lock"

SQLITE_BUSY_CODES = {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
SQLITE_CORRUPTION_CODES = {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB}
SQLITE_RETRY_DELAYS = (0.05, 0.1, 0.2, 0.4)
CACHE_LOCK_TIMEOUT = 15.0


def _ensure_cache_schema(conn: sqlite3.Connection) -> None:
    """Creates the cache schema on an open SQLite connection if missing."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache ("
        "key TEXT PRIMARY KEY, "
        "filepath TEXT, "
        "version INTEGER, "
        "data TEXT"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache_quarantine ("
        "key TEXT, data TEXT, error TEXT, quarantined_at TEXT"
        ")"
    )


TRACK_REQUIRED_FIELDS = frozenset({
    "filePath", "fileName", "artist", "title", "genre", "duration", "bpm",
    "keyNote", "keyMode", "camelotCode", "energy", "bass_intensity",
    "stem_analysis", "embedding_analysis",
    "avg_bass", "avg_mids", "avg_highs", "mix_in_point", "mix_out_point",
    "first_downbeat", "downbeat_confidence", "bar_position_status", "beatgrid_source",
    "beatgrid_status", "beatgrid_windows_checked",
    "beatgrid_max_phase_error_ms", "measurement_diagnostics", "neural_analysis", "native_phrase_analysis", "native_beat_analysis", "first_phrase", "phrase_confidence",
    "key_confidence", "lufs", "mix_in_bars", "mix_out_bars",
    "detected_genre", "genre_confidence", "genre_source", "sections",
    "phrase_unit", "phrase_unit_source", "phrase_unit_candidate",
    "phrase_unit_score", "phrase_unit_margin", "brightness", "vocal_instrumental", "danceability",
    "spectral_flatness", "percussive_ratio", "mfcc_fingerprint",
    "timbre_fingerprint", "groove_pattern", "bass_pattern", "syncopation",
    "sub_energy", "bass_punch", "ai_metadata", "rekordbox_signature",
    "analysis_mode", "analysis_coverage", "outro_covered", "lufs_status",
    "lufs_coverage_seconds", "lufs_channels", "lufs_sample_rate", "phrases",
    "cue_points", "phrase_grid", "mix_in_candidates", "mix_out_candidates",
})
VALID_ANALYSIS_MODES = frozenset({"rekordbox_fast_tail", "librosa_full_or_tail"})
TRACK_LIST_FIELDS = {
    "sections", "mfcc_fingerprint", "timbre_fingerprint", "analysis_coverage",
    "groove_pattern", "bass_pattern",
    "phrases", "cue_points", "phrase_grid", "mix_in_candidates", "mix_out_candidates",
}
TRACK_DICT_FIELDS = {"ai_metadata", "measurement_diagnostics", "neural_analysis", "native_phrase_analysis", "native_beat_analysis",
                     "stem_analysis", "embedding_analysis"}
TRACK_CONFIDENCE_FIELDS = {
    "downbeat_confidence", "phrase_confidence", "key_confidence",
    "genre_confidence",
}
TRACK_STRING_FIELDS = {
    field.name for field in fields(Track) if isinstance(field.default, str)
}
TRACK_BOOL_FIELDS = {
    field.name for field in fields(Track) if isinstance(field.default, bool)
}
TRACK_NUMERIC_FIELDS = {
    field.name
    for field in fields(Track)
    if isinstance(field.default, (int, float))
    and not isinstance(field.default, bool)
}


class CacheValidationError(ValueError):
    """Ein einzelner Cache-Record verletzt den Track-Datenvertrag."""


def _validate_finite_values(value, path: str) -> None:
    """Verhindert nicht-endliche Zahlen auch in verschachtelten JSON-Feldern."""
    if isinstance(value, float) and not math.isfinite(value):
        raise CacheValidationError(f"{path} ist nicht endlich")
    if isinstance(value, dict):
        for key, nested in value.items():
            _validate_finite_values(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_finite_values(nested, f"{path}[{index}]")


MIX_CANDIDATE_FIELDS = {field.name for field in fields(MixCandidate)}
MIX_CANDIDATE_STRING_FIELDS = {
    "section_label", "phrase_label", "camelot_lokal", "energy_trend",
}
MIX_CANDIDATE_UNIT_INTERVAL_FIELDS = {
    "neuheit", "syncopation_lokal", "percussive_ratio_lokal", "sub_energy",
    "key_confidence_lokal", "flatness_lokal",
}
MIX_CANDIDATE_FINITE_FIELDS = {"bass_rms_dbfs", "lufs_lokal"}
MIX_CANDIDATE_PERCENT_FIELDS = {"avg_mids_lokal", "avg_highs_lokal"}
MIX_CANDIDATE_INT_PERCENT_FIELDS = {"brightness_lokal", "energy_lokal"}
MIX_CANDIDATE_BOOL_FIELDS = {"traegt_allein", "kick_aktiv", "vocal_aktiv_lokal"}


def _is_finite_number(value) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def _validate_optional_number(value, path: str, minimum=None, maximum=None) -> None:
    if value is None:
        return
    if not _is_finite_number(value):
        raise CacheValidationError(f"{path} muss eine endliche reelle Zahl oder None sein")
    if minimum is not None and value < minimum:
        raise CacheValidationError(f"{path} liegt unter {minimum}")
    if maximum is not None and value > maximum:
        raise CacheValidationError(f"{path} liegt ueber {maximum}")


def _require_dict_fields(value, path: str, required_fields: set[str]) -> dict:
    if not isinstance(value, dict):
        raise CacheValidationError(f"{path} muss ein Dictionary sein")
    missing = sorted(required_fields.difference(value))
    if missing:
        raise CacheValidationError(f"{path}.{missing[0]} fehlt")
    return value


def _validate_time(value, path: str, duration: float) -> float:
    if not _is_finite_number(value) or value < 0.0:
        raise CacheValidationError(f"{path} muss eine endliche nichtnegative Zahl sein")
    if value > duration:
        raise CacheValidationError(f"{path} liegt hinter dem Trackende")
    return float(value)


def _validate_json_scalar_or_none(value, path: str) -> None:
    if value is None or isinstance(value, (str, bool)) or _is_finite_number(value):
        return
    raise CacheValidationError(f"{path} muss ein JSON-Skalar oder None sein")


def _validate_sections(sections: list, duration: float) -> None:
    required = {"label", "start_time", "end_time", "start_bar", "end_bar", "avg_energy"}
    previous_start = None
    previous_end = None
    for index, section in enumerate(sections):
        path = f"sections[{index}]"
        section = _require_dict_fields(section, path, required)
        if not isinstance(section["label"], str):
            raise CacheValidationError(f"{path}.label muss ein String sein")
        start = _validate_time(section["start_time"], f"{path}.start_time", duration)
        end = _validate_time(section["end_time"], f"{path}.end_time", duration)
        if end < start:
            raise CacheValidationError(f"{path}.end_time liegt vor start_time")
        if (
            previous_start is not None
            and start < previous_start - VALIDATION_TIME_TOLERANCE
        ):
            raise CacheValidationError("sections muss nach start_time sortiert sein")
        if (
            previous_end is not None
            and start < previous_end - VALIDATION_TIME_TOLERANCE
        ):
            raise CacheValidationError("sections darf nicht ueberlappen")
        for field_name in ("start_bar", "end_bar"):
            value = section[field_name]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CacheValidationError(f"{path}.{field_name} muss ein nichtnegativer Integer sein")
        if section["end_bar"] < section["start_bar"]:
            raise CacheValidationError(f"{path}.end_bar liegt vor start_bar")
        if (
            not _is_finite_number(section["avg_energy"])
            or not 0.0 <= section["avg_energy"] <= 100.0
        ):
            raise CacheValidationError(f"{path}.avg_energy muss in 0..100 liegen")
        _validate_finite_values(section, path)
        previous_start = start
        previous_end = end


VALIDATION_TIME_TOLERANCE = 1e-6
ANALYSIS_COVERAGE_GAP_TOLERANCE = 1.0


def _validate_analysis_coverage(coverage: list, duration: float) -> list[tuple[float, float]]:
    required = {"start", "end"}
    windows = []
    previous_start = None
    previous_end = None
    for index, window in enumerate(coverage):
        path = f"analysis_coverage[{index}]"
        window = _require_dict_fields(window, path, required)
        start = _validate_time(window["start"], f"{path}.start", duration)
        end = _validate_time(window["end"], f"{path}.end", duration)
        if end < start:
            raise CacheValidationError(f"{path}.end liegt vor start")
        if end == start:
            raise CacheValidationError(f"{path}.end muss groesser als start sein")
        if previous_start is not None and start < previous_start:
            raise CacheValidationError("analysis_coverage muss nach start sortiert sein")
        if previous_end is not None and start < previous_end - VALIDATION_TIME_TOLERANCE:
            raise CacheValidationError("analysis_coverage darf nicht ueberlappen")
        _validate_finite_values(window, path)
        windows.append((start, end))
        previous_start = start
        previous_end = end
    return windows


def _validate_phrases(phrases: list, duration: float) -> list[tuple[float, float]]:
    required = {"start_s", "end_s", "label", "mood", "kind", "fill"}
    intervals = []
    for index, phrase in enumerate(phrases):
        path = f"phrases[{index}]"
        phrase = _require_dict_fields(phrase, path, required)
        start = _validate_time(phrase["start_s"], f"{path}.start_s", duration)
        end = _validate_time(phrase["end_s"], f"{path}.end_s", duration)
        if end < start:
            raise CacheValidationError(f"{path}.end_s liegt vor start_s")
        if not isinstance(phrase["label"], str):
            raise CacheValidationError(f"{path}.label muss ein String sein")
        for field_name in ("mood", "kind", "fill"):
            value = phrase[field_name]
            if isinstance(value, bool) or not isinstance(value, int):
                raise CacheValidationError(f"{path}.{field_name} muss ein Integer sein")
        _validate_finite_values(phrase, path)
        intervals.append((start, end))
    for index in range(1, len(intervals)):
        previous_end = intervals[index - 1][1]
        start = intervals[index][0]
        if abs(start - previous_end) > VALIDATION_TIME_TOLERANCE:
            raise CacheValidationError(
                f"phrases[{index}].start_s muss dem vorherigen end_s entsprechen"
            )
    return intervals


def _validate_cue_points(cue_points: list, duration: float) -> None:
    required = {"t", "name", "provenance"}
    for index, cue in enumerate(cue_points):
        path = f"cue_points[{index}]"
        cue = _require_dict_fields(cue, path, required)
        _validate_time(cue["t"], f"{path}.t", duration)
        if not isinstance(cue["name"], str):
            raise CacheValidationError(f"{path}.name muss ein String sein")
        if (
            not isinstance(cue["provenance"], str)
            or cue["provenance"] not in {"manual", "auto", "leer"}
        ):
            raise CacheValidationError(f"{path}.provenance ist ungueltig")
        for field_name in ("typ", "hot_cue"):
            if field_name in cue:
                _validate_json_scalar_or_none(cue[field_name], f"{path}.{field_name}")
        _validate_finite_values(cue, path)


def _validate_phrase_grid(phrase_grid: list, duration: float) -> None:
    previous = None
    for index, value in enumerate(phrase_grid):
        point = _validate_time(value, f"phrase_grid[{index}]", duration)
        if previous is not None and point <= previous:
            raise CacheValidationError("phrase_grid muss streng aufsteigend sein")
        previous = point


def _validate_coverage_sections(
    coverage: list[tuple[float, float]],
    sections: list,
    duration: float,
) -> None:
    unanalysed = sorted(
        (
            (float(section["start_time"]), float(section["end_time"]))
            for section in sections
            if section["label"] == "unanalysed"
        ),
        key=lambda interval: interval[0],
    )
    if not coverage and not unanalysed:
        return

    gaps = []
    cursor = 0.0
    for start, end in coverage:
        if start > cursor + ANALYSIS_COVERAGE_GAP_TOLERANCE:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if duration > cursor + ANALYSIS_COVERAGE_GAP_TOLERANCE:
        gaps.append((cursor, duration))

    if len(gaps) != len(unanalysed) or any(
        abs(gap_start - section_start) > VALIDATION_TIME_TOLERANCE
        or abs(gap_end - section_end) > VALIDATION_TIME_TOLERANCE
        for (gap_start, gap_end), (section_start, section_end)
        in zip(gaps, unanalysed)
    ):
        raise CacheValidationError(
            "analysis_coverage ist nicht konsistent mit unanalysed-Sections"
        )


def _validate_phrases_and_grid(
    phrases: list[tuple[float, float]],
    phrase_grid: list,
) -> None:
    expected = [start for start, _ in phrases]
    if phrases:
        expected.append(phrases[-1][1])
    if len(expected) != len(phrase_grid) or any(
        abs(expected_value - float(actual_value)) > VALIDATION_TIME_TOLERANCE
        for expected_value, actual_value in zip(expected, phrase_grid)
    ):
        raise CacheValidationError("phrases und phrase_grid sind inkonsistent")


def _validate_candidate_pattern(value, path: str, *, length: int, unit_interval: bool) -> None:
    if not isinstance(value, list) or len(value) not in {0, length}:
        raise CacheValidationError(f"{path} muss eine Liste der Laenge 0 oder {length} sein")
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not _is_finite_number(item):
            raise CacheValidationError(f"{item_path} muss eine endliche reelle Zahl sein")
        if unit_interval and not 0.0 <= item <= 1.0:
            raise CacheValidationError(f"{item_path} liegt ausserhalb 0..1")


def _validate_candidate_mood(value, path: str) -> None:
    if not isinstance(value, dict):
        raise CacheValidationError(f"{path} muss ein Dictionary sein")
    if "brightness" in value:
        _validate_optional_number(value["brightness"], f"{path}.brightness", 0.0, 100.0)
    if "flatness" in value:
        _validate_optional_number(value["flatness"], f"{path}.flatness", 0.0, 1.0)
    if "key_mode" in value and not isinstance(value["key_mode"], str):
        raise CacheValidationError(f"{path}.key_mode muss ein String sein")
    if "pssi_mood" in value:
        _validate_optional_number(value["pssi_mood"], f"{path}.pssi_mood")


def _validate_mix_candidate(candidate, path: str, duration: float) -> dict:
    if not isinstance(candidate, dict):
        raise CacheValidationError(f"{path} muss ein Dictionary sein")
    missing = MIX_CANDIDATE_FIELDS.difference(candidate)
    if missing:
        field_name = sorted(missing)[0]
        raise CacheValidationError(f"{path}.{field_name} fehlt")

    t = candidate["t"]
    if not _is_finite_number(t) or t < 0.0:
        raise CacheValidationError(f"{path}.t muss eine endliche nichtnegative reelle Zahl sein")
    if duration > 0.0 and t > duration:
        raise CacheValidationError(f"{path}.t liegt hinter dem Trackende")

    schema = candidate["schema"]
    if (
        not isinstance(schema, list)
        or not schema
        or any(not isinstance(item, str) or item not in SCHEMA_PRIORITAET for item in schema)
    ):
        raise CacheValidationError(f"{path}.schema ist ungueltig")
    if not isinstance(candidate["provenance"], str) or not candidate["provenance"]:
        raise CacheValidationError(f"{path}.provenance muss ein nichtleerer String sein")
    _validate_optional_number(candidate["confidence"], f"{path}.confidence", 0.0, 1.0)
    if candidate["confidence"] is None:
        raise CacheValidationError(f"{path}.confidence darf nicht None sein")

    for field_name in MIX_CANDIDATE_STRING_FIELDS:
        if not isinstance(candidate[field_name], str):
            raise CacheValidationError(f"{path}.{field_name} muss ein String sein")
    if candidate["energy_trend"] not in {"", "rising", "falling", "stable"}:
        raise CacheValidationError(f"{path}.energy_trend ist ungueltig")

    _validate_candidate_pattern(
        candidate["groove_pattern_lokal"], f"{path}.groove_pattern_lokal",
        length=16, unit_interval=True,
    )
    _validate_candidate_pattern(
        candidate["bass_pattern_lokal"], f"{path}.bass_pattern_lokal",
        length=16, unit_interval=True,
    )
    _validate_candidate_pattern(
        candidate["timbre_fingerprint_lokal"], f"{path}.timbre_fingerprint_lokal",
        length=13, unit_interval=False,
    )

    for field_name in MIX_CANDIDATE_UNIT_INTERVAL_FIELDS:
        _validate_optional_number(candidate[field_name], f"{path}.{field_name}", 0.0, 1.0)
    _validate_optional_number(candidate["bass_punch"], f"{path}.bass_punch", 0.0)
    for field_name in MIX_CANDIDATE_PERCENT_FIELDS:
        _validate_optional_number(candidate[field_name], f"{path}.{field_name}", 0.0, 100.0)
    for field_name in MIX_CANDIDATE_FINITE_FIELDS:
        _validate_optional_number(candidate[field_name], f"{path}.{field_name}")

    for field_name in MIX_CANDIDATE_INT_PERCENT_FIELDS:
        value = candidate[field_name]
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100
        ):
            raise CacheValidationError(f"{path}.{field_name} muss ein Integer 0..100 oder None sein")
    for field_name in MIX_CANDIDATE_BOOL_FIELDS:
        value = candidate[field_name]
        if value is not None and not isinstance(value, bool):
            raise CacheValidationError(f"{path}.{field_name} muss ein Boolean oder None sein")
    _validate_candidate_mood(candidate["mood"], f"{path}.mood")
    return {field_name: candidate[field_name] for field_name in MIX_CANDIDATE_FIELDS}


def _validate_mix_candidate_lists(filtered: dict, duration: float) -> None:
    for list_name in ("mix_in_candidates", "mix_out_candidates"):
        filtered[list_name] = [
            _validate_mix_candidate(
                candidate,
                f"{list_name}[{index}]",
                duration,
            )
            for index, candidate in enumerate(filtered.get(list_name, []))
        ]


def _require_real_in_range(
    filtered: dict, name: str, minimum: float, maximum: float, *,
    minimum_exclusive: bool = False, maximum_exclusive: bool = False,
) -> float:
    value = filtered[name]
    if not _is_finite_number(value):
        raise CacheValidationError(f"{name} muss eine endliche reelle Zahl sein")
    if (value <= minimum if minimum_exclusive else value < minimum):
        raise CacheValidationError(f"{name} liegt ausserhalb des gueltigen Bereichs")
    if (value >= maximum if maximum_exclusive else value > maximum):
        raise CacheValidationError(f"{name} liegt ausserhalb des gueltigen Bereichs")
    return float(value)


def _require_int_in_range(filtered: dict, name: str, minimum: int, maximum: int) -> int:
    value = filtered[name]
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise CacheValidationError(f"{name} muss ein Integer in {minimum}..{maximum} sein")
    return value


def _require_nonnegative_int(filtered: dict, name: str) -> int:
    value = filtered[name]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CacheValidationError(f"{name} muss ein nichtnegativer Integer sein")
    return value


def _validate_top_level_patterns(filtered: dict) -> None:
    for name in ("groove_pattern", "bass_pattern"):
        values = filtered[name]
        _validate_candidate_pattern(values, name, length=16, unit_interval=True)
        if values and not math.isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise CacheValidationError(f"{name} muss L1-normalisiert sein")
    for name in ("mfcc_fingerprint", "timbre_fingerprint"):
        _validate_candidate_pattern(filtered[name], name, length=13, unit_interval=False)


def _validate_lufs_contract(filtered: dict, duration: float) -> None:
    status = filtered["lufs_status"]
    if status not in {"unknown", "complete", "invalid", "error"}:
        raise CacheValidationError("lufs_status ist ungueltig")
    lufs = filtered["lufs"]
    if not _is_finite_number(lufs):
        raise CacheValidationError("lufs muss endlich sein")
    coverage = _require_real_in_range(
        filtered, "lufs_coverage_seconds", 0.0, duration
    )
    channels = _require_nonnegative_int(filtered, "lufs_channels")
    sample_rate = _require_nonnegative_int(filtered, "lufs_sample_rate")
    if status == "complete":
        if not -70.0 <= lufs < 0.0 or coverage <= 0.0 or not 1 <= channels <= 5 or sample_rate <= 0:
            raise CacheValidationError("vollstaendiger LUFS-Record ist inkonsistent")
    elif status == "invalid":
        if lufs != 0.0 or coverage <= 0.0 or channels <= 0 or sample_rate <= 0:
            raise CacheValidationError("ungueltiger LUFS-Record ist inkonsistent")
    elif lufs != 0.0 or coverage != 0.0 or channels != 0 or sample_rate != 0:
        raise CacheValidationError(f"LUFS-Status {status} erfordert leere Messwerte")


def _validate_top_level_physics(filtered: dict) -> tuple[float, float, float]:
    duration = _require_real_in_range(
        filtered, "duration", 0.0, 7200.0, minimum_exclusive=True
    )
    _require_real_in_range(
        filtered, "bpm", 20.0, 300.0,
        minimum_exclusive=True, maximum_exclusive=True,
    )
    for name in ("energy", "bass_intensity", "brightness", "danceability"):
        _require_int_in_range(filtered, name, 0, 100)
    bands = [
        _require_real_in_range(filtered, name, 0.0, 100.0)
        for name in ("avg_bass", "avg_mids", "avg_highs")
    ]
    if any(bands) and not math.isclose(sum(bands), 100.0, rel_tol=0.0, abs_tol=0.21):
        raise CacheValidationError("avg_bass/avg_mids/avg_highs muessen zusammen etwa 100 ergeben")
    for name in ("spectral_flatness", "percussive_ratio", "syncopation", "sub_energy"):
        _require_real_in_range(filtered, name, 0.0, 1.0)
    _require_real_in_range(filtered, "bass_punch", 0.0, sys.float_info.max)
    first_downbeat = _require_real_in_range(filtered, "first_downbeat", 0.0, duration)
    first_phrase = filtered["first_phrase"]
    if not _is_finite_number(first_phrase) or (
        first_phrase != MIX_POINT_UNSET and not 0.0 <= first_phrase <= duration
    ):
        raise CacheValidationError("first_phrase muss -1 oder innerhalb der Dauer sein")
    for name in ("mix_in_bars", "mix_out_bars", "beatgrid_windows_checked"):
        _require_nonnegative_int(filtered, name)
    _validate_top_level_patterns(filtered)
    _validate_lufs_contract(filtered, duration)
    return duration, first_downbeat, float(first_phrase)


def validate_track_dict(data: dict) -> dict:
    """Validiert Typen und Kerninvarianten eines flachen Track-Records."""
    if not isinstance(data, dict):
        raise CacheValidationError("Track-Record ist kein Dictionary")

    missing = sorted(TRACK_REQUIRED_FIELDS.difference(data))
    if missing:
        raise CacheValidationError(f"Pflichtfeld {missing[0]} fehlt")

    filtered = {key: value for key, value in data.items() if key in TRACK_REQUIRED_FIELDS}
    # Bereichsfehler benennen, bevor Herkunftsprüfungen diese Werte vergleichen.
    for name in TRACK_CONFIDENCE_FIELDS:
        _require_real_in_range(filtered, name, 0.0, 1.0)
    from .measurement_contract import validate_measurement_diagnostics
    from .ai_models.cue_service import validate_neural_analysis
    from .models import bar_position_usage_blocked
    try:
        validate_measurement_diagnostics(filtered["measurement_diagnostics"])
        measured = filtered['measurement_diagnostics']
        if measured.get('version') in {6, 7, 8}:
            phrase_diagnostic = measured['phrase_unit']
            for diagnostic_key, track_key in (
                    ('unit', 'phrase_unit'), ('source', 'phrase_unit_source'),
                    ('candidate', 'phrase_unit_candidate'),
                    ('raw_score', 'phrase_unit_score'),
                    ('ranking_margin', 'phrase_unit_margin')):
                if phrase_diagnostic[diagnostic_key] != filtered[track_key]:
                    raise CacheValidationError(
                        f"measurement_diagnostics.phrase_unit.{diagnostic_key} widerspricht {track_key}"
                    )
        if bar_position_usage_blocked(measured):
            if (
                filtered["first_phrase"] != MIX_POINT_UNSET
                or filtered["phrase_confidence"] != 0.0
                or filtered["phrases"]
                or filtered["phrase_grid"]
                or filtered["mix_in_candidates"]
                or filtered["mix_out_candidates"]
                or filtered["mix_in_point"] != MIX_POINT_UNSET
                or filtered["mix_out_point"] != MIX_POINT_UNSET
            ):
                raise ValueError("Taktpositionsrotation verlangt gesperrte Phrasen- und Mixausgaben")
        if measured.get('version') in {2, 3, 4, 5, 6, 7, 8} and 'anchor' in measured:
            active = measured['anchor']
            if (active['source'] != filtered['beatgrid_source']
                    or active['anchor_s'] != filtered['first_downbeat']
                    or active['confidence'] != filtered['downbeat_confidence']
                    or measured['grid']['status'] != filtered['beatgrid_status']
                    or measured['grid']['windows_checked'] != filtered['beatgrid_windows_checked']
                    or measured['grid']['max_phase_error_ms'] != filtered['beatgrid_max_phase_error_ms']):
                raise ValueError('Aktive Ankerdiagnose widerspricht Track')
            if active['source'] != 'rekordbox' and filtered['phrases']:
                raise ValueError('PSSI erfordert bestaetigte Rekordbox-Referenz')

        from .ai_models.native_track_beats import validate_snapshot as validate_native_beats
        native_beats = filtered['native_beat_analysis']
        if native_beats:
            validate_native_beats(native_beats, duration=filtered['duration'])
        native_method = measured.get('anchor', {}).get('method')
        blocked_bar_position = bar_position_usage_blocked(measured)
        bar_status = filtered['bar_position_status']
        if ((bar_status == 'blocked') != blocked_bar_position
                or bar_status == 'reference_verified' and not (
                    filtered['beatgrid_source'] == 'rekordbox'
                    and filtered['beatgrid_status'] == 'verified'
                    and filtered['downbeat_confidence'] == 1.0
                    and measured.get('anchor', {}).get('bar_position_comparison', {}).get('status') == 'aligned')
                or bar_status == 'reference_candidate' and not (
                    filtered['beatgrid_source'] == 'rekordbox'
                    and filtered['beatgrid_status'] == 'verified'
                    and filtered['downbeat_confidence'] == 1.0
                    and measured.get('anchor', {}).get('bar_position_comparison', {}).get('status') != 'aligned')
                or bar_status == 'native_candidate' and not (
                    native_method in {'native_rekordbox', 'native_rekordbox_audio_offset'}
                    and native_beats.get('status') == 'ok')
                or native_method in {'native_rekordbox', 'native_rekordbox_audio_offset'}
                   and bar_status != 'native_candidate'
                or bar_status == 'audio_estimate' and not (
                    filtered['beatgrid_source'] == 'audio'
                    and native_method not in {'native_rekordbox', 'native_rekordbox_audio_offset'}
                    and filtered['downbeat_confidence'] > 0.0)
                or bar_status == 'unknown'
                   and filtered['downbeat_confidence'] >= DOWNBEAT_RELIABLE_MIN):
            raise ValueError('Taktpositionsstatus widerspricht der aktiven Analysequelle')
        if native_method in {'native_rekordbox', 'native_rekordbox_audio_offset'}:
            from .ai_models.native_beat_alignment import active_anchor
            if (native_beats.get('status') != 'ok'
                    or filtered['bpm'] != native_beats['bpm']
                    or filtered['first_downbeat'] != active_anchor(native_beats)
                    or ('audio_alignment' in native_beats) != (native_method == 'native_rekordbox_audio_offset')
                    or filtered['beatgrid_status'] != 'verified'):
                raise ValueError('Native beat provenance conflicts with active track')
        from .ai_models.native_phrase_adapter import validate_snapshot, _normalize_grid_origin
        validate_snapshot(filtered['native_phrase_analysis'], duration=filtered['duration'],
            grid_verified=(filtered['beatgrid_status'] == 'verified'
                           and (filtered['downbeat_confidence'] >= DOWNBEAT_RELIABLE_MIN
                                or filtered['bar_position_status'] == 'native_candidate')),
            usage_blocked=bar_position_usage_blocked(measured))
        native = filtered['native_phrase_analysis']
        phase_usable = (
            filtered['bar_position_status'] not in {
                'reference_candidate', 'native_candidate', 'blocked', 'unknown',
            }
            and (filtered['bar_position_status'] != 'audio_estimate'
                 or filtered['downbeat_confidence'] >= DOWNBEAT_RELIABLE_MIN)
            and (filtered['beatgrid_source'] != 'rekordbox'
                 or filtered['bar_position_status'] == 'reference_verified')
        )
        if filtered['phrases'] and (
                filtered['beatgrid_source'] != 'rekordbox'
                or filtered['beatgrid_status'] != 'verified'
                or blocked_bar_position):
            raise ValueError('PSSI requires a verified, unblocked Rekordbox beatgrid')
        if native.get('status') == 'ok' and not phase_usable:
            raise ValueError('Native phrases require a usable phrase phase')
        if native.get('status') == 'ok':
            native_grid = native['input_grid']
            if native_grid['offset_ms'] * native_grid['bpm_hundredths'] >= 6_000_000:
                raise ValueError(
                    'Native phrase offset rounds to a full beat period'
                )
            from .ai_models.native_key import native_key_index
            expected_key = native_key_index(filtered['keyNote'], filtered['keyMode'])
            if (native['key_source'] != ('native_unknown_fallback_zero' if expected_key is None
                                        else 'hpg_key_native_table')
                    or native_grid['key_index'] != (0 if expected_key is None else expected_key)):
                raise ValueError('Native phrase key provenance mismatch')
            if (filtered['phrases'] or not filtered['neural_analysis']
                    or native_grid['bpm_hundredths'] != int(math.floor(filtered['bpm']*100+.5))
                    or (native_grid['basis'] == 'verified_rekordbox_grid') != (filtered['beatgrid_source'] == 'rekordbox')):
                raise ValueError('Native phrase provenance contradicts track')
            if native_grid['basis'] == 'native_verified_audio_grid':
                if (native_method not in {'native_rekordbox', 'native_rekordbox_audio_offset'}
                        or native_beats.get('status') != 'ok'):
                    raise ValueError('Native phrase grid lacks accepted native beats')
                from .ai_models.native_beat_alignment import active_anchor
                shift = (native_beats['audio_alignment']['offset_seconds']
                         if 'audio_alignment' in native_beats else 0.0)
                expected_grid = [
                    (row['pos'] / 44100.0 + shift, row['numBar'])
                    for row in native_beats['grid']
                    if 0.0 <= row['pos'] / 44100.0 + shift <= filtered['duration']
                ]
                if not expected_grid:
                    raise ValueError('Native phrase grid lacks source beats')
                expected_times, expected_positions, extension = _normalize_grid_origin(
                    [row[0] for row in expected_grid], [row[1] for row in expected_grid],
                    bpm=filtered['bpm'])
                if (abs(active_anchor(native_beats) - filtered['first_downbeat']) > 1e-9
                        or native_grid['source_beat_count'] != len(expected_grid)
                        or native_grid['origin_extension_beats'] != extension
                        or native_grid['beat_count'] != len(expected_times)
                        or native_grid['bar_position'] != expected_positions[0]
                        or abs(native_grid['first_tick_s'] - expected_times[0]) > 1e-9
                        or abs(native_grid['last_tick_s'] - expected_times[-1]) > 1e-9
                        or any(not any(abs(phrase[key] - stamp) <= 1e-9
                                       for stamp in expected_times)
                               for phrase in native['phrases']
                               for key in ('start_s', 'end_s'))):
                    raise ValueError('Native phrase boundaries do not follow accepted native beats')
        validate_neural_analysis(filtered["neural_analysis"], track_duration_s=filtered['duration'])
        if filtered['neural_analysis']:
            suffix = '|neural:' + filtered['neural_analysis']['fingerprint']
            if not isinstance(filtered['rekordbox_signature'], str) or not filtered['rekordbox_signature'].endswith(suffix):
                raise ValueError('neural_analysis passt nicht zur Quellidentität')
    except ValueError as error:
        raise CacheValidationError(str(error)) from error
    if filtered.get("ai_metadata"):
        from .ai_engine import validate_ai_metadata
        if not validate_ai_metadata(filtered["ai_metadata"], duration=filtered.get("duration")):
            raise CacheValidationError("ai_metadata verletzt den KI-Vertrag")
    for required in ("filePath", "fileName"):
        if not isinstance(filtered.get(required), str) or not filtered[required]:
            raise CacheValidationError(f"Pflichtfeld {required} fehlt oder ist ungueltig")

    for name in TRACK_STRING_FIELDS:
        if not isinstance(filtered[name], str):
            raise CacheValidationError(f"{name} muss ein String sein")
    if filtered["bar_position_status"] not in {
            "reference_verified", "reference_candidate", "native_candidate",
            "audio_estimate", "blocked", "unknown"}:
        raise CacheValidationError("Ungültiger Taktpositionsstatus")
    for name in TRACK_BOOL_FIELDS:
        if not isinstance(filtered[name], bool):
            raise CacheValidationError(f"{name} muss ein Boolean sein")

    for name in TRACK_LIST_FIELDS:
        if name in filtered and not isinstance(filtered[name], list):
            raise CacheValidationError(f"{name} muss eine Liste sein")
    for name in TRACK_DICT_FIELDS:
        if name in filtered and not isinstance(filtered[name], dict):
            raise CacheValidationError(f"{name} muss ein Dictionary sein")

    for name in TRACK_NUMERIC_FIELDS:
        if name in filtered and (
            isinstance(filtered[name], bool)
            or not isinstance(filtered[name], (int, float))
        ):
            raise CacheValidationError(f"{name} muss numerisch sein")

    for name, value in filtered.items():
        if name not in {"mix_in_candidates", "mix_out_candidates"}:
            _validate_finite_values(value, name)
    duration, _first_downbeat, _first_phrase = _validate_top_level_physics(filtered)
    from .ai_models.deep_features import source_duration_tolerance, validate as validate_deep_feature
    try:
        for kind, field in (('stems', 'stem_analysis'), ('embedding', 'embedding_analysis')):
            snapshot = filtered[field]
            validate_deep_feature(
                snapshot, kind=kind, duration=duration,
                duration_tolerance=source_duration_tolerance(filtered['filePath']),
            )
    except (ValueError, TypeError, KeyError) as error:
        raise CacheValidationError(str(error)) from error

    source = filtered.get("beatgrid_source", "unknown")
    status = filtered.get("beatgrid_status", "unknown")
    if source not in BEATGRID_SOURCES:
        raise CacheValidationError("beatgrid_source ist ungueltig")
    if status not in BEATGRID_STATUSES:
        raise CacheValidationError("beatgrid_status ist ungueltig")
    windows = filtered.get("beatgrid_windows_checked", 0)
    if isinstance(windows, bool) or not isinstance(windows, int) or windows < 0:
        raise CacheValidationError("beatgrid_windows_checked ist ungueltig")
    phase_error = filtered.get("beatgrid_max_phase_error_ms", -1.0)
    if not _is_finite_number(phase_error) or (
        phase_error != MIX_POINT_UNSET and phase_error < 0.0
    ):
        raise CacheValidationError("beatgrid_max_phase_error_ms ist ungueltig")
    if status == "verified" and (
        source not in {"rekordbox", "audio"}
        or windows < 3
        or phase_error < 0.0
        or phase_error > EXACT_BEAT_SYNC_TOLERANCE_SECONDS * 1000.0
    ):
        raise CacheValidationError("verifiziertes Beatgrid hat unvollstaendige Messwerte")
    if source == "rekordbox" and status == "verified" and filtered.get(
        "downbeat_confidence"
    ) != REFERENCE_BEATGRID_CONFIDENCE:
        raise CacheValidationError("verifiziertes Rekordbox-Beatgrid braucht Referenzkonfidenz")

    mix_in = filtered["mix_in_point"]
    mix_out = filtered["mix_out_point"]
    for name, value in (("mix_in_point", mix_in), ("mix_out_point", mix_out)):
        if not _is_finite_number(value) or (
            value != MIX_POINT_UNSET and not 0.0 <= value <= duration
        ):
            raise CacheValidationError(f"{name} muss -1 oder innerhalb der Dauer sein")
    if mix_in >= 0 and mix_out >= 0 and not mix_in < mix_out:
        raise CacheValidationError("Mix-In muss vor Mix-Out liegen")
    phrase_unit = filtered["phrase_unit"]
    if (
        not is_supported_phrase_unit(phrase_unit)
    ):
        raise CacheValidationError("phrase_unit muss 8, 16 oder 32 sein")
    phrase_unit_source = filtered["phrase_unit_source"]
    if (type(phrase_unit_source) is not str
            or phrase_unit_source not in {"genre_prior", "audio_novelty", "configured"}):
        raise CacheValidationError("phrase_unit_source ist ungueltig")
    phrase_unit_candidate = filtered["phrase_unit_candidate"]
    if (phrase_unit_candidate is not None
            and not is_supported_phrase_unit(phrase_unit_candidate)):
        raise CacheValidationError("phrase_unit_candidate muss 8, 16, 32 oder None sein")
    phrase_unit_score = filtered["phrase_unit_score"]
    phrase_unit_margin = filtered["phrase_unit_margin"]
    if phrase_unit_candidate is None:
        if phrase_unit_score is not None or phrase_unit_margin is not None:
            raise CacheValidationError("Novelty-Score ohne Phrasenkandidat")
    else:
        if phrase_unit_score is None or not _is_finite_number(phrase_unit_score):
            raise CacheValidationError("phrase_unit_score muss endlich sein")
        if phrase_unit_margin is not None and (
            not _is_finite_number(phrase_unit_margin) or phrase_unit_margin < 0.0
        ):
            raise CacheValidationError("phrase_unit_margin muss endlich und nichtnegativ sein")
    if phrase_unit_source == "audio_novelty" and (
        phrase_unit_candidate != phrase_unit or phrase_unit_score is None or phrase_unit_margin is None
    ):
        raise CacheValidationError("audio_novelty erfordert vollstaendige Messwerte")
    _validate_sections(filtered["sections"], duration)
    coverage = _validate_analysis_coverage(filtered["analysis_coverage"], duration)
    phrases = _validate_phrases(filtered["phrases"], duration)
    _validate_cue_points(filtered["cue_points"], duration)
    _validate_phrase_grid(filtered["phrase_grid"], duration)
    _validate_coverage_sections(coverage, filtered["sections"], duration)
    if filtered["outro_covered"] and (
        not coverage
        or duration - coverage[-1][1] > ANALYSIS_COVERAGE_GAP_TOLERANCE
    ):
        raise CacheValidationError(
            "outro_covered erfordert Analyse-Coverage bis zum Trackende"
        )
    native_phrases = filtered['native_phrase_analysis'].get('phrases', [])
    active_intervals = phrases or [(p['start_s'], p['end_s']) for p in native_phrases]
    _validate_phrases_and_grid(active_intervals, filtered["phrase_grid"])
    _validate_mix_candidate_lists(filtered, duration)
    if filtered["analysis_mode"] not in VALID_ANALYSIS_MODES:
        raise CacheValidationError("analysis_mode ist ungueltig")
    return filtered


def _quarantine_cache_row_on_connection(
    conn: sqlite3.Connection,
    cache_key: str,
    data: str,
    error: Exception,
) -> None:
    """Isoliert einen ungueltigen Record auf einer bereits gesperrten Verbindung."""
    _ensure_cache_schema(conn)
    conn.execute(
        "INSERT INTO cache_quarantine (key, data, error, quarantined_at) VALUES (?, ?, ?, ?)",
        (cache_key, data, str(error), datetime.now(timezone.utc).isoformat()),
    )
    conn.execute("DELETE FROM cache WHERE key = ?", (cache_key,))
    conn.commit()


def _sqlite_error_code(error: sqlite3.Error) -> int | None:
    """Extrahiert den primaeren SQLite-Code ohne Extended-Code-Bits."""
    code = getattr(error, "sqlite_errorcode", None)
    return code & 0xFF if isinstance(code, int) else None


def _connect_cache() -> sqlite3.Connection:
    """Oeffnet den Cache mit begrenztem Retry nur fuer BUSY/LOCKED."""
    last_error = None
    for delay in (*SQLITE_RETRY_DELAYS, None):
        try:
            conn = sqlite3.connect(CACHE_FILE, timeout=15.0)
            conn.execute("PRAGMA busy_timeout=15000;")
            conn.execute("PRAGMA foreign_keys=ON;")
            return conn
        except sqlite3.OperationalError as error:
            last_error = error
            if _sqlite_error_code(error) not in SQLITE_BUSY_CODES or delay is None:
                raise
            time.sleep(delay)
    raise last_error


def _is_confirmed_corrupt_on_connection() -> bool:
    """Bestaetigt Korruption per integrity_check oder eindeutigem Resultcode."""
    conn = None
    try:
        conn = sqlite3.connect(CACHE_FILE, timeout=2.0)
        row = conn.execute("PRAGMA integrity_check;").fetchone()
        return not row or str(row[0]).lower() != "ok"
    except sqlite3.DatabaseError as error:
        return _sqlite_error_code(error) in SQLITE_CORRUPTION_CODES
    finally:
        if conn is not None:
            conn.close()


def _quarantine_corrupt_cache() -> bool:
    """Verschiebt eine bestaetigt defekte DB reversibel statt sie zu loeschen."""
    with file_lock(LOCK_FILE, timeout=CACHE_LOCK_TIMEOUT):
        if not os.path.exists(CACHE_FILE) or not _is_confirmed_corrupt_on_connection():
            return False

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        quarantine_dir = Path(CACHE_FILE).parent / "quarantine"
        quarantine_dir.mkdir(parents=True, exist_ok=True)

        for suffix in ("", "-wal", "-shm", "-journal"):
            source = Path(CACHE_FILE + suffix)
            if source.exists():
                destination = quarantine_dir / f"{source.name}.{timestamp}.corrupt"
                shutil.move(str(source), str(destination))
    logger.error("Bestaetigt defekter Cache wurde nach %s verschoben", quarantine_dir)
    return True


def _handle_database_error(operation: str, error: sqlite3.DatabaseError) -> None:
    """Trennt Korruption von transienten oder programmatischen DB-Fehlern."""
    code = _sqlite_error_code(error)
    if code in SQLITE_CORRUPTION_CODES and _quarantine_corrupt_cache():
        logger.error("SQLite-%s scheiterte wegen bestaetigter Korruption: %s", operation, error)
        init_cache()
        return
    logger.warning(
        "SQLite-%s fehlgeschlagen ohne Korruptions-Recovery (Code=%s): %s",
        operation,
        code,
        error,
    )


def _snapshot_value(value):
    """Erstellt rekursiv JSON-nahe, vom Track losgeloeste Daten."""
    if isinstance(value, dict):
        return {key: _snapshot_value(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_snapshot_value(nested) for nested in value]
    if isinstance(value, np.generic):
        return value.item()
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _snapshot_value(to_dict())
    return value


def track_to_dict(track: Track) -> dict:
    """Erstellt einen rekursiv losgeloesten Snapshot des Track-Objekts."""
    # Laufzeitattribute wie analysis_origin sind kein persistierter Trackvertrag.
    return {field.name: _snapshot_value(getattr(track, field.name)) for field in fields(Track)}


def dict_to_track(d: dict) -> Track:
    """Creates a Track object from a dictionary, ensuring all keys are present."""
    d = validate_track_dict(_snapshot_value(d))
    from .ai_models.deep_features import _empty, config_fingerprint
    try:
        feature_fingerprints = config_fingerprint()
    except Exception:
        feature_fingerprints = {}
    for kind, field_name in (('stems', 'stem_analysis'),
                             ('embedding', 'embedding_analysis')):
        snapshot = d[field_name]
        feature_fingerprint = feature_fingerprints.get(kind)
        expected_version = 5 if kind == 'embedding' else 3
        if (snapshot.get('status') == 'ok'
                and (snapshot.get('version') != expected_version or feature_fingerprint is None
                     or snapshot.get('fingerprint') != feature_fingerprint)):
            d[field_name] = _empty(kind, d['duration'],
                feature_fingerprint or '0'*64, 'unavailable', 'stale_feature_producer')
    filePath = d['filePath']
    fileName = d['fileName']
    track = Track(filePath=filePath, fileName=fileName)
    for k, v in d.items():
        if k in ('filePath', 'fileName'):
            continue
        setattr(track, k, v)
    return track


def _cache_marker_is_current(marker) -> bool:
    """Prueft den kanonischen Versionsmarker vollstaendig."""
    return marker == ("system", CACHE_VERSION, "metadata")


def _reset_cache_rows(conn: sqlite3.Connection) -> None:
    """Ersetzt alle Cache-Zeilen atomar durch den kanonischen Marker."""
    conn.execute("DELETE FROM cache")
    conn.execute(
        "INSERT INTO cache (key, filepath, version, data) "
        "VALUES ('version', 'system', ?, 'metadata')",
        (CACHE_VERSION,),
    )


def init_cache() -> None:
    """Initializes the SQLite database and creates the cache table."""
    cache_dir = os.path.dirname(CACHE_FILE)
    if cache_dir and not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)

    conn = None
    try:
        # Establish connection with a generous timeout for concurrent writes
        with file_lock(LOCK_FILE, timeout=CACHE_LOCK_TIMEOUT):
            # Establish connection with a generous timeout for concurrent writes
            conn = _connect_cache()
            # Enable WAL mode for high concurrency
            conn.execute("PRAGMA journal_mode=WAL;")
            _ensure_cache_schema(conn)
            conn.commit()

            # Check version and clear cache if it was created with an old version
            cursor = conn.cursor()
            cursor.execute(
                "SELECT filepath, version, data FROM cache "
                "WHERE key = 'version' LIMIT 1"
            )
            row = cursor.fetchone()
            if not _cache_marker_is_current(row):
                # Ohne kanonischen Marker sind vorhandene Records nicht vertrauenswuerdig.
                _reset_cache_rows(conn)
                conn.commit()
                logger.info(f"Cache-Marker initialisiert (Version {CACHE_VERSION})")
            else:
                cursor.execute(
                    "DELETE FROM cache WHERE key <> 'version' AND (version IS NULL OR version <> ?)",
                    (CACHE_VERSION,),
                )
                conn.commit()

        conn.close()
    except sqlite3.DatabaseError as e:
        if conn is not None:
            conn.close()
            conn = None
        # M14-Fix: korrupte DB ("database disk image is malformed") nicht nur
        # loggen, sondern loeschen und neu anlegen — sonst bleibt der Cache tot
        _handle_database_error("Init", e)
    except Exception as e:
        logger.error(f"Init-Fehler des SQLite-Caches: {e}")
    finally:
        if conn is not None:
            conn.close()


def generate_cache_key(file_path: str, source_signature: str = "") -> str | None:
    """Generiert einen stabilen Key aus Pfad und mehreren Dateizeitstempeln."""
    if not file_path:
        return None
    # normpath: QFileDialog liefert D:/pfad, os.walk D:\pfad -- ohne
    # Normalisierung entstehen doppelte Cache-Eintraege und die GUI
    # verfehlt vorhandene Analysen (Cache-Miss trotz identischer Datei)
    identifier = os.path.normcase(os.path.abspath(os.path.normpath(str(file_path))))
    try:
        stat = os.stat(identifier)
        key = (
            f"{identifier}-{stat.st_size}-{stat.st_mtime}-"
            f"{stat.st_mtime_ns}-{stat.st_ctime_ns}"
        )
        if source_signature:
            key = f"{key}-source-{source_signature}"
        return key
    except OSError:
        # Auch ohne lesbare Dateistatistik muss die Rekordbox-Signatur Teil der
        # Cache-Identitaet bleiben. JSON kodiert beide Felder eindeutig; eine
        # einfache Trennzeichen-Verkettung koennte kollidierende Paare bilden.
        if source_signature:
            fallback_payload = json.dumps(
                [identifier, str(source_signature)],
                ensure_ascii=True,
                separators=(",", ":"),
            )
            return hashlib.sha256(fallback_payload.encode("utf-8")).hexdigest()
        return hashlib.sha256(identifier.encode("utf-8", "ignore")).hexdigest()


def get_cached_track(cache_key: str, file_path: str = None) -> Track | None:
    """Retrieves a track from the SQLite cache."""
    if not cache_key:
        return None

    conn = None
    try:
        with file_lock(LOCK_FILE, timeout=CACHE_LOCK_TIMEOUT):
            conn = _connect_cache()
            _ensure_cache_schema(conn)
            conn.commit()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data FROM cache WHERE key = ? AND version = ?",
                (cache_key, CACHE_VERSION),
            )
            row = cursor.fetchone()

            if row:
                try:
                    data_dict = json.loads(row[0])
                    track = dict_to_track(data_dict)
                except (
                    json.JSONDecodeError,
                    CacheValidationError,
                    TypeError,
                    ValueError,
                    OverflowError,
                ) as error:
                    _quarantine_cache_row_on_connection(conn, cache_key, row[0], error)
                    logger.warning("Ungueltiger Cache-Record %s quarantinisiert: %s", cache_key, error)
                    return None

                # Validate cache key against physical file changes
                if file_path:
                    expected_key = generate_cache_key(
                        file_path, track.rekordbox_signature
                    )
                    if expected_key != cache_key:
                        return None
                return track
    except sqlite3.DatabaseError as e:
        if conn is not None:
            conn.close()
            conn = None
        _handle_database_error("Lesen", e)
        return None
    except Exception as e:
        # AUDIT-FIX C-02 (2026-07-24): auf WARNING statt DEBUG. Schema-Drift
        # nach einem Track-Feld-Rename (dict_to_track wirft) fuehrte sonst
        # dazu, dass JEDER Track bei jedem Start neu analysiert wurde — im Log
        # unsichtbar, User merkte nur "ploetzlich langsam".
        logger.warning(f"SQLite cache read error (Track wird neu analysiert): {e}")
        return None
    finally:
        if conn is not None:
            conn.close()
    return None


def _load_current_cache_row(
    conn: sqlite3.Connection, cache_key: str, file_path: str
) -> tuple[str, dict] | None:
    """Liest und validiert genau die aktuelle, streng pfadgebundene Zeile."""
    row = conn.execute(
        "SELECT filepath, data FROM cache WHERE key = ? AND version = ?",
        (cache_key, CACHE_VERSION),
    ).fetchone()
    if row is None:
        return None
    stored_path, data_json = row
    try:
        data = validate_track_dict(json.loads(data_json))
        if data["filePath"] != stored_path:
            raise CacheValidationError("Cache-Zeile enthaelt widerspruechliche Dateipfade")
    except (
        json.JSONDecodeError, CacheValidationError, TypeError, ValueError,
        OverflowError,
    ) as error:
        _quarantine_cache_row_on_connection(conn, cache_key, data_json, error)
        logger.warning("Ungueltiger Cache-Record %s quarantinisiert: %s", cache_key, error)
        return None
    if stored_path != file_path:
        return None
    return data_json, data


def merge_cached_ai_metadata(
    cache_key: str, file_path: str, ai_data: dict
) -> bool:
    """Ersetzt atomar nur ``ai_metadata`` einer gueltigen aktuellen Zeile."""
    if not cache_key or not isinstance(file_path, str) or not file_path:
        return False
    snapshot = _snapshot_value(ai_data)
    if not isinstance(snapshot, dict):
        return False
    try:
        _validate_finite_values(snapshot, "ai_metadata")
    except CacheValidationError:
        return False

    conn = None
    try:
        with file_lock(LOCK_FILE, timeout=CACHE_LOCK_TIMEOUT):
            conn = _connect_cache()
            _ensure_cache_schema(conn)
            current = _load_current_cache_row(conn, cache_key, file_path)
            if current is None:
                return False
            old_json, data = current
            data["ai_metadata"] = snapshot
            filtered = validate_track_dict(data)
            new_json = json.dumps(filtered, allow_nan=False)
            cursor = conn.execute(
                "UPDATE cache SET data = ? WHERE key = ? AND filepath = ? "
                "AND version = ? AND data = ?",
                (new_json, cache_key, file_path, CACHE_VERSION, old_json),
            )
            if cursor.rowcount != 1:
                conn.rollback()
                return False
            conn.commit()
            return True
    except sqlite3.DatabaseError as error:
        if conn is not None:
            conn.close()
            conn = None
        _handle_database_error("KI-Metadaten-Merge", error)
    except Exception as error:
        logger.warning("SQLite AI metadata merge failed: %s", error)
    finally:
        if conn is not None:
            conn.close()
    return False


CANDIDATE_OPTIONAL_NUMERIC_FIELDS = (
    MIX_CANDIDATE_UNIT_INTERVAL_FIELDS
    | MIX_CANDIDATE_FINITE_FIELDS
    | MIX_CANDIDATE_PERCENT_FIELDS
    | MIX_CANDIDATE_INT_PERCENT_FIELDS
    | {"bass_punch"}
)
CANDIDATE_LOCAL_VECTOR_FIELDS = {
    "groove_pattern_lokal", "bass_pattern_lokal", "timbre_fingerprint_lokal",
}
CANDIDATE_MOOD_OPTIONAL_NUMERIC_FIELDS = {"brightness", "flatness", "pssi_mood"}


def _is_nonfinite_number(value) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and not math.isfinite(value)
    )


def _normalize_cache_snapshot(data: dict) -> dict:
    """Normalisiert nur die explizit tolerierten nicht-endlichen Messwerte."""
    for list_name in ("mix_in_candidates", "mix_out_candidates"):
        candidates = data.get(list_name)
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            for field_name in CANDIDATE_OPTIONAL_NUMERIC_FIELDS:
                if _is_nonfinite_number(candidate.get(field_name)):
                    candidate[field_name] = None
            for field_name in CANDIDATE_LOCAL_VECTOR_FIELDS:
                vector = candidate.get(field_name)
                if isinstance(vector, list) and any(_is_nonfinite_number(value) for value in vector):
                    candidate[field_name] = []
            mood = candidate.get("mood")
            if isinstance(mood, dict):
                for field_name in CANDIDATE_MOOD_OPTIONAL_NUMERIC_FIELDS:
                    if _is_nonfinite_number(mood.get(field_name)):
                        mood[field_name] = None
    return data


def cache_track(cache_key: str, track: Track) -> bool:
    """Speichert einen Track und meldet, ob die Zeile persistiert wurde."""
    if not cache_key or not track:
        return False

    conn = None
    try:
        data_dict = track_to_dict(track)
        _normalize_cache_snapshot(data_dict)
        filtered = validate_track_dict(data_dict)

        with file_lock(LOCK_FILE, timeout=CACHE_LOCK_TIMEOUT):
            conn = _connect_cache()
            conn.execute("PRAGMA journal_mode=WAL;")
            _ensure_cache_schema(conn)
            marker = conn.execute(
                "SELECT filepath, version, data FROM cache "
                "WHERE key = 'version' LIMIT 1"
            ).fetchone()
            if not _cache_marker_is_current(marker):
                _reset_cache_rows(conn)
            else:
                conn.execute(
                    "DELETE FROM cache WHERE key <> 'version' AND (version IS NULL OR version <> ?)",
                    (CACHE_VERSION,),
                )
            current = _load_current_cache_row(
                conn, cache_key, filtered["filePath"]
            )
            if current is not None:
                _old_json, current_data = current
                filtered["ai_metadata"] = _snapshot_value(
                    current_data["ai_metadata"]
                )
                filtered = validate_track_dict(filtered)
            data_json = json.dumps(filtered, allow_nan=False)
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, filepath, version, data) VALUES (?, ?, ?, ?)",
                (cache_key, filtered["filePath"], CACHE_VERSION, data_json)
            )
            conn.commit()
        return True
    except sqlite3.DatabaseError as e:
        if conn is not None:
            conn.close()
            conn = None
        _handle_database_error("Schreiben", e)
    except Exception as e:
        logger.warning(f"SQLite cache write failed: {e}")
    finally:
        if conn is not None:
            conn.close()
    return False


# Platform-specific locking imports for backward compatibility
if sys.platform == 'win32':
    import msvcrt

    def _lock_file(file_handle):
        """Lock file on Windows using msvcrt"""
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock_file(file_handle):
        """Unlock file on Windows using msvcrt"""
        try:
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
        except (IOError, OSError):
            pass
else:
    import fcntl

    def _lock_file(file_handle):
        """Lock file on Unix/Linux using fcntl"""
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock_file(file_handle):
        """Unlock file on Unix/Linux using fcntl"""
        try:
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
        except (IOError, OSError):
            pass


@contextmanager
def file_lock(lock_path: str, timeout: float = 5.0):
    """
    Cross-platform file-based locking context manager for backward compatibility and testing.
    """
    lock_file_handle = None
    start_time = time.time()

    try:
        lock_path_obj = Path(lock_path)
        lock_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # Step 1: Open the lock file with retries
        while True:
            try:
                lock_file_handle = open(lock_path, 'a+b')
                if lock_file_handle.seek(0, os.SEEK_END) == 0:
                    lock_file_handle.write(b'\0')
                    lock_file_handle.flush()
                lock_file_handle.seek(0)
                break
            except (PermissionError, IOError) as e:
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Could not open lock file {lock_path} within {timeout}s: {e}")
                time.sleep(0.02)

        # Step 2: Acquire exclusive lock with timeout
        while True:
            try:
                _lock_file(lock_file_handle)
                break  # Lock acquired
            except (BlockingIOError, IOError):
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Could not acquire lock on {lock_path} within {timeout}s")
                lock_file_handle.close()
                lock_file_handle = None
                time.sleep(0.01)
                lock_file_handle = open(lock_path, 'a+b')
                lock_file_handle.seek(0)

        yield lock_file_handle

    finally:
        if lock_file_handle:
            try:
                _unlock_file(lock_file_handle)
            except OSError:
                pass
            try:
                lock_file_handle.close()
            except OSError:
                pass

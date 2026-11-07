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
# v178: Native Taktanker mit sechs bestätigten Modell-/Audiofenstern.
# v179: Native Taktbestätigung nutzt vorab gewählte regelmäßige Beatfenster und behält Fehlbelege.
# v180: Native Taktbestätigung und Gridprüfung messen dieselbe Attack-Phase.
# v181: Native Taktbestätigung schließt Audio-Gegenkandidaten zum Modell aus.
# v183: Native Auftaktabschnitte sperren keine folgenden taktrichtigen Mixkandidaten.
CACHE_VERSION = 183
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


# Kompatible Namen; die Validierung besitzt keine Datenbankabhängigkeit.
from .cache_validation import (
    TRACK_REQUIRED_FIELDS,
    VALID_ANALYSIS_MODES,
    TRACK_LIST_FIELDS,
    TRACK_DICT_FIELDS,
    TRACK_CONFIDENCE_FIELDS,
    TRACK_STRING_FIELDS,
    TRACK_BOOL_FIELDS,
    TRACK_NUMERIC_FIELDS,
    CacheValidationError,
    _validate_finite_values,
    MIX_CANDIDATE_FIELDS,
    MIX_CANDIDATE_STRING_FIELDS,
    MIX_CANDIDATE_UNIT_INTERVAL_FIELDS,
    MIX_CANDIDATE_FINITE_FIELDS,
    MIX_CANDIDATE_PERCENT_FIELDS,
    MIX_CANDIDATE_INT_PERCENT_FIELDS,
    MIX_CANDIDATE_BOOL_FIELDS,
    _is_finite_number,
    _validate_optional_number,
    _require_dict_fields,
    _validate_time,
    _validate_json_scalar_or_none,
    _validate_sections,
    VALIDATION_TIME_TOLERANCE,
    ANALYSIS_COVERAGE_GAP_TOLERANCE,
    _validate_analysis_coverage,
    _validate_phrases,
    _validate_cue_points,
    _validate_phrase_grid,
    _validate_coverage_sections,
    _validate_phrases_and_grid,
    _validate_candidate_pattern,
    _validate_candidate_mood,
    _validate_mix_candidate,
    _validate_mix_candidate_lists,
    _require_real_in_range,
    _require_int_in_range,
    _require_nonnegative_int,
    _validate_top_level_patterns,
    _validate_lufs_contract,
    _validate_top_level_physics,
    validate_track_dict,
)


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


def get_legacy_cached_core(file_path: str, rekordbox_signature: str, core_identity: str) -> Track | None:
    """Liest nachweislich kompatible Altanalysen; schreibt keine Cache-Zeile um."""
    from types import SimpleNamespace
    from .ai_models import cue_service

    if not os.path.isfile(file_path) or core_identity != cue_service.core_fingerprint():
        return None
    # Derselbe normalisierte Quellvertrag wie beim direkten Lookup; filepath
    # kann aus QFileDialog oder os.walk unterschiedlich geschrieben sein.
    source_prefix = generate_cache_key(file_path) + '-source-'
    conn = None
    try:
        with file_lock(LOCK_FILE, timeout=CACHE_LOCK_TIMEOUT):
            conn = _connect_cache()
            rows = conn.execute(
                'SELECT key, data FROM cache WHERE version = ? AND substr(key, 1, ?) = ? '
                'ORDER BY rowid DESC LIMIT 32', (CACHE_VERSION, len(source_prefix), source_prefix)
            ).fetchall()
        for old_key, raw in rows:
            try:
                # Vor dict_to_track prüfen: diese Funktion entwertet veraltete
                # Zusatzmerkmale und würde deren historische Identität verlieren.
                payload = validate_track_dict(json.loads(raw))
                old_signature = payload['rekordbox_signature']
                if os.path.normcase(os.path.abspath(payload['filePath'])) != os.path.normcase(os.path.abspath(file_path)):
                    continue
                if generate_cache_key(file_path, old_signature) != old_key:
                    continue
                if not cue_service.legacy_core_matches(SimpleNamespace(**payload), rekordbox_signature):
                    continue
                payload['rekordbox_signature'] = f'{rekordbox_signature}|neural:{core_identity}'
                payload['neural_analysis']['fingerprint'] = core_identity
                track = dict_to_track(payload)
                if generate_cache_key(file_path, old_signature) == old_key:
                    return track
            except (ValueError, TypeError, KeyError, OverflowError):
                continue
    except (sqlite3.DatabaseError, OSError, TimeoutError) as error:
        logger.warning('Historische Kernanalyse nicht wiederverwendbar: %s', error)
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
    cache_key: str, file_path: str, ai_data: dict, *, expected_source_key: str | None = None
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
            if expected_source_key is not None:
                # Die LLM-Antwort gehört zur vor der Anfrage beobachteten Quelle.
                # Nach Lock-Wartezeit erneut prüfen, ohne auf eine neue Zeile
                # umzubinden oder gültige alte Daten zu verändern.
                if expected_source_key != cache_key:
                    return False
                try:
                    os.stat(file_path)
                except OSError:
                    return False
                if generate_cache_key(file_path, data.get("rekordbox_signature", "")) != expected_source_key:
                    return False
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

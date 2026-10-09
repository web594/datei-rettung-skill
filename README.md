# Rettung beschädigter Sony-Kameradateien (MP4/XAVC S und MXF/XAVC-Intra)

Rekonstruiert eine Sony-Kameradatei, bei der die Aufnahme durch Akku-Ausfall
abbrach: Dann fehlt der Index (`moov`) am Dateiende, oft ist zusätzlich der
Datei-*anfang* (ftyp/erster Metadatenblock) mit Firmware-Daten überschrieben.
Die eigentlichen Video-/Audiodaten sind aber i. d. R. vollständig da.

## Prinzip
Aus einer **gesunden Referenzdatei derselben Kamera/Einstellung** (Nachbarclip,
z. B. C0001.MP4) werden alle statischen Boxen übernommen (avcC/SPS/PPS, tkhd,
edts …). Der fehlende Index wird aus der kaputten Datei **neu berechnet**:
- Sony XAVC S verschachtelt in fester Periode: `[rtmd][Video 12 Frames][Audio]`.
- Video-Frames beginnen mit einem **AUD-NAL** (Signatur `00 00 00 02 09`), die
  dank Emulation-Prevention **nie** in echten Videodaten vorkommt.
- Chunk-Grenzen werden **proaktiv** über `pos + (Audio+rtmd)` → nächster AUD
  erkannt, *bevor* Audio je als NAL fehlgedeutet wird (wichtig: bei leisem Ton
  sehen PCM-Bytes sonst wie eine gültige NAL-Länge aus → Überlauf).

## Erfolgsfall
13,8-GB-Datei, Sony AX100, XAVC S 4K 25p (H.264 High@5.1 + PCM). Nur die ersten
~4 KB zerstört. Ergebnis: **32:25 min**, alle 4052 Chunk-Grenzen verifiziert,
A/V-Sync ±0,02 s. Genau **1** B-Frame (bei 16:24) im Original physisch
angeknackst → wird vom Decoder verdeckt, sonst fehlerfrei.

## Kamera-/Modus-spezifische Konstanten (oben in recover_xavcs.py)
Gelten für **XAVC S 4K 25p**. Für andere Modi/Kameras neu bestimmen mit
`mp4tables.py <referenz.mp4>` (liefert Frames/Chunk, Audio-/rtmd-Chunkgröße,
Movie-Timescale, ctts-Muster):
- `V0` Offset des 1. Video-Chunks (hier 12480)
- `FRAMES_PC` Frames pro Video-Chunk (12), `AUDIO_BYTES` (92160), `RTMD_BYTES` (12288)
- ctts-Muster `3000,0,0` (B-Frame-Reorder), Movie-Timescale 90000
- SRC/REF/OUT-Pfade

## Nutzung
```
py recover_xavcs.py            # Trockenlauf (schreibt nichts) – prüft alle Grenzen
py recover_xavcs.py --build    # baut OUT (kopiert die Nutzdaten, ~Dateigröße)
py recover_xavcs.py --build --limit=200   # kurze Testdatei zum Verifizieren
```
Danach prüfen: `ffmpeg -v error -i OUT -f null -` (0 = sauber; einzelne
„corrupt decoded frame"-*Warnungen* = original angeknackste Frames, unkritisch).
`-xerror` NICHT als Erfolgskriterium nehmen – es bricht schon bei solchen
Warnungen ab.

## Zweiter Fall: nicht abgeschlossene Sony-MXF (XAVC-Intra)
Bricht bei einer Sony FS7 II die Aufnahme ab, besteht die `.MXF` nur aus den
Inhaltspaketen (System-Item, Bild, 8× Ton, ANC) – Kopf, Index und Fuß fehlen.
Hier ist **kein Referenzclip nötig**: `vorlagen/mxf_abschliessen.py` geht die Pakete
ab und lässt Bild und Ton von ffmpeg ohne Neukodierung in eine abgeschlossene MXF
verpacken, Timecode inklusive.
```
py vorlagen/mxf_scan.py <defekt.MXF>                      # zählt Pakete, prüft Grenzen
py vorlagen/mxf_abschliessen.py <defekt.MXF> <ziel.mxf>   # Ziel auf anderem Laufwerk
```
Erfolgsfall: 30-GB-Clip, UHD 25p → 23.980 Bilder (15:59 min), 0 Dekodierfehler,
nur das letzte angefangene Bild fällt weg. Details und Fallstricke in `SKILL.md`.
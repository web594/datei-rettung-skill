---
name: datei-rettung
description: Beschädigte Kamera-Videodatei retten, v. a. Sony XAVC S / MP4-MOV nach Akku-Ausfall während der Aufnahme (Datei unlesbar, weil moov-Index fehlt und/oder Dateianfang überschrieben ist). Nutzen bei "Akku ist während der Aufnahme ausgefallen", "Datei beschädigt/kaputt/unlesbar", "MP4 wiederherstellen/reparieren", "Clip lässt sich nicht öffnen", "corrupt". Rekonstruiert den Index aus einem gesunden Nachbarclip derselben Kamera. Werkzeuge in vorlagen/.
---

# Beschädigte Videodatei retten (wunder-media)

Für den häufigen Fall: **Akku fällt während der Aufnahme aus.** Die Sony-Kamera
finalisiert die Datei nicht mehr → der Index (`moov`) am Dateiende fehlt, oft ist
zusätzlich der Datei­anfang (ftyp + erster Metadatenblock) mit Firmware-Daten
überschrieben. Player/Resolve sehen „unlesbar". Die eigentlichen Video-/Audio­daten
sind aber fast immer **vollständig vorhanden** — es fehlt nur die Container-Struktur.

**Kernidee:** Aus einem **gesunden Nachbarclip derselben Kamera + Einstellung**
(z. B. C0001.MP4) die statischen Boxen übernehmen (avcC/SPS/PPS, tkhd, edts …) und
den Index für die kaputte Datei **neu berechnen**. Kein fremder Download nötig; alles
mit Python (`py`-Launcher) + ffmpeg, beides vorhanden.

> Bestätigter Erfolg: Sony AX100, XAVC S 4K 25p, 13,8-GB-Clip nach Akku-Ausfall
> → repariert, 32:25 min, A/V ±0,02 s, nur 1 original-angeknackster Frame.

## Werkzeuge (in vorlagen/)
- `recover_xavcs.py` — der Rekonstruktor (Trockenlauf, Testbau, Vollbau).
- `mp4dump.py <datei>` — Box-Baum (ftyp/mdat/moov …), zeigt was fehlt.
- `mp4tables.py <ref>` — Index-Tabellen + **Chunk-Interleave** der Referenz.
- `gop_pattern.py <ref>` — ctts/stss (B-Frame-Reorder + Sync-Frames).
- `headers.py <ref>` — mvhd/tkhd/mdhd/elst-Felder (Timescales, Dauern, media_time).

## Ablauf

### 1. Lage prüfen (nichts am Original ändern!)
- Ordner listen: welche Clips sind gesund (mit `*M01.XML`/Thumbnail), welcher ist der
  Riesige ohne XML? Die **fehlende `Cxxxx M01.XML`** verrät den nicht finalisierten Clip.
- `mp4dump.py` auf gesunden Clip **und** auf den kaputten. Gesund: `ftyp/uuid/mdat/moov`.
  Kaputt: schon der Anfang ist Kauderwelsch → Header überschrieben, `moov` fehlt.
- **Datei kartieren:** die Datei an ~40 Stellen anlesen und %-Nullen messen. Erwartung:
  nur die ersten paar KB zerstört, danach durchgehend dichte Daten (~0,3 % Null =
  normales H.264). Viele Nullen/Müll mittendrin = schlechter, ggf. teils unrettbar.

### 2. Referenz vermessen (gesunder Nachbarclip)
- `mp4tables.py <ref>`: liefert Spuren (Video avc1 / Audio `twos`=PCM / Daten `rtmd`),
  **Frames pro Chunk**, Audio-/rtmd-Chunkgröße, und das **Interleave** (Reihenfolge in
  `mdat`). Sony XAVC S: `[rtmd][Video N Frames][Audio]`, feste Periode.
- `gop_pattern.py <ref>`: ctts-Muster (z. B. `3000,0,0` je 3 Frames = B-Frames) + stss
  (IDR-Abstand = GOP).
- `headers.py <ref>`: Movie-Timescale, mdhd-Timescales, elst `media_time` (B-Frame-
  Kompensation), Track-IDs.
- `ffprobe` auf die Referenz: Codec/Auflösung/fps/Profil bestätigen (muss dem Modus der
  kaputten Aufnahme entsprechen — gleiche Session, gleiche Kamera).

### 3. Konstanten in recover_xavcs.py setzen
Oben im Skript: `SRC` (kaputt), `REF` (gesund), `OUT` (Ziel neben dem Projekt),
`V0` (Offset des 1. Video-Chunks — bei XAVC S 4K 25p = 12480), `FRAMES_PC` (12),
`AUDIO_BYTES` (92160), `RTMD_BYTES` (12288), `MOVIE_TS` (90000). Diese Werte kommen
alle aus Schritt 2. Für andere Kameras/Modi (HD, 50p, andere Bitrate) neu bestimmen.

### 4. Trockenlauf → Testbau → Vollbau
```
py vorlagen/recover_xavcs.py                # Trockenlauf: prüft JEDE Chunk-Grenze
py vorlagen/recover_xavcs.py --build --limit=200   # kurze Testdatei (_test.mp4)
py vorlagen/recover_xavcs.py --build        # volle Datei (kopiert die Nutzdaten)
```
Trockenlauf muss zeigen: `boundary_ok` ≈ Anzahl Chunks, `boundary_bad=0`,
Frames/Chunk fast alle = FRAMES_PC, A/V-Diff ~0 s, „verbraucht bis Offset" ≈ Dateiende.
Erst wenn das stimmt, bauen.

### 5. Verifizieren (Pflicht)
```
ffprobe -v error -show_entries stream=... <OUT>     # Auflösung/Dauer/Frames
ffmpeg  -v error -i <OUT> -f null -                  # 0 Fehlerzeilen = sauber
ffmpeg  -v error -y -ss <sek> -i <OUT> -frames:v 1 bild.jpg   # Standbilder ansehen
```
Standbilder an Anfang/Mitte/Ende prüfen (echtes Bild, nicht schwarz). Ton per
`-af volumedetect` (sinnvolle Pegel, nicht Stille/Rauschen).

## Fallstricke (teuer erlernt)
- **`-xerror` NICHT als Erfolgskriterium!** Es bricht schon bei harmlosen „corrupt
  decoded frame"-**Warnungen** ab (einzelne original-angeknackste Frames). Maßstab ist
  `-v error` (Fehler-Ebene) = 0 Zeilen. Einzelne verdeckte Frames sind unvermeidbar
  (die Bytes auf der Karte sind physisch beschädigt) und praktisch unsichtbar.
- **Audio sieht wie Video aus:** Bei leisem Ton ergeben die PCM-Bytes zufällig eine
  plausible NAL-Länge → eine naive „NAL ungültig → Audio"-Erkennung läuft über die
  Grenze hinweg und desynchronisiert. Deshalb Grenzen **proaktiv** über die AUD-Signatur
  `00 00 00 02 09` bei `pos + AUDIO + RTMD` erkennen (die Signatur kommt wegen
  Emulation-Prevention **nie** in echten Videodaten vor). So macht es recover_xavcs.py.
- **B-Frames:** ctts-Muster aus der Referenz kacheln (sonst ruckelt/verschiebt sich die
  Wiedergabe). elst `media_time` verbatim übernehmen (A/V-Sync-Kompensation).
- **>4 GB:** Chunk-Offsets brauchen `co64` (64-Bit), nicht `stco`; `mdat` braucht einen
  64-Bit-Header. recover_xavcs.py macht das.
- **Nie schneiden/überschreiben am Original.** Ausgabe ist immer eine neue Datei.

## Grenzen
Funktioniert, solange die Nutzdaten intakt sind (nur Kopf/Index weg). Sind mitten in
der Datei große Null-/Müllbereiche (überschriebene Cluster), ist dieser Teil verloren —
dann nur das Stück bis zur ersten großen Lücke rettbar. Ein anderer Codec/Container
(AVCHD `.MTS`, XAVC-Intra, HEVC) braucht angepasste Konstanten bzw. eine andere
NAL-Logik — dann Schritt 2 gründlich neu machen.

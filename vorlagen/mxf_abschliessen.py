"""Nicht abgeschlossene Sony-XAVC-Intra-MXF (FS7 II: nur Essenz, Kopf/Index/Fuss fehlen)
in eine abspielbare Datei ueberfuehren. Das Original wird nur gelesen.

Aufruf:
  py mxf_abschliessen.py <defekt.MXF> <ausgabe.mxf|.mov> [--limit=N] [--fps=25]

Ablauf: Inhaltspakete abgehen (System-Item, Bild, 8x Ton, ANC), Ton in acht
Mono-Rohdateien neben die Ausgabe schreiben, Bild als H.264-Rohstrom daneben schreiben und von ffmpeg verpacken lassen
(-c copy, keine Neukodierung). Unvollstaendiges letztes Paket wird weggelassen.
"""
import os, shutil, subprocess, sys, time

SYS = bytes.fromhex("060e2b34020501010d01030104010100")
PIC = bytes.fromhex("060e2b34010201010d010301150105")
SND = bytes.fromhex("060e2b34010201010d010301160803")
# ffmpeg: Umgebungsvariable FFMPEG, sonst aus dem Suchpfad
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"


def klv(f, pos):
    f.seek(pos)
    h = f.read(20)
    if len(h) < 17 or h[:4] != b"\x06\x0e\x2b\x34":
        return None
    b = h[16]
    if b < 0x80:
        return h[:16], b, pos + 17
    n = b & 0x7F
    return h[:16], int.from_bytes(h[17:17 + n], "big"), pos + 17 + n


def pakete(path, limit=None):
    """Liefert je vollstaendigem Paket (bild_offset, bild_laenge, [8 ton_offsets], ton_laenge)."""
    size = os.path.getsize(path)
    out = []
    tc = None
    with open(path, "rb") as f:
        pos = 0
        while pos < size and (limit is None or len(out) < limit):
            k = klv(f, pos)
            if k is None or k[0] != SYS:
                break
            if tc is None:
                f.seek(k[2])
                tc = f.read(k[1])
            pic = None
            snd = []
            sl = 0
            ok = True
            while True:
                nxt = k[2] + k[1]
                if nxt > size:
                    ok = False
                    break
                k = klv(f, nxt)
                if k is None:
                    ok = nxt == size
                    pos = nxt
                    break
                if k[0] == SYS:
                    pos = nxt
                    break
                if k[0][:15] == PIC:
                    pic = (k[2], k[1])
                elif k[0][:15] == SND:
                    snd.append(k[2]); sl = k[1]
            if not ok or pic is None or len(snd) != 8 or pic[0] + pic[1] > size:
                break
            out.append((pic[0], pic[1], snd, sl))
            if k is None:
                break
    return out, tc


def timecode(sysitem):
    """Timecode aus dem System-Item (Benutzer-Zeitstempel, SMPTE 12M, BCD)."""
    for off in (40, 23):
        s = sysitem[off:off + 17]
        if len(s) == 17 and s[0] == 0x81:
            ff, ss, mm, hh = s[1] & 0x3F, s[2] & 0x7F, s[3] & 0x7F, s[4] & 0x3F
            bcd = lambda v: (v >> 4) * 10 + (v & 15)
            return "%02d:%02d:%02d:%02d" % (bcd(hh), bcd(mm), bcd(ss), bcd(ff))
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--"))
    src, out = args[0], args[1]
    limit = int(opts["limit"]) if "limit" in opts else None
    fps = opts.get("fps", "25")
    src_drive = os.path.splitdrive(os.path.abspath(src))[0].upper()
    if os.path.splitdrive(os.path.abspath(out))[0].upper() == src_drive:
        sys.exit("Abbruch: Ausgabe laege auf dem Quell-Laufwerk - dort wird nichts geschrieben.")

    t0 = time.time()
    cps, sysitem = pakete(src, limit)
    tc = timecode(sysitem)
    print("Pakete: %d  (%.1f s bei %s B/s)  Timecode: %s  [%.0f s]" % (len(cps), len(cps) / float(fps), fps, tc, time.time() - t0))

    tmp = [out + ".a%d.pcm" % i for i in range(8)]
    with open(src, "rb") as f:
        fa = [open(p, "wb") for p in tmp]
        for n, (_, _, snd, sl) in enumerate(cps):
            for i, o in enumerate(snd):
                f.seek(o)
                fa[i].write(f.read(sl))
        for h in fa:
            h.close()
        print("Ton geschrieben [%.0f s]" % (time.time() - t0))

        # Bild als reinen H.264-Strom neben die Ausgabe schreiben.
        roh = out + ".bild.h264"
        total = sum(c[1] for c in cps)
        done = 0
        last = time.time()
        with open(roh, "wb") as fv:
            for n, (po, pl, _, _) in enumerate(cps):
                f.seek(po)
                fv.write(f.read(pl))
                done += pl
                if time.time() - last > 10:
                    last = time.time()
                    print("Bild %5.1f %%  (%d/%d Bilder, %.0f MB/s)" % (100 * done / total, n + 1, len(cps), done / 1e6 / (time.time() - t0)), flush=True)
    print("Bild geschrieben [%.0f s] - ffmpeg verpackt das Bild ..." % (time.time() - t0), flush=True)
    # Zwei Schritte: erst nur das Bild verpacken, dann den Ton dazu. In einem Schritt
    # (Rohstrom + Ton) haelt ffmpeg das gesamte Bild im Speicher und bricht bei
    # grossen Dateien mit "Cannot allocate memory" ab (gemessen: 4,5 GB statt 40 MB).
    bild = out + ".bild.mxf"
    kopf = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    rc = subprocess.call(kopf + ["-f", "h264", "-framerate", fps, "-i", roh, "-c", "copy", bild])
    os.remove(roh)
    print("Bild verpackt (Rueckgabe %d) [%.0f s] - Ton dazu ..." % (rc, time.time() - t0), flush=True)
    if rc == 0:
        cmd = kopf + ["-i", bild]
        for p in tmp:
            cmd += ["-f", "s24le", "-ar", "48000", "-ac", "1", "-i", p]
        cmd += ["-map", "0:v"]
        for i in range(8):
            cmd += ["-map", "%d:a" % (i + 1)]
        cmd += ["-c:v", "copy", "-c:a", "pcm_s24le"]
        if tc:
            cmd += ["-timecode", tc]
        rc = subprocess.call(cmd + [out])
    tmp.append(bild)
    for q in tmp:
        os.remove(q)
    print("ffmpeg-Rueckgabe:", rc, "| Dauer %.0f s" % (time.time() - t0))
    sys.exit(rc)


if __name__ == "__main__":
    main()

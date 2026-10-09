"""Nicht abgeschlossene Sony-MXF (nur Essenz, ohne Kopf) durchmessen. Nur lesen.
Aufruf: py mxf_scan.py <datei> [start]
Zaehlt Inhaltspakete (System-Item -> Bild -> Ton -> ANC), prueft jede Grenze.
"""
import sys, os, collections

SYS = bytes.fromhex("060e2b34020501010d01030104010100")
PIC = bytes.fromhex("060e2b34010201010d010301150105")
SND = bytes.fromhex("060e2b34010201010d010301160803")
ANC = bytes.fromhex("060e2b34010201010d010301170102")
FILL = bytes.fromhex("060e2b34010101020301021001000000")

def klv(f):
    pos = f.tell()
    h = f.read(20)
    if len(h) < 17:
        return None
    key = h[:16]
    b = h[16]
    if b < 0x80:
        ln, hl = b, 17
    else:
        n = b & 0x7F
        ln, hl = int.from_bytes(h[17:17 + n], "big"), 17 + n
    return pos, key, ln, pos + hl

def scan(path, start=0):
    size = os.path.getsize(path)
    cps = []          # (offset, bildlaenge)
    sizes = collections.Counter()
    piclens = []
    bad = None
    with open(path, "rb") as f:
        pos = start
        while pos < size:
            f.seek(pos)
            k = klv(f)
            if k is None or k[1] != SYS:
                bad = (pos, k[1].hex() if k else "EOF")
                break
            cp = pos
            npic = nsnd = nanc = 0
            piclen = 0
            end_ok = True
            while True:
                nxt = k[3] + k[2]
                if nxt > size:
                    end_ok = False
                    break
                f.seek(nxt)
                k2 = klv(f)
                if k2 is None:
                    pos = nxt
                    break
                if k2[1] == SYS:
                    pos = nxt
                    break
                if k2[1][:4] != b"\x06\x0e\x2b\x34":
                    end_ok = False
                    bad = (nxt, k2[1].hex())
                    break
                if k2[1][:15] == PIC:
                    npic += 1; piclen = k2[2]
                elif k2[1][:15] == SND:
                    nsnd += 1
                elif k2[1][:15] == ANC:
                    nanc += 1
                k = k2
            if not end_ok:
                print("unvollstaendiges Paket ab", cp, "| Grund:", bad)
                break
            if (npic, nsnd, nanc) != (1, 8, 1):
                print("abweichendes Paket bei", cp, (npic, nsnd, nanc))
            cps.append(cp)
            piclens.append(piclen)
            sizes[pos - cp] += 1
            if k2 is None:
                break
    print("Dateigroesse      :", size)
    print("Inhaltspakete     :", len(cps))
    print("letztes Paket bei :", cps[-1] if cps else None)
    print("verbraucht bis    :", pos, "| Rest:", size - pos)
    print("Abbruchgrund      :", bad)
    print("Paketgroessen     :", sizes.most_common(6))
    print("Bildlaenge min/max:", min(piclens), max(piclens))
    return cps

if __name__ == "__main__":
    scan(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 0)

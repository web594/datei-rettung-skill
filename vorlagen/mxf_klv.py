"""KLV-Struktur einer MXF-Datei auflisten (nur lesen).
Aufruf: py mxf_klv.py <datei> [start] [max_klv]
"""
import sys

def ber(f):
    b = f.read(1)
    if not b:
        return None
    b = b[0]
    if b < 0x80:
        return b
    n = b & 0x7F
    return int.from_bytes(f.read(n), "big")

def walk(path, start=0, maxn=60):
    with open(path, "rb") as f:
        f.seek(start)
        n = 0
        last = None
        rep = 0
        while n < maxn:
            pos = f.tell()
            key = f.read(16)
            if len(key) < 16:
                print("EOF bei", pos)
                break
            if key[:4] != b"\x06\x0e\x2b\x34":
                print(f"{pos:>14}  KEIN KLV-Schluessel: {key.hex()}")
                break
            ln = ber(f)
            val = f.tell()
            extra = ""
            if key[4:13] == bytes.fromhex("020501010d01020101"):
                d = f.read(min(ln, 88))
                extra = (" PART kag=%d this=%d prev=%d footer=%d hdrbytes=%d idxbytes=%d idxsid=%d bodyoff=%d bodysid=%d"
                         % (int.from_bytes(d[4:8], "big"), int.from_bytes(d[8:16], "big"),
                            int.from_bytes(d[16:24], "big"), int.from_bytes(d[24:32], "big"),
                            int.from_bytes(d[32:40], "big"), int.from_bytes(d[40:48], "big"),
                            int.from_bytes(d[48:52], "big"), int.from_bytes(d[52:60], "big"),
                            int.from_bytes(d[60:64], "big")))
            print(f"{pos:>14}  {key.hex()}  len={ln:>10}{extra}")
            f.seek(val + ln)
            n += 1

if __name__ == "__main__":
    p = sys.argv[1]
    s = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    m = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    walk(p, s, m)

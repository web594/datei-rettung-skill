import sys, struct

CONT = {b'moov',b'trak',b'mdia',b'minf',b'stbl',b'dinf',b'edts',b'udta',b'mvex'}

def read_boxes(f, start, end, depth, out):
    pos = start
    while pos < end:
        f.seek(pos)
        hdr = f.read(8)
        if len(hdr) < 8:
            break
        size = struct.unpack('>I', hdr[:4])[0]
        typ = hdr[4:8]
        hsize = 8
        if size == 1:
            size = struct.unpack('>Q', f.read(8))[0]
            hsize = 16
        elif size == 0:
            size = end - pos
        out.append((depth, typ.decode('latin1','replace'), pos, size))
        if typ in CONT:
            read_boxes(f, pos+hsize, pos+size, depth+1, out)
        elif typ == b'stsd':
            # parse sample description for avcC / audio
            f.seek(pos+hsize)
            data = f.read(size-hsize)
            parse_stsd(data, depth, out)
        pos += size
        if size <= 0:
            break

def parse_stsd(data, depth, out):
    # version/flags(4) entry_count(4) then entries
    n = struct.unpack('>I', data[4:8])[0]
    p = 8
    for i in range(n):
        esize = struct.unpack('>I', data[p:p+4])[0]
        fmt = data[p+4:p+8].decode('latin1','replace')
        out.append((depth+1, 'sampleentry:'+fmt, p, esize))
        entry = data[p:p+esize]
        # look for avcC inside
        idx = entry.find(b'avcC')
        if idx >= 0:
            av = entry[idx-4:]
            parse_avcc(av, depth+2, out)
        p += esize

def parse_avcc(av, depth, out):
    # av starts at size(4) 'avcC'
    d = av[8:]
    configVersion=d[0]; profile=d[1]; compat=d[2]; level=d[3]
    nalLen = (d[4] & 0x03)+1
    numSPS = d[5] & 0x1f
    p = 6
    sps=[]
    for i in range(numSPS):
        l = struct.unpack('>H', d[p:p+2])[0]; p+=2
        sps.append(d[p:p+l]); p+=l
    numPPS = d[p]; p+=1
    pps=[]
    for i in range(numPPS):
        l = struct.unpack('>H', d[p:p+2])[0]; p+=2
        pps.append(d[p:p+l]); p+=l
    out.append((depth,'avcC profile=%d level=%d nalLenSize=%d nSPS=%d nPPS=%d'%(profile,level,nalLen,numSPS,numPPS),0,0))
    for s in sps: out.append((depth+1,'SPS len=%d hex=%s'%(len(s), s.hex()),0,0))
    for p_ in pps: out.append((depth+1,'PPS len=%d hex=%s'%(len(p_), p_.hex()),0,0))

def full_boxes(path):
    with open(path,'rb') as f:
        f.seek(0,2); end=f.tell()
        out=[]
        read_boxes(f,0,end,0,out)
        return out

def parse_table(path, typ):
    # returns raw bytes of first box of type typ
    with open(path,'rb') as f:
        f.seek(0,2); end=f.tell()
        out=[]
        read_boxes(f,0,end,0,out)
        for d,t,pos,size in out:
            if t==typ:
                f.seek(pos)
                return f.read(size)
    return None

if __name__=='__main__':
    path=sys.argv[1]
    boxes=full_boxes(path)
    for d,t,pos,size in boxes:
        print('  '*d + '%-28s off=%-14d size=%-14d'%(t,pos,size))

import struct
PATH=r'D:\CAM\PRIVATE\M4ROOT\CLIP\C0001.MP4'
CONT={b'moov',b'trak',b'mdia',b'minf',b'stbl',b'edts'}
def walk(f,s,e,path,out):
    pos=s
    while pos<e:
        f.seek(pos);h=f.read(8)
        if len(h)<8:break
        sz=struct.unpack('>I',h[:4])[0];t=h[4:8];hs=8
        if sz==1: sz=struct.unpack('>Q',f.read(8))[0];hs=16
        elif sz==0: sz=e-pos
        out.append((list(path)+[t],pos,sz,hs))
        if t in CONT: walk(f,pos+hs,pos+sz,list(path)+[t],out)
        pos+=sz
        if sz<=0:break
f=open(PATH,'rb');f.seek(0,2);END=f.tell();out=[];walk(f,0,END,[],out)
# identify trak ranges
traks=[(pos,pos+sz) for p,pos,sz,h in out if p[-1]==b'trak']
def boxin(rng,name):
    lo,hi=rng
    for p,pos,sz,h in out:
        if lo<=pos<hi and p[-1]==name:
            f.seek(pos);return f.read(sz),pos,sz,h
    return None
def u32(b,o):return struct.unpack('>I',b[o:o+4])[0]
# mvhd
for p,pos,sz,h in out:
    if p[-1]==b'mvhd':
        f.seek(pos);b=f.read(sz);ver=b[8]
        if ver==0:
            ts=u32(b,20);dur=u32(b,24)
        else:
            ts=u32(b,28);dur=struct.unpack('>Q',b[32:40])[0]
        print('mvhd ver=%d timescale=%d duration=%d nextTrackID=%d'%(ver,ts,dur,u32(b,sz-4) if ver==0 else 0))
for i,rng in enumerate(traks):
    print('--- TRAK %d range=%s'%(i,rng))
    tk=boxin(rng,b'tkhd')
    if tk:
        b=tk[0];ver=b[8]
        if ver==0:
            trackID=u32(b,20);dur=u32(b,28)
        else:
            trackID=u32(b,28);dur=struct.unpack('>Q',b[36:44])[0]
        print('   tkhd ver=%d size=%d trackID=%d duration=%d'%(ver,tk[2],trackID,dur))
    md=boxin(rng,b'mdhd')
    if md:
        b=md[0];ver=b[8]
        if ver==0: ts=u32(b,20);dur=u32(b,24)
        else: ts=u32(b,28);dur=struct.unpack('>Q',b[32:40])[0]
        print('   mdhd ver=%d timescale=%d duration=%d'%(ver,ts,dur))
    el=boxin(rng,b'elst')
    if el:
        b=el[0];n=u32(b,12);print('   elst size=%d entries=%d'%(el[2],n))
        off=16
        for j in range(n):
            sd=u32(b,off);mt=struct.unpack('>i',b[off+4:off+8])[0];rate=u32(b,off+8)
            print('       seg_dur=%d media_time=%d rate=0x%08x'%(sd,mt,rate));off+=12
    hd=boxin(rng,b'hdlr')
    if hd: print('   hdlr size=%d handler=%s'%(hd[2],hd[0][16:20].decode('latin1')))
    for bx in (b'tkhd',b'edts',b'mdhd',b'hdlr',b'vmhd',b'smhd',b'nmhd',b'dinf',b'stsd'):
        r=boxin(rng,bx)
        if r: print('     have %s size=%d'%(bx.decode(),r[2]))
f.close()

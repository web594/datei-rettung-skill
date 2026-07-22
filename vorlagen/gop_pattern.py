import sys, struct

CONT = {b'moov',b'trak',b'mdia',b'minf',b'stbl'}
def walk(f,start,end,path,out):
    pos=start
    while pos<end:
        f.seek(pos); hdr=f.read(8)
        if len(hdr)<8: break
        size=struct.unpack('>I',hdr[:4])[0]; typ=hdr[4:8]; hsize=8
        if size==1: size=struct.unpack('>Q',f.read(8))[0]; hsize=16
        elif size==0: size=end-pos
        out.append((path+[typ],pos,size,hsize))
        if typ in CONT: walk(f,pos+hsize,pos+size,path+[typ],out)
        pos+=size
        if size<=0: break

def getbox(f,path,box):
    f.seek(0,2); end=f.tell(); out=[]; walk(f,0,end,[],out)
    r=[]
    for p,pos,size,h in out:
        if p[-1]==box:
            f.seek(pos); r.append(f.read(size))
    return r

def dec_ctts(b):
    n=struct.unpack('>I',b[12:16])[0]  # after size+type+ver/flags? b starts at size
    # b: [size4][ctts4][ver1 flags3][count4][entries...]
    n=struct.unpack('>I',b[12:16])[0]
    e=[struct.unpack('>Ii',b[16+8*i:24+8*i]) for i in range(n)]  # (sample_count, offset signed)
    return e
def dec_stss(b):
    n=struct.unpack('>I',b[12:16])[0]
    return [struct.unpack('>I',b[16+4*i:20+4*i])[0] for i in range(n)]
def dec_stts(b):
    n=struct.unpack('>I',b[12:16])[0]
    return [struct.unpack('>II',b[16+8*i:24+8*i]) for i in range(n)]

path=sys.argv[1]
f=open(path,'rb')
# ctts/stss/stts are in the VIDEO trak (first). getbox returns per occurrence; video is first.
ctts=getbox(f,None,b'ctts')
stss=getbox(f,None,b'stss')
stts=getbox(f,None,b'stts')
print('=== %s ==='%path)
print('stts(video):',dec_stts(stts[0]))
c=dec_ctts(ctts[0])
print('ctts entries (sample_count, offset):')
for e in c: print('   ',e)
# expand ctts to per-sample offsets
offs=[]
for cnt,off in c:
    offs += [off]*cnt
print('per-sample composition offsets (erste 30):',offs[:30])
print('Anzahl ctts-Samples gesamt:',len(offs))
s=dec_stss(stss[0])
print('stss (sync/IDR sample numbers, 1-based):',s)
f.close()

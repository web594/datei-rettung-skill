import sys, struct

CONT = {b'moov',b'trak',b'mdia',b'minf',b'stbl',b'dinf',b'edts',b'udta',b'mvex'}

def walk(f,start,end,depth,path,out):
    pos=start
    while pos<end:
        f.seek(pos); hdr=f.read(8)
        if len(hdr)<8: break
        size=struct.unpack('>I',hdr[:4])[0]; typ=hdr[4:8]; hsize=8
        if size==1:
            size=struct.unpack('>Q',f.read(8))[0]; hsize=16
        elif size==0:
            size=end-pos
        out.append((path+[typ], pos, size, hsize))
        if typ in CONT:
            walk(f,pos+hsize,pos+size,depth+1,path+[typ],out)
        pos+=size
        if size<=0: break

def get_all(path):
    with open(path,'rb') as f:
        f.seek(0,2); end=f.tell(); out=[]
        walk(f,0,end,0,[],out)
        return out,end

def rd(f,pos,size,hsize):
    f.seek(pos+hsize); return f.read(size-hsize)

def dec_stco(b):
    n=struct.unpack('>I',b[4:8])[0]; return [struct.unpack('>I',b[8+4*i:12+4*i])[0] for i in range(n)]
def dec_stco64(b):
    n=struct.unpack('>I',b[4:8])[0]; return [struct.unpack('>Q',b[8+8*i:16+8*i])[0] for i in range(n)]
def dec_stsz(b):
    ss=struct.unpack('>I',b[4:8])[0]; n=struct.unpack('>I',b[8:12])[0]
    if ss!=0: return ss,n,[ss]*n
    return 0,n,[struct.unpack('>I',b[12+4*i:16+4*i])[0] for i in range(n)]
def dec_stsc(b):
    n=struct.unpack('>I',b[4:8])[0]
    return [struct.unpack('>III',b[8+12*i:20+12*i]) for i in range(n)]  # first_chunk, spc, sdidx
def dec_stts(b):
    n=struct.unpack('>I',b[4:8])[0]
    return [struct.unpack('>II',b[8+8*i:16+8*i]) for i in range(n)]  # count, delta

def track_info(f, trakpath_items):
    info={}
    for path,pos,size,hsize in trakpath_items:
        t=path[-1]
        if t==b'hdlr':
            d=rd(f,pos,size,hsize); info['handler']=d[8:12].decode('latin1','replace')
        elif t==b'stsd':
            d=rd(f,pos,size,hsize); info['fmt']=d[12:16].decode('latin1','replace')
        elif t==b'stco':
            info['stco']=dec_stco(rd(f,pos,size,hsize))
        elif t==b'co64':
            info['stco']=dec_stco64(rd(f,pos,size,hsize))
        elif t==b'stsz':
            info['stsz']=dec_stsz(rd(f,pos,size,hsize))
        elif t==b'stsc':
            info['stsc']=dec_stsc(rd(f,pos,size,hsize))
        elif t==b'stts':
            info['stts']=dec_stts(rd(f,pos,size,hsize))
        elif t==b'mdhd':
            d=rd(f,pos,size,hsize)
            ver=d[0]
            if ver==1:
                ts=struct.unpack('>I',d[20:24])[0]; dur=struct.unpack('>Q',d[24:32])[0]
            else:
                ts=struct.unpack('>I',d[12:16])[0]; dur=struct.unpack('>I',d[16:20])[0]
            info['timescale']=ts; info['duration']=dur
    return info

def main(path):
    boxes,end=get_all(path)
    with open(path,'rb') as f:
        # group into traks
        traks=[]
        cur=None
        # find trak ranges
        trak_ranges=[(pos,pos+size) for p,pos,size,h in boxes if p[-1]==b'trak']
        for (ts,te) in trak_ranges:
            items=[(p,pos,size,h) for p,pos,size,h in boxes if ts<=pos<te]
            traks.append(track_info(f,items))
        for i,tr in enumerate(traks):
            print('--- TRAK %d handler=%s fmt=%s timescale=%s dur=%s'%(i,tr.get('handler'),tr.get('fmt'),tr.get('timescale'),tr.get('duration')))
            ss,n,sizes=tr.get('stsz',(0,0,[]))
            print('   samples=%d  sample_size(fixed)=%d'%(n,ss))
            print('   stts=%s'%tr.get('stts'))
            print('   stsc=%s'%tr.get('stsc'))
            print('   #chunks=%d stco[:6]=%s'%(len(tr.get('stco',[])),tr.get('stco',[])[:6]))
            if sizes:
                print('   stsz[:8]=%s ... total=%d'%(sizes[:8],sum(sizes)))
        # Build interleave map: list of (chunk_offset, track_idx, chunk_index)
        allchunks=[]
        for i,tr in enumerate(traks):
            for ci,off in enumerate(tr.get('stco',[])):
                allchunks.append((off,i,ci))
        allchunks.sort()
        print('\n=== INTERLEAVE (erste 30 Chunks, nach Offset) ===')
        for off,i,ci in allchunks[:30]:
            print('   off=%-12d trak=%d chunk#%d'%(off,i,ci))
        # compute per-chunk byte size for track0 by using next chunk offset or samples
        print('\n=== Chunk-Groessen (aus stsc+stsz) Track0 (Video) ===')
        tr=traks[0]
        stsc=tr.get('stsc'); ss,n,sizes=tr.get('stsz'); stco=tr.get('stco')
        # expand stsc -> samples per chunk
        spc=[]
        for j in range(len(stsc)):
            fc=stsc[j][0]; s=stsc[j][1]
            nextfc = stsc[j+1][0] if j+1<len(stsc) else len(stco)+1
            for c in range(fc,nextfc):
                spc.append(s)
        # samples per chunk list length == num chunks
        idx=0
        for ci in range(min(len(stco),8)):
            cnt=spc[ci] if ci<len(spc) else spc[-1]
            csz=sum(sizes[idx:idx+cnt])
            print('   chunk#%d off=%d samples=%d bytes=%d'%(ci,stco[ci],cnt,csz))
            idx+=cnt

if __name__=='__main__':
    main(sys.argv[1])

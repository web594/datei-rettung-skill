import sys, struct, os, time

SRC   = r'D:\CAM\PRIVATE\M4ROOT\CLIP\C0002.MP4'
REF   = r'D:\CAM\PRIVATE\M4ROOT\CLIP\C0001.MP4'
OUT   = r'D:\CAM\C0002_repariert.mp4'

V0        = 12480          # Start des ersten Video-Chunks (wie in beiden Referenzen)
FRAMES_PC = 12             # Video-Frames pro Chunk
AUDIO_BYTES = 92160        # 23040 samples * 4 bytes
RTMD_BYTES  = 12288        # 12 samples * 1024 bytes
MOVIE_TS  = 90000
MAXNAL    = 5_000_000

# ---------------- Referenz-Boxen einlesen ----------------
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

def load_ref():
    f=open(REF,'rb');f.seek(0,2);END=f.tell();out=[];walk(f,0,END,[],out)
    traks=[(pos,pos+sz) for p,pos,sz,h in out if p[-1]==b'trak']
    def raw(rng,name):
        lo,hi=rng
        for p,pos,sz,h in out:
            if lo<=pos<hi and p[-1]==name:
                f.seek(pos);return f.read(sz)
        return None
    def rawtop(name):
        for p,pos,sz,h in out:
            if p[-1]==name:
                f.seek(pos);return f.read(sz)
        return None
    R={}
    R['ftyp']=rawtop(b'ftyp')
    R['mvhd']=rawtop(b'mvhd')
    # video trak = traks[0], audio = traks[1]
    for label,rng in (('v',traks[0]),('a',traks[1])):
        R[label]={
            'tkhd':raw(rng,b'tkhd'),
            'mdhd':raw(rng,b'mdhd'),
            'hdlr':raw(rng,b'hdlr'),
            'dinf':raw(rng,b'dinf'),
            'stsd':raw(rng,b'stsd'),
            'vmhd':raw(rng,b'vmhd'),
            'smhd':raw(rng,b'smhd'),
        }
    f.close()
    return R

# ---------------- C0002 durchlaufen ----------------
VALID={1,5,6,9}          # beobachtete NAL-Typen: slice, IDR, SEI, AUD
GAP=AUDIO_BYTES+RTMD_BYTES  # 104448 = Audio + rtmd zwischen zwei Video-Chunks
AUD_SIG=b'\x00\x00\x00\x02\x09'

class Reader:
    def __init__(self,f,END,win=64*1024*1024):
        self.f=f; self.END=END; self.win=win; self.base=-1; self.buf=b''
    def _ensure(self,pos):
        if self.base>=0 and self.base<=pos and pos+5<=self.base+len(self.buf): return
        self.f.seek(pos); self.buf=self.f.read(self.win); self.base=pos
    def read5(self,pos):
        self._ensure(pos)
        o=pos-self.base; b=self.buf[o:o+5]
        if len(b)<5: return None,None
        return int.from_bytes(b[:4],'big'), b[4]&0x1f
    def is_aud(self,pos):
        if pos+5>self.END: return False
        self._ensure(pos)
        o=pos-self.base
        return self.buf[o:o+5]==AUD_SIG

def dry_walk():
    f=open(SRC,'rb'); f.seek(0,2); END=f.tell()
    r=Reader(f,END)
    pos=V0
    vframe_sizes=[]; vframe_idr=[]
    vchunk_off=[]; vchunk_cnt=[]
    achunk_off=[]; achunk_cnt=[]
    boundary_ok=0; boundary_bad=0; ending=''
    cur_chunk_start=pos; cur_chunk_frames=0
    cur_frame_start=None; cur_frame_idr=False
    def close_frame(end):
        nonlocal cur_frame_start,cur_frame_idr,cur_chunk_frames
        if cur_frame_start is not None and end>cur_frame_start:
            vframe_sizes.append(end-cur_frame_start); vframe_idr.append(cur_frame_idr)
            cur_chunk_frames+=1
        cur_frame_start=None; cur_frame_idr=False
    def do_boundary(audio_start):
        # schliesst aktuellen Chunk ab, registriert Audio, springt ueber GAP
        nonlocal pos,cur_chunk_start,cur_chunk_frames,boundary_ok
        close_frame(audio_start)
        vchunk_off.append(cur_chunk_start); vchunk_cnt.append(cur_chunk_frames)
        achunk_off.append(audio_start); achunk_cnt.append(23040)
        boundary_ok+=1
        pos=audio_start+GAP
        cur_chunk_start=pos; cur_chunk_frames=0
    while pos+5<=END:
        # Proaktive Chunk-Grenze: ab dem 12. Frame pruefen, ob nach Audio+rtmd
        # (GAP) wieder ein AUD folgt. Faengt die Grenze EXAKT ab, bevor Audio
        # jemals als NAL fehlgedeutet werden kann.
        if cur_chunk_frames>=FRAMES_PC-1 and pos+GAP<=END and r.is_aud(pos+GAP):
            do_boundary(pos); continue
        L,t=r.read5(pos)
        if L is None: break
        valid = (t in VALID) and (0<L<=MAXNAL) and (pos+4+L<=END)
        if valid:
            if t==9:  # AUD -> neuer Frame
                close_frame(pos)
                cur_frame_start=pos; cur_frame_idr=False
            if t==5: cur_frame_idr=True
            pos+=4+L
        else:
            # ungueltige NAL -> Audio-Grenze (Fallback, auch fuer unregelmaessige Chunks)
            if pos+GAP<=END and r.is_aud(pos+GAP):
                do_boundary(pos); continue
            # sonst: Datei-Ende / letzte (Teil-)Gruppe
            close_frame(pos)
            if cur_chunk_frames>0:
                vchunk_off.append(cur_chunk_start); vchunk_cnt.append(cur_chunk_frames)
            audio_start=pos; rem=END-audio_start
            if rem>=4:
                achunk_off.append(audio_start); achunk_cnt.append(min(rem,AUDIO_BYTES)//4)
            ending='Ende bei Offset %d (rem=%d, kein AUD nach GAP)'%(audio_start,rem)
            cur_frame_start=None
            pos=END; break
    # evtl. offener letzter Frame/Chunk (Aufnahme mitten im Video abgebrochen)
    if cur_frame_start is not None:
        close_frame(min(pos,END))
        if cur_chunk_frames>0 and (not vchunk_off or vchunk_off[-1]!=cur_chunk_start):
            vchunk_off.append(cur_chunk_start); vchunk_cnt.append(cur_chunk_frames)
        if not ending: ending='Ende: Aufnahme mitten im Video-Chunk abgebrochen'
    if not ending: ending='sauber bis Dateiende'
    # Chunk-Frame-Statistik
    from collections import Counter
    cnts=Counter(vchunk_cnt)
    f.close()
    return dict(END=END,vframe_sizes=vframe_sizes,vframe_idr=vframe_idr,
               vchunk_off=vchunk_off,vchunk_cnt=vchunk_cnt,
               achunk_off=achunk_off,achunk_cnt=achunk_cnt,
               groups=len(achunk_off),ending=ending,boundary_ok=boundary_ok,boundary_bad=boundary_bad,
               chunk_frame_hist=dict(cnts),last_pos=pos)

# ---------------- Box-Bau ----------------
def box(typ,payload): return struct.pack('>I',8+len(payload))+typ+payload
def fbox(typ,ver,flags,payload): return box(typ,bytes([ver])+flags.to_bytes(3,'big')+payload)
def make_stts(entries):
    p=struct.pack('>I',len(entries))
    for c,d in entries:p+=struct.pack('>II',c,d)
    return fbox(b'stts',0,0,p)
def make_ctts(entries):
    p=struct.pack('>I',len(entries))
    for c,o in entries:p+=struct.pack('>Ii',c,o)
    return fbox(b'ctts',0,0,p)
def make_stsz(ss,count,sizes=None):
    if ss!=0: return fbox(b'stsz',0,0,struct.pack('>II',ss,count))
    p=struct.pack('>II',0,count)
    for s in sizes:p+=struct.pack('>I',s)
    return fbox(b'stsz',0,0,p)
def make_stsc(entries):
    p=struct.pack('>I',len(entries))
    for a,b_,c in entries:p+=struct.pack('>III',a,b_,c)
    return fbox(b'stsc',0,0,p)
def make_co64(offs):
    p=struct.pack('>I',len(offs))
    for o in offs:p+=struct.pack('>Q',o)
    return fbox(b'co64',0,0,p)
def make_stss(nums):
    p=struct.pack('>I',len(nums))
    for n in nums:p+=struct.pack('>I',n)
    return fbox(b'stss',0,0,p)
def make_elst(seg_dur,media_time,rate=0x00010000):
    return box(b'edts',fbox(b'elst',0,0,struct.pack('>I',1)+struct.pack('>iii',seg_dur,media_time,rate)))

def patch_dur(raw, off, val):
    return raw[:off]+struct.pack('>I',val)+raw[off+4:]

def stsc_from_counts(counts):
    e=[]
    for idx,c in enumerate(counts):
        if not e or e[-1][1]!=c: e.append((idx+1,c,1))
    return e

def build(R, W, base_guess=0):
    N=len(W['vframe_sizes'])
    A=sum(W['achunk_cnt'])
    v_mdhd_dur=N*1000
    a_mdhd_dur=A
    v_trk_dur=N*3600
    a_trk_dur=round(A*MOVIE_TS/48000)
    mov_dur=max(v_trk_dur,a_trk_dur)
    # ctts
    offs=[3000 if i%3==0 else 0 for i in range(N)]
    ce=[];i=0
    while i<N:
        j=i
        while j<N and offs[j]==offs[i]: j+=1
        ce.append((j-i,offs[i]));i=j
    # stss
    stss_nums=[i+1 for i,idr in enumerate(W['vframe_idr']) if idr]
    # offsets (mit base)
    v_co=[base_guess+(o-V0) for o in W['vchunk_off']]
    a_co=[base_guess+(o-V0) for o in W['achunk_off']]
    # --- video stbl ---
    vstbl=box(b'stbl',
        R['v']['stsd']+
        make_stts([(N,1000)])+
        make_ctts(ce)+
        make_stsc(stsc_from_counts(W['vchunk_cnt']))+
        make_stsz(0,N,W['vframe_sizes'])+
        make_co64(v_co)+
        make_stss(stss_nums))
    vminf=box(b'minf',R['v']['vmhd']+R['v']['dinf']+vstbl)
    vmdia=box(b'mdia',patch_dur(R['v']['mdhd'],24,v_mdhd_dur)+R['v']['hdlr']+vminf)
    vtkhd=patch_dur(R['v']['tkhd'],28,v_trk_dur)
    vtrak=box(b'trak',vtkhd+make_elst(v_trk_dur,1000)+vmdia)
    # --- audio stbl ---
    astbl=box(b'stbl',
        R['a']['stsd']+
        make_stts([(A,1)])+
        make_stsc(stsc_from_counts(W['achunk_cnt']))+
        make_stsz(4,A)+
        make_co64(a_co))
    aminf=box(b'minf',R['a']['smhd']+R['a']['dinf']+astbl)
    amdia=box(b'mdia',patch_dur(R['a']['mdhd'],24,a_mdhd_dur)+R['a']['hdlr']+aminf)
    atkhd=patch_dur(R['a']['tkhd'],28,a_trk_dur)
    atrak=box(b'trak',atkhd+make_elst(a_trk_dur,0)+amdia)
    mvhd=patch_dur(R['mvhd'],24,mov_dur)
    moov=box(b'moov',mvhd+vtrak+atrak)
    return moov, dict(N=N,A=A,mov_dur=mov_dur,v_trk_dur=v_trk_dur,a_trk_dur=a_trk_dur,stss=len(stss_nums))

def truncate_W(W,L):
    L=min(L,len(W['vchunk_off']))
    nframes=sum(W['vchunk_cnt'][:L])
    W2=dict(W)
    W2['vchunk_off']=W['vchunk_off'][:L]; W2['vchunk_cnt']=W['vchunk_cnt'][:L]
    W2['vframe_sizes']=W['vframe_sizes'][:nframes]; W2['vframe_idr']=W['vframe_idr'][:nframes]
    W2['achunk_off']=W['achunk_off'][:L]; W2['achunk_cnt']=W['achunk_cnt'][:L]
    return W2

def main():
    dobuild='--build' in sys.argv
    limit=None; outpath=OUT
    for a in sys.argv:
        if a.startswith('--limit='):
            limit=int(a.split('=')[1]); outpath=OUT.replace('.mp4','_test.mp4')
    t0=time.time()
    print('== Trockenlauf: C0002.MP4 durchlaufen ==')
    W=dry_walk()
    N=len(W['vframe_sizes']); A=sum(W['achunk_cnt'])
    consumed=W['last_pos']-V0
    print('  Dateigroesse         : {:,}'.format(W['END']))
    print('  Video-Frames         : {:,}  ({:.1f}s @25p = {:d}:{:02d})'.format(N,N/25.0,int(N/25//60),int(N/25%60)))
    print('  Video-Chunks         : {:,}'.format(len(W['vchunk_off'])))
    print('  Audio-Chunks         : {:,}  (samples={:,} = {:.1f}s)'.format(len(W['achunk_off']),A,A/48000.0))
    print('  IDR/Sync-Frames      : {:,}'.format(sum(1 for x in W["vframe_idr"] if x)))
    print('  Gruppen (validiert)  : {:,}  boundary_ok={:,} boundary_bad={:,}'.format(W['groups'],W['boundary_ok'],W['boundary_bad']))
    print('  Frames/Chunk-Verteil.: {}'.format(W['chunk_frame_hist']))
    print('  verbraucht bis Offset: {:,} von {:,}  (Rest {:,} Bytes)'.format(W['last_pos'],W['END'],W['END']-W['last_pos']))
    print('  Ende-Status          : '+W['ending'])
    print('  Zeit Trockenlauf     : %.1fs'%(time.time()-t0))
    # A/V-Laenge Konsistenz
    print('  A/V-Check            : Video {:.2f}s  Audio {:.2f}s  Diff {:.3f}s'.format(N/25.0,A/48000.0,N/25.0-A/48000.0))
    if not dobuild:
        print('\n(Kein --build: es wurde NICHTS geschrieben.)')
        return
    if limit:
        W=truncate_W(W,limit)
        print('\n== TESTBAU: nur erste %d Chunks -> %s =='%(len(W['vchunk_off']),outpath))
    else:
        print('\n== Baue moov + schreibe Ausgabedatei ==')
    R=load_ref()
    moov0,_=build(R,W,0)
    ftyp=R['ftyp']
    base=len(ftyp)+len(moov0)+16   # +16 = mdat 64bit header
    moov,info=build(R,W,base)
    assert len(moov)==len(moov0),'moov Groesse instabil!'
    if limit:
        payload_len=(W['achunk_off'][-1]+W['achunk_cnt'][-1]*4)-V0
    else:
        payload_len=W['END']-V0
    mdat_size=16+payload_len
    print('  ftyp={} moov={} base(mdat payload)={} payload={:,}'.format(len(ftyp),len(moov),base,payload_len))
    print('  N={:,} A={:,} movie_dur={} (={:.1f}s) stss={}'.format(info['N'],info['A'],info['mov_dur'],info['mov_dur']/MOVIE_TS,info['stss']))
    with open(outpath,'wb') as o:
        o.write(ftyp); o.write(moov)
        o.write(struct.pack('>I',1)+b'mdat'+struct.pack('>Q',mdat_size))
        # payload kopieren
        with open(SRC,'rb') as s:
            s.seek(V0)
            left=payload_len; buf=32*1024*1024; done=0; tlast=time.time()
            while left>0:
                chunk=s.read(min(buf,left))
                if not chunk: break
                o.write(chunk); left-=len(chunk); done+=len(chunk)
                if time.time()-tlast>3:
                    print('    ... %.1f%% (%.2f GB)'%(100*done/payload_len,done/1e9)); tlast=time.time()
    print('  FERTIG: %s  (%.2f GB)'%(outpath,os.path.getsize(outpath)/1e9))
    print('  Gesamtzeit: %.1fs'%(time.time()-t0))

if __name__=='__main__':
    main()

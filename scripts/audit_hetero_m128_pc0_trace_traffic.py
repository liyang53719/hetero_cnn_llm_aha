"""Actual address-qualified AXI envelope from one pinned original PC0 continuation."""
from collections import Counter,deque
from pathlib import Path
import hashlib,json,re,sys

ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'round_20261120T0933/host/campaign'
RUN=ROOT/'round_20261120T1033/host/campaign'
SRC='round_20261119T1933/launch_pc2/FIVE_LAUNCH_MAP.json'
REF='round_20261119T2033/observe/PC0_MAP.json'
SAVE_HASHES=('eeb3597f13078d3adbfda6d7efc9e9ebe3ebee0089822c6c06054a84bae8fe4d','f268e5b2a2c8f746c81b688e6ba382b88a6964822317bebf79e369a7f3043b48','f56765ec5029b2f60f4f77fb11ca53acceebd00adb356020e7fc921d5171670b','da582c47378b37d556844d7c7bf802e6c19107f47849fe913e634a7fb62f67e2','db6862be120aa690626cd6e5d000007769982d08bdb46fc1a43fcf276edcefc7')
RX=re.compile(r'TRACE_CONSUMED profile=(\d+) tick=(\d+) (AR|R|AW|W|B) (.*)')
KEYS={'AR':{'addr','id','len'},'R':{'id','last'},'AW':{'addr','id','len'},'W':{'strb','last'},'B':{'id','initialized_bytes'}}
def need(v,m):
    if not v: raise ValueError(m)
def sha(d): return hashlib.sha256(d).hexdigest()
def read(p,h):
    b=p.read_bytes();need(sha(b)==h,'pin drift '+p.name);return b
def region(a,segments):
    k=[n for n,start,count in segments if start<=a and a+64<=start+count]
    need(len(k)==1,'must resolve exactly one original address range')
    return k[0]
def parse(prof,logs,segments,out,row):
    last=-1;rd=deque();aw=deque();w=deque();bq=deque();events=[]
    read_types=Counter();retired=[];latency=Counter();addresses=Counter()
    for line in logs:
        if not line.startswith('TRACE_CONSUMED '): continue
        m=RX.fullmatch(line);need(m is not None,'bad trace row')
        p,t,k,vs=m.groups();t=int(t);q={a:int(b,0) for a,b in (x.split('=',1) for x in vs.split())}
        need(int(p)==prof and t&1 and t>=last and set(q)==KEYS[k],'bad profile, tick or fields')
        tick=t//2;last=t
        kind=address=None
        if k=='AR':
            need(q['len']==0 and q['addr']%64==0,'only aligned one-beat PC0 trace')
            address=q['addr'];kind=region(address,segments);rd.append((q['id'],tick,kind,address));addresses[(kind,address)]+=1
        elif k=='R':
            need(bool(rd),'R without AR');i,c,kind,address=rd.popleft()
            need(i==q['id'] and q['last']==1 and c<=tick,'invalid R')
            read_types[kind]+=1;latency[tick-c]+=1
        elif k=='AW':
            need(q['len']==0 and q['addr']%64==0 and out<=q['addr']<out+128*row,'only PC0 output AW')
            aw.append((q['id'],q['addr']))
        elif k=='W':
            need(q['last']==1 and q['strb']==2**64-1,'only full output beat allowed');w.append(tick)
        elif k=='B':
            need(bool(bq),'B without AW/W');i,a=bq.popleft()
            need(i==q['id'] and q['initialized_bytes']==64*(len(retired)+1) and a==out+64*len(retired),'output is not ordered coverage')
            retired.append((tick,a))
        while aw and w:
            w.popleft();bq.append(aw.popleft())
        events.append((tick,k,kind,address))
    perf=[]
    for base in range(len(retired)//(row//64)):
        n=row//64
        t1=retired[(base+1)*n-1][0]
        t0=retired[base*n-1][0] if base else -1
        ee=[(t,k,d,a) for t,k,d,a in events if t0<t<=t1]
        unique={t for t,_,_,_ in ee}
        kinds=Counter(d for _,k,d,_ in ee if k=='R')
        rr=max(t for t,k,_,_ in ee if k=='R')
        wa=min(t for t,k,_,_ in ee if k=='AW')
        by_type={x:Counter(a for _,k,d,a in ee if k=='R' and d==x) for x in kinds}
        distinct={x:64*len(v) for x,v in by_type.items()}
        if prof and row in (2048,4096):
            x_start=next(a for name,a,_ in segments if name=='input')+base*row
            g_start=next(a for name,a,_ in segments if name=='input_gamma')
            need(by_type['input']=={a:2 for a in range(x_start,x_start+row,64)} and
                 by_type['input_gamma']=={a:1 for a in range(g_start,g_start+row,64)},
                 'BF16 row x was not exactly read twice or gamma was not reread')
        if not prof and row==6144:
            x_start=next(a for name,a,_ in segments if name=='x')+base*row
            g_start=next(a for name,a,_ in segments if name=='gamma0')
            need(by_type['x']=={a:1 for a in range(x_start,x_start+row,64)} and
                 by_type['gamma0']=={a:1 for a in range(g_start,g_start+row,64)},
                 'FP32 row x/gamma reads differed from trace envelope')
        perf.append(dict(row=base,last_B_cycle=t1+1,cycle_delta=(t1-t0) if base else None,
          observed_read_B={k:64*v for k,v in sorted(kinds.items())}, observed_distinct_read_B=distinct,
          observed_write_B=row,bus_handshake_cycles=len(unique),
          complete_window_without_observed_axi_handshake=(t1-t0-len(unique)) if base else None,
          last_R_to_first_AW_cycle_gap=wa-rr if rr<=wa else None,post_last_read_may_have_prior_tile_writes=rr>wa))
    return dict(profile=prof,rows_completed_in_output_only=len(perf),writes_B=len(retired)*64,
        full_pc0=False,rows=perf,retired_reads_B={k:64*v for k,v in sorted(read_types.items())},
        planned_row_payload_B=row,range_unique_issued_beats=dict(Counter(k for k,_ in addresses)),
        ar_to_r_elapsed_cycle_histogram=dict(sorted(latency.items())),
        pending=dict(ar=len(rd),aw=len(aw),w=len(w),b=len(bq)))

def full():
    pins=json.loads(read(ROOT/SRC,'0f5200a55824a430bd88c15ac5e571d045667613125c6376c2ba2485aebfbce7'))
    refs=json.loads(read(ROOT/REF,'6cdbff3007b7857e68712293f74ed7a42bcaaf842980a761ae3eca95e679f3c0'))
    terminal=json.loads(read(RUN/'RESULT.json','9a2d5e82fe96bb4c21e68fa9a46e781cdd8d091ea52f322767c4d0f7045c4caa'))
    predecessor=json.loads(read(OLD/'RESULT.json','3cf0dff991b873f54429f11af6bda25ec33e5cd4cfa3dc4a5966209291ad04fd'))
    need(terminal['all_terminal'] and pins['matrix_macs']==4096,'not original completed qualification')
    results=[]
    for i in range(5):
        pp=pins['profiles'][i];rp=refs[i];rows=terminal['profiles'][str(i)]
        past=predecessor['completed'][str(i)]
        od=OLD/f'profile_{i}'
        # Old save and resume have single lifetime trace; no +8 is appended (overlap).
        logs=read(od/'save/stdout.log',SAVE_HASHES[i]).decode().splitlines()
        logs+=read(od/'resume_first_b/stdout.log',past['first_B_terminal']['stdout_sha256']).decode().splitlines()
        logs+=read(RUN/f'profile_{i}/run/stdout.log',rows['stdout_sha256']).decode().splitlines()
        # uDMA reads a 64B beat aligned down even for 16B SCM records. The
        # readonly command/descriptor region is used as the address qualifier.
        seg=[(x['name'],x['address'],((x['bytes']+63)//64)*64)
             for x in pp['segments']]
        r=parse(i,logs,seg,rp['base'],rp['bytes']//128)
        need(r['writes_B']==int(rows['commits'][-1]['bytes']),'retired write accounting mismatch')
        results.append(r)
    print(json.dumps(dict(scope='ACTUAL_ORIGINAL_CHISEL_ARC_PC0_TRACE_IDEAL_MEMORY_ONLY',
       note='Counters are external handshake and byte timings, not internal utilization or target DDR. No whole block or RTL claim.',
       profiles=results),indent=2,sort_keys=True))

if __name__=='__main__':full()

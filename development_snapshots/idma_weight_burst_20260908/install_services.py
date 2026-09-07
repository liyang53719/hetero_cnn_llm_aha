#!/usr/bin/env python3
"""Developer-only deterministic publication bridge for two tested service files.

This runs in CI, never in the local execution-agent handoff. It changes no RTL.
Both input and output Git blobs are frozen, and files are prepared in memory
before any write. A replay after publication is read-only and idempotent.
"""
from pathlib import Path
import hashlib, sys
root=Path(sys.argv[1]).resolve()
base=root/'chisel/continuous_prefill'
expected={
    'tests/host_block_commands.cpp':('37ca93ebed27623477441a37aa7b0c43b2a9ba3a','82411ae486a7da59097bfb1c8b0e674727bf4f7b'),
    'scripts/verify_host_block_gate.py':('791ef2c969407f253775651f457a7dbe55a44f2d','1e285ea46f3935334c1f306f663d87309b3286eb')
}
def blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
raw={n:(base/n).read_bytes() for n in expected}
if all(blob(raw[n])==v[1] for n,v in expected.items()):
    print('ALREADY_PUBLISHED_EXACT_SERVICE_FILES');raise SystemExit(0)
if not all(blob(raw[n])==v[0] for n,v in expected.items()):raise SystemExit('REFUSE_CHANGED_INPUTS')
prepared={}
p=base/'tests/host_block_commands.cpp'
s=p.read_text()
s=s.replace('#ifndef OWNER_MATRIX_MACS','#ifndef OWNER_WEIGHT_READ_BEATS\n#define OWNER_WEIGHT_READ_BEATS 1\n#endif\n#ifndef OWNER_MATRIX_MACS',1)
s=s.replace('unsigned delay=0;std::array<uint32_t,16>', 'unsigned delay=0,remaining=1,total=1;std::array<uint32_t,16>')
s=s.replace('uint32_t rng=20260907;', 'uint64_t readBursts=0,burstAtStart=0,deviceBurstAtStart=0,deviceReadsAtStart=0,cacheHitsAtStart=0;\n uint32_t rng=20260907;')
s=s.replace('||mode=="descriptor-read-error"){', '||mode=="descriptor-read-error"||mode=="weight-mid-error"||mode=="weight-last-error"){')
s=s.replace('return a.address==b.address&&a.id==b.id&&a.mask==b.mask&&a.data==b.data;', 'return a.address==b.address&&a.id==b.id&&a.mask==b.mask&&a.data==b.data&&a.total==b.total;')
s=s.replace('d.io_axi_r_bits_last=1;', 'd.io_axi_r_bits_last=pending.remaining==1;')
s=s.replace('check(d.io_axi_ar_bits_len==0&&d.io_axi_ar_bits_size==6&&d.io_axi_ar_bits_burst==1,"bad AR");', '''c.total=c.remaining=d.io_axi_ar_bits_len+1;
     check(c.total<=OWNER_WEIGHT_READ_BEATS&&d.io_axi_ar_bits_size==6&&d.io_axi_ar_bits_burst==1&&((c.address&4095)+64*c.total)<=4096,"bad AR");
     if(c.total>1){bool allowed=false;for(const auto&t:ALLOCATIONS){std::string n=t.name;const auto k=n.substr(n.size()-std::min(size_t(2),n.size()));
       bool matrix=k=="wq"||k=="wk"||k=="wv"||k=="wo"||k=="wg"||k=="wu"||k=="wd";
       if(matrix&&t.readonly&&c.address>=t.address&&c.address+64*c.total<=t.address+4*t.words)allowed=true;}
       check(allowed,"burst escaped readonly matrix weight tensor");}
     ''')
s=s.replace('next=c;reads++;readBeats[d.io_pc]++;if(next.address<META_LIMIT)metadata++;', 'next=c;readBursts++;reads+=c.total;readBeats[d.io_pc]+=c.total;if(next.address<META_LIMIT){check(c.total==1,"metadata burst forbidden");metadata++;}')
start=s.index('     if(!injected&&d.io_pc==faultTargetPc){')
end=s.index('\n   }\n   if(d.io_completion_valid)',start)
block=s[start:end]
block=block.replace('(mode=="last-write-error"&&next.write&&next.address==last);', '''(mode=="last-write-error"&&next.write&&next.address==last)||
         (mode=="weight-mid-error"&&!next.write&&next.total>1&&next.total-next.remaining==next.total/2)||
         (mode=="weight-last-error"&&!next.write&&next.total>1&&next.remaining==1);''')
s=s[:start]+'     maybeFault(next);'+s[end:]
anchor=' void step(){'
s=s.replace(anchor,' void maybeFault(Beat& next){\n'+block+'\n }\n'+anchor,1)
s=s.replace('}else ackReads++;pending={};}', '''}else ackReads++;
     if(!pending.write&&pending.remaining>1){
       pending.address+=64;pending.remaining--;pending.error=false;pending.delay=1+random()%5;
       checkRead(pending.address);for(unsigned i=0;i<16;i++)pending.data[i]=mem[pos(pending.address)+i];maybeFault(pending);
     }else pending={};}''')
s=s.replace('   dmaAtStart=d.io_idmaTransfers;', '''   burstAtStart=readBursts;
#if OWNER_WEIGHT_READ_BEATS > 1
   deviceBurstAtStart=d.io_idmaReadBursts;deviceReadsAtStart=d.io_idmaReadBeats;cacheHitsAtStart=d.io_idmaCacheHits;
#endif
   dmaAtStart=d.io_idmaTransfers;''')
s=s.replace('check(reads==ackReads&&writes==ackWrites&&reads+writes==d.io_idmaTransfers-dmaAtStart,"all memory crossed iDMA");', '''check(reads==ackReads&&writes==ackWrites,"read/write beat ACK balance");
     check(readBursts-burstAtStart+writes==d.io_idmaTransfers-dmaAtStart,"every burst/store crossed iDMA");
     uint64_t cacheHits=0;
#if OWNER_WEIGHT_READ_BEATS > 1
     check(d.io_idmaReadBursts-deviceBurstAtStart==readBursts-burstAtStart&&d.io_idmaReadBeats-deviceReadsAtStart==reads,"hardware/AXI read accounting");
     cacheHits=d.io_idmaCacheHits-cacheHitsAtStart;
     check(cacheHits==reads-(readBursts-burstAtStart),"unused or fabricated prefetched beat");
#endif''')
s=s.replace('<<" request_stalls="<<stalls', '<<" read_bursts="<<(readBursts-burstAtStart)<<" weight_read_burst_beats="<<OWNER_WEIGHT_READ_BEATS<<" weight_cache_hits="<<cacheHits<<" request_stalls="<<stalls')
prepared[str(p.relative_to(base))]=s.encode()
p=p.parents[1]/'scripts/verify_host_block_gate.py';s=p.read_text()
s=s.replace("    require(int(end['read_bytes'])//64+int(end['write_ack_bytes'])//64==int(end['idma_transfers']),'iDMA conservation')",'''    burst_beats=scope.get('weight_read_burst_beats',1)
    require(type(burst_beats) is int and burst_beats in (1,16),'unsupported read burst profile')
    read_beats=int(end['read_bytes'])//64;write_beats=int(end['write_ack_bytes'])//64
    require(int(end['read_bytes'])%64==0 and int(end['write_ack_bytes'])%64==0,'nonintegral AXI beat count')
    if burst_beats==1:
        require(read_beats+write_beats==int(end['idma_transfers']),'iDMA conservation')
    else:
        bursts=int(end['read_bursts']);hits=int(end['weight_cache_hits'])
        require(int(end['weight_read_burst_beats'])==16 and bursts>0 and bursts<=read_beats<=16*bursts,'read burst capacity')
        require(bursts+write_beats==int(end['idma_transfers']),'real iDMA burst/store conservation')
        require(hits==read_beats-bursts and hits>0,'prefetch beat consumption conservation')
        require(scope.get('weight_read_cache_bytes')==1024,'bounded mailbox footprint')''')
prepared[str(p.relative_to(base))]=s.encode()
for name,value in expected.items():
    if blob(prepared[name])!=value[1]:raise SystemExit('REFUSE_UNVERIFIED_TRANSFORM:'+name)
for name,data in prepared.items():
    (base/name).write_bytes(data)
    if blob((base/name).read_bytes())!=expected[name][1]:raise SystemExit('WRITE_MISMATCH')
print('PUBLISHED_EXACT_SERVICE_FILES')

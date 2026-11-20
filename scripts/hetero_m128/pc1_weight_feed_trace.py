"""Causal per-channel read accounting only; original M128 PC1 log before cut.

Input is decoder's TRACE_CONSUMED text (not offers), and immutable profile
metadata. Every counted byte must have a prior accepted address and accepted R
beat. A stopped trace can leave open transactions; it cannot claim a PASS.
"""
import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path
import re

MANIFESTS = (
    ("round_20261119T1133/stimuli/Qwen2/manifest.json",
     "109072c5710e59c7855d778c22fbf697e6983f9ac1e6b4f686c22e0eda3adf22"),
    ("round_20261119T1133/stimuli/L0/manifest.json",
     "dd7af762b380f4c40d0faef8a82006167fa60374035fa3ff64e918813ec78d1e"),
    ("round_20261119T1133/stimuli/L3/manifest.json",
     "88c90a81c372eeb2ea23236c04cdc21d41f7e4291b82cd0032ffcfedeeac3a7b"),
    ("round_20261119T1233/big/stimuli/L0/manifest.json",
     "cfb844a82658e41dd7c6b3f81da3708a67da02b708c523ac199f920ac1764e7e"),
    ("round_20261119T1233/big/stimuli/L3/manifest.json",
     "c2a9bdc1df689dcb33e9ddacb15bc9de738e27867ba5e486d76adcdfd9945bed"),
)

AXI = re.compile(r"TRACE_CONSUMED profile=(\d+) tick=(\d+) (AR|R) (.*)")
CMP = re.compile(r"TRACE_COMPLETION_FIRE profile=(\d+) tick=(\d+) count=(\d+)(?: |$)")
# Actual Host trace includes more fields. Recognized AXI payload fields only.
FIELD = re.compile(r"(\w+)=([^ ]+)")
CHANNEL_BEAT_B = 64

def need(p, what):
    if not p:
        raise ValueError(what)

def source_ranges(root, profile):
    path, sha = MANIFESTS[profile]
    raw = (Path(root)/path).read_bytes()
    need(hashlib.sha256(raw).hexdigest()==sha,"ABI manifest hash mismatch")
    m=json.loads(raw)
    need(m["tokens"]==128 and m["schedule"][1]["pc"]==1,"not original M128 PC1")
    op=m["schedule"][1]
    def span(key):
        item=m["tensors"][op[key]]
        return (item["address"],item["address"]+item.get("bytes",item.get("words",0)*4))
    a,b,d=span("a"),span("b"),span("d" if "d" in op else "dst")
    spans={"input_activation":a,"weight":b,"output":d}
    for l,(lo,hi) in spans.items():
        need(lo < hi and (lo | hi)%CHANNEL_BEAT_B == 0,f"unaligned {l}")
    for x,y in [(a,b),(a,d),(b,d)]:
        need(x[1]<=y[0] or y[1]<=x[0],"PC1 tensor ranges overlap")
    return spans

def audit(lines,profile,tick_limit,spans):
    need(0<=profile<5 and tick_limit>=0, "bad profile or cut")
    starts={}
    typed0=typed1=None
    ar=Counter(); reads=Counter()
    seen=defaultdict(set)
    pending=defaultdict(deque)
    last=None
    for line in lines:
        line=line.rstrip("\n")
        q=CMP.fullmatch(line) or CMP.match(line)
        if q:
            p,t,count=map(int,q.groups())
            if p!=profile or t>tick_limit:
                continue
            if count==1:
                need(typed0 is None,"duplicate PC0 trace retirement")
                typed0=t
            elif count==2:
                need(typed0 is not None and typed1 is None and t>typed0,"orphan or duplicate PC1 retirement")
                typed1=t
            continue
        a=AXI.fullmatch(line)
        if not a:
            continue
        p,t,kind,tail=a.groups()
        if int(p)!=profile:
            continue
        t=int(t)
        if t>tick_limit:
            continue
        need(last is None or t>=last,"AXI trace out of order")
        last=t
        f=dict(FIELD.findall(tail))
        if typed0 is None or typed1 is not None:
            # R crossing the scope is detected if an orphan enters the PC1
            # interval. No bytes from old outstanding reads can be credited.
            continue
        need(t>typed0,"read is concurrent with PC0 retirement")
        num=int(f["id"],0)
        if kind=="AR":
            addr=int(f["addr"],0)
            count=1+int(f["len"],0)
            need(addr%64==0 and 1<=count<=256,"invalid AR burst")
            stop=addr+count*64
            labels=[l for l,(lo,hi) in spans.items() if lo<=addr<stop<=hi]
            # Never silently split a crossing burst across labels.
            need(bool(labels) or all(stop<=lo or addr>=hi for lo,hi in spans.values()),"AR crosses a PC1 tensor boundary")
            name=labels[0] if labels else "metadata_or_other"
            ar[name]+=1
            pending[num].append([name,addr,count,t])
            starts.setdefault(name+".first_ar_tick",t)
        else:
            need(bool(pending[num]),"orphan R inside PC1 scope")
            item=pending[num][0]
            name,addr,count,ar_t=item
            need(t>ar_t and int(f["last"],0)==(count==1),"R.last or causality mismatch")
            starts.setdefault(name+".first_r_tick",t)
            reads[name]+=1
            seen[name].add(addr)
            if count==1:
                pending[num].popleft()
            else:
                item[1:3]=[addr+64,count-1]
    stats={n:dict(ar=ar[n],accepted_R=reads[n],accepted_read_bytes=64*reads[n],
                  unique_read_bytes=64*len(seen[n]),reissued_read_bytes=64*(reads[n]-len(seen[n])))
           for n in (*spans,"metadata_or_other")}
    return dict(profile=profile,cut_tick=tick_limit,typed_PC0_tick=typed0,typed_PC1_tick=typed1,
                proof="accepted read-transaction accounting only; not Matrix or numerical proof",
                open_AR_count=sum(map(len,pending.values())),
                timeline=starts,outstanding_R_beats=sum(q[2] for queues in pending.values() for q in queues),
                traffic=stats,full_block_utilization=None)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True)
    p.add_argument("--profile",required=True,type=int,choices=range(5))
    p.add_argument("--log",required=True,type=Path)
    p.add_argument("--end-tick",required=True,type=int)
    a=p.parse_args()
    with a.log.open() as f:
        print(json.dumps(audit(f,a.profile,a.end_tick,source_ranges(a.root,a.profile)),indent=2,sort_keys=True))

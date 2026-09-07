#!/usr/bin/env python3
"""Relocate individual tensor allocations, not just the arena base (test-only).

Uses the existing public descriptor records. Writes a NEW fixture directory and
leaves the input untouched. The same unmodified compiled DUT must use the new
addresses; this exposes hardwired producer/consumer offsets.
"""
from pathlib import Path
import argparse,hashlib,json,re,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
from heteronpu.descriptor_chain import DescriptorRecord

def swap(source:Path,target:Path):
    if target.exists():raise ValueError('new target required')
    m=json.loads((source/'manifest.json').read_text());header=(source/'owner_fixture.h').read_text()
    for a,b in [('wq','wo'),('qraw','qr'),('att','o')]:
        x,y=m['tensors'][a],m['tensors'][b]
        if x['words']!=y['words'] or x['readonly']!=y['readonly']:raise ValueError('incompatible allocation swap')
        x['address'],y['address']=y['address'],x['address']
    raw=bytearray((source/'host_descriptors.bin').read_bytes())
    for op in m['schedule']:
        for name,root in zip([op['a'],op['b'],op['dst']],op['roots']):
            if name is None:continue
            r=DescriptorRecord.unpack(int.from_bytes(raw[16*root:16*root+16],'little'))
            address=m['tensors'][name]['address']
            p=(r.payload & ~(((1<<48)-1)|(255<<64)))|(address&((1<<48)-1))|((address>>48)<<64)
            raw[16*root:16*root+16]=DescriptorRecord(r.record_type,r.subtype,r.flags,r.next_index,p).pack().to_bytes(16,'little')
    for name,t in m['tensors'].items():
        header,n=re.subn(r'(\bA_'+re.escape(name.upper())+r'=)\d+ULL',lambda match:match[1]+str(t['address'])+'ULL',header)
        if n!=1:raise ValueError('missing header constant '+name)
        header=re.sub(r'(\{"'+re.escape(name)+r'",)\d+ULL',lambda match:match[1]+str(t['address'])+'ULL',header)
    target.mkdir(parents=True)
    (target/'host_commands.bin').write_bytes((source/'host_commands.bin').read_bytes())
    (target/'host_descriptors.bin').write_bytes(raw);(target/'owner_fixture.h').write_text(header)
    m['individual_allocation_swaps']=[['wq','wo'],['qraw','qr'],['att','o']]
    m['table_sha256']={n:hashlib.sha256((target/n).read_bytes()).hexdigest() for n in ['host_commands.bin','host_descriptors.bin']}
    (target/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('target',type=Path);a=p.parse_args();swap(a.source,a.target)

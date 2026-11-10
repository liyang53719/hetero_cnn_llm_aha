"""Portable minimal scalar witnesses; NOT a hardware execution/first-cycle test."""
from pathlib import Path
import json
from exact import value,rounded

def reject(flags,finite=True,gradual=False):
    return not finite or bool(flags & (0x1c if gradual else 0x1e))

def main():
    results=[]
    for c in json.loads(Path(__file__).with_name('cases.json').read_text()):
        a,b=(int(c[k],16) for k in ('a','b'))
        u,f=rounded(value(a)*value(b),bool((a^b)>>31))
        if (u,f)!=(int(c['result'],16),c['flags']):raise ValueError(('mismatch',c,u,f))
        if not reject(f):raise ValueError('LegacyRaw must reject underflow')
        if reject(f,gradual=True):raise ValueError('explicit gradual policy distinction lost')
        results.append(dict(head=c['head'],result=f'{u:08x}',flags=f,legacy_vector_error=True))
    # Exact subnormal is not tiny-inexact: no UF/NX, valid under LegacyRaw.
    u,f=rounded(value(0x00800000)*value(0x3f000000))
    if (u,f)!=(0x00400000,0) or reject(f):raise ValueError('exact subnormal')
    # Original Conv tap MulIeeeRne has a distinct authorized policy.
    u,f=rounded(value(0x04650000)*value(0x02200000))
    if (u,f)!=(0,3) or reject(f,gradual=True) or not reject(f):raise ValueError('tap policy')
    for f in (4,8,16):
        if not reject(f,gradual=True):raise ValueError('severe flags cannot be relaxed')
    print(json.dumps(dict(status='PASS_MINIMAL_REFERENCE_WITNESSES',cases=results,
         hardware_executed=False,full_block_pass=False,first_hardware_cycle_proven=False),indent=2))
if __name__=='__main__':main()

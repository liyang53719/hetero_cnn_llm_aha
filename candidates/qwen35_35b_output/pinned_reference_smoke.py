"""Explicit retained-producer smoke; excluded from download-free cold suites."""
from . import o_reference as r

def main():
    for m in (16,128):
        raw,_,_,evidence=r.actual_gated_norm_input(r.ROOT/f'work/gated_norm_actual_m{m}',
            r.ACTUAL_INPUT_PINS[m]['summary_sha256'],m)
        r.require(len(raw)==m*4096*2 and r.sha(raw)==r.ACTUAL_INPUT_PINS[m]['input_sha256'],
            'original actual producer pin')
        r.require(evidence['source_before']==evidence['source_after'],'producer source freeze')
    print('PASS two retained actual producer identities; no projection arithmetic')
if __name__=='__main__':main()

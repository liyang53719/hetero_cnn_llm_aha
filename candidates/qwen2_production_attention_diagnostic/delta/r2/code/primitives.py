"""Unmodified existing strict lane primitives and field comparator; no owner loop."""
import ast
from fractions import Fraction
from functools import lru_cache
import hashlib
from pathlib import Path
import struct
def need(value, detail):
    if not value: raise ValueError(detail)

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while block:=f.read(1<<20): h.update(block)
    return h.hexdigest()

def load_exact(path):
    """Only existing primitive ASTs; no reference execution before DUT terminal."""
    names={'exact','rn','ref_add','ref_mul','ref_bf'}
    tree=ast.parse(Path(path).read_text());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    need({n.name for n in nodes}==names,'exact helper definitions')
    ns={'Fraction':Fraction,'struct':struct,'lru_cache':lru_cache}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),ns)
    return ns

def lanes(work, exact):
    finite=lambda a:a&0x7f800000!=0x7f800000
    def op(kind,a,b):
        if not finite(a) or not finite(b):return work.LaneResult(0,16)
        mathematical=exact['exact'](a)+exact['exact'](b) if kind=='add' else exact['exact'](a)*exact['exact'](b)
        word=exact['ref_'+kind](a,b);flags=0
        if not finite(word):flags=5
        elif exact['exact'](word)!=mathematical:
            flags=1
            if not word&0x7f800000:flags|=2
        return work.LaneResult(word,flags)
    return work.StrictLaneOps(add=lambda a,b:op('add',a,b),mul=lambda a,b:op('mul',a,b),bf=exact['ref_bf'],finite=finite)

def compare_fields(actual,reference):
    names={'dot_parts','unrounded_dot_sum','dot_bf16','scores_bf16','softmax_exp','softmax_fp32','prob_bf16','normalizer','pv_raw','pv_bf16'}
    need(set(actual)==set(reference)==names,'exact ten captured fields required')
    for name in sorted(names):
        a,b=actual[name],reference[name]
        need(a['shape']==b['shape'],'field shape mismatch '+name)
        need(bytes(a['observed'])==bytes(b['observed']),'field presence mismatch '+name)
        need(tuple(a['words'])==tuple(b['words']),'bit-exact intermediate mismatch '+name)
    # Each collector validates its own actual event frequency contract. Reference
    # normalizer may be observed per PV key/column; never copy those frequencies.
    return True

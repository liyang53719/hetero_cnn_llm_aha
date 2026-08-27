import math, random
from heteronpu.hierarchical_attention import *

def test_q1024_merge_count_contract():
    assert causal_merge_count(1024,12,128)==43008
    assert causal_merge_count(128,12,128)==0

def test_blockwise_matches_single_summary_with_fp32_tolerance():
    rng=random.Random(19)
    for n in (1,127,128,129,384,1024):
        scores=[rng.uniform(-8,8) for _ in range(n)]
        values=[[rng.uniform(-1,1) for _ in range(4)] for _ in range(n)]
        a=normalized(summarize(scores,values));b=normalized(blockwise(scores,values,128))
        assert max(abs(x-y) for x,y in zip(a,b)) < 2e-4

def test_merge_identity_and_width_guard():
    x=Summary(1.0,1.0,(2.0,3.0))
    assert merge(Summary.empty(2),x)==x
    try: merge(x,Summary.empty(3))
    except ValueError: pass
    else: raise AssertionError('width mismatch accepted')

"""Selected-cell arithmetic projection for one existing 16x256 Matrix tile.

This candidate is not an accepted legacy MatrixService profile. Packed packets
need a future reviewed controller/profile. Only the output-dependency cells are
numerically evaluated here; every enabled physical cell is counted as issued
work. No extra arithmetic unit, operand bank or per-query row-freeze is assumed.
"""
from collections import Counter
from dataclasses import dataclass

ROWS=16
COLUMNS=256
CONTEXTS=5
METADATA_SLOTS=8
RESULT_TILES=2
SCALE=0x3db504f3


def need(ok):
    if not ok:raise ValueError('attention batch domain')


def word(x):return type(x) is int and 0<=x<1<<32

def selected_finite(x):
    if (x & 0x7f800000)==0x7f800000:raise ValueError('nonfinite selected Matrix lane')

def row(value,n):
    need(type(value) in (tuple,list) and len(value)==n and all(word(x) for x in value))
    for x in value:selected_finite(x)
    return tuple(value)


@dataclass(frozen=True)
class Result:
    scores:tuple=()
    output:tuple=()
    trace:tuple=()
    counts:tuple=()


class Arithmetic:
    def __init__(self,op,fma):
        need(callable(op) and callable(fma));self.op=op;self.fma=fma;self.counts=Counter()
    def scalar(self,name,a,b=0):
        self.counts['scalar_'+name]+=1
        value=self.op(name,a,b);need(word(value));return value
    def mac(self,a,b,c):
        self.counts['selected_cell_fmas']+=1
        value=self.fma(a,b,c);need(word(value));return value


def qk(q_words,key_rows,*,op,fma):
    """Up to16 keys for ONE query/head, original8-step stripes and16-add fold."""
    q=row(q_words,128)
    need(type(key_rows) in (tuple,list) and 1<=len(key_rows)<=16)
    keys=tuple(row(k,128) for k in key_rows);a=Arithmetic(op,fma)
    cells=[0]*(ROWS*COLUMNS);trace=[]
    for step in range(8):
        depth=step*16
        left=tuple(a.scalar('bf',q[depth+r]) for r in range(16))
        right=[0]*256
        for k,key in enumerate(keys):
            for r in range(16):right[16*k+r]=a.scalar('bf',key[depth+r])
        for k in range(len(keys)):
            for r in range(16):
                address=r*256+16*k+r
                cells[address]=a.mac(left[r],right[16*k+r],cells[address])
                selected_finite(cells[address])
        trace.append((step,step==0,step==7,step==7,0xff))
    scores=[]
    for k in range(len(keys)):
        total=0
        for r in range(16):total=a.scalar('add',total,cells[r*256+16*k+r])
        dot=a.scalar('bf',total)
        score=a.scalar('bf',a.scalar('mul',dot,SCALE));selected_finite(score)
        scores.append(score)
    a.counts.update(matrix_steps=8,matrix_groups=1,emitted_tiles=1,enabled_slices=8,
        issued_cell_fmas=8*16*256,accumulator_cells=4096)
    return Result(scores=tuple(scores),trace=tuple(trace),counts=tuple(sorted(a.counts.items())))


def pv(probability_rows,inverses,value_rows,*,op,fma):
    """Six GQA heads for ONE query/KV head; no future-key padding or row freeze."""
    need(type(value_rows) in (tuple,list) and 1<=len(value_rows)<=128)
    n=len(value_rows);values=tuple(row(v,128) for v in value_rows)
    need(type(probability_rows) in (tuple,list) and len(probability_rows)==6)
    probabilities=tuple(row(p,n) for p in probability_rows);inverses=row(inverses,6)
    a=Arithmetic(op,fma);cells=[0]*(ROWS*COLUMNS);trace=[]
    for key,v in enumerate(values):
        left=tuple(a.scalar('bf',a.scalar('mul',probabilities[h][key],inverses[h])) for h in range(6))
        right=tuple(a.scalar('bf',x) for x in v)
        for h in range(6):
            for col in range(128):
                address=h*256+col
                cells[address]=a.mac(left[h],right[col],cells[address])
                selected_finite(cells[address])
        trace.append((key,key==0,key==n-1,key==n-1,0x0f))
    output=tuple(tuple(a.scalar('bf',cells[h*256+col]) for col in range(128)) for h in range(6))
    for h in output:
        for x in h:selected_finite(x)
    a.counts.update(matrix_steps=n,matrix_groups=1,emitted_tiles=1,enabled_slices=4,
        issued_cell_fmas=n*16*128,accumulator_cells=4096)
    return Result(output=output,trace=tuple(trace),counts=tuple(sorted(a.counts.items())))


def schedule_counts(tokens):
    need(type(tokens) is int and 1<=tokens<=128)
    pairs=12*tokens*(tokens+1)//2
    qk_groups=12*sum((n+15)//16 for n in range(1,tokens+1))
    qk_steps=8*qk_groups;pv_groups=2*tokens;pv_steps=tokens*(tokens+1)
    return dict(tokens=tokens,causal_head_key_pairs=pairs,
        legacy_qk_steps=8*pairs,legacy_pv_steps=8*pairs,
        packed_qk_steps=qk_steps,packed_pv_steps=pv_steps,
        packed_steps=qk_steps+pv_steps,physical_slice_issues=qk_steps*8+pv_steps*4,
        legacy_physical_slice_issues=16*pairs,qk_groups=qk_groups,pv_groups=pv_groups,
        emitted_tiles=qk_groups+pv_groups,qk_fold_adds=16*pairs,
        qk_issued_fmas=qk_steps*4096,pv_issued_fmas=pv_steps*2048,
        useful_qk_fmas=128*pairs,useful_pv_fmas=128*pairs,
        contexts_available=CONTEXTS,contexts_used=1,metadata_slots_available=METADATA_SLOTS,
        metadata_slots_used=1,result_tiles_available=RESULT_TILES,result_tiles_used=1,
        extra_mac_units=0,extra_payload_banks=0)


def serial_lower_bound(tokens,*,dense_issue_cycles,fold_latency=3,fold_ii=3):
    """Optimistic schedule bound only. Unmodeled exp/div/feed/DDR/stalls add time."""
    need(type(dense_issue_cycles) is int and dense_issue_cycles>=0)
    need(type(fold_latency) is int and fold_latency>=1 and type(fold_ii) is int and fold_ii>=1)
    c=schedule_counts(tokens)
    # Each chain is ordered; a dependent add cannot use II to bypass latency.
    fold_cycles=c['qk_fold_adds']*max(fold_latency,fold_ii)
    cycles=dense_issue_cycles+c['packed_steps']+fold_cycles
    return dict(matrix_issue_cycles=dense_issue_cycles+c['packed_steps'],ordered_fold_cycles=fold_cycles,
        serial_minimum_cycles=cycles,actual_hardware_cycles=None,
        existing_scalar_minimum_spacing=3,current_owner_fold_spacing=5,
        hypothetical_unrealizable_ii1=max(fold_latency,fold_ii)<3,
        includes_exp_div=False,includes_feed_stalls=False,includes_ddr=False,
        measured_utilization=None,accepts_80_percent=False,accepts_90_percent=False)

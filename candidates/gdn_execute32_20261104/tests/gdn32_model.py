#!/usr/bin/env python3
"""Independent bounded GDN32 schedule/numeric model. NOT a DUT/Chisel simulator."""
from collections import namedtuple
from dataclasses import dataclass
import random

SHAPES = (
    ('gates',64,16), ('q',64,128), ('k',64,128), ('v',64,128),
    ('kb',64,128), ('vb',64,128), ('kbg',64,128), ('qg',64,128),
    ('ke',64,128), ('kt',128,64), ('ket',128,64), ('pair',64,64),
    ('ut',64,64), ('intra',64,64), ('solvek',64,128), ('solvev',64,128),
    ('pred',64,128), ('vnew',64,128), ('inter',64,128), ('local',64,128),
    ('out',64,128), ('state_update',128,128), ('decay_state',128,128),
    ('next_state',128,128))
OFFSETS = {}
CHUNK_BYTES = 0
for _name, _r, _c in SHAPES:
    OFFSETS[_name] = CHUNK_BYTES
    CHUNK_BYTES += _r * _c * 4
STATE_BYTES = 65536
ADDRESS_LIMIT = 1 << 56

Phase = namedtuple('Phase', 'a b dst rows cols k')
PHASES = dict(zip(range(5,18), map(lambda x: Phase(*x), (
    ('kb','kt','ut',64,64,128), ('q','kt','intra',64,64,128),
    ('ut','vb','solvev',64,128,64), ('ut','kbg','solvek',64,128,64),
    ('solvek','next_state','pred',64,128,128),
    ('solvev','pred','vnew',64,128,0),
    ('qg','next_state','inter',64,128,128),
    ('intra','vnew','local',64,128,64), ('inter','local','out',64,128,0),
    ('ket','vnew','state_update',128,128,64),
    ('next_state','gates','decay_state',128,128,0),
    ('decay_state','state_update','next_state',128,128,0),
    ('out','out','out',64,128,0)))))
DOT = frozenset((5,6,9,11,12,14))
SOLVE = frozenset((7,8))
FACTOR = frozenset((5,6))
Event = namedtuple('Event', 'kind role row col k half address')
Counts = namedtuple('Counts', 'reads vectors writes')

@dataclass(frozen=True)
class Plan:
    tokens: int = 128
    value_heads: int = 32
    head: int = 0
    chunk: int = 0
    key_heads: int = 16
    layout_id: int = 0
    layout_version: int = 1
    row_bytes: int = 51200
    scratch: int = 0x10000000
    output: int = 0x20000000

    def __post_init__(self):
        if self.tokens not in (16,128):
            raise ValueError('M16/M128 only')
        if (self.key_heads != 16 or self.value_heads not in (16,32) or
            self.layout_id != 0 or self.layout_version != 1 or
            self.row_bytes != self.value_heads * 1600):
            raise ValueError('inadmissible retained layout')
        if not (0 <= self.head < self.value_heads and 0 <= self.chunk < self.chunks):
            raise ValueError('head/chunk outside layout')
        for base, size in ((self.scratch, self.stride*self.value_heads),
                           (self.output, self.tokens*self.value_heads*256)):
            if base < 0 or base % 64 or base+size > ADDRESS_LIMIT:
                raise ValueError('unaligned or overflowing complete span')
        if max(self.scratch,self.output) < min(self.scratch+self.stride*self.value_heads,
                                              self.output+self.tokens*self.value_heads*256):
            raise ValueError('output/scratch alias')

    @property
    def chunks(self): return 2 if self.tokens == 128 else 1
    @property
    def stride(self): return STATE_BYTES + self.chunks * CHUNK_BYTES
    @property
    def head_base(self): return self.scratch + self.head * self.stride
    @property
    def chunk_base(self): return self.head_base + STATE_BYTES + self.chunk * CHUNK_BYTES
    @property
    def previous(self):
        return self.head_base if self.chunk == 0 else self.chunk_base-CHUNK_BYTES+OFFSETS['next_state']
    def base(self, name): return self.chunk_base + OFFSETS[name]
    def output_address(self,row,col):
        return self.output + (((self.chunk*64+row)*self.value_heads+self.head)*128+col)*2


def schedule(phase, plan, width=32, rows=None, groups=None):
    """Stream only requests. Each request must receive an ACK/result before next.

    rows/groups select bounded witnesses; defaults cover the complete leaf job.
    a coefficients remain 16 FP32 per 64B beat even for width=32.
    """
    if width not in (16,32) or phase not in PHASES:
        raise ValueError('unsupported phase/lane width')
    p = PHASES[phase]
    active_rows = 16 if phase == 17 and plan.tokens == 16 else p.rows
    selected_rows = range(active_rows) if rows is None else rows
    out_width = 32 if phase == 17 else width
    selected_groups = range(p.cols//out_width) if groups is None else groups
    abase = plan.previous if phase == 15 else plan.base(p.a)
    bbase = plan.previous if phase in (9,11) else plan.base(p.b)
    dst = plan.base(p.dst)
    for row in selected_rows:
        if not 0 <= row < active_rows: raise ValueError('row')
        for group in selected_groups:
            col = group*out_width
            if not 0 <= col < p.cols: raise ValueError('group')
            def ev(kind,role,k=-1,half=-1,address=-1):
                return Event(kind,role,row,col,k,half,address)
            if phase in DOT or phase in SOLVE:
                limit = row if phase in SOLVE else p.k
                acols = 64 if phase in SOLVE else p.k
                for k in range(limit):
                    if k % 16 == 0:
                        yield ev('R','a',k,0,abase+(row*acols+(k//16)*16)*4)
                    for half in range(width//16):
                        source = dst if phase in SOLVE else bbase
                        yield ev('R','prior' if phase in SOLVE else 'b',k,half,
                                 source+(k*p.cols+col+half*16)*4)
                    yield ev('V','multiply',k)
                    yield ev('V','accumulate',k)
                if phase in FACTOR:
                    for half in range(width//16):
                        yield ev('R','factor',half=half,
                                 address=plan.base('pair')+(row*64+col+half*16)*4)
                    yield ev('V','factor_multiply')
                elif phase in SOLVE:
                    for half in range(width//16):
                        yield ev('R','rhs',half=half,
                                 address=bbase+(row*p.cols+col+half*16)*4)
                    yield ev('V','subtract')
            elif phase == 17:
                for half in range(2):
                    yield ev('R','format_input',half=half,
                             address=abase+(row*128+col+half*16)*4)
                for half in range(32//width):
                    yield ev('V','format',half=half)
                yield ev('W','output',half=0,address=plan.output_address(row,col))
                continue
            else:
                for half in range(width//16):
                    yield ev('R','a',half=half,address=abase+(row*p.cols+col+half*16)*4)
                if phase != 15:
                    for half in range(width//16):
                        yield ev('R','b',half=half,address=bbase+(row*p.cols+col+half*16)*4)
                yield ev('V','decay' if phase == 15 else 'subtract' if phase == 10 else 'add')
            for half in range(width//16):
                yield ev('W','scratch',half=half,address=dst+(row*p.cols+col+half*16)*4)


def expected_counts(phase, tokens=128, width=32):
    p = PHASES[phase]
    r = 16 if phase == 17 and tokens == 16 else p.rows
    h, g = width//16, p.cols//width
    if phase in DOT:
        f = int(phase in FACTOR)
        return Counts(r*g*(h*p.k+(p.k+15)//16+h*f), r*g*(2*p.k+f), r*p.cols//16)
    if phase in SOLVE:
        return Counts(g*sum(h*i+(i+15)//16+h for i in range(r)),
                      g*sum(2*i+1 for i in range(r)), r*p.cols//16)
    if phase == 17: return Counts(r*8, r*4*(32//width), r*4)
    return Counts(r*p.cols//16*(1 if phase == 15 else 2),r*g,r*p.cols//16)


class ProtocolError(ValueError): pass

def audit_pairing(events, phase):
    """Small independent checker for 32lane input pairing/64B write order.

    It checks actual request witnesses, not the candidate source or a DUT trace.
    """
    collected=[]; write_half=0; previous_write=None
    for e in events:
        if e.kind == 'R':
            if e.role == 'a' and phase in DOT | SOLVE:
                continue  # Coefficients intentionally stay one 16-word beat.
            collected.append(e)
        elif e.kind == 'V':
            if e.role == 'accumulate':
                required=[]
            elif e.role == 'multiply':
                required=['prior']*2 if phase in SOLVE else ['b']*2
            elif e.role == 'factor_multiply': required=['factor']*2
            elif e.role == 'format': required=['format_input']*2
            elif phase in SOLVE: required=['rhs']*2
            elif phase == 15: required=['a']*2
            else: required=['a']*2+['b']*2
            if [x.role for x in collected] != required:
                raise ProtocolError('vector issued without complete intended pairs')
            for i in range(0,len(collected),2):
                lo,hi=collected[i:i+2]
                if ((lo.half,hi.half)!=(0,1) or hi.address!=lo.address+64 or
                    (lo.row,lo.col,lo.k)!=(hi.row,hi.col,hi.k)):
                    raise ProtocolError('reordered, aliased, or noncontiguous halves')
            collected=[]
        elif e.kind == 'W':
            if collected: raise ProtocolError('unconsumed inputs at write')
            if phase == 17:
                if e.half != 0: raise ProtocolError('output writes one packed beat')
            else:
                if e.half != write_half: raise ProtocolError('write half order')
                if write_half and (e.address != previous_write.address+64 or
                    (e.row,e.col)!=(previous_write.row,previous_write.col)):
                    raise ProtocolError('write halves not from same group')
                previous_write=e; write_half^=1
    if collected or write_half: raise ProtocolError('incomplete final group')


class SerialEngine:
    """Abstract ready/valid/result gate, NOT RTL or an implementation oracle.

    Includes held requests, one outstanding memory and vector, exact identities,
    and ACK-before-next semantics. A failed identity is quarantined, not drained.
    """
    def __init__(self, events):
        self.events=iter(events); self.pending=next(self.events,None)
        self.outstanding=None; self.seq=0; self.trace=[]; self.failed=False
    def issue(self, ready=True):
        if self.failed or self.outstanding is not None or self.pending is None or not ready:
            return None
        e=self.pending
        identity=('mem',self.seq) if e.kind != 'V' else ('vec',e.role,e.role=='format')
        self.outstanding=(e,identity)
        self.trace.append(e)
        return identity
    def respond(self, identity, error=False):
        if self.failed or self.outstanding is None:
            self.failed=True; raise ProtocolError('unsolicited/duplicate response')
        e, want=self.outstanding
        if identity != want:
            self.failed=True; raise ProtocolError('identity mismatch; outstanding retained')
        self.outstanding=None
        if error:
            self.failed=True; raise ProtocolError('backend error')
        if e.kind != 'V': self.seq+=1
        self.pending=next(self.events,None)
    @property
    def complete(self): return not self.failed and self.pending is None and self.outstanding is None


def run_backpressure(events, seed):
    engine=SerialEngine(events); rng=random.Random(seed); cycles=0; stalls=0
    while not engine.complete:
        cycles+=1
        if cycles > 200000: raise AssertionError('bounded liveness witness timed out')
        if engine.outstanding is None:
            held=engine.pending
            ready=rng.randrange(4) == 0
            identity=engine.issue(ready)
            if not ready:
                stalls+=1
                if engine.pending != held or engine.outstanding is not None:
                    raise AssertionError('request changed while not ready')
            if identity is not None:
                if engine.issue(True) is not None:
                    raise AssertionError('second request accepted while outstanding')
        elif rng.randrange(4) == 0:
            engine.respond(engine.outstanding[1])
    return engine.trace, cycles, stalls


# Exact integer IEEE-754 binary32 round-to-nearest-even for finite operands.
# Gradual subnormals are computed; no claim is made about the bank's flag policy.
def finite(bits): return (bits & 0x7f800000) != 0x7f800000

def unpack(bits):
    if not finite(bits): raise ValueError('finite operands required')
    exponent=(bits >> 23) & 255; mantissa=bits & 0x7fffff
    return bits >> 31, (mantissa | 0x800000) if exponent else mantissa, exponent-150 if exponent else -149

def round_shift(n, shift):
    if shift <= 0: return n << -shift
    q,r=divmod(n,1 << shift); half=1 << (shift-1)
    return q + (r > half or (r == half and q & 1))

def pack_exact(sign, magnitude, exponent):
    if magnitude == 0: return sign << 31
    top=magnitude.bit_length()-1+exponent
    quantum=max(top-23,-149)
    q=round_shift(magnitude,quantum-exponent)
    if not q: return sign << 31
    top=q.bit_length()-1+quantum
    if top > 127: return (sign << 31) | 0x7f800000
    if top < -126: return (sign << 31) | (q << (quantum+149))
    significand=q >> max(0,q.bit_length()-24)
    significand <<= max(0,24-q.bit_length())
    return (sign << 31) | ((top+127) << 23) | (significand & 0x7fffff)

def fp_mul(a,b):
    sa,ma,ea=unpack(a); sb,mb,eb=unpack(b)
    return pack_exact(sa^sb,ma*mb,ea+eb)

def fp_add(a,b):
    sa,ma,ea=unpack(a); sb,mb,eb=unpack(b)
    e=min(ea,eb)
    n=((-ma if sa else ma) << (ea-e))+((-mb if sb else mb) << (eb-e))
    return pack_exact(int(n<0) if n else int(ma==0 and mb==0 and sa==sb==1),abs(n),e)

def bf16_rne(a):
    if not finite(a): raise ValueError('finite FP32 input required')
    return ((a+0x7fff+((a >> 16)&1)) >> 16) & 0xffff

def format_beat(low,high):
    if len(low) != 16 or len(high) != 16: raise ValueError('two 64B FP32 beats required')
    rounded=[bf16_rne(x) for x in low+high]
    if any((x & 0x7f80)==0x7f80 for x in rounded): raise ValueError('nonfinite BF16 expansion')
    return b''.join(x.to_bytes(2,'little') for x in rounded)

def dot16_reference(coeff, rhs):
    """Old order: each half completes ascending K before the next half."""
    result=[]
    for half in range(2):
        for lane in range(16):
            acc=0
            for k,a in enumerate(coeff): acc=fp_add(acc,fp_mul(a,rhs[k][half*16+lane]))
            result.append(acc)
    return result

def dot32_candidate(coeff,rhs):
    """New order: all 32 independent lanes take the same ascending K step."""
    result=[0]*32
    for k,a in enumerate(coeff):
        product=[fp_mul(a,rhs[k][lane]) for lane in range(32)]
        result=[fp_add(result[lane],product[lane]) for lane in range(32)]
    return result

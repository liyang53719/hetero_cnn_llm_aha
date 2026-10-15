"""Tiny normal-mode QK payload runner, source-order numeric test, no cycle model.

Only actual SRAM words feed payloads. Debug observes partial/dot/score; it never
supplies a value. Five B partial slots alias the original 80KiB B allocation.
The required selected-lane adapter/owner/port arbitration is NOT implemented RTL.
"""
from collections import Counter
import ctypes as C
import struct

from candidates.qwen2_exact_tree_scheduler.model import require
from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import bf, finite
from scripts.qwen2_rectangular_attention_model import scratch_layout, scratch_address


def configure(lib):
    u, h = C.c_uint32, C.c_uint16
    lib.reset.argtypes = []; lib.reset.restype = C.c_int
    lib.begin.argtypes = [u]; lib.begin.restype = C.c_int
    lib.step.argtypes = [u,u,u,C.POINTER(h),C.POINTER(h),C.POINTER(u),C.POINTER(u)]
    lib.step.restype = C.c_int
    lib.scalar_add.argtypes = [u,u,C.POINTER(u)]; lib.scalar_add.restype = C.c_int
    lib.post_dot.argtypes = [u,C.POINTER(u)]; lib.post_dot.restype = C.c_int
    require(lib.environment_ok() == 1 and lib.accumulator_bytes() == 81920, 'RNE / five-context ABI')
    return lib


class Scratch:
    def __init__(self, tokens):
        require(type(tokens) is int and 1 <= tokens <= 128, 'M1..128 only')
        self.layout = scratch_layout(tokens, 5)
        self.a = bytearray(b'\xc1\x7f')*(704512//2)
        self.b = bytearray(b'\xc1\x7f')*(81920//2)
        self.accesses = Counter()

    def position(self, name, row, column):
        group, bank, word, offset = scratch_address(self.layout, name, row, column)
        return (self.a if group == 'A' else self.b), (bank*(1376 if group=='A' else 160)+word)*32+offset

    def put(self, name, row, column, bits):
        memory, offset = self.position(name, row, column)
        size = 2 if name in ('q','k','v') else 4
        struct.pack_into('<H' if size==2 else '<I', memory, offset, bits>>16 if size==2 else bits)
        self.accesses['write:'+name] += 1

    def get(self, name, row, column):
        memory, offset = self.position(name, row, column)
        size = 2 if name in ('q','k','v') else 4
        value = struct.unpack_from('<H' if size==2 else '<I', memory, offset)[0]
        self.accesses['read:'+name] += 1
        return value<<16 if size==2 else value


def payload(scratch, qbase, rows, stripe, step, columns, tokens):
    require(0 <= stripe < 16 and 0 <= step < 8, '16 ordered stripes / eight steps')
    depth = stripe+16*step
    a = tuple(scratch.get('q', r, depth)>>16 if r<rows else 0 for r in range(16))
    b = tuple(scratch.get('k', k, depth)>>16 if k<min(tokens,columns) else 0 for k in range(256))
    valid = tuple(qbase+r+1 if r<rows else 0 for r in range(16))
    return a,b,valid


def run_tile(lib, q, k, *, qbase=0, debug=None):
    """q contains this tile's FP32 containers; k contains one KV head.

    No softmax/PV or source job is executed. Calls are synchronous model events;
    finite physical port throughput, ACK/abort transport and latency are pending.
    """
    tokens, rows = len(k), len(q)
    require(type(qbase) is int and qbase%16==0 and 0<=qbase<tokens and
            rows==min(16,tokens-qbase), 'canonical query tile / tail')
    require(all(len(row)==128 for row in (*q,*k)), 'head dimension 128')
    require(all(type(x) is int and 0<=x<=0xffffffff for row in (*q,*k) for x in row), 'FP32 words')
    s = Scratch(tokens)
    for r,row in enumerate(q):
        for j,x in enumerate(row): s.put('q',r,j,bf(x))
    for r,row in enumerate(k):
        for j,x in enumerate(row): s.put('k',r,j,bf(x))
    columns = ((qbase+rows+31)//32)*32
    require(lib.reset()==0, 'native numerical environment')
    out, folded, post = (C.c_uint32*4096)(), C.c_uint32(), (C.c_uint32*3)()
    partial_tags = [None]*5
    stats = Counter()
    for sb in (0,5,10,15):
        count = min(5,16-sb)
        require(not any(x is not None for x in partial_tags) and lib.begin(count)==0, 'partial group reuse')
        for t in range(8):
            for ctx in range(count):
                stripe = sb+ctx
                a,b,valid = payload(s,qbase,rows,stripe,t,columns,tokens)
                rc = lib.step(ctx,t,columns,(C.c_uint16*16)(*a),(C.c_uint16*256)(*b),
                              (C.c_uint32*16)(*valid),out)
                require(rc==(1 if t==7 else 0), 'selected QK lane finite / native sequence')
                stats['wide_issues'] += 1
                stats['physical_fmas'] += 16*columns
                stats['fixed_4096_lane_issue_capacity'] += 4096
                stats['useful_fmas'] += sum(valid)
                if t==7:
                    for r in range(16):
                        for key in range(columns):
                            s.put('partial_or_pv_capture',ctx*16+r,key,out[r*256+key])
                    partial_tags[ctx] = stripe
        for ctx in range(count):
            stripe = sb+ctx
            require(partial_tags[ctx]==stripe, 'partial stripe identity')
            for r in range(rows):
                for key in range(qbase+r+1):
                    part = s.get('partial_or_pv_capture',ctx*16+r,key)
                    if debug is not None: debug('partial',(r,key,stripe),(part,))
                    prior = 0 if stripe==0 else s.get('score',r,key)
                    require(lib.scalar_add(prior,part,C.byref(folded))==0, 'original scalar fold exception')
                    s.put('score',r,key,folded.value)
                    stats['ordered_scalar_adds'] += 1
            partial_tags[ctx] = None
    for r in range(rows):
        for key in range(qbase+r+1):
            total = s.get('score',r,key)
            require(lib.post_dot(total,post)==0, 'original scalar scale / score exception')
            require(finite(post[2]), 'selected score finite')
            if debug is not None: debug('dot_score',(r,key),(total,*post))
            s.put('score',r,key,post[2])
            stats['scalar_scale_muls'] += 1
    require(stats['wide_issues']==128 and not any(x is not None for x in partial_tags), 'terminal numeric graph')
    return s,dict(stats)

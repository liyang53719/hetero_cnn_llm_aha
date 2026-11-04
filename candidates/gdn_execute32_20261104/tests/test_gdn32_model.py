#!/usr/bin/env python3
"""Bounded independent model tests: no Chisel elaboration, DUT, tensor packages."""
import os
import sys
import resource
import signal
import time
# Hard resource bounds apply before test imports/allocation.
LIMIT=128*1024*1024
resource.setrlimit(resource.RLIMIT_AS,(LIMIT,LIMIT))
signal.alarm(29)
START=time.monotonic()
import hashlib
import json
import random
import re
import struct
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path
from gdn32_model import *

TEST_ROOT=Path(__file__).resolve().parent
CANDIDATE_ROOT=TEST_ROOT.parent
CANDIDATE_SOURCE=CANDIDATE_ROOT/'source'/'GdnRuntimeChunkExecuteOwner32V1.scala'

def resolve_base_root():
    override=os.environ.get('GDN_BASE_SOURCE_ROOT')
    if override:
        return Path(override).expanduser().resolve()
    # In a repository, tests live in candidates/<candidate>/tests. Also allow
    # a candidate under another repository-local directory without cwd coupling.
    for ancestor in (CANDIDATE_ROOT,*CANDIDATE_ROOT.parents):
        probe=ancestor/'candidates'/'fresh_original_top_recovery_20261028'/'source'
        if probe.is_dir(): return probe
    return CANDIDATE_ROOT.parent/'fresh_original_top_recovery_20261028'/'source'

BASE=resolve_base_root()
PINS={
 'GdnRuntimeChunkExecuteOwnerV8.scala':'b4bc9397b88bc4542b72213fa14aad5b4df5e428881e96e2fd3893a49af3c15e',
 'GdnChunkAddressPlan.scala':'f8534849bad082b77de88cf2cef43558a91f045122694640e9f33391f101b943',
 'GdnRuntimeChunkLayout.scala':'54451d4cf504ca76ed387c23790875828eb966ce1603aa08a2200406023ad346'}

def bits(x): return struct.unpack('<I',struct.pack('<f',x))[0]
def number(x): return struct.unpack('<f',struct.pack('<I',x))[0]
def sample(rng): return bits(rng.randint(-64,64)/32.0)

class ScheduleTests(unittest.TestCase):
    def test_01_baseline_source_pins_and_geometry(self):
        for name,pin in PINS.items(): self.assertEqual(hashlib.sha256((BASE/name).read_bytes()).hexdigest(),pin)
        src=(BASE/'GdnRuntimeChunkExecuteOwnerV8.scala').read_text()
        found={int(p):Phase(a,b,d,int(r),int(c),int(k)) for p,a,b,d,r,c,k in
               re.findall(r'\((\d+),"(\w+)","(\w+)","(\w+)",(\d+),(\d+),(\d+)\)',src)}
        self.assertEqual(found,PHASES)
        self.assertEqual(CHUNK_BYTES,806912)
        self.assertEqual(OFFSETS['next_state']+65536,CHUNK_BYTES)
        self.assertEqual(len(SHAPES),24)
        shape_source=(BASE/'GdnChunkAddressPlan.scala').read_text()
        parsed=tuple((n,int(r),int(c)) for n,r,c in
                     re.findall(r'Shape\("(\w+)", (\d+), (\d+)\)',shape_source))
        self.assertEqual(parsed,SHAPES)

    def test_02_full_13_phase_counts_streaming(self):
        for width in (16,32):
            for phase in PHASES:
                observed=Counter(); write_addresses=set()
                for e in schedule(phase,Plan(),width):
                    observed[e.kind]+=1
                    if e.kind != 'V': self.assertEqual(e.address%64,0)
                    if e.kind == 'W':
                        self.assertNotIn(e.address,write_addresses); write_addresses.add(e.address)
                exp=expected_counts(phase,width=width)
                self.assertEqual((observed['R'],observed['V'],observed['W']),exp,(phase,width))
        self.assertEqual(expected_counts(7),Counts(17264,16384,512))
        self.assertEqual(expected_counts(7,width=16),Counts(17888,32768,512))

    def test_03_preserves_write_bytes_halves_vectors(self):
        for phase in PHASES:
            old,new=expected_counts(phase,width=16),expected_counts(phase)
            self.assertEqual(old.writes,new.writes)
            self.assertEqual(old.vectors,new.vectors*2)
            self.assertLessEqual(new.reads,old.reads)
        for m in (16,128):
            r=16 if m==16 else 64
            self.assertEqual(expected_counts(17,m),Counts(8*r,4*r,4*r))

    def test_04_dot_coefficients_and_pair_addresses(self):
        plan=Plan(head=31,chunk=1)
        for phase in DOT:
            p=PHASES[phase]
            for row in (0,p.rows-1):
                for group in (0,p.cols//32-1):
                    events=list(schedule(phase,plan,rows=[row],groups=[group]))
                    a=[e for e in events if e.role=='a']
                    self.assertEqual([e.k for e in a],list(range(0,p.k,16)))
                    self.assertEqual([e.address for e in a],
                                     [plan.base(p.a)+(row*p.k+k)*4 for k in range(0,p.k,16)])
                    b=[e for e in events if e.role=='b']
                    bbase=plan.previous if phase in (9,11) else plan.base(p.b)
                    self.assertEqual([e.address for e in b],
                        [bbase+(k*p.cols+group*32+h*16)*4 for k in range(p.k) for h in (0,1)])
                    self.assertEqual([(e.role,e.k) for e in events if e.kind=='V'][:2*p.k],
                                     [(op,k) for k in range(p.k) for op in ('multiply','accumulate')])
                    if phase in FACTOR:
                        self.assertEqual([e.address for e in events if e.role=='factor'],
                                         [plan.base('pair')+(row*64+group*32+h*16)*4 for h in (0,1)])

    def test_05_solve_triangular_ack_dependency(self):
        for phase in SOLVE:
            plan=Plan(); p=PHASES[phase]
            # A schedule event is retired/ACKed before the next request is allowed.
            row_write_acks=Counter(); last_row=0; selected_coeffs=[]
            for e in schedule(phase,plan):
                if e.row != last_row:
                    self.assertEqual(row_write_acks[last_row],8)
                    self.assertEqual(e.row,last_row+1); last_row=e.row
                if e.role=='prior':
                    self.assertLess(e.k,e.row)
                    self.assertEqual(row_write_acks[e.k],8)
                    self.assertEqual(e.address,plan.base(p.dst)+(e.k*128+e.col+16*e.half)*4)
                if e.role=='multiply':
                    self.assertLess(e.k,e.row); selected_coeffs.append((e.row,e.k))
                if e.kind=='W': row_write_acks[e.row]+=1
            self.assertEqual(row_write_acks[63],8)
            zero=list(schedule(phase,plan,rows=[0],groups=[0]))
            self.assertEqual([e.role for e in zero],['rhs','rhs','subtract','scratch','scratch'])
            # 64B coefficient fetch can physically include the diagonal; it is never selected.
            self.assertTrue(all(r>k for r,k in selected_coeffs))
            for row in (1,16,17,32,63):
                a=[e for e in schedule(phase,plan,rows=[row],groups=[0]) if e.role=='a']
                self.assertEqual(len(a),(row+15)//16)

    def test_06_m16_m128_all_heads_layout_output(self):
        for tokens in (16,128):
            for heads in (16,32):
                all_outputs=set(); scratch_spans=[]
                for head in range(heads):
                    for chunk in range(1 if tokens==16 else 2):
                        p=Plan(tokens=tokens,value_heads=heads,head=head,chunk=chunk,row_bytes=heads*1600)
                        self.assertEqual(p.previous,p.head_base if chunk==0 else p.base('next_state')-CHUNK_BYTES)
                        scratch_spans.append((p.chunk_base,p.chunk_base+CHUNK_BYTES))
                        events=list(schedule(17,p))
                        self.assertEqual(Counter(e.kind for e in events),
                                         Counter(R=8*(16 if tokens==16 else 64),V=4*(16 if tokens==16 else 64),W=4*(16 if tokens==16 else 64)))
                        for e in events:
                            if e.kind=='W':
                                expected=p.output+((chunk*64+e.row)*heads+head)*256+e.col*2
                                self.assertEqual(e.address,expected)
                                self.assertNotIn(e.address,all_outputs); all_outputs.add(e.address)
                self.assertEqual(len(all_outputs),tokens*heads*4)
                self.assertEqual(sorted(all_outputs),list(range(0x20000000,0x20000000+tokens*heads*256,64)))
                ss=sorted(scratch_spans)
                self.assertTrue(all(a[1]<=b[0] for a,b in zip(ss,ss[1:])))
        for kwargs in ({'tokens':64},{'head':32},{'chunk':2},{'key_heads':8},
                       {'value_heads':24},{'layout_id':1},{'layout_version':2},
                       {'row_bytes':25600},{'scratch':1},{'scratch':ADDRESS_LIMIT-64},
                       {'output':0x10000000},{'tokens':16,'chunk':1}):
            with self.assertRaises(ValueError,msg=str(kwargs)): Plan(**kwargs)

    def test_07_binary_low_high_order_addresses(self):
        plan=Plan(head=15,chunk=1)
        for phase in (10,13,15,16):
            p=PHASES[phase]
            e=list(schedule(phase,plan,rows=[p.rows-1],groups=[3]))
            expected=['a','a']+([] if phase==15 else ['b','b'])+[
                'decay' if phase==15 else 'subtract' if phase==10 else 'add','scratch','scratch']
            self.assertEqual([x.role for x in e],expected)
            for role in ('a','b','scratch'):
                pair=[x for x in e if x.role==role]
                if pair:
                    self.assertEqual([x.half for x in pair],[0,1])
                    self.assertEqual(pair[1].address,pair[0].address+64)
            a_base=plan.previous if phase==15 else plan.base(p.a)
            self.assertEqual(e[0].address,a_base+((p.rows-1)*128+96)*4)

    def test_08_random_backpressure_keeps_order_and_ack_barriers(self):
        for phase in PHASES:
            rows=[0,1,16,17,63] if phase in SOLVE else [0,PHASES[phase].rows-1]
            witness=list(schedule(phase,Plan(),rows=rows,groups=[0,1]))
            for seed in (0,17,1234):
                trace,cycles,stalls=run_backpressure(witness,seed)
                self.assertEqual(trace,witness)
                self.assertGreater(cycles,len(witness)*2); self.assertGreater(stalls,0)
        # Holding the high-half ACK must prevent next-row issue.
        events=list(schedule(7,Plan(),rows=[0,1],groups=[0]))
        engine=SerialEngine(events)
        while engine.pending.row==0:
            identity=engine.issue()
            if engine.pending.kind=='W' and engine.pending.half==1:
                for _ in range(11): self.assertIsNone(engine.issue())
                self.assertFalse(engine.complete)
            engine.respond(identity)
        self.assertEqual(engine.pending.row,1)

    def test_09_negative_protocol_models(self):
        events=list(schedule(17,Plan(tokens=16),rows=[0],groups=[0]))
        for bad in (('mem',1),('vec','format',True)):
            e=SerialEngine(events); e.issue()
            with self.assertRaises(ProtocolError): e.respond(bad)
            self.assertTrue(e.failed); self.assertIsNotNone(e.outstanding); self.assertFalse(e.complete)
        e=SerialEngine(events)
        with self.assertRaises(ProtocolError): e.respond(('mem',0))
        e=SerialEngine(events); i=e.issue(); e.respond(i)
        with self.assertRaises(ProtocolError): e.respond(i)
        e=SerialEngine(events); i=e.issue()
        with self.assertRaises(ProtocolError): e.respond(i,error=True)
        self.assertFalse(e.complete)
        e=SerialEngine([events[2]]); e.issue()
        with self.assertRaises(ProtocolError): e.respond(('vec','format',False))

    def test_15_full_address_multisets_and_extents(self):
        plan=Plan(head=31,chunk=1)
        for phase,p in PHASES.items():
            old=Counter(); new=Counter()
            for width,target in ((16,old),(32,new)):
                for e in schedule(phase,plan,width):
                    if e.kind=='V': continue
                    target[(e.kind,e.role,e.address)]+=1
                    if e.role=='output':
                        base=plan.output; length=plan.tokens*plan.value_heads*256
                    elif e.role=='a':
                        base=plan.previous if phase==15 else plan.base(p.a)
                        length=65536 if phase==15 else next(r*c*4 for n,r,c in SHAPES if n==p.a)
                    elif e.role in ('b','rhs'):
                        base=plan.previous if phase in (9,11) else plan.base(p.b)
                        length=65536 if phase in (9,11) else next(r*c*4 for n,r,c in SHAPES if n==p.b)
                    elif e.role=='factor': base=plan.base('pair'); length=16384
                    else:
                        name='out' if e.role=='format_input' else p.dst
                        base=plan.base(name); length=next(r*c*4 for n,r,c in SHAPES if n==name)
                    self.assertGreaterEqual(e.address,base)
                    self.assertLessEqual(e.address+64,base+length)
            self.assertEqual(set(old),set(new))
            for key,count in new.items():
                ratio=2 if key[1]=='a' and phase in DOT | SOLVE else 1
                self.assertEqual(old[key],count*ratio,(phase,key))

    def test_16_pairing_checker_and_schedule_mutations(self):
        for phase in PHASES:
            row=17 if phase in SOLVE else 0
            events=list(schedule(phase,Plan(),rows=[row],groups=[0]))
            audit_pairing(events,phase)
            # Remove one upper half, swap the halves, or point high at low.
            index=next(i for i,e in enumerate(events) if e.kind=='R' and e.half==1)
            for mutant in (events[:index]+events[index+1:],
                           events[:index-1]+[events[index],events[index-1]]+events[index+1:],
                           events[:index]+[events[index]._replace(address=events[index-1].address)]+events[index+1:]):
                with self.assertRaises(ProtocolError,msg=str(phase)): audit_pairing(mutant,phase)
            # Early vector issue before collecting high must fail.
            vi=next(i for i,e in enumerate(events) if e.kind=='V')
            moved=events[:index]+[events[vi]]+events[index:vi]+events[vi+1:]
            with self.assertRaises(ProtocolError,msg=str(phase)): audit_pairing(moved,phase)
            if phase!=17:
                mutant=events[:-2]+[events[-1],events[-2]]
                with self.assertRaises(ProtocolError): audit_pairing(mutant,phase)

    def test_17_candidate_source_static_binding_not_execution(self):
        # Textual structural anchors only. This does not execute Scala or the DUT.
        source=CANDIDATE_SOURCE.read_text()
        code=re.sub(r'/\*.*?\*/|//[^\n]*','',source,flags=re.S)
        compact=re.sub(r'\s+','',code)
        anchors=(
            'classGdnRuntimeChunkExecuteOwner32V1extendsModule',
            'valvectorRequest=Decoupled(newUnifiedVectorElement32PayloadV4)',
            'valvectorResult=Flipped(Decoupled(newUnifiedVectorElement32ResultPayloadV4))',
            'vala=Reg(UInt(1024.W))', 'valb=Reg(UInt(1024.W))', 'valtotal=Reg(UInt(1024.W))',
            'valbeatsPerRow=Mux(outputPhase,4.U(4.W),cols>>5)',
            'valcoefficient=a(511,0).asTypeOf(Vec(16,UInt(32.W)))(k(3,0))',
            'io.vectorRequest.bits.a:=Mux(formatOnly,a,vectorA).asTypeOf(Vec(32,UInt(32.W)))',
            'io.vectorRequest.bits.b:=Mux(formatOnly,0.U(1024.W),vectorB).asTypeOf(Vec(32,UInt(32.W)))',
            'valdotReadBeats=(rows*(cols>>5)*((reduction<<1)+(reduction>>4)+(factor.asUInt<<1))).pad(64)',
            'valdotVectors=(rows*(cols>>5)*((reduction<<1)+factor.asUInt)).pad(32)',
            'valexpectedReadBeats=Mux(dot,dotReadBeats,Mux(solve,17264.U(64.W),',
            'valexpectedVectors=Mux(dot,dotVectors,Mux(solve,16384.U(32.W),',
            'Mux(outputPhase,(activeRows.pad(32)<<2),(rows*(cols>>5)).pad(32))',
            'valpairedRead=step=/=readA||!(dot||solve)',
            'valreadAddress=readBaseAddress+Mux(readHalf,64.U(66.W),0.U(66.W))',
            'valformatOnly=step===formatOutput',
            'RawFp32ToBf16Rne.U',
            'io.memory.bits.data:=Mux(state===issueWrite,Mux(writeHalf,total(1023,512),total(511,0)),0.U)',
        )
        for anchor in anchors: self.assertIn(anchor,compact)
        self.assertNotIn('UnifiedOrdinaryVectorRequestV5',compact)
        found={int(p):Phase(a,b,d,int(r),int(c),int(k)) for p,a,b,d,r,c,k in
               re.findall(r'\((\d+),"(\w+)","(\w+)","(\w+)",(\d+),(\d+),(\d+)\)',code)}
        self.assertEqual(found,PHASES)

class NumericTests(unittest.TestCase):
    def test_10_exact_binary32_oracle_checks(self):
        vectors=[(1.0,2**-24),(1.0,3*2**-24),(-0.0,-0.0),(2**-126,2**-149),
                 (2**24,1.0),(-1.5,0.75)]
        for a,b in vectors:
            self.assertEqual(fp_add(bits(a),bits(b)),bits(a+b))
            self.assertEqual(fp_mul(bits(a),bits(b)),bits(a*b))
        rng=random.Random(908)
        for _ in range(1000):
            a,b=sample(rng),sample(rng)
            self.assertEqual(fp_add(a,b),bits(number(a)+number(b)))
            self.assertEqual(fp_mul(a,b),bits(number(a)*number(b)))
        self.assertEqual(fp_mul(0x00000001,0x3f000000),0)
        self.assertEqual(fp_mul(0x00000003,0x3f000000),2)
        self.assertEqual(fp_add(0x80000000,0x80000000),0x80000000)
        self.assertEqual(fp_add(0x80000000,0),0)
        with self.assertRaises(ValueError): fp_add(0x7f800000,0)

    def test_11_32lane_dot_and_factor_preserve_per_lane_order(self):
        rng=random.Random(820)
        for phase in DOT:
            k=PHASES[phase].k
            coeff=[sample(rng) for _ in range(k)]
            rhs=[[sample(rng) for _ in range(32)] for _ in range(k)]
            old=dot16_reference(coeff,rhs); new=dot32_candidate(coeff,rhs)
            self.assertEqual(old,new,phase)
            if phase in FACTOR:
                factor=[sample(rng) for _ in range(32)]
                self.assertEqual([fp_mul(old[i],factor[i]) for i in range(32)],
                                 [fp_mul(new[i],factor[i]) for i in range(32)])
        # Negative witnesses: reassociation and fused multiply-add would change bits.
        coeff=[bits(1.0)]*3
        rhs=[[bits(x)]*32 for x in (2**24,1.0,-2**24)]
        self.assertEqual(dot32_candidate(coeff,rhs),[0]*32)
        reassociated=fp_add(bits(2**24),fp_add(bits(1.0),bits(-2**24)))
        self.assertNotEqual(reassociated,0)
        a,b,c=0x3f800001,0x3f7ffffe,0xbf800000
        separate=fp_add(fp_mul(a,b),c)
        # (1+2^-23)*(1-2^-23)-1 = -2^-46 before intermediate rounding.
        fused=bits(-(2**-46))
        self.assertNotEqual(separate,fused)
        self.assertEqual(dot32_candidate([0x80000000],[[bits(1.0)]*32]),[0]*32)

    def test_12_triangular_numeric_solve_32lane_matches16(self):
        # Two local 64x32 tiles only; no diagonal coefficient is supplied or selected.
        rng=random.Random(190)
        prior16=[]; prior32=[]
        for row in range(64):
            coeff=[bits(rng.randint(-2,2)/128) for _ in range(row)]
            rhs=[sample(rng) for _ in range(32)]
            total16=dot16_reference(coeff,prior16)
            total32=dot32_candidate(coeff,prior32)
            out16=[fp_add(rhs[i],total16[i]^0x80000000) for i in range(32)]
            out32=[fp_add(rhs[i],total32[i]^0x80000000) for i in range(32)]
            self.assertEqual(out16,out32,row)
            prior16.append(out16); prior32.append(out32)
        # Row zero subtracts the initial +0; no diagonal division is possible here.
        self.assertEqual(fp_add(0x80000000,0x80000000),0x80000000)

    def test_13_binary_lane_halves_and_decay(self):
        rng=random.Random(54)
        for phase in (10,13,15,16):
            a=[sample(rng) for _ in range(32)]; b=[sample(rng) for _ in range(32)]
            decay=bits(0.75)
            def op(i):
                return fp_mul(a[i],decay) if phase==15 else fp_add(a[i],b[i]^(0x80000000 if phase==10 else 0))
            reference=[op(i) for half in (0,1) for i in range(16*half,16*(half+1))]
            self.assertEqual(reference,[op(i) for i in range(32)])

    def test_14_bf16_ties_pack_order_and_failures(self):
        for upper in (0x0000,0x0001,0x007f,0x0080,0x3f80,0x3f81,0x7f7e,
                      0x8000,0x8001,0x8080,0xbf80,0xbf81):
            self.assertEqual(bf16_rne((upper<<16)|0x7fff),upper)
            self.assertEqual(bf16_rne((upper<<16)|0x8000),upper+(upper&1))
            self.assertEqual(bf16_rne((upper<<16)|0x8001),upper+1)
        inputs=[bits((i-15)/8) for i in range(32)]
        beat=format_beat(inputs[:16],inputs[16:])
        self.assertEqual(len(beat),64)
        self.assertEqual(list(struct.unpack('<32H',beat)),[bf16_rne(x) for x in inputs])
        self.assertNotEqual(format_beat(inputs[16:],inputs[:16]),beat)
        with self.assertRaises(ValueError): format_beat(inputs[:15],inputs[16:])
        for invalid in (0x7f800000,0x7fc00001,0x7f7fffff):
            with self.assertRaises(ValueError): format_beat([invalid]*16,[0]*16)
        self.assertEqual(bf16_rne(0x80000000),0x8000)
        self.assertEqual(bf16_rne(0),0)

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    totals={str(tokens):{str(width):dict(zip(Counts._fields,
        [sum(expected_counts(p,tokens,width)[i] for p in PHASES) for i in range(3)]))
        for width in (16,32)} for tokens in (16,128)}
    summary={
        'evidence_kind':'independent_python_model_plus_textual_source_anchors_not_dut_or_chisel_simulation',
        'python_optimization_level':sys.flags.optimize,
        'candidate_source':{'relative_path':'source/GdnRuntimeChunkExecuteOwner32V1.scala',
                            'sha256':hashlib.sha256(CANDIDATE_SOURCE.read_bytes()).hexdigest(),
                            'bytes':CANDIDATE_SOURCE.stat().st_size,
                            'check_kind':'textual_anchors_only_not_dynamic_execution'},
        'baseline_sha256':PINS,
        'test_sha256':{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                       for name in ('gdn32_model.py','test_gdn32_model.py')},
        'tests_run':result.testsRun,'failures':len(result.failures),
        'errors':len(result.errors),'wall_seconds':round(time.monotonic()-START,6),
        'address_space_limit_bytes':LIMIT,'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'phase_counts':{str(p):{'candidate32':expected_counts(p)._asdict(),
                              'baseline16':expected_counts(p,width=16)._asdict()} for p in PHASES},
        'phase17_m16':expected_counts(17,16)._asdict(),
        'totals_per_head_per_chunk_phases_5_through_17':totals,
        'coverage':{'schedule_mutations_rejected':64,'backpressure_seed_phase_cases':39,
                    'max_numeric_tile_elements':128*32},
        'limitations':['Does not import, instantiate, elaborate, simulate, build, or dynamically verify candidate RTL; source binding is textual only.',
                       'No physical resources, synthesis, timing, hardware flags, end-to-end model, or installed artifact acceptance evidence.',
                       'Abstract backpressure assumes finite eventual ready/result and serial response-before-next-request behavior.',
                       'Coefficient beat may contain unused diagonal words; only k < row coefficients are selected.']}
    suffix='_O' if sys.flags.optimize else ''
    TEST_ROOT.joinpath('MODEL_TEST_REPORT'+suffix+'.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ('tests_run','failures','errors','wall_seconds','max_rss_kib')}))
    raise SystemExit(not result.wasSuccessful())

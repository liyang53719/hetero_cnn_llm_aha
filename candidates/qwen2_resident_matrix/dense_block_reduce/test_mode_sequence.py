"""Small synthetic mode chain on one owner/bank/Matrix allocation.

Q/K/V and O use K=N32. Gate/Up use K32 and all 56 local N160
windows of the real N8960 Activation address span. Down consumes that
ACK-written span at K8960/N32, including all three real prefix/seed restores.
This is a mode-handoff test, not a full-model M16 numerical acceptance run.
No saved output, reference function, array clone or compilation feeds execution.
"""
from collections import Counter, deque
import ctypes as C
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import time
import unittest

from ..ffn_public import execute_numeric as public
from ..ffn_attention.matrix_service import MatrixService, MatrixValue
from ..official_bf16.test_owners import verified_library
from . import k_window_model as kmodel
from .dense_drain import DenseReductionOwner, DenseDrainRequest, Job, drain
from .sum_tiles import TileSumController, SumInvocation, shared_loan_edge, owner_tile_edge
from .vector_add_model import VectorLoanModel, Request, LaneReply, add_lane


def require(ok, reason):
    if not ok:
        raise AssertionError(reason)


class PhysicalMemory:
    """Address-decoded test DDR; writable bytes become readable only after ACK.

    Only readonly synthetic operands are initialized. Every downstream source
    is populated by accepted write-data beats and prior tagged ACK records.
    """
    def __init__(self):
        self.regions = []
        self.pending = None
        self.counts = Counter()

    def add(self, name, base, rows, cols, *, weight=None, activation=None):
        readonly = weight is not None or activation is not None
        width = 2 if weight is not None else 4
        extent = rows * cols * width
        require(base % 64 == 0 and extent % 64 == 0, 'DDR alignment')
        require(all(base + extent <= r['base'] or r['base'] + r['extent'] <= base
                    for r in self.regions), 'full physical DDR spans alias')
        value = weight if weight is not None else activation if activation is not None else 0xa5963cc3
        raw = bytearray(struct.pack('<H' if width == 2 else '<I', value) * (rows * cols))
        r = dict(name=name, base=base, extent=extent, width=width, readonly=readonly,
                 raw=raw, written=set(), acked=set(), acks=[], published=readonly)
        self.regions.append(r)
        return r

    def region(self, address, size=64):
        found = [r for r in self.regions if r['base'] <= address and address + size <= r['base'] + r['extent']]
        require(len(found) == 1 and address % 64 == 0, 'physical DDR address decode')
        return found[0]

    def read64(self, address):
        r = self.region(address)
        require(r['published'] and (r['readonly'] or address in r['acked']),
                'read before actual predecessor ACK/publication')
        self.counts['read_' + r['name']] += 1
        return r['name'], struct.unpack_from('<32H' if r['width'] == 2 else '<16I', r['raw'], address-r['base'])

    def write_event(self, kind, value):
        if kind == 'command':
            require(self.pending is None, 'overlapping accepted DDR write')
            r = self.region(value.address, value.beats * 64)
            require(not r['readonly'] and not r['published'], 'write immutable/published source')
            require(1 <= value.beats <= 16 and value.address//1024 == (value.address+value.beats*64-1)//1024,
                    'physical burst boundary')
            self.pending = [value, r, 0]
        elif kind == 'data':
            require(self.pending is not None, 'data without accepted write descriptor')
            cmd, r, index = self.pending
            require(value.mask == (1 << 64)-1 and value.last == (index+1 == cmd.beats), 'DDR mask/LAST')
            address = cmd.address + index*64
            require(address not in r['written'], 'duplicate output write')
            struct.pack_into('<16I', r['raw'], address-r['base'], *value.words)
            r['written'].add(address)
            self.pending[2] += 1
            self.counts['accepted_data_bytes'] += 64
        elif kind == 'ack':
            require(self.pending is not None, 'ACK without accepted descriptor')
            cmd, r, index = self.pending
            require(index == cmd.beats and value.tag == cmd.tag and not value.error and value.nbytes == cmd.beats*64,
                    'physical ACK identity/count')
            r['acked'].update(range(cmd.address, cmd.address+cmd.beats*64, 64))
            r['acks'].append((cmd, value));self.pending = None
            self.counts['acknowledged_bytes'] += value.nbytes
        else:
            raise AssertionError('unexpected write event '+kind)
        self.counts['write_'+kind] += 1

    def publish(self, r):
        require(self.pending is None and r['written'] == r['acked'] == set(range(r['base'], r['base']+r['extent'], 64)),
                'source publication before exact full ACK coverage')
        r['published'] = True

    def source(self, job):
        r = self.region(job.a, job.m*job.k*4)
        require((r['base'],r['extent']) == (job.a,job.m*job.k*4), 'full A span/row stride')
        return public.down_driver.DenseSource(r['base'],r['extent'],
            'readonly' if r['readonly'] else 'published', lambda:r['published'],
            lambda:bytes(r['raw']), lambda:tuple(r['acks']))


class AcceptedVectorBackend(VectorLoanModel):
    """Same loan FSM for Add and six-phase SiLU; actual accepted operands only.

    The existing ELF's sf_vector supplies its observed six phase results.
    Each phase is returned only after the corresponding loan lane issue. Its
    reference entrypoint is never called. This is a software adapter, not RTL.
    """
    def __init__(self, library):
        super().__init__(auto_respond=False)
        self.lib = library
        self.next_returns = None
        self.phase_values = self.phase_flags = self.final_words = None
        self.calls = Counter()

    def tick(self, **inputs):
        if self.next_returns is not None:
            require(self.state == 'wait', 'vector reply without accepted lane issue')
            inputs['lane_returns'] = self.next_returns
            self.next_returns = None
        phase = self.phase
        e = super().tick(**inputs)
        if e['request_fire'] and not self.input.binary_add:
            a,b,out = (C.c_uint32*16)(*self.input.gate),(C.c_uint32*16)(*self.input.up),(C.c_uint32*16)()
            values,flags,errors = (C.c_uint32*96)(),(C.c_uint32*96)(),(C.c_uint32*16)()
            require(self.lib.sf_vector(a,b,out,values,flags,errors) == 0 and not any(errors), 'actual ELF SiLU failed')
            self.phase_values,self.phase_flags,self.final_words = tuple(values),tuple(flags),tuple(out)
            self.calls['silu_requests'] += 1
        if e['issued'] is not None:
            if self.input.binary_add:
                self.next_returns = {i:add_lane(a,b) for i,(_,a,b) in enumerate(e['issued'])}
                self.calls['add_issues'] += 1
            else:
                require(all(op == ('exp_negative','add','div','mul','mul','mul')[phase]
                            for op,_,_ in e['issued']), 'SiLU six-phase mode drift')
                self.next_returns = {i:LaneReply(self.phase_values[phase*16+i],
                    0 if phase == 0 else self.phase_flags[phase*16+i]) for i in range(16)}
                self.calls['silu_phase_issues'] += 1
        if e['result_fire']:
            if not self.input.binary_add:
                require(e['words'] == self.final_words, 'SiLU loan did not retire actual ELF output')
                self.phase_values=self.phase_flags=self.final_words=None
                self.calls['silu_results'] += 1
            else:self.calls['add_results'] += 1
        return e


class Sequence:
    def __init__(self, library, out):
        self.deadline = time.monotonic()+175
        self.out = Path(out)
        self.memory = PhysicalMemory()
        self.owner = DenseReductionOwner(drain.PrefixWorkspace(0x10000000,16384,71,2560),
            enable_dense_drain=True,enable_k_window=True,enable_ffn_drain=True,
            enable_ffn_window=True,enable_ffn_tiles=True)
        self.service = MatrixService(library)
        self.loan = AcceptedVectorBackend(library)
        self.sum = TileSumController(self.owner.tiles,bank_tick=lambda **p:owner_tile_edge(self.owner,**p))
        self.ids = (id(self.owner),id(self.owner.a_banks),id(self.owner.b_banks),id(self.owner.tiles.banks),
                    self.service.resource_address,id(self.loan))
        self.counts = Counter()
        self.trace = public.numeric.CappedTrace()
        self.phases = []
        self.previous = self.snapshot()

    def snapshot(self):
        return dict(matrix=dict(self.service.report()['counters']),ddr=dict(self.memory.counts),
            vector=dict(self.loan.calls),owner=dict(self.counts),
            window_a_load_fences=dict(k=self.owner.k_a_fences,legacy=self.owner.a_fences))

    def checkpoint(self, name):
        current=self.snapshot()
        delta={group:{k:values.get(k,0)-self.previous[group].get(k,0)
                for k in values.keys()|self.previous[group].keys()}
               for group,values in current.items()}
        self.phases.append(dict(name=name,accepted_delta=delta))
        self.previous=current

    def check(self, *, lease=False, tiles=False):
        o = self.owner
        require(time.monotonic() < self.deadline, 'synthetic same-instance chain exceeded 175s')
        require(self.ids == (id(o),id(o.a_banks),id(o.b_banks),id(o.tiles.banks),
                    self.service.lib.matrix_accumulator_address(),id(self.loan)), 'physical allocation replaced')
        require(o.state == 'idle' and o.window_request is None and o.drain_request is None and
            o.tiles.idle and not o.error and not o.drain_poison and not o.tiles.poison and
            not any((o.read_active,o.a_hold,o.a_rmw_pending,o.pending,o.fifo,o.final_value,o.seed_outstanding)) and
            o.write_state == 'idle' and self.memory.pending is None,
            'mode handoff with physical obligations: '+str({name:getattr(o,name) for name in
                ('state','window_request','drain_request','read_active','a_hold','a_rmw_pending',
                 'pending','final_value','seed_outstanding','write_state','accepted_write','error','drain_poison')}))
        # The unchanged ordinary Down model retains its final descriptor after
        # ACK. Its idle writer has no obligation; prove the historical ACK
        # instead of clearing that source-model field between modes.
        if o.accepted_write is not None:
            require(any(cmd == o.accepted_write for r in self.memory.regions for cmd,_ in r['acks']),
                    'retained ordinary descriptor has no real ACK')
        require(o.ports()['write_command'] is None and o.ports()['write_data'] is None and
                not o.ports()['write_ack_ready'],'writer still exposes a live obligation')
        require(self.service.owner is None and self.service.lib.matrix_state()&255 == 0 and
                self.loan.ports()['drained'] and self.loan.next_returns is None and not self.sum.busy,
                'arithmetic service not actually retired')
        require((o.lease is not None) == lease and o.tiles.leased == tiles, 'mode lease state')

    def window(self, q):
        o,svc=self.owner,self.service
        require(svc.acquire(o,'dense',q.job.tag), 'Matrix acquisition')
        adapter=svc.dense_library(o)
        require(o.tick(window=q)['window_fire'], 'real window admission')
        pending=None;results=deque();counts=Counter();held=0
        length=q.k_end-q.k_begin if isinstance(q,kmodel.KWindowRequest) else q.job.k
        while True:
            require(time.monotonic()<self.deadline, 'window wall budget')
            p=o.ports();args=dict(read_command_ready=counts['ticks']%5!=0,step_ready=counts['ticks']%7!=0)
            if pending is not None:args['read_beat']=drain.ReadBeat(pending[0].tag,pending[1],True)
            if results:args['result']=results[0]
            if p['step'] is not None and p['step'].last and len(results)>=2:args['step_ready']=False
            if o.group_started and not o.group_done and svc.lib.matrix_done_ready():args['matrix_done']=drain.MatrixDone(q.job.tag)
            if p['window_result'] is not None and held<2:
                args['window_result_ready']=False;held+=1
                require(svc.owner is o, 'service released before held owner terminal')
            e=o.tick(**args);counts['ticks']+=1
            if e.get('read_fire'):pending=None
            if e.get('read_command_fire'):
                require(pending is None,'overlapping read')
                cmd=e['read_command'];_,words=self.memory.read64(cmd.address);pending=(cmd,words)
                counts[cmd.kind+'_reads']+=1
            if e.get('group_fire'):require(adapter.td_group(0,length,q.cols//32)==0,'actual window Matrix group')
            if e.get('result_fire'):adapter.retire_result(results.popleft());counts['results']+=1
            if e.get('step_fire'):
                s=e['step'];a,b,out=(C.c_uint16*16)(*s.a),(C.c_uint16*256)(*s.b),(C.c_uint32*4096)()
                rc=adapter.td_step(s.k,s.context,s.clear,s.last,s.finish,s.emit,a,b,out)
                require(rc==int(s.last),'actual accepted Matrix step')
                if rc:results.append(drain.MatrixResult(s.context,MatrixValue(bytes(out))))
                counts['steps']+=1
            if e.get('matrix_done_fire'):adapter.retire_done(args['matrix_done']);counts['done']+=1
            require(not o.error and not o.tiles.poison,'window error '+str(o.error))
            if e.get('window_result_fire'):
                r=e['window_result'];require(r.committed and r.status is None,'window terminal')
                require(pending is None and not results and counts['done']==1 and held==2,'window retirement')
                require(o.lease == public.numeric.model.ALease.for_request(q),'canonical public ALease equality')
                svc.retire_owner_response(o);svc.release(o)
                break
        require(counts['steps']==length*q.cols//32 and counts['results']==q.cols//32,'accepted step/result count')
        require(counts['a_reads']==(0 if q.reuse_a else q.job.m*q.job.k//16),'full original A read count')
        self.counts['matrix_steps']+=counts['steps'];self.counts['windows']+=1
        return r

    def tile(self, **kwargs):
        require(time.monotonic()<self.deadline,'tile wall budget')
        e=self.owner.tick(**kwargs,loan_busy=True)['tile']
        require(not self.owner.error and not self.owner.tiles.poison,'tile owner fault')
        return e

    def control(self, op, slot, identity, ng, cols):
        q=drain.Control(op,slot,identity,ng,16,cols)
        for _ in range(8):
            if self.tile(tile_control=q)['ctl_fire']:return
        raise AssertionError('tile control stall')

    def read_tile(self, slot, identity, ng, cols, index):
        require(self.tile(tile_read=drain.Read(slot,identity,ng,index),tile_response_ready=False)['read_fire'],'tile read')
        for _ in range(8):
            e=self.tile()
            if e['response_fire']:return tuple(e['response'].words)
        raise AssertionError('tile response missing')

    def silu(self, identity, ng, cols):
        self.control(0,2,identity,ng,cols)
        for i in range(cols):
            g=self.read_tile(0,identity,ng,cols,i);u=self.read_tile(1,identity,ng,cols,i)
            require(self.loan.tick(request=Request(g,u,False))['request_fire'],'SiLU loan admission')
            self.tile()
            for _ in range(40):
                e=self.loan.tick(result_ready=True);self.tile()
                if e['result_fire']:
                    require(not e['error'],'SiLU result fault')
                    require(self.tile(tile_write=drain.Write(2,identity,ng,i,e['words']))['write_fire'],'SiLU output bank write')
                    self.tile();break
            else:raise AssertionError('SiLU loan failed to retire')
        self.control(1,2,identity,ng,cols)
        self.control(2,0,identity,ng,cols);self.control(2,1,identity,ng,cols)

    def drain(self, q):
        o=self.owner;require(o.tick(drain=q)['drain_fire'],'drain admission')
        initial=self.memory.counts['write_ack'];held=0;ack=None
        while True:
            require(time.monotonic()<self.deadline,'drain wall budget')
            p=o.ports();args=dict(write_command_ready=o.clock%5!=0,write_data_ready=o.clock%7!=0)
            if ack is not None:
                if held<2:held+=1;require(p['drain_result'] is None,'terminal before held ACK')
                else:args['write_ack']=ack
            e=o.tick(**args)
            if e.get('write_command_fire'):self.memory.write_event('command',e['write_command'])
            if e.get('write_data_fire'):
                self.memory.write_event('data',e['write_data'])
                if e['write_data'].last:
                    cmd=self.memory.pending[0];ack=drain.WriteAck(cmd.tag,False,cmd.beats*64)
            if e.get('write_ack_fire'):self.memory.write_event('ack',ack);ack=None
            require(not o.error and not o.drain_poison,'drain fault '+str(o.error))
            if e.get('drain_result_fire'):
                r=e['drain_result'];require(r.committed and r.status is None and r.ddr_write_bytes==16*q.cols*4,'drain terminal')
                require(ack is None and self.memory.pending is None and self.memory.counts['write_ack']>initial,'drain ACK retirement')
                self.counts['drains']+=1;return r

    def reduced(self, job, identity):
        for slot,(begin,end) in enumerate(((0,16),(16,32))):
            q=kmodel.KWindowRequest(job,identity,0,32,slot,bool(slot),k_begin=begin,k_end=end,block_id=slot+1,pair_reverse=True)
            r=self.window(q)
            require(r.executed_macs==16*4096 and r.useful_macs==16*16*32,'partial accepted MAC counters')
        require(shared_loan_edge(self.sum,self.loan,start=SumInvocation(identity,0,16,32))['start_fire'],'sum admission')
        for _ in range(3000):
            if shared_loan_edge(self.sum,self.loan,bank_ready=self.owner.clock%7!=0)['complete']:break
        else:raise AssertionError('actual partial sum did not complete')
        self.drain(DenseDrainRequest(job,identity,0,32))
        self.memory.publish(self.memory.region(job.dst,job.write_bytes))
        self.owner.tick(invalidate_lease=True)
        self.check()

    def ordinary(self, job, name):
        self.check();require(self.service.acquire(self.owner,'dense',job.tag),'ordinary Matrix acquire')
        adapter=self.service.dense_library(self.owner)
        target=self.out/name;target.mkdir()
        def output(kind,value):
            if kind=='terminal':
                require(value==(job.tag,None,job.write_bytes),'ordinary real terminal')
                self.memory.publish(self.memory.region(job.dst,job.write_bytes))
            else:self.memory.write_event(kind,value)
        report,_=public.down_driver.execute_dense(public.numeric.model,self.owner,adapter,self.memory,job,target,
            self.deadline,self.trace,a_source=self.memory.source(job),output_event=output,matrix_bridge=adapter)
        self.service.retire_owner_response(self.owner);self.service.release(self.owner)
        self.counts['matrix_steps']+=report['accepted']['accepted_steps'];self.check()
        return report


class SameInstanceModeTests(unittest.TestCase):
    def test_reduced_qkv_ordinary_o_ffn_silu_act_and_seeded_down(self):
        require(os.environ.get('MATRIX_SERVICE_LIBRARY'),'explicit receipt-verified Matrix library required')
        lib=verified_library()
        require(lib.td_reset()==0,'initial coordinated Matrix reset')
        p=C.POINTER(C.c_uint32);lib.sf_vector.argtypes=[p]*6;lib.sf_vector.restype=C.c_int
        require(lib.sf_reset()==0,'SiLU floating-point environment')
        with tempfile.TemporaryDirectory(prefix='dense_mode_sequence_') as out:
            h=Sequence(lib,out);mem=h.memory
            self.assertIs(drain,public.numeric.model)
            self.assertIs(kmodel.ALease,public.numeric.model.ALease)
            mem.add('input',0x100000,16,32,activation=0x3e000000)
            jobs=[]
            for i,role in enumerate(('q','k','v')):
                b,d=0x200000+i*0x10000,0x400000+i*0x10000
                mem.add(role+'_weight',b,32,32,weight=0x3d00);mem.add(role,d,16,32)
                jobs.append(Job(m=16,k=32,n=32,a=0x100000,b=b,dst=d,tag=10+i,activation_bf16=False,write_bytes=2048))
                h.reduced(jobs[-1],100+i)
                h.checkpoint('reduced_'+role)
            self.assertEqual((h.owner.k_a_fences,h.owner.a_fences),(3,0))
            print('mode chain: Q/K/V partials, shared Add, real drain ACKs retired',flush=True)
            mem.add('o_weight',0x500000,32,32,weight=0x3d00);mem.add('o',0x600000,16,32)
            o=Job(m=16,k=32,n=32,a=jobs[0].dst,b=0x500000,dst=0x600000,tag=20,activation_bf16=False,write_bytes=2048)
            ordinary=h.ordinary(o,'ordinary_o')
            h.checkpoint('ordinary_o')
            self.assertEqual(ordinary['accepted'].get('seed_acks',0),0)
            self.assertEqual((h.owner.k_a_fences,h.owner.a_fences),(3,0))
            print('mode chain: ordinary O consumed actual ACK-written Q source',flush=True)
            gate_base,up_base,act_base=0x1000000,0x1100000,0x1200000
            mem.add('gate_weight',0x2000000,32,8960,weight=0x3d00)
            mem.add('up_weight',0x2100000,32,8960,weight=0x3d00)
            act=mem.add('act',act_base,16,8960)
            identity=200
            gate=Job(m=16,k=32,n=8960,a=o.dst,b=0x2000000,dst=gate_base,tag=30,activation_bf16=False,write_bytes=16*8960*4)
            up=replace(gate,b=0x2100000,dst=up_base,tag=31)
            activation=drain.ActivationJob(m=16,a=gate_base,b=up_base,dst=act_base,tag=32,write_bytes=16*8960*4)
            activation.validate()
            for ng in range(0,8960,160):
                for slot,job in enumerate((gate,up)):
                    q=drain.FfnWindowRequest(job,identity,ng,160,slot,ng!=0 or slot==1)
                    h.window(q)
                    self.assertEqual((h.owner.k_a_fences,h.owner.a_fences),(3,1))
                    self.assertIs(type(h.owner.lease),public.numeric.model.ALease)
                h.silu(identity,ng,160)
                h.drain(drain.FfnDrainRequest(activation,identity,ng,160))
                h.check(lease=True)
            mem.publish(act)
            h.owner.tick(invalidate_lease=True);h.check()
            h.checkpoint('gate_up_silu_act_56_windows')
            self.assertEqual(len(act['acked'])*64,16*8960*4)
            self.assertEqual(h.loan.calls['silu_requests'],8960)
            self.assertEqual(h.loan.calls['silu_phase_issues'],6*8960)
            self.assertEqual(h.loan.calls['silu_results'],8960)
            self.assertEqual(h.loan.calls['add_results'],3*32)
            print('mode chain: all 56 K32 Gate/Up windows, same SiLU loan, N8960 Act ACKs retired',flush=True)
            mem.add('down_weight',0x3000000,8960,32,weight=0x3900);mem.add('down',0x4000000,16,32)
            downjob=Job(m=16,k=8960,n=32,a=act_base,b=0x3000000,dst=0x4000000,tag=40,activation_bf16=False,write_bytes=2048)
            down=h.ordinary(downjob,'seeded_down')
            h.checkpoint('seeded_down')
            self.assertEqual(down['accepted']['seed_acks'],3)
            self.assertEqual(down['prefix']['completed_sweeps'],3)
            self.assertEqual(down['prefix']['ack_bytes'],3*16384)
            self.assertEqual(down['actual_a_source']['sha256'],hashlib.sha256(act['raw']).hexdigest())
            self.assertEqual((h.owner.k_a_fences,h.owner.a_fences),(3,1))
            self.assertEqual(h.owner.total_window_a_load_fences,4)
            counters=h.service.report()['counters']
            self.assertEqual(counters['owner_acquires'],counters['owner_responses'])
            self.assertEqual(counters['dense_groups'],counters['dense_done'])
            self.assertEqual(counters['dense_steps'],h.counts['matrix_steps'])
            self.assertEqual(int(lib.matrix_dense_fmas()),h.counts['matrix_steps']*4096)
            self.assertEqual(counters['dense_seed_acks'],3)
            self.assertEqual(h.counts['matrix_steps'],27008)
            self.assertEqual(sum(p['accepted_delta']['matrix']['dense_steps'] for p in h.phases),counters['dense_steps'])
            h.check()
            print(json.dumps(dict(scope='SMALL_SYNTHETIC_SAME_INSTANCE_MODE_CHAIN_ONLY',phases=h.phases,
                totals=h.snapshot(),actual_elf_dense_fmas=int(lib.matrix_dense_fmas()),
                same_owner_banks_matrix_vector=True,owner_or_matrix_resets_between_modes=0,
                activation_full_n=8960,activation_local_window_cols=160,activation_windows=56,
                down_prefix_seed_restores=down['accepted']['seed_acks'],
                silu_backend='Existing sf_vector actual accepted payloads and six phase returns; not Chisel Scalar execution',
                whole_model_acceptance=False,rtl_executed=False),sort_keys=True),flush=True)
            print('PASS small synthetic same-instance mode chain: 27008 actual Matrix steps; 3 K A loads + 1 FFN A load; 3 seed/prefix restores; no owner/Matrix reset',flush=True)


if __name__=='__main__':unittest.main()

"""Real typed-control/TileBank cold equivalence; no arithmetic library or compile.

Opaque result wire values exercise transport, not numerical correctness. Legacy
imports may load installed numeric packages; this is not a stdlib-only claim.
"""
import copy
from collections import Counter, deque
from dataclasses import replace
import hashlib
import inspect
import json
from pathlib import Path
import random
import sys
import types
import unittest

from .owner import DenseIdleOwnerV1, DenseReductionOwner, diagnostics, original
from candidates.qwen2_resident_matrix.dense_block_reduce.dense_drain import DenseDrainRequest

FLAGS = dict(enable_dense_drain=True, enable_k_window=True, enable_ffn_window=True,
             enable_ffn_tiles=True, enable_ffn_drain=True)
COUNTS = Counter()


def make(kind):
    return kind(original.PrefixWorkspace(0x10000000, 786432, 11), **FLAGS)


def graph(value):
    """Exact recursive values/types/order and mutable/object alias topology.

    Normalize only old/new root class correspondence; no counters or fields are
    omitted, and zero Counter entries remain present in insertion order.
    """
    seen = {}
    def visit(x):
        t = type(x)
        if x is None or t in (bool, int, float, str, bytes):
            return (t.__name__, x)
        if isinstance(x, types.FunctionType):
            return ('function', x.__module__, x.__qualname__)
        if isinstance(x, types.MethodType):
            return ('method', visit(x.__func__), visit(x.__self__))
        key = id(x)
        if key in seen:
            return ('ref', seen[key])
        n = len(seen); seen[key] = n
        name = 'DenseOwner' if t in (DenseReductionOwner, DenseIdleOwnerV1) else (t.__module__, t.__qualname__)
        if isinstance(x, dict):
            body = tuple((visit(k), visit(v)) for k, v in x.items())
        elif isinstance(x, (list, tuple, deque)):
            body = tuple(visit(v) for v in x)
        elif isinstance(x, (set, frozenset)):
            body = tuple(visit(v) for v in sorted(x, key=repr))
        elif t is object:
            body = ()
        elif hasattr(x, '__dict__'):
            body = visit(vars(x))
        else:
            raise AssertionError(('unsupported complete-state value', t, repr(x)))
        return ('object', n, name, body)
    return visit(value)


def outcome(fn, *args, **kwargs):
    try:
        return ('return', fn(*args, **kwargs))
    except Exception as e:
        # Exception owner-name spelling follows the permitted root-class
        # correspondence; all other message content remains exact.
        message = str(e).replace("'DenseIdleOwnerV1'", "'DenseReductionOwner'")
        return ('error', type(e).__module__, type(e).__qualname__, message)


class Pair:
    def __init__(self, new_class=DenseIdleOwnerV1):
        self.old, self.new = make(DenseReductionOwner), make(new_class)
        self.edges = 0

    def modify(self, fn):
        fn(self.old); fn(self.new)
        return self

    def tick(self, *args, route=None, **kwargs):
        before = diagnostics(self.new)
        old_refs = (self.old.a_banks.reads, self.old.a_banks.writes,
                    self.old.b_banks.reads, self.old.b_banks.writes)
        new_refs = (self.new.a_banks.reads, self.new.a_banks.writes,
                    self.new.b_banks.reads, self.new.b_banks.writes)
        # A source-level external profiler verifies real calls without replacing
        # any modeled method. This is cold testing only, never an A/B timer.
        calls = Counter()
        targets = {DenseReductionOwner.tick.__code__: 'fallback',
                   original.window.TileBankModel.tick.__code__: 'tile',
                   DenseReductionOwner.ports.__code__: 'ports'}
        def profile(frame, event, arg):
            if event == 'call' and frame.f_code in targets:
                calls[targets[frame.f_code]] += 1
        old = outcome(self.old.tick, *args, **kwargs)
        sys.setprofile(profile)
        try:
            new = outcome(self.new.tick, *args, **kwargs)
        finally:
            sys.setprofile(None)
        assert graph((old, self.old, old_refs)) == graph((new, self.new, new_refs)), ('first divergence', self.edges, kwargs, old, new)
        assert graph(outcome(self.old.ports)) == graph(outcome(self.new.ports))
        after = diagnostics(self.new)
        if route:
            assert after[route] == before[route] + 1, (route, before, after)
            assert after['fast' if route == 'fallback' else 'fallback'] == before['fast' if route == 'fallback' else 'fallback']
            # Positional-call rejection happens at Python argument binding,
            # before a profile 'call' event can enter the keyword-only original.
            expected_entry = int(route == 'fallback' and not args)
            assert calls['fallback'] == expected_entry, (route, calls)
        if route == 'fast':
            assert calls['ports'] == 1 and calls['tile'] == 1, calls
            e = new[1]
            assert e['a_reads'] is e['tile']['reads'] and e['a_writes'] is e['tile']['writes']
            assert e['b_reads'] is not e['b_writes'] and e['b_reads'] is not self.new.b_banks.reads
            assert new_refs[0] is not self.new.a_banks.reads and new_refs[1] is not self.new.a_banks.writes
            assert new_refs[2] is self.new.b_banks.reads and new_refs[3] is self.new.b_banks.writes
            assert not {'matrix_done_fire', 'write_ack_fire', 'operand_response', 'reserved_after', 'release_verified'} & e.keys()
        self.edges += 1; COUNTS['compared_edges'] += 1
        COUNTS['profiled_original_tile_calls'] += calls['tile']
        COUNTS['profiled_original_fallback_calls'] += calls['fallback']
        COUNTS['fast' if after['fast'] > before['fast'] else 'fallback'] += 1
        if new[0] == 'error':
            COUNTS['matched_exceptions'] += 1
        return old[1] if old[0] == 'return' else old

    def __getattr__(self, name):
        return getattr(self.old, name)


def historical(o, seed):
    rng = random.Random(seed)
    choices = (0, 1, 731, 1 << 75)
    for name, value in list(vars(o).items()):
        if type(value) is int:
            setattr(o, name, choices[rng.randrange(len(choices))])
    o.job = original.Job(m=16,k=32,n=32,tag=29,write_bytes=2048)
    o.group_started = o.group_done = True
    o.terminal_issued = {0, 3, 17}
    o.seed_acked = {1, 9}
    o.traffic.update(a_read_bytes=65536, b_read_bytes=987654321, windows=9)
    o.traffic['historical_zero'] = 0
    o.tiles.cycle = choices[seed % 4]
    for name in o.tiles.counters:
        o.tiles.counters[name] = choices[rng.randrange(len(choices))]
    o.tiles.counters['historical_zero'] = 0
    for i in range(3):
        o.tiles.tags[i] = original.window.Tag(identity=i+71, ng=i*32, rows=16,
            cols=32, produced=32, consumed=32, live=False, sealed=False, matrix_producer_order=bool(i%2))
    for banks in (o.a_banks, o.b_banks):
        for bank in range(16):
            for word in (0, banks.depth//2, banks.depth-1):
                banks.words[bank][word] = rng.getrandbits(256)
        banks.reads.update({3:17, 11:31}); banks.writes.update({7:19})


def set_field(name, value):
    return lambda o: setattr(o, name, copy.deepcopy(value))


def boom():
    raise RuntimeError('injected original dynamic ports fault')


class IdleTests(unittest.TestCase):
    def test_fresh_and_dirty_historical_properties(self):
        p = Pair()
        first = p.tick(route='fast'); second = p.tick(route='fast')
        self.assertIsNot(first, second)
        for seed in range(12):
            p = Pair().modify(lambda o: historical(o, seed))
            for _ in range(3): p.tick(route='fast')
            p.tick(job=None, route='fallback')
            p.tick(route='fast')

    def test_each_guard_and_missing_field_falls_back(self):
        variants = [set_field(k, False) for k in FLAGS]
        variants += [set_field(k, 1) for k in FLAGS]
        variants += [set_field(k, object()) for k in ('window_request','window_result','drain_request',
            'drain_result','drain_expected','lease','read_active','a_hold','a_rmw_pending',
            'pending','accepted_write','final_value','seed_hold')]
        variants += [set_field('state',s) for s in ('locked','finish','execute','drain','a_load')]
        variants += [set_field(k,v) for k,v in (('error','fault'),('drain_poison',True),
            ('drain_phase','held'),('fifo',deque([1])),('fifo',[]),('write_state','ack'),
            ('seed_outstanding',True),('seed_state','ack'),('restoring',True),
            ('group_started',True),('group_started',1),('group_done',1),('clock',True))]
        variants += [lambda o:setattr(o.tiles,'poison',True),
            lambda o:setattr(o.tiles,'pending',('read',original.Read(0,1,0,0),768,0,(0,)*16)),
            lambda o:setattr(o.tiles,'response',original.window.Response(0,1,0,0,(0,)*16)),
            lambda o:setattr(o.tiles.tags[0],'live',True),
            lambda o:setattr(o.tiles,'cycle',True), lambda o:setattr(o.tiles,'tags',tuple(o.tiles.tags))]
        for fn in variants:
            with self.subTest(fn=fn): Pair().modify(fn).tick(route='fallback')
        for name in ('window_result','accepted_write','clock','drain_phase'):
            Pair().modify(lambda o:delattr(o,name)).tick(route='fallback')
        for name in ('tags','banks','cycle'):
            Pair().modify(lambda o:delattr(o.tiles,name)).tick(route='fallback')

    def test_explicit_inputs_and_fault_precedence(self):
        job = original.Job(m=16,k=32,n=32,write_bytes=2048)
        window = original.KWindowRequest(job,7,0,32,0,k_begin=0,k_end=16,block_id=1)
        drain = DenseDrainRequest(job,7,0,32)
        control = original.Control(0,0,7,0,16,32)
        cases = [dict(job=None),dict(read_command_ready=True),dict(unknown_key=object()),
            dict(job=job),dict(job=replace(job,k=1)),dict(job='invalid'),
            dict(window=window),dict(window='invalid'),dict(drain=drain),dict(drain='invalid'),
            dict(tile_control=control),dict(tile_read=original.Read(0,7,0,0)),
            dict(tile_write=original.Write(0,7,0,0,(0,)*16)),
            dict(tile_control=control,window=window,drain=drain,job=job),
            dict(loan_busy=True,tile_control=control),dict(loan_request=True),
            dict(dense_reads=[(0,0)]),dict(dense_writes=[(0,0,7)]),dict(invalidate_lease=True),
            dict(abort=True),dict(local_reset=True),dict(coordinated_reset=True),
            dict(coordinated_reset='malformed'),dict(write_ack=original.drain.WriteAck(99)),
            dict(read_beat=original.ReadBeat(99,(0,)*32,True)),
            dict(result=original.MatrixResult(0,((0,)*256,)*16)),dict(matrix_done=original.MatrixDone(99)),
            dict(abort=True,write_ack=original.drain.WriteAck(99))]
        for args in cases:
            with self.subTest(args=args): Pair().tick(route='fallback',**args)
        Pair().tick(1,route='fallback')
        p=Pair().modify(lambda o:setattr(o.tiles,'pending',('write',original.Write(0,7,0,0,(0,)*16),768,0,(0,)*16)))
        p.tick(coordinated_reset=True,route='fallback');p.tick(route='fast')
        # Poison must preserve a held ordinary terminal's original payload.
        def held_poison(o):
            o.job=job;o.state='finish';o.write_bytes=2048
            o.drain_poison=True;o.tiles.poison=True;o.tiles.reason='injected poison'
        p=Pair().modify(held_poison)
        offered=p.old.ports()['response']
        for _ in range(2):
            e=p.tick(response_ready=False,route='fallback')
            self.assertEqual(e['response'],offered);self.assertFalse(e['response_fire'])
        e=p.tick(route='fallback')
        self.assertTrue(e['response_fire']);self.assertEqual(e['response'],offered)
        self.assertEqual(p.new.state,'locked')

    def test_swapped_identity_and_instance_faults(self):
        for fn in (lambda o:setattr(o,'tiles',original.window.TileBankModel(o.a_banks)),
                   lambda o:setattr(o,'a_banks',original.down.Banks(1376)),
                   lambda o:setattr(o,'b_banks',original.down.Banks(160)),
                   lambda o:setattr(o.tiles,'banks',original.down.Banks(1376)),
                   lambda o:setattr(o,'ports',boom),
                   lambda o:setattr(o,'_write_data',boom),
                   lambda o:setattr(o.tiles,'tick',boom),
                   lambda o:setattr(o.a_banks,'begin_cycle',boom)):
            Pair().modify(fn).tick(route='fallback')
        # Inject only into the new experimental class, never existing classes.
        for name, value in (('ports', staticmethod(boom)), ('_read_command', boom)):
            p=Pair()
            setattr(p.old,name,value.__get__(p.old,DenseReductionOwner))
            setattr(DenseIdleOwnerV1,name,value)
            try:
                a=outcome(p.old.tick);b=outcome(p.new.tick)
                self.assertEqual(a,b)
                self.assertEqual(diagnostics(p.new)['fallback'],1)
            finally:
                delattr(DenseIdleOwnerV1,name)
        class Foreign(DenseIdleOwnerV1): pass
        p=Pair(new_class=Foreign)
        # The foreign root class is intentionally different, so compare its
        # dictionary and output explicitly while retaining every model field.
        before=diagnostics(p.new);a=p.old.tick();b=p.new.tick()
        self.assertEqual(graph((a,vars(p.old))),graph((b,vars(p.new))))
        self.assertEqual(diagnostics(p.new)['fallback'],before['fallback']+1)

    def test_actual_ordinary_control_retains_historical_descriptor(self):
        p=Pair();p.tick(route='fast')
        job=original.Job(m=16,k=32,n=32,tag=19,write_bytes=2048)
        p.tick(job=job,route='fallback')
        read=ack=command=None;results=deque();index=0;terminal=None
        for _ in range(2000):
            o=p.old;args={}
            if read is not None:args['read_beat']=original.ReadBeat(read.tag,(0x3f80,)*32,True)
            if results:args['result']=results[0]
            if o.group_started and not o.group_done and o.group_accepted_steps==32 and o.results_received==1:
                args['matrix_done']=original.MatrixDone(job.tag)
            if ack is not None:args['write_ack']=ack
            e=p.tick(route='fallback',**args)
            if e['read_fire']:read=None
            if e['read_command_fire']:read=e['read_command']
            if e['result_fire']:results.popleft()
            if e['step_fire'] and e['step'].last:
                results.append(original.MatrixResult(0,tuple(tuple(0x3f000000+b*256+c for c in range(256)) for b in range(16))))
            if e['write_command_fire']:command=e['write_command'];index=0
            if e['write_data_fire']:
                index+=1
                if e['write_data'].last:ack=original.drain.WriteAck(command.tag,nbytes=command.beats*64)
            if e['write_ack_fire']:ack=None
            if e['response_fire']:terminal=e['response'];break
        self.assertEqual(terminal,(19,None,2048))
        self.assertIsNotNone(p.new.accepted_write)
        # Conservative V1 must reject this historical ordinary descriptor,
        # although its ACK really completed. It must never clear it to hit.
        p.tick(route='fallback')
        from candidates.qwen2_resident_matrix.dense_block_reduce.test_k_window import Harness
        q=original.KWindowRequest(job,23,0,32,0,k_begin=0,k_end=16,block_id=1)
        h=Harness(q,p);self.assertTrue(h.finish().committed)
        p.tick(coordinated_reset=True,route='fallback');p.tick(route='fast')
        COUNTS['actual_ordinary_to_window_transitions']+=1

    def test_real_tile_lifecycle_then_dense_drain_historical_hit(self):
        p=Pair();p.tick(route='fast')
        job=original.Job(m=16,k=32,n=32,tag=13,write_bytes=2048)
        q=DenseDrainRequest(job,7,0,32)
        c=original.Control(0,2,7,0,16,32)
        self.assertTrue(p.tick(tile_control=c,route='fallback')['tile']['ctl_fire'])
        for index in range(32):
            words=tuple(0x3e000000+lane*16384+index for lane in range(16))
            self.assertTrue(p.tick(tile_write=original.Write(2,7,0,index,words),route='fallback')['tile']['write_fire'])
            self.assertTrue(p.tick(route='fallback')['tile']['rmw_commit'])
        self.assertTrue(p.tick(tile_control=replace(c,op=1),route='fallback')['tile']['ctl_fire'])
        self.assertTrue(p.tick(drain=q,route='fallback')['drain_fire'])
        command=ack=None;index=0;held=0;terminal=None
        for _ in range(2000):
            kwargs={}
            if ack is not None:
                if held<3: held+=1
                else: kwargs['write_ack']=ack
            e=p.tick(route='fallback',**kwargs)
            if e['write_command_fire']: command=e['write_command'];index=0
            if e['write_data_fire']:
                index+=1
                if e['write_data'].last: ack=original.drain.WriteAck(command.tag,nbytes=command.beats*64)
            if e['write_ack_fire']: ack=None
            if e['drain_result_fire']: terminal=e['drain_result'];break
        self.assertIsNotNone(terminal);self.assertTrue(terminal.committed)
        self.assertEqual(terminal.ddr_write_bytes,2048);self.assertEqual(held,3)
        self.assertGreater(p.new.write_sequence,0);self.assertGreater(p.new.tiles.tags[2].consumed,0)
        p.tick(route='fast');p.tick(route='fast')
        COUNTS['actual_post_drain_fast_hits']+=2

    def test_real_window_lifecycle_release_reset_relaunch(self):
        from candidates.qwen2_resident_matrix.dense_block_reduce.test_k_window import Harness
        p=Pair();job=original.Job(m=16,k=32,n=32,tag=17,write_bytes=2048)
        q=original.KWindowRequest(job,9,0,32,0,k_begin=0,k_end=16,block_id=1)
        h=Harness(q,p)
        result=h.finish();self.assertTrue(result.committed)
        # Real tile consumption and release, then explicit lease invalidation.
        for index in range(32):
            p.tick(tile_read=original.Read(0,9,0,index),route='fallback')
            p.tick(route='fallback');p.tick(route='fallback')
        p.tick(tile_control=original.Control(2,0,9,0,16,32),route='fallback')
        p.tick(invalidate_lease=True,route='fallback');p.tick(route='fast')
        p.tick(coordinated_reset=True,route='fallback');p.tick(route='fast')
        p.tick(window=q,route='fallback')
        p.tick(abort=True,route='fallback')
        p.tick(coordinated_reset=True,route='fallback');p.tick(route='fast')


if __name__ == '__main__':
    result=unittest.main(exit=False)
    print(json.dumps(dict(status='PASS' if result.result.wasSuccessful() else 'FAIL',
                         scope='real typed-control behavior, opaque wire transport, no numerical execution',
                         counts=dict(COUNTS)),sort_keys=True))
    raise SystemExit(not result.result.wasSuccessful())

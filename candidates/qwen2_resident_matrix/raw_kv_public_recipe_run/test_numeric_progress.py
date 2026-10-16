"""Cold metadata/accepted-event fixtures only; no numerical or native execution."""
import ast
import hashlib
import copy
from dataclasses import asdict, dataclass, is_dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from . import numeric_progress as p

CONTEXT={'schema':1,'checkout_commit':'a'*40,'deadline_ns':1}
SOURCES={'fixed.py':'b'*64}

class ProgressTests(unittest.TestCase):
    def fixture(self,root):return p.Writer(root,CONTEXT,SOURCES)

    def test_phase_return_is_never_validation_or_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=self.fixture(root)
            with w.phase('setup_admission'):pass
            value=p.read(root,CONTEXT,SOURCES)
            self.assertEqual(value['phase_state'],'RETURNED')
            self.assertFalse(value['numerical_acceptance']);self.assertFalse(value['postflight_complete'])
            self.assertNotIn('status',value);self.assertNotIn('PASS',json.dumps(value))
            self.assertLess((root/p.FILE).stat().st_size,p.LIMIT)

    def test_unknown_fields_and_fake_pass_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=self.fixture(Path(tmp))
            for key,value in [('payload',[1,2]),('status','PASS'),('numerical_acceptance',True),
                              ('postflight_complete',True),('operator','/private/SECRET'),('phase','SUCCESS'),
                              ('stage','tensor'),('event','SUCCESS'),('schema',True),('ordinal',True),('capped',1)]:
                bad=copy.deepcopy(w.value);bad[key]=value
                with self.subTest(key=key),self.assertRaises((ValueError,TypeError)):p.validate(bad,w.identity)
            bad=copy.deepcopy(w.value);bad['counts']['array']=[1,2]
            with self.assertRaises(ValueError):p.validate(bad,w.identity)

    def test_nonfinite_boolean_overflow_and_unknown_count_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=self.fixture(Path(tmp))
            for key in ('elapsed_seconds','phase_elapsed_seconds'):
                for value in (float('nan'),float('inf'),-1,3421,True):
                    bad=copy.deepcopy(w.value);bad[key]=value
                    with self.subTest(key=key,value=value),self.assertRaises(ValueError):p.validate(bad,w.identity)
            for key,bound in p.COUNTS.items():
                for value in (True,-1,bound+1,1.5):
                    bad=copy.deepcopy(w.value);bad['counts'][key]=value
                    with self.subTest(key=key,value=value),self.assertRaises(ValueError):p.validate(bad,w.identity)

    def test_invalid_wire_json_is_bounded_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=self.fixture(root)
            raw=(root/p.FILE).read_bytes()
            cases=[b'{',b'['+b'0,'*p.LIMIT+b'0]',raw.replace(b'"schema":1',b'"schema":1,"schema":1'),
                   raw.replace(b'"elapsed_seconds":',b'"elapsed_seconds":NaN,"duplicate":'),
                   raw.replace(b'"elapsed_seconds":',b'"elapsed_seconds":1e999,"duplicate":')]
            for blob in cases:
                (root/p.FILE).write_bytes(blob)
                with self.subTest(length=len(blob)),self.assertRaises((ValueError,UnicodeError)):p.read(root,CONTEXT,SOURCES)

    def test_context_source_writer_mismatch_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=self.fixture(root)
            for context,sources in ((dict(CONTEXT,deadline_ns=2),SOURCES),(CONTEXT,{'changed.py':'c'*64})):
                with self.assertRaises(ValueError):p.read(root,context,sources)
            bad=copy.deepcopy(w.value);bad['writer_sha256']='c'*64
            (root/p.FILE).write_bytes(p.assets.encoded(bad))
            with self.assertRaises(ValueError):p.read(root,CONTEXT,SOURCES)
            (root/p.FILE).unlink();(root/p.FILE).symlink_to(root/p.OWNER)
            with self.assertRaises(ValueError):p.read(root,CONTEXT,SOURCES)

    def test_duplicate_and_stale_writer_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=self.fixture(root)
            with self.assertRaises(FileExistsError):self.fixture(root)
            saved=(root/p.FILE).read_bytes();other=root/'replacement'
            other.write_bytes((root/p.OWNER).read_bytes());other.replace(root/p.OWNER)
            with self.assertRaises(ValueError):w.emit('PHASE')
            self.assertEqual((root/p.FILE).read_bytes(),saved)

    def test_intervening_snapshot_change_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=self.fixture(root)
            for blob in (b'{}',b'x'*(p.LIMIT+1)):
                (root/p.FILE).write_bytes(blob)
                with self.assertRaises(ValueError):w.emit('PHASE')
                self.assertEqual((root/p.FILE).read_bytes(),blob)

    def test_partial_atomic_file_preserves_last_complete_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=self.fixture(root);old=p.read(root,CONTEXT,SOURCES)
            pending=root/(p.FILE+'.pending');pending.write_bytes(b'{"payload":')
            self.assertEqual(p.read(root,CONTEXT,SOURCES),old)
            with self.assertRaises(ValueError):w.emit('PHASE')
            (root/p.FILE).unlink()
            with self.assertRaises(FileNotFoundError):p.read(root,CONTEXT,SOURCES)
            self.assertEqual(pending.read_bytes(),b'{"payload":')

    def test_elapsed_sequence_phase_and_counts_are_monotonic(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=self.fixture(Path(tmp));previous=copy.deepcopy(w.value)
            with w.phase('setup_admission'):pass
            self.assertGreater(w.value['elapsed_seconds'],previous['elapsed_seconds'])
            for changes in ({'sequence':w.value['sequence']+2},{'elapsed_seconds':0},
                            {'phase':'context_check'},{'writer_sha256':'e'*64}):
                bad=copy.deepcopy(w.value);bad['sequence']+=1;bad.update(changes)
                with self.subTest(changes=changes),self.assertRaises(ValueError):p.validate(bad,w.identity,previous=w.value)
            with patch.object(p.time,'monotonic_ns',return_value=w.started-1):
                with self.assertRaises(ValueError):w.emit('PHASE')

    def test_write_cap_and_existing_metadata_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);sentinels=('context.json','source_hashes.json','numeric.complete.json')
            for name in sentinels:(root/name).write_bytes(b'IMMUTABLE_SENTINEL')
            w=self.fixture(root)
            for _ in range(p.MAX_WRITES+4):w.emit('PHASE')
            self.assertEqual(w.value['sequence'],p.MAX_WRITES);self.assertTrue(w.value['capped'])
            self.assertEqual(p.read(root,CONTEXT,SOURCES)['sequence'],p.MAX_WRITES)
            for name in sentinels:self.assertEqual((root/name).read_bytes(),b'IMMUTABLE_SENTINEL')

    def test_session_resets_after_exception_and_unattached_hooks_are_noops(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(TimeoutError):
                with p.session(Path(tmp),CONTEXT,SOURCES):raise TimeoutError()
            self.assertIsNone(p._ACTIVE)
            p.stage('none');p.host('HEARTBEAT',0,0,0,0,0,0)

    def test_existing_host_events_are_forwarded_unchanged_without_payload_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);forwarded=[];trace=SimpleNamespace(event=lambda value:forwarded.append(value))
            with p.session(root,CONTEXT,SOURCES) as writer:
                with writer.phase('actual_execute'):
                    p.observe_trace(trace);p.stage('public_suffix')
                    for tick,flags in enumerate(({'request_fire':True},{'owner_result_fire':True},{'completion_fire':True}),1):
                        edge=dict(request_fire=False,owner_result_fire=False,completion_fire=False,result_fire=False,
                            group_request=None,ordinary_request=SimpleNamespace(tag=(7<<16)|12),completion=SimpleNamespace(pc=12))
                        edge.update(flags)
                        event=dict(kind='public_host',tick=tick,edge=edge,private_payload='/SECRET/tensor=[1,2]')
                        trace.event(event);self.assertIs(forwarded[-1],event)
                    record=p.read(root,CONTEXT,SOURCES)
                    self.assertEqual((record['operator'],record['ordinal']),('Attention',12))
                    self.assertEqual(record['counts'],dict(host_model_ticks=3,request_fire=1,owner_result_fire=1,completion_fire=1,result_fire=0))
                    self.assertNotIn('SECRET',json.dumps(record))
            self.assertFalse(p.read(root,CONTEXT,SOURCES)['numerical_acceptance'])

    def test_group_request_uses_actual_gate_tag_and_completion_pc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);trace=SimpleNamespace(event=lambda value:None)
            with p.session(root,CONTEXT,SOURCES) as writer:
                with writer.phase('actual_execute'):
                    p.observe_trace(trace)
                    edge=dict(request_fire=True,owner_result_fire=False,completion_fire=False,result_fire=False,
                        group_request=SimpleNamespace(gate=SimpleNamespace(tag=(9<<16)|16)),ordinary_request=None,completion=None)
                    trace.event(dict(kind='public_host',tick=4,edge=edge))
                    self.assertEqual((writer.value['operator'],writer.value['ordinal']),('FFN',16))

    def test_real_tiny_child_timeout_keeps_atomic_phase_without_postflight(self):
        # CONTROL_ONLY sleeper uses the production process-group cleanup, no numerical imports.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            script="""from pathlib import Path
import time
from candidates.qwen2_resident_matrix.raw_kv_public_recipe_run import numeric_progress as p
with p.session(Path(%r),%r,%r) as w:
    with w.phase('snapshot_prepare'):
        time.sleep(30)
""" % (str(root),CONTEXT,SOURCES)
            with (root/'private.log').open('wb') as log,self.assertRaises(subprocess.TimeoutExpired):
                p.setup.run_group([sys.executable,'-B','-c',script],cwd=Path(__file__).resolve().parents[3],
                    env=dict(os.environ),log=log,timeout=.4,grace=.2)
            value=p.read(root,CONTEXT,SOURCES)
            self.assertEqual((value['phase'],value['phase_state']),('snapshot_prepare','ENTERED'))
            self.assertFalse(value['numerical_acceptance']);self.assertFalse(value['postflight_complete'])
            self.assertFalse((root/'numeric.complete.json').exists())

ROOT = Path(p.__file__).resolve().parents[3]
# Historical original-source identities, also checked against the existing fresh
# pins. These are independent of the new observer implementation and its tests.
ORIGINAL_SINK_SOURCES = {
    'candidates/qwen2_resident_matrix/ffn_drain/check_numeric.py':
        '7e552390364b985e112a350387623204d76fd17cc6ce146afb42ca2bc8b825be',
    'candidates/qwen2_resident_matrix/ffn_fullgroup/check_numeric.py':
        '7fd62ea5f59af4ba6da36d74b289e0aba85b1eb35b1d3e060a7d8e95d0b55336',
}


class OriginalTraceRegressionTests(unittest.TestCase):
    def original_trace_type(self):
        pins = p.assets.read_json(ROOT / 'candidates/qwen2_resident_matrix/raw_kv_public_fresh/pins.json')
        namespace = {'json': json, 'hashlib': hashlib, 'asdict': asdict, 'is_dataclass': is_dataclass}
        symbols = (
            ('candidates/qwen2_resident_matrix/ffn_drain/check_numeric.py', ast.FunctionDef, 'jsonable'),
            ('candidates/qwen2_resident_matrix/ffn_fullgroup/check_numeric.py', ast.ClassDef, 'CappedTrace'),
        )
        for relative, kind, name in symbols:
            path = ROOT / relative
            raw = path.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), ORIGINAL_SINK_SOURCES[relative])
            self.assertEqual(pins['source_sha256'][relative], ORIGINAL_SINK_SOURCES[relative])
            selected = [node for node in ast.parse(raw).body if isinstance(node, kind) and node.name == name]
            self.assertEqual(len(selected), 1)
            # Execute only this exact original symbol; never its module imports.
            exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
            if name == 'jsonable':
                namespace['drain_check'] = SimpleNamespace(jsonable=namespace['jsonable'])
        return namespace['CappedTrace']

    def test_original_trace_hash_bytes_and_counts_are_unchanged(self):
        Trace = self.original_trace_type()

        @dataclass(frozen=True)
        class ControlOnlyRequest:
            tag: int

        @dataclass(frozen=True)
        class ControlOnlyCompletion:
            pc: int

        @dataclass(frozen=True)
        class ControlOnlyGroup:
            gate: ControlOnlyRequest

        # Synthetic accepted-event schedule only. Attention is one ordinary
        # request tagged PC12 with three completions; FFN uses gate PC16.
        jobs = [(pc, (pc,), False) for pc in range(10)]
        jobs += [(12, (10, 11, 12), False)]
        jobs += [(pc, (pc,), False) for pc in range(13, 16)]
        jobs += [(16, (16, 17, 18), True), (19, (19,), False), (20, (20,), False)]
        self.assertEqual(len(jobs), 17)

        # Exercise both the full original stream and its original truncation.
        for cap in (512, 131072):
            with self.subTest(cap=cap), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                baseline = Trace(root / 'baseline.trace', cap=cap)
                observed = Trace(root / 'observed.trace', cap=cap)
                try:
                    with p.session(root, CONTEXT, SOURCES) as writer:
                        with writer.phase('actual_execute'):
                            original_event = observed.event
                            forwarded = []

                            def checked_original(value):
                                forwarded.append(value)
                                return original_event(value)

                            observed.event = checked_original
                            p.observe_trace(observed)
                            tick = 0

                            def replay(value):
                                self.assertIs(observed.event(value), baseline.event(value))
                                self.assertIs(forwarded[-1], value)
                                self.assertEqual(observed.report(), baseline.report())

                            def host_edge(flag, request_pc=None, completion_pc=None, grouped=False):
                                nonlocal tick
                                tick += 1
                                request = None if request_pc is None else ControlOnlyRequest((9 << 16) | request_pc)
                                edge = dict(request_fire=False, owner_result_fire=False,
                                    completion_fire=False, result_fire=False,
                                    group_request=ControlOnlyGroup(request) if grouped else None,
                                    ordinary_request=None if grouped else request,
                                    completion=None if completion_pc is None else ControlOnlyCompletion(completion_pc))
                                edge[flag] = True
                                replay(dict(kind='public_host', tick=tick, edge=edge,
                                    private_payload='CONTROL_ONLY_PRIVATE_SENTINEL'))

                            for request_pc, completion_pcs, grouped in jobs:
                                host_edge('request_fire', request_pc=request_pc, grouped=grouped)
                                self.assertEqual(writer.value['ordinal'], request_pc)
                                host_edge('owner_result_fire')
                                for pc in completion_pcs:
                                    host_edge('completion_fire', completion_pc=pc)
                                    self.assertEqual(writer.value['ordinal'], pc)
                                    sequence = writer.value['sequence']
                                    replay(dict(kind='control_only_owner', tick=tick, scalar_marker=pc))
                                    self.assertEqual(writer.value['sequence'], sequence)
                            host_edge('result_fire')
                            self.assertEqual(writer.value['counts'], dict(host_model_ticks=56,
                                request_fire=17, owner_result_fire=17, completion_fire=21, result_fire=1))
                            self.assertEqual(writer.value['sequence'], 58)
                            self.assertNotIn('CONTROL_ONLY_PRIVATE_SENTINEL', json.dumps(p.read(root, CONTEXT, SOURCES)))
                            self.assertEqual(observed.report()['records'], 77)
                            self.assertEqual(observed.truncated, cap == 512)
                    self.assertEqual((root / 'observed.trace').read_bytes(), (root / 'baseline.trace').read_bytes())
                finally:
                    observed.close()
                    baseline.close()

    def test_original_sink_exception_and_return_are_unchanged(self):
        class SentinelError(Exception):
            pass

        failure = SentinelError('CONTROL_ONLY')
        token = object()
        with tempfile.TemporaryDirectory() as tmp:
            with p.session(Path(tmp), CONTEXT, SOURCES) as writer:
                before = writer.value['sequence']
                trace = SimpleNamespace(event=lambda value: token)
                p.observe_trace(trace)
                self.assertIs(trace.event({'kind': 'control_only_owner'}), token)
                self.assertEqual(writer.value['sequence'], before)

                def fail(value):
                    raise failure

                trace = SimpleNamespace(event=fail)
                p.observe_trace(trace)
                # Malformed Host metadata would raise differently if observation
                # ran first. The original exact exception must win unchanged.
                with self.assertRaises(SentinelError) as caught:
                    trace.event({'kind': 'public_host'})
                self.assertIs(caught.exception, failure)
                self.assertEqual(writer.value['sequence'], before)


if __name__=='__main__':unittest.main()

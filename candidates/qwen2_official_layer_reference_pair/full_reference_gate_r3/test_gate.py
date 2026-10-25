"""Pure stdlib, synthetic-data and mock tests. Never launch the real worker."""
import ast
import copy
import hashlib
import importlib.abc
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

class DenyML(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch', 'numpy', 'transformers'}:
            raise AssertionError('ML import forbidden in static/mock tests: ' + fullname)
sys.meta_path.insert(0, DenyML())
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gate_common as common
import run_gate as launcher
import worker
import prepare_gate
import validate_outputs as validation
import network_policy
PAIR_DIR = HERE.parent / 'capture_pair_r3'
pair_spec = importlib.util.spec_from_file_location('static_mock_capture_pair', PAIR_DIR / 'capture_pair.py')
pair = importlib.util.module_from_spec(pair_spec)
pair_spec.loader.exec_module(pair)


def proposal():
    return {'limits': copy.deepcopy(common.LIMITS), 'reviewed_runtime_profile': {'test': 'mock'},
            'loopback_probe': {'test': 'mock'}, 'capture_sources': {'test': 'mock'},
            'capture_profile': copy.deepcopy(pair.PAIR_PROFILE),
            'scope': {'model_forward': 'two complete Qwen2DecoderLayer.forward calls on one identical instance: baseline then observed'}}


def review_approval(config):
    review = {'schema': 1, 'status': 'APPROVED_FOR_SINGLE_M16_OFFICIAL_REFERENCE_PAIR',
              'config_sha256': 'c' * 64, 'limits': config['limits'], 'blockers': [],
              'model_import_executed': False, 'reviewer': 'synthetic-independent-reviewer',
              'runtime_profile': config['reviewed_runtime_profile'], 'loopback_probe': config['loopback_probe'],
              'capture_sources': config['capture_sources'], 'capture_profile': config['capture_profile']}
    approval = {'schema': 1, 'action': 'single_official_m16_full_layer_reference_pair',
                'config_sha256': 'c' * 64, 'review_sha256': 'r' * 64,
                'maximum_invocations': 1, 'no_retry': True, 'issued_by': 'root',
                'exclusive_reference_slot': True, 'run_id': 'synthetic_test_only', 'go': 'GO', 'scope': config['scope']}
    return review, approval


class ApprovalTests(unittest.TestCase):
    def test_valid_synthetic_review_schema(self):
        c = proposal(); r, a = review_approval(c)
        launcher.validate_review(r, 'c'*64, 'r'*64, a, c)

    def test_every_missing_required_review_field_fails(self):
        c = proposal(); r, a = review_approval(c)
        for key in r:
            altered = dict(r); del altered[key]
            with self.subTest(key=key), self.assertRaises((ValueError, KeyError)):
                launcher.validate_review(altered, 'c'*64, 'r'*64, a, c)

    def test_every_missing_required_approval_field_fails(self):
        c = proposal(); r, a = review_approval(c)
        for key in a:
            altered = dict(a); del altered[key]
            with self.subTest(key=key), self.assertRaises((ValueError, KeyError)):
                launcher.validate_review(r, 'c'*64, 'r'*64, altered, c)

    def test_not_root_go_or_scope_rejected(self):
        c=proposal(); r,a=review_approval(c)
        for key,value in [('issued_by','worker'),('go','go'),('maximum_invocations',2),('no_retry',False),('exclusive_reference_slot',False),('scope',{})]:
            b=dict(a, **{key:value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                launcher.validate_review(r,'c'*64,'r'*64,b,c)

    def test_exact_resource_profile_and_helper_required(self):
        c=proposal(); r,a=review_approval(c)
        for key,value in [('limits',{}),('runtime_profile',{}),('loopback_probe',{}),('capture_sources',{}),('blockers',['blocked']),('model_import_executed',True)]:
            b=dict(r, **{key:value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                launcher.validate_review(b,'c'*64,'r'*64,a,c)

    def test_original_import_approval_cannot_authorize_forward(self):
        c=proposal(); r,a=review_approval(c)
        a['action']='single_official_normal_import_only'
        with self.assertRaises(ValueError): launcher.validate_review(r,'c'*64,'r'*64,a,c)

    def test_no_cli_go_stops_before_any_file_or_process(self):
        with patch.object(launcher.subprocess,'Popen',side_effect=AssertionError('must not launch')):
            with self.assertRaises(ValueError): launcher.launch(types.SimpleNamespace(go=None))

    def test_worker_without_claim_stops_before_any_import(self):
        with self.assertRaises(ValueError): worker.run({},Path('/not-used'),{'go':'GO'},object())

    def test_regular_file_cannot_be_fifo_capability(self):
        with tempfile.TemporaryFile() as f:
            with self.assertRaises(ValueError): worker.claim(f.fileno(),{},'c'*64,Path('/not-used'))

    def test_wrong_parent_fifo_capability_rejected(self):
        read,write=os.pipe()
        os.write(write,json.dumps({'go':'GO','parent_pid':-1}).encode());os.close(write)
        with self.assertRaises(ValueError): worker.claim(read,{},'c'*64,Path('/not-used'))

    def test_one_use_ledger_atomic_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'claim.json'; common.write_new(p,{'consumed':True})
            with self.assertRaises(FileExistsError): common.write_new(p,{'consumed':False})
            self.assertEqual(json.loads(p.read_text()),{'consumed':True})

    def test_full_postflight_detects_each_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'synthetic-input';p.write_bytes(b'old')
            expected={str(p):common.file_id(p)};p.write_bytes(b'new')
            check=launcher.manifest_postflight(expected)
            self.assertFalse(check['passed']);self.assertEqual(set(check['differences']),{str(p)})

    def test_parent_environment_exact_four_threads_offline(self):
        env=launcher.runtime_environment(Path('/synthetic-run'))
        for name in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):self.assertEqual(env[name],'4')
        self.assertEqual(env['HF_HUB_OFFLINE'],'1');self.assertNotIn('PYTHONPATH',env)


class SourceContractTests(unittest.TestCase):
    def test_all_sources_parse_without_execution(self):
        for path in HERE.glob('*.py'):ast.parse(path.read_bytes(),filename=str(path))

    def test_frozen_capture_is_unchanged_and_public_disabled(self):
        p=HERE.parent/'full_layer_capture/capture.py'
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),'4fe8428c8ae2a1d96a900b0fc26e9a34cb98663f037c029595a5e51d4fc9bfc4')
        f=next(x for x in ast.parse(p.read_bytes()).body if isinstance(x,ast.FunctionDef) and x.name=='run_capture')
        self.assertEqual(len(f.body),2);self.assertIsInstance(f.body[-1],ast.Raise)

    def test_network_helper_is_exact_frozen_source_region(self):
        provenance=json.loads((HERE/'NETWORK_HELPER_PROVENANCE.json').read_text())
        r2=HERE.parent/'import_gate_r2/worker.py'
        self.assertEqual(common.file_id(r2),provenance['upstream_files'][str(r2)])
        old=r2.read_text();region=old[old.index('# Exact trusted stdlib'):old.index('\ndef install_guards(config):')]
        self.assertTrue((HERE/'network_policy.py').read_text().endswith(region))
        self.assertEqual(hashlib.sha256(region.encode()).hexdigest(),provenance['extracted_worker_region_sha256'])

    def test_single_capture_private_call_and_no_public_override(self):
        tree=ast.parse((HERE/'worker.py').read_text())
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='_capture_pair_impl']
        self.assertEqual(len(calls),1)
        self.assertNotIn('run_capture =',(HERE/'worker.py').read_text())

    def test_model_imports_only_inside_function_body(self):
        for name in common.GATE_FILES:
            tree=ast.parse((HERE/name).read_text())
            for n in tree.body:
                if isinstance(n,ast.Import): self.assertFalse(any(x.name.split('.')[0] in {'torch','numpy','transformers'} for x in n.names))
                if isinstance(n,ast.ImportFrom):self.assertNotIn((n.module or '').split('.')[0],{'torch','numpy','transformers'})

    def test_no_comparison_expected_outputs_or_dut_exec(self):
        source=(HERE/'worker.py').read_text()
        self.assertNotIn('from_pretrained(',source)
        self.assertNotIn('Qwen2ForCausalLM(',source)
        self.assertNotIn('Qwen2Model(',source)
        self.assertIn("'expected_output_hashes': None",source)

    def test_completion_seal_only_under_passed_parent_condition(self):
        tree=ast.parse((HERE/'run_gate.py').read_text())
        clauses=[n for n in ast.walk(tree) if isinstance(n,ast.If) and isinstance(n.test,ast.Name) and n.test.id=='passed']
        self.assertEqual(len(clauses),1)
        self.assertIn('COMPLETION_SEAL.json',ast.unparse(clauses[0]))
        self.assertNotIn('COMPLETION_SEAL.json', (HERE/'worker.py').read_text().replace('COMPLETION_SEAL.json qualifies.',''))

    def test_proposed_limits_not_old_import_limits(self):
        self.assertEqual(common.LIMITS['affinity_count'],4);self.assertEqual(common.LIMITS['cpu_seconds_hard'],60)
        self.assertEqual(common.LIMITS['wall_seconds'],90);self.assertEqual(common.LIMITS['sampled_tree_rss_bytes'],1610612736)
        self.assertFalse(common.LIMITS['rss_is_hard_cap']);self.assertFalse(common.LIMITS['address_space_limit_changed'])

    def test_helper_identity_full_marshal_v2(self):
        identity=common.complete_probe_code_identity((lambda:None).__code__)
        self.assertEqual(identity['marshal_version'],2);self.assertIn('complete_marshal_sha256',identity)


class GuardTests(unittest.TestCase):
    def guards(self):
        c={'target':'/synthetic-target','loopback_probe':None,'raw_input_manifest':{'/synthetic/raw/x.bin':{}},
           '_output':'/synthetic/run','excluded_module_prefixes':['tkinter']}
        with patch.object(sys,'addaudithook') as audit,patch.object(sys,'setprofile') as profile:
            state,network,callback=worker.install_guards(c)
        return state,callback,audit.call_args.args[0]

    def model_frame(self,qualname):
        return types.SimpleNamespace(f_code=types.SimpleNamespace(co_filename='/synthetic-target/transformers/models/qwen2/modeling_qwen2.py',co_name=qualname.split('.')[-1],co_qualname=qualname,co_firstlineno=1))

    def test_model_before_authorized_capture_rejected(self):
        state,profile,audit=self.guards()
        with self.assertRaises(RuntimeError):profile(self.model_frame('Qwen2DecoderLayer.__init__'),'call',None)
        self.assertEqual(len(state['denied_model_calls']),1)

    def test_only_two_decoder_forwards_after_capture_phase(self):
        state,profile,audit=self.guards();state['phase']='capture'
        frame=self.model_frame('Qwen2DecoderLayer.forward');profile(frame,'call',None);profile(frame,'call',None)
        with self.assertRaises(ValueError):profile(frame,'call',None)

    def test_full_model_rejected_even_in_capture(self):
        state,profile,audit=self.guards();state['phase']='capture'
        with self.assertRaises(RuntimeError):profile(self.model_frame('Qwen2ForCausalLM.forward'),'call',None)

    def test_unknown_old_or_provider_payload_denied(self):
        state,profile,audit=self.guards()
        for path in ('/synthetic/typed/wq.bin','/old/reference/y.f32le','/downloads/model.safetensors'):
            with self.assertRaises(RuntimeError):audit('open',(path,'r',0))
        self.assertEqual(len(state['denied_payload_opens']),3)

    def test_only_original_raw_and_fresh_capture_payload_allowed(self):
        state,profile,audit=self.guards()
        audit('open',('/synthetic/raw/x.bin','r',0));audit('open',('/synthetic/run/capture/y.native.bin','w',0))
        self.assertEqual(state['denied_payload_opens'],[])

    def test_worker_child_process_denied(self):
        state,profile,audit=self.guards()
        for event in ('subprocess.Popen','os.fork','os.exec','os.system'):
            with self.assertRaises(RuntimeError):audit(event,())


class RevisionBoundaryTests(unittest.TestCase):
    def guard_for_root(self, root):
        raw = root / 'raw' / 'x.bin'
        raw.parent.mkdir(); raw.write_bytes(b'synthetic-only')
        run = root / 'run'; run.mkdir(); (run / 'capture').mkdir()
        c = {'target': '/synthetic-target', 'loopback_probe': None,
             'raw_input_manifest': {str(raw): {}}, '_output': str(run),
             'excluded_module_prefixes': ['tkinter']}
        with patch.object(sys, 'addaudithook') as registered, patch.object(sys, 'setprofile'):
            state, network, callback = worker.install_guards(c)
        return state, registered.call_args.args[0], raw, run

    def test_dotdot_capture_escape_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            state, audit, raw, run = self.guard_for_root(Path(temp))
            escaped = run / 'capture' / '..' / '..' / 'old' / 'y.bin'
            with self.assertRaises(RuntimeError): audit('open', (str(escaped), 'r', 0))
            self.assertEqual(len(state['denied_payload_opens']), 1)

    def test_leaf_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); state, audit, raw, run = self.guard_for_root(root)
            target = root / 'old.bin'; target.write_bytes(b'synthetic-only')
            link = run / 'capture' / 'y.bin'; link.symlink_to(target)
            with self.assertRaises(RuntimeError): audit('open', (str(link), 'r', 0))

    def test_directory_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); state, audit, raw, run = self.guard_for_root(root)
            old = root / 'old'; old.mkdir(); (old / 'y.bin').write_bytes(b'synthetic-only')
            link = run / 'capture' / 'nested'; link.symlink_to(old, target_is_directory=True)
            with self.assertRaises(RuntimeError): audit('open', (str(link / 'y.bin'), 'r', 0))

    def test_capture_root_symlink_cannot_redefine_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); state, audit, raw, run = self.guard_for_root(root)
            (run / 'capture').rmdir(); (run / 'capture').symlink_to(root, target_is_directory=True)
            with self.assertRaises(RuntimeError): audit('open', (str(run / 'capture' / 'y.bin'), 'w', os.O_WRONLY))

    def test_alias_suffix_does_not_hide_old_tensor(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); state, audit, raw, run = self.guard_for_root(root)
            target = root / 'old.bin'; target.write_bytes(b'synthetic-only')
            link = run / 'capture' / 'pretend.txt'; link.symlink_to(target)
            with self.assertRaises(RuntimeError): audit('open', (str(link), 'r', 0))

    def test_original_raw_write_flags_and_modes_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            state, audit, raw, run = self.guard_for_root(Path(temp))
            for mode, flags in [('w', 0), ('r+', 0), (None, os.O_RDWR), (None, os.O_WRONLY), (None, os.O_CREAT)]:
                with self.subTest(mode=mode, flags=flags), self.assertRaises(RuntimeError):
                    audit('open', (str(raw), mode, flags))
            audit('open', (str(raw), 'r', os.O_RDONLY))
            audit('open', (str(run / 'capture' / 'new.bin'), 'w', os.O_WRONLY | os.O_CREAT))

    def process(self, pid, start, ppid, pgrp, rss=10):
        return {'pid': pid, 'start_ticks': start, 'ppid': ppid, 'pgrp': pgrp, 'state': 'S', 'rss_bytes': rss}

    def test_reused_pid_current_owned_child_rebound_and_counted(self):
        tracked = launcher.OwnedIdentities(); tracked.update({100: 10, 101: 11})
        table = {100: self.process(100, 10, 900, 100, 1000), 101: self.process(101, 22, 100, 100, 2000)}
        active = launcher.expand_owned_tree(table, 100, tracked, 900)
        self.assertEqual(tracked[101], 22); self.assertEqual(sum(r['rss_bytes'] for r in active.values()), 3000)
        self.assertEqual(set(active), {100, 101}); self.assertEqual(len(tracked.rebindings), 1)
        self.assertEqual(tracked.rebindings[0]['old_start_ticks'], 11)
        self.assertTrue(tracked.rebindings[0]['verified_current_parent'])

    def test_reused_pid_unrelated_not_rebound_or_owned(self):
        tracked = launcher.OwnedIdentities(); tracked.update({100: 10, 101: 11})
        table = {100: self.process(100, 10, 900, 100), 101: self.process(101, 22, 777, 777)}
        active = launcher.expand_owned_tree(table, 100, tracked, 900)
        self.assertEqual(tracked[101], 11); self.assertNotIn(101, active); self.assertEqual(tracked.rebindings, [])

    def test_reused_pid_transitive_new_owned_descendant_counted(self):
        tracked = launcher.OwnedIdentities(); tracked.update({100: 10, 101: 11})
        table = {102: self.process(102, 33, 101, 102), 101: self.process(101, 22, 100, 101), 100: self.process(100, 10, 900, 100)}
        active = launcher.expand_owned_tree(table, 100, tracked, 900)
        self.assertEqual(set(active), {100, 101, 102}); self.assertEqual(tracked[102], 33)

    def test_reused_pid_group_membership_can_rebind_without_original_parent(self):
        tracked = launcher.OwnedIdentities(); tracked.update({100: 10, 101: 11})
        table = {100: self.process(100, 10, 900, 100), 101: self.process(101, 22, 777, 100)}
        active = launcher.expand_owned_tree(table, 100, tracked, 900)
        self.assertIn(101, active); self.assertTrue(tracked.rebindings[0]['verified_current_group'])

    def test_reused_pid_no_valid_group_cannot_bootstrap_ownership(self):
        tracked = launcher.OwnedIdentities(); tracked.update({100: 10, 101: 11})
        table = {100: self.process(100, 99, 777, 100), 101: self.process(101, 22, 777, 100)}
        active = launcher.expand_owned_tree(table, 100, tracked, 900)
        self.assertEqual(active, {}); self.assertEqual(tracked.rebindings, [])

    def test_reuse_between_discovery_and_signal_never_signaled(self):
        tracked = {100: 10, 101: 22}
        active = {100: self.process(100, 10, 900, 100), 101: self.process(101, 22, 100, 100)}
        later = dict(active); later[101] = self.process(101, 23, 777, 777)
        with patch.object(launcher, 'discover_tree', return_value=active), \
             patch.object(launcher, 'process_stat', side_effect=lambda pid: later.get(pid)), \
             patch.object(launcher.os, 'kill') as kill, patch.object(launcher.os, 'killpg') as killpg:
            launcher.stop_owned(100, tracked)
        self.assertEqual([c.args[0] for c in kill.call_args_list], [100])
        self.assertEqual(killpg.call_args.args[0], 100)


class PairSourceAndHelperTests(unittest.TestCase):
    def tree(self):
        return ast.parse((PAIR_DIR / 'capture_pair.py').read_bytes())

    def test_two_calls_same_layer_and_exact_same_argument_names(self):
        f=next(n for n in self.tree().body if isinstance(n,ast.FunctionDef) and n.name=='_capture_pair_impl')
        calls=[n for n in ast.walk(f) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='layer']
        self.assertEqual(len(calls),2)
        self.assertEqual(ast.dump(calls[0],include_attributes=False),ast.dump(calls[1],include_attributes=False))
        constructors=[n for n in ast.walk(f) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='Qwen2DecoderLayer']
        self.assertEqual(len(constructors),1)

    def test_baseline_precedes_observer_instantiation_and_hooks(self):
        source=(PAIR_DIR/'capture_pair.py').read_text()
        body=source[source.index('def _capture_pair_impl('):]
        baseline=body.index('baseline_returned = layer(')
        freeze=body.index('freeze_baseline(torch, baseline_returned')
        observer=body.index('observer = Observer(')
        hooks=body.index('handles = install_hooks(')
        observed=body.index('returned = layer(',body.index('sys.settrace(observer.trace)'))
        self.assertTrue(baseline < freeze < observer < hooks < observed)

    def test_three_fresh_boundary_enumerations_and_no_old_dict_reuse(self):
        source=(PAIR_DIR/'capture_pair.py').read_text()
        state=next(n for n in self.tree().body if isinstance(n,ast.FunctionDef) and n.name=='capture_state')
        names=[n.func.attr for n in ast.walk(state) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        self.assertIn('named_parameters',names);self.assertIn('named_buffers',names)
        f=next(n for n in self.tree().body if isinstance(n,ast.FunctionDef) and n.name=='_capture_pair_impl')
        state_calls=[n for n in ast.walk(f) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='capture_state']
        self.assertEqual(len(state_calls),3)
        self.assertIn('hex(id(tensor))',source)

    def test_paired_public_entry_still_literal_disabled(self):
        f=next(n for n in self.tree().body if isinstance(n,ast.FunctionDef) and n.name=='run_capture')
        self.assertIsInstance(f.body[-1],ast.Raise)
        with self.assertRaises(pair.ExecutionDisabled):pair.run_capture('/unused','/unused',{})

    def test_old_single_arm_approval_and_profile_rejected(self):
        config=proposal();review,approval=review_approval(config)
        approval['action']='single_official_m16_full_layer_reference'
        with self.assertRaises(ValueError):launcher.validate_review(review,'c'*64,'r'*64,approval,config)
        review,approval=review_approval(config);review['capture_profile']={'forward_calls':1}
        with self.assertRaises(ValueError):launcher.validate_review(review,'c'*64,'r'*64,approval,config)

    def test_state_value_and_original_object_replacement_rejected(self):
        original={'inputs':{'x':{'object_id':'0x1','native_sha256':'a'*64}},'parameters':{},'buffers':{}}
        for key,value in [('object_id','0x2'),('native_sha256','b'*64)]:
            altered=copy.deepcopy(original);altered['inputs']['x'][key]=value
            with self.assertRaises(ValueError):pair.require_same_state(original,altered,'mock')
        self.assertTrue(pair.require_same_state(original,copy.deepcopy(original),'mock')['passed'])

    def fake_layer(self):
        class Tensor:
            def __init__(self, payload): self.payload=payload;self.shape=[1];self.dtype='torch.bfloat16';self.device='cpu'
            def stride(self):return (1,)
            def storage_offset(self):return 0
            def untyped_storage(self):return self
            def data_ptr(self):return id(self)
            def nbytes(self):return len(self.payload)
            def numel(self):return 1
            def element_size(self):return 2
        class Layer:
            def __init__(self):
                self.parameters={str(n):Tensor(b'\x00\x00') for n in range(12)}
                self.buffers={'self_attn.rotary_emb.'+n:Tensor(b'\x00\x00') for n in ('inv_freq','cos_cached','sin_cached')}
                self.training=False
                self.self_attn=types.SimpleNamespace(attention_dropout=0.0,rotary_emb=types.SimpleNamespace(max_seq_len_cached=32768),training=False)
            def named_parameters(self):return iter(self.parameters.items())
            def named_buffers(self):return iter(self.buffers.items())
            def named_modules(self):return iter([('',self),('self_attn',self.self_attn)])
        return Layer(),Tensor

    def test_capture_state_fresh_enumeration_detects_replaced_parameter(self):
        layer,Tensor=self.fake_layer();inputs=[Tensor(b'\x00\x00') for _ in range(3)]
        with patch.object(pair,'tensor_native_sha256',side_effect=lambda torch,t:hashlib.sha256(t.payload).hexdigest()):
            before=pair.capture_state(None,layer,*inputs)
            layer.parameters['0']=Tensor(b'\x00\x00')
            after=pair.capture_state(None,layer,*inputs)
        self.assertEqual(before['parameters']['0']['native_sha256'],after['parameters']['0']['native_sha256'])
        self.assertNotEqual(before['parameters']['0']['object_id'],after['parameters']['0']['object_id'])
        with self.assertRaises(ValueError):pair.require_same_state(before,after,'replacement')

    def test_capture_state_fresh_enumeration_detects_buffer_value_mutation(self):
        layer,Tensor=self.fake_layer();inputs=[Tensor(b'\x00\x00') for _ in range(3)]
        with patch.object(pair,'tensor_native_sha256',side_effect=lambda torch,t:hashlib.sha256(t.payload).hexdigest()):
            before=pair.capture_state(None,layer,*inputs)
            layer.buffers['self_attn.rotary_emb.cos_cached'].payload=b'\x80\x3f'
            after=pair.capture_state(None,layer,*inputs)
        with self.assertRaises(ValueError):pair.require_same_state(before,after,'mutation')

    def test_baseline_controls_reject_existing_observer_or_dropout(self):
        layer,Tensor=self.fake_layer()
        torch=types.SimpleNamespace(is_grad_enabled=lambda:False,nn=types.SimpleNamespace(modules=types.SimpleNamespace(module=types.SimpleNamespace())))
        with patch.object(pair.sys,'getprofile',return_value=object()):
            self.assertTrue(pair.require_baseline_without_observer(torch,layer)['safety_profile_remains_active'])
            layer._forward_hooks={'unexpected':object()}
            with self.assertRaises(ValueError):pair.require_baseline_without_observer(torch,layer)
            layer._forward_hooks={};layer.self_attn.attention_dropout=0.1
            with self.assertRaises(ValueError):pair.require_baseline_without_observer(torch,layer)

    def test_baseline_native_bytes_frozen_before_later_alias_change(self):
        pins=pair.load_pins()
        tensors=[]
        for name in ('y','prob'):
            tensors.append(types.SimpleNamespace(shape=pins['fields'][name]['shape'],dtype='torch.bfloat16',device='cpu',payload=bytes(pins['fields'][name]['export_f32_bytes']//2)))
        with tempfile.TemporaryDirectory() as temp,patch.object(pair,'tensor_native_bytes',side_effect=lambda torch,t:t.payload):
            values,records=pair.freeze_baseline(None,tuple(tensors),Path(temp),pins)
            before=values['y'];tensors[0].payload=b'\x80\x3f'+before[2:]
            self.assertEqual(values['y'],before)
            self.assertEqual((Path(temp)/'baseline/y.native.bin').read_bytes(),before)
            self.assertFalse(pair.compare_pair_outputs(None,values,tuple(tensors))['passed'])

    def test_missing_baseline_bytes_and_wrong_return_rejected(self):
        with self.assertRaises(ValueError):pair.compare_pair_outputs(None,{},())
        with self.assertRaises(ValueError):pair.compare_pair_outputs(None,{'y':b'', 'prob':b''},())

    def test_exact_pair_outputs_scope_never_all29(self):
        returned=(types.SimpleNamespace(payload=b'one'),types.SimpleNamespace(payload=b'two'))
        with patch.object(pair,'tensor_native_bytes',side_effect=lambda torch,t:t.payload):
            result=pair.compare_pair_outputs(None,{'y':b'one','prob':b'two'},returned)
        self.assertTrue(result['passed']);self.assertFalse(result['all29_intermediate_noninterference_claimed'])


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.out=self.root/'capture';self.out.mkdir()
        pins=json.loads((HERE.parent/'full_layer_capture/pins.json').read_text())
        self.config={'output_contract':pins['fields'],'comparison_gates':pins['comparison_gates'], 'capture_profile': copy.deepcopy(pair.PAIR_PROFILE),
                     'raw13':[{'local_name':'embed_tokens.rows_0_255','path':str(self.root/'synthetic-embedding.bin')}]}
        (self.root/'synthetic-embedding.bin').write_bytes(bytes(16*1536*2))
        self.report={'status':'PAIR_CAPTURE_COMPLETE_NOT_NUMERIC_PASS','official_layer_call_started':True,'official_layer_call_returned':True,
                     'numeric_acceptance':'NOT_RUN','dut_comparison':'NOT_RUN','full_model_forward_executed':False,
                     'dynamic_cache_executed':False,'legacy_results_inherited':False,'source_rewritten':False,'exports':{}}
        for name,f in pins['fields'].items():
            data=bytes(math.prod(f['shape'])*(4 if name=='softmax_fp32' else 2))
            if name=='mask':data=b''.join(struct.pack('<H',0xff7f if k>q else 0) for q in range(16) for k in range(16))
            if name=='logits':data=b''.join(struct.pack('<H',0xff7f if k>q else 0) for h in range(12) for q in range(16) for k in range(16))
            if name in ('prob','softmax_fp32'):
                data=b''.join(struct.pack('<f',1.0 if k==0 else 0.0) if name=='softmax_fp32' else struct.pack('<H',0x3f80 if k==0 else 0) for h in range(12) for q in range(16) for k in range(16))
            self.replace(name,data)
        self.make_pair_evidence()

    def make_pair_evidence(self):
        state_item = {'object_id': '0x123', 'native_sha256': 'a' * 64, 'native_bytes': 2}
        state = {'layer_object_id': '0x111', 'inputs': {n: dict(state_item) for n in ('x','mask','positions')},
                 'parameters': {str(n): dict(state_item) for n in range(12)},
                 'buffers': {'self_attn.rotary_emb.' + n: dict(state_item) for n in ('inv_freq','cos_cached','sin_cached')}}
        self.report.update({'capture_profile': copy.deepcopy(pair.PAIR_PROFILE), 'layer_instance_count': 1,
                            'forward_call_count': 2, 'baseline_layer_call_started': True, 'baseline_layer_call_returned': True,
                            'baseline_controls': {n: True for n in ('capture_trace_absent','module_hooks_absent','global_module_hooks_absent','eval','no_grad','safety_profile_remains_active')},
                            'state_checkpoints': {n: copy.deepcopy(state) for n in ('before_baseline','after_baseline','after_observed')},
                            'baseline_state_unchanged': {'passed': True}, 'observed_state_unchanged': {'passed': True},
                            'baseline_exports': {}, 'pair_output_comparison': {'passed': True, 'all29_intermediate_noninterference_claimed': False, 'outputs': {}}})
        self.report['baseline_controls']['attention_dropout'] = 0.0
        baseline = self.out / 'baseline'; baseline.mkdir()
        for name in ('y','prob'):
            data = (self.out / (name + '.native.bin')).read_bytes()
            (baseline / (name + '.native.bin')).write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            self.report['baseline_exports'][name] = {'file': 'baseline/' + name + '.native.bin', 'native_bytes': len(data),
                'native_sha256': digest, 'shape': self.config['output_contract'][name]['shape'], 'native_dtype': 'bfloat16'}
            self.report['pair_output_comparison']['outputs'][name] = {'byte_identical': True, 'native_bytes': len(data),
                'baseline_sha256': digest, 'observed_sha256': digest}

    def tearDown(self):self.tmp.cleanup()

    def replace(self,name,data):
        f=self.config['output_contract'][name]
        wide=data if f['dtype']=='float32' else validation.wide_bf16(data)
        (self.out/(name+'.native.bin')).write_bytes(data);(self.out/(name+'.f32.bin')).write_bytes(wide)
        self.report['exports'][name]={'shape':f['shape'],'native_dtype':f['dtype'],'device':'cpu','native_bytes':len(data),'fp32_bytes':len(wide),
            'native_file':name+'.native.bin','fp32_file':name+'.f32.bin','native_sha256':hashlib.sha256(data).hexdigest(),
            'fp32_sha256':hashlib.sha256(wide).hexdigest(),'nonfinite_count':0}

    def sync_baseline(self, name):
        data=(self.out/(name+'.native.bin')).read_bytes();digest=hashlib.sha256(data).hexdigest()
        (self.out/'baseline'/(name+'.native.bin')).write_bytes(data)
        self.report['baseline_exports'][name]['native_sha256']=digest
        self.report['pair_output_comparison']['outputs'][name].update({'baseline_sha256':digest,'observed_sha256':digest})

    def test_synthetic_all29_complete(self):
        r=validation.validate_capture(self.config,self.out,self.report)
        self.assertTrue(r['passed']);self.assertEqual(len(r['fields']),29);self.assertEqual(r['future_probability_positive_zero_count'],1440)
        self.assertFalse(r['bf16_prob_rowsum_hard_gate_added']);self.assertIsNone(r['expected_output_hashes'])

    def test_missing_field_and_geometry_fail(self):
        del self.report['exports']['y']
        with self.assertRaises(ValueError):validation.validate_capture(self.config,self.out,self.report)

    def test_nonfinite_even_self_declared_finite_fails(self):
        data=bytearray((self.out/'y.native.bin').read_bytes());data[:2]=b'\x80\x7f';self.replace('y',bytes(data))
        with self.assertRaises(ValueError):validation.validate_capture(self.config,self.out,self.report)

    def test_f32_widening_corruption_fails(self):
        p=self.out/'y.f32.bin';data=bytearray(p.read_bytes());data[0]=1;p.write_bytes(data)
        self.report['exports']['y']['fp32_sha256']=hashlib.sha256(data).hexdigest()
        with self.assertRaises(ValueError):validation.validate_capture(self.config,self.out,self.report)

    def test_semantic_residual_mismatch_fails(self):
        data=bytearray((self.out/'r.native.bin').read_bytes());data[:2]=b'\x80\x3f';self.replace('r',bytes(data))
        with self.assertRaises(ValueError):validation.validate_capture(self.config,self.out,self.report)

    def test_alias_repeat_mismatch_fails(self):
        data=bytearray((self.out/'cache_k.native.bin').read_bytes());data[:2]=b'\x80\x3f';self.replace('cache_k',bytes(data))
        with self.assertRaises(ValueError):validation.validate_capture(self.config,self.out,self.report)

    def test_future_negative_zero_fails(self):
        p=bytearray((self.out/'prob.native.bin').read_bytes());p[2:4]=struct.pack('<H',0x8000);self.replace('prob',bytes(p))
        s=bytearray((self.out/'softmax_fp32.native.bin').read_bytes());s[4:8]=struct.pack('<I',0x80000000);self.replace('softmax_fp32',bytes(s))
        self.sync_baseline('prob')
        with self.assertRaisesRegex(ValueError,'positive-zero'):validation.validate_capture(self.config,self.out,self.report)

    def test_actual_fp32_rowsum_gate_fails(self):
        s=bytearray((self.out/'softmax_fp32.native.bin').read_bytes());s[:4]=struct.pack('<f',0.5);self.replace('softmax_fp32',bytes(s))
        p=bytearray((self.out/'prob.native.bin').read_bytes());p[:2]=struct.pack('<H',0x3f00);self.replace('prob',bytes(p))
        self.sync_baseline('prob')
        with self.assertRaisesRegex(ValueError,'row-sum'):validation.validate_capture(self.config,self.out,self.report)

    def test_changed_original_tolerance_fails(self):
        self.config['comparison_gates']['rowsum_abs_error_lte']=0.1
        with self.assertRaisesRegex(ValueError,'tolerance changed'):validation.validate_capture(self.config,self.out,self.report)

    def test_missing_baseline_cannot_pass_observed_all29(self):
        self.report['baseline_layer_call_returned']=False
        with self.assertRaisesRegex(ValueError,'baseline missing'):validation.validate_capture(self.config,self.out,self.report)

    def test_baseline_file_mismatch_rejected_even_with_claimed_pass(self):
        path=self.out/'baseline/y.native.bin';data=bytearray(path.read_bytes());data[:2]=b'\x80\x3f';path.write_bytes(data)
        with self.assertRaisesRegex(ValueError,'actual output bytes differ'):validation.validate_capture(self.config,self.out,self.report)

    def test_boundary_parameter_replacement_rejected(self):
        self.report['state_checkpoints']['after_observed']['parameters']['0']['object_id']='0x999'
        with self.assertRaisesRegex(ValueError,'identities changed'):validation.validate_capture(self.config,self.out,self.report)

    def test_boundary_input_value_change_rejected(self):
        self.report['state_checkpoints']['after_baseline']['inputs']['mask']['native_sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'identities changed'):validation.validate_capture(self.config,self.out,self.report)

    def test_single_forward_or_second_layer_rejected(self):
        for key,value in [('forward_call_count',1),('layer_instance_count',2)]:
            saved=self.report[key];self.report[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'one layer/two forwards'):validation.validate_capture(self.config,self.out,self.report)
            self.report[key]=saved

    def test_scope_overclaim_rejected(self):
        self.report['pair_output_comparison']['all29_intermediate_noninterference_claimed']=True
        with self.assertRaisesRegex(ValueError,'scope overstated'):validation.validate_capture(self.config,self.out,self.report)

    def test_no_prior_oracle_pass_accepted(self):
        self.report['legacy_results_inherited']=True
        with self.assertRaises(ValueError):validation.validate_capture(self.config,self.out,self.report)


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if set(sys.modules)&{'torch','numpy','transformers'}:raise AssertionError('Forbidden ML import')
    print('No actual raw13 payload read; all binary test inputs were synthetic temporary files.')
    raise SystemExit(not result.wasSuccessful())

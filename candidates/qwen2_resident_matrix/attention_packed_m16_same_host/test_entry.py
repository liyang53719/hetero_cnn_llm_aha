"""Cold, synthetic metadata and source tests. Never producer/ELF/numeric runs."""
import ast
import copy
from contextlib import ExitStack
from dataclasses import asdict, make_dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch
from . import admission as A, contract as C, prepare as P


def synthetic_qualification():
    p = dict(attempt_nonce='a'*64, source_manifest_sha256='b'*64,
             host={'boot_id':'synthetic'}, runtime_identity={'synthetic':True},
             ci=dict(commit='c'*40, run_id='123', run_attempt='1'))
    q = dict(schema=1, profile=A.QUALIFIED_PROFILE, status='PASS_FRESH_M16_PRODUCER',
        attempt_nonce=p['attempt_nonce'], producer_manifest_sha256='d'*64,
        producer_source_manifest_sha256=p['source_manifest_sha256'], host_sha256=C.sha(C.encoded(p['host'])),
        runtime_identity_sha256=C.sha(C.encoded(p['runtime_identity'])), ci=p['ci'], child_pid=123,
        child_exit_code=0, owned_group_cleanup_complete=True, producer_native_gate_validated=True,
        elapsed_seconds=1, claims={k:False for k in A.CLAIMS},fresh_tiny_result_sha256='e'*64,
        fresh_tiny_source_manifest_sha256='f'*64)
    return p,q


def synthetic_manifest():
    pointer = dict(path='/tmp/synthetic-not-read',sha256='a'*64)
    sources = {'synthetic.py':'b'*64}
    return dict(schema=1,profile=C.PROFILE,status=A.STATUS,rows=16,past_tokens=0,
        enable_raw_kv=True,enable_packed=True,source_sha256=sources,
        source_manifest_sha256=C.sha(C.encoded(sources)),producer_workspace='/tmp/synthetic-not-read',
        producer_manifest=pointer.copy(),producer_receipt=pointer.copy(),
        tiny=dict(workspace='/tmp/synthetic-tiny-not-read',result=pointer.copy(),input_contract=pointer.copy()),
        library=dict(origin_root='/tmp/synthetic-origin-not-read',receipt=pointer.copy(),
                     binary=dict(path='/tmp/synthetic-not-read.so',bytes=1,sha256='c'*64)))


def synthetic_tiny_binding(directory):
    """Binding-only fixture; delegated schema checks are explicit test doubles.

    No fabricated result is passed to the real qualification schema or used as
    evidence. The tests exercise this entry's file/runtime/parent binding and
    verify that both unchanged external validators are called fail-closed.
    """
    workspace = Path(directory)/'tiny'; workspace.mkdir()
    (workspace/'source').mkdir(); (workspace/'build').mkdir()
    inputs = dict(source_sha256={}, generated_sha256={})
    for group, name in (('source_sha256','original.py'), ('generated_sha256','generated.py')):
        raw = ('synthetic non-executable bytes '+name).encode()
        (workspace/'source'/name).write_bytes(raw)
        inputs[group][name] = C.sha(raw)
    def pointer(path, value):
        raw = C.encoded(value); path.write_bytes(raw)
        return dict(path=str(path),sha256=C.sha(raw))
    producer, qualified = synthetic_qualification()
    observed = dict(python_executable_sha256='1'*64,
                    compiler=dict(path='/synthetic/compiler',sha256='2'*64,version='synthetic compiler'))
    producer['runtime_observation'] = observed
    identity = dict(interpreter=dict(sha256='1'*64),
                    compiler={k:observed['compiler'][k] for k in ('sha256','version')},
                    combined_elf=dict(sha256='3'*64,bytes=7))
    result = dict(library_sha256='3'*64,
                  identities={k:copy.deepcopy(identity) for k in ('build','profile2','scalar_silu')})
    manifest = dict(tiny=dict(workspace=str(workspace),
        result=pointer(workspace/'result.json',result),
        input_contract=pointer(Path(directory)/'input.json',inputs)),
        library=dict(origin_root=str(workspace/'source'),
            receipt=pointer(workspace/'build/official_bf16_compile.json',{'synthetic':True}),
            binary=dict(path=str(workspace/'build/official_bf16_matrix_silu.so'),sha256='3'*64,bytes=7)))
    Path(manifest['library']['binary']['path']).write_bytes(b'no ELF!')
    qualified['fresh_tiny_result_sha256'] = manifest['tiny']['result']['sha256']
    qualified['fresh_tiny_source_manifest_sha256'] = C.sha(C.encoded(
        dict(inputs['source_sha256'],**inputs['generated_sha256'])))
    contract = types.ModuleType('synthetic_tiny_contract')
    contract.shape = Mock(side_effect=lambda value:value)
    contract.result = Mock(side_effect=lambda value,launch,inputs:value)
    contract.safe = lambda root,name:C.safe(Path(root)/name)
    package = types.ModuleType('candidates.qwen2_resident_matrix.portable_consumer_qualification')
    package.contract = contract
    return manifest,qualified,producer,dict(library_sha256='3'*64),inputs,result,contract,package


# These are immutable numerical source files, not freshly invented encoder
# doubles. AST extraction below executes only the named metadata functions.
WRITER_SOURCES = {
    'dense_block_reduce/check_public_numeric.py':
        '1b5466572150afc9c47ba9ee847957f24da2819f7b83c4a7fc7be930da2c2c6b',
    'official_bf16/check_numeric.py':
        'efa2d88c698536332646fe3528f0943adf3cd79544f47f160a991a415d581e93',
    'ffn_public/check_fullgraph_numeric.py':
        '198e2b7b87c6fbf7a317174d7653ea2d4da912c7eabda09b8addfd9bc2752992',
    'ffn_public/check_prefix_numeric.py':
        'edb9c89cff4f26734587ea691e201cb9f458acdef410ebc6185ae7037ca3a699',
    'official_bf16/execution.py':
        'e3b5906d7589885e5aade7344d8c7d7497b61aa967b2034dbba4e1e0ebeb25d0',
}


def source_writer_contract():
    """Extract the pinned writer, save body, and policy-report metadata path.

    Never import the original numerical modules. The original validated job
    binding and report methods run over synthetic metadata and a synthetic
    parent; no transaction driver, native library, tensor, or producer runs.
    """
    trees = {}
    for relative, expected in WRITER_SOURCES.items():
        path = P.ROOT/'candidates/qwen2_resident_matrix'/relative
        raw = path.read_bytes()
        C.need(C.sha(raw) == expected, 'cold writer source pin differs: '+relative)
        trees[relative] = ast.parse(raw, filename=str(path))
    aliases = {
        'dense_block_reduce/check_public_numeric.py': (
            'from ..official_bf16 import check_numeric as prior',
            'require,sha,encoded,file_sha=prior.require,prior.sha,prior.encoded,prior.file_sha'),
        'official_bf16/check_numeric.py': (
            'from candidates.qwen2_resident_matrix.ffn_public import check_fullgraph_numeric as old',
            'base=old.base',
            'require,sha,encoded,file_sha=base.require,base.sha,base.encoded,base.file_sha'),
        'ffn_public/check_fullgraph_numeric.py': (
            'from candidates.qwen2_resident_matrix.ffn_public import check_prefix_numeric as base',
            'require,sha,encoded,file_sha=base.require,base.sha,base.encoded,base.file_sha'),
    }
    for relative, statements in aliases.items():
        actual = {ast.dump(n, include_attributes=False) for n in trees[relative].body}
        for statement in statements:
            C.need(ast.dump(ast.parse(statement).body[0], include_attributes=False) in actual,
                   'original writer alias chain differs')
    def function(tree, name):
        return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    encoder_node = function(trees['ffn_public/check_prefix_numeric.py'], 'encoded')
    namespace = {'json':json}
    exec(compile(ast.Module(body=[encoder_node], type_ignores=[]), '<pinned-writer-encoder>', 'exec'), namespace)
    encoder = namespace['encoded']
    run_node = function(trees['dense_block_reduce/check_public_numeric.py'], 'run')
    save_node = function(run_node, 'save')
    C.need(any(isinstance(n, ast.Return) and isinstance(n.value, ast.Name) and n.value.id == 'report'
               for n in ast.walk(run_node)), 'original runner must return its saved report')
    def save(out, report):
        scope = dict(out=Path(out), report=report, encoded=encoder)
        exec(compile(ast.Module(body=[save_node], type_ignores=[]), '<pinned-summary-save>', 'exec'), scope)
        scope['save']()
    policy_tree = trees['official_bf16/execution.py']
    selected = [n for n in policy_tree.body if isinstance(n, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id in ('JOBS','DENSE_ROLES','POLICY_ID') for t in n.targets)]
    selected.append(function(policy_tree, 'validate_job'))
    cls = copy.deepcopy(next(n for n in policy_tree.body if isinstance(n, ast.ClassDef) and
                             n.name == 'OfficialPublicExecution'))
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ('advance_to_request','report')]
    selected.append(cls)
    class SyntheticParent:
        def advance_to_request(self, limit=4096):
            return dict(group_request=None, ordinary_request=self.synthetic_job)
        def report(self):
            return {}
    scope = dict(PublicExecution=SyntheticParent, require=C.need, asdict=asdict)
    exec(compile(ast.Module(body=selected, type_ignores=[]), '<pinned-policy-metadata>', 'exec'), scope)
    return types.SimpleNamespace(encoded=encoder, save=save, policy=scope)


def source_integer_policy_report(writer):
    """Real pinned validation/store/report bodies, synthetic metadata only."""
    policy = writer.policy
    Job = make_dataclass('SyntheticJob', [(n,object) for n in
        ('tag','kind','a','b','dst','m','n','k','write_bytes','weight_bf16','activation_bf16','output_bf16','c')])
    names = sorted({name for _,a,b,dst in policy['JOBS'].values() for name in (a,b,dst)} | {'cache_v'})
    specs = {name:(4096*(i+1),(16,32)) for i,name in enumerate(names)}
    fixture = types.SimpleNamespace(config=types.SimpleNamespace(epoch=7), specs=specs,
        allocations={name:types.SimpleNamespace(storage_bytes=16*32*4) for name in names})
    execution = policy['OfficialPublicExecution']()
    execution.policy_fixture = fixture
    execution.policy_jobs = {}
    execution.matrix_service = types.SimpleNamespace(bind_dense_job=lambda job,role:None)
    for pc,(kind,a,b,dst) in policy['JOBS'].items():
        c = specs['rope'][0]+1024*64*4 if kind=='Rope' else specs['cache_v'][0] if kind=='Attention' else 0
        execution.synthetic_job = Job((7<<16)|pc,kind,specs[a][0],specs[b][0],specs[dst][0],16,
            256 if pc==9 else 32,128 if pc==12 else 32,16*32*4,kind=='Dense',False,False,c)
        execution.advance_to_request()
    report = execution.report()
    C.need(report['validated_policy_jobs'] is execution.policy_jobs, 'policy report changed mapping identity')
    return report


class EntryWriterContractTests(unittest.TestCase):
    """Actual entry.run + strict reader + real terminal validator, cold only."""
    @classmethod
    def setUpClass(cls):
        cls.writer = source_writer_contract()

    def setUp(self):
        from . import entry, terminal_validator
        from .test_terminal_validator import fixture
        self.entry, self.terminal = entry, terminal_validator
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.workspace = root/'full'
        self.snapshot_path = self.workspace/'snapshot/SNAPSHOT.json'
        self.summary_path = self.workspace/'actual/summary.json'
        self.report,self.snapshot,self.sources = fixture(self.snapshot_path)
        self.report['execution']['host'].update(source_integer_policy_report(self.writer))
        self.producer = root/'producer.json'
        self.producer.write_bytes(C.encoded(dict(attempt_nonce='a'*64)))
        self.manifest_path = root/'manifest.json'
        self.manifest = dict(producer_receipt=dict(sha256='b'*64),
            producer_manifest=dict(path=str(self.producer),sha256=C.sha(self.producer.read_bytes())),
            library=dict(receipt=dict(path=str(root/'synthetic-receipt.json'))))
        self.context = dict(attempt_nonce='a'*64,producer_receipt_sha256='b'*64,work_deadline=1924)
        self.return_change = self.disk_change = self.read_change = self.after_terminal = None
        self.post_sources = self.sources
        self.clock_values = [1000,1000]

    def invoke(self, *, post_verify_error=False):
        def prepare(out, receipt, reference, reference_sha256, **kwargs):
            self.assertEqual(Path(out),self.snapshot_path.parent)
            self.assertEqual(kwargs,dict(rows=16,enable_raw_kv=True,fresh_profile=True,
                fresh_manifest=str(self.manifest_path),fresh_manifest_sha256='c'*64,enable_packed=True))
            Path(out).mkdir()
            self.snapshot_path.write_bytes(self.writer.encoded(self.snapshot))
            self.report.update(snapshot=str(self.snapshot_path),snapshot_sha256=C.sha(self.snapshot_path.read_bytes()))
            return self.snapshot_path,self.snapshot
        def run(out, path, digest, **kwargs):
            self.assertEqual((Path(out),path,digest),(self.summary_path.parent,self.snapshot_path,
                C.sha(self.snapshot_path.read_bytes())))
            self.assertEqual(kwargs,dict(wall_budget=C.NUMERIC_SECONDS,enable_raw_kv=True,
                fresh_profile=True,enable_packed=True,run_context=self.context))
            Path(out).mkdir()
            # Execute the exact extracted original save(), using its actual
            # original encoder, then return the same in-memory report.
            self.writer.save(out,self.report)
            if self.disk_change:
                self.summary_path.write_bytes(self.disk_change(self.summary_path.read_bytes()))
            if self.return_change:
                self.return_change(self.report)
            return self.report
        module_name = 'candidates.qwen2_resident_matrix.dense_block_reduce.check_public_numeric'
        original = types.ModuleType(module_name)
        original.prepare,original.run,original.encoded = prepare,run,self.writer.encoded
        package = types.ModuleType(module_name.rsplit('.',1)[0])
        package.__path__ = []
        package.check_public_numeric = original
        read_json = C.read_json
        def strict_read(path, expected=None, **kwargs):
            if Path(path) == self.summary_path and self.read_change:
                self.read_change(self.summary_path)
            return read_json(path,expected,**kwargs)
        validate_terminal = self.terminal.validate_terminal
        def validate(*args):
            value = validate_terminal(*args)
            if self.after_terminal:
                self.after_terminal()
            return value
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules,{module_name:original,package.__name__:package}))
            stack.enter_context(patch.object(C,'authorize_run',return_value=self.sources))
            stack.enter_context(patch.object(A,'read_manifest',return_value=self.manifest))
            self.verify = stack.enter_context(patch.object(A,'verify',side_effect=
                [None,ValueError('synthetic postflight admission failure')] if post_verify_error else None))
            stack.enter_context(patch.object(C,'snapshot',return_value=self.post_sources))
            stack.enter_context(patch.object(self.entry.time,'monotonic',side_effect=self.clock_values))
            self.reader = stack.enter_context(patch.object(C,'read_json',side_effect=strict_read))
            self.validator = stack.enter_context(patch.object(self.terminal,'validate_terminal',side_effect=validate))
            return self.entry.run(self.workspace,manifest=self.manifest_path,
                manifest_sha256='c'*64,run_context=self.context)

    def assert_no_child_result(self):
        self.assertFalse((self.workspace/'CHILD_RESULT.json').exists())

    def test_original_integer_pc_writer_reproduces_old_false_mismatch(self):
        report = source_integer_policy_report(self.writer)
        jobs = report['validated_policy_jobs']
        self.assertEqual(set(jobs),set(self.writer.policy['JOBS']))
        self.assertTrue(all(type(pc) is int for pc in jobs))
        raw = self.writer.encoded(report)
        parsed = json.loads(raw)
        self.assertEqual(parsed['validated_policy_jobs']['2'],jobs[2])
        self.assertEqual(parsed['validated_policy_jobs']['12'],jobs[12])
        self.assertNotEqual(C.encoded(report),C.encoded(parsed))
        self.assertNotEqual(self.writer.encoded(report),self.writer.encoded(parsed))
        self.assertLess(raw.index(b'"2":'),raw.index(b'"12":'))
        self.assertLess(self.writer.encoded(parsed).index(b'"12":'),self.writer.encoded(parsed).index(b'"2":'))

    def test_real_entry_accepts_original_writer_integer_keys_and_real_terminal(self):
        output = self.invoke()
        raw = self.summary_path.read_bytes()
        self.assertEqual(raw,self.writer.encoded(self.report))
        self.assertNotEqual(C.encoded(self.report),C.encoded(C.read_json(self.summary_path)))
        self.reader.assert_any_call(self.summary_path,C.sha(raw),limit=4*1024*1024)
        self.validator.assert_called_once_with(self.summary_path,C.sha(raw),self.sources,
            self.snapshot_path,C.sha(self.snapshot_path.read_bytes()))
        self.assertEqual(self.verify.call_count,2)
        self.assertEqual(output['validation']['assigned_official_gates'],27)
        self.assertEqual(output['validation']['public_completions'],21)
        self.assertEqual(output['summary_sha256'],C.sha(raw))
        self.assertFalse(output['full_29_node_acceptance'])
        self.assertEqual(C.read_json(self.workspace/'CHILD_RESULT.json'),output)

    def test_returned_numeric_type_changes_keep_distinct_writer_bytes(self):
        cases = (('rows',16.0),('host_peak_rss_kib',True),('host_wall_seconds',3.0))
        for i,(field,value) in enumerate(cases):
            with self.subTest(field=field,value=value):
                self.workspace = Path(self.tmp.name)/('numeric-type-'+str(i))
                self.snapshot_path = self.workspace/'snapshot/SNAPSHOT.json'
                self.summary_path = self.workspace/'actual/summary.json'
                # Isolate each returned-object change after saving valid bytes.
                original = self.report[field]
                self.return_change = lambda report,field=field,value=value:report.update({field:value})
                with self.assertRaisesRegex(ValueError,'writer bytes differ'):self.invoke()
                self.validator.assert_not_called(); self.assert_no_child_result()
                self.report[field] = original

    def test_writer_equivalent_tuple_list_conversion_is_allowed(self):
        self.report['metadata']['synthetic_writer_conversion'] = [1,2]
        self.snapshot['metadata']['synthetic_writer_conversion'] = [1,2]
        self.return_change = lambda report:report['metadata'].update(synthetic_writer_conversion=(1,2))
        output = self.invoke()
        self.assertEqual(output['validation']['assigned_official_gates'],27)
        self.assertEqual(self.summary_path.read_bytes(),self.writer.encoded(self.report))
        self.validator.assert_called_once()

    def test_returned_nonfinite_values_fail_original_writer(self):
        self.return_change = lambda report:report.update(host_wall_seconds=float('nan'))
        with self.assertRaises(ValueError):self.invoke()
        self.validator.assert_not_called(); self.assert_no_child_result()

    def test_changed_writer_whitespace_is_not_semantically_normalized(self):
        self.disk_change = lambda raw:raw+b'\n'
        with self.assertRaisesRegex(ValueError,'writer bytes differ'):self.invoke()
        self.validator.assert_not_called(); self.assert_no_child_result()

    def test_changed_disk_metadata_rejected_before_terminal(self):
        self.disk_change = lambda raw:raw.replace(b'"rows": 16',b'"rows": 128',1)
        with self.assertRaisesRegex(ValueError,'writer bytes differ'):self.invoke()
        self.validator.assert_not_called(); self.assert_no_child_result()

    def test_changed_returned_metadata_rejected_before_terminal(self):
        self.return_change = lambda report:report.update(rows=128)
        with self.assertRaisesRegex(ValueError,'writer bytes differ'):self.invoke()
        self.validator.assert_not_called(); self.assert_no_child_result()

    def test_strict_reader_rejects_duplicates_nonfinite_and_size_before_terminal(self):
        cases = (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}',b'{"x":1e999}',
                 b' '*(4*1024*1024+1))
        for i,raw in enumerate(cases):
            with self.subTest(case=i):
                self.workspace = Path(self.tmp.name)/('strict-'+str(i))
                self.snapshot_path = self.workspace/'snapshot/SNAPSHOT.json'
                self.summary_path = self.workspace/'actual/summary.json'
                self.disk_change = lambda original,raw=raw:raw
                with self.assertRaises(ValueError):self.invoke()
                self.validator.assert_not_called(); self.assert_no_child_result()

    def test_strict_reader_binds_hash_of_first_read(self):
        self.read_change = lambda path:path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'metadata hash differs'):self.invoke()
        self.validator.assert_not_called(); self.assert_no_child_result()

    def test_writer_match_does_not_bypass_terminal_metadata_rejection(self):
        self.report['rows'] = 128
        with self.assertRaisesRegex(self.terminal.InvalidReceipt,'SUMMARY_STATUS'):self.invoke()
        self.validator.assert_called_once(); self.assert_no_child_result()

    def test_writer_match_does_not_bypass_terminal_official_gate(self):
        stage = self.report['comparison']['methods']['official_self_cache']['stages']['y']
        stage['verdict']['passed'] = False
        with self.assertRaises(self.terminal.InvalidReceipt):self.invoke()
        self.validator.assert_called_once(); self.assert_no_child_result()

    def test_postflight_source_drift_still_rejected(self):
        self.post_sources = dict(self.sources,extra='d'*64)
        with self.assertRaisesRegex(ValueError,'postflight source/snapshot drift'):self.invoke()
        self.validator.assert_called_once(); self.assert_no_child_result()

    def test_postflight_snapshot_drift_still_rejected(self):
        self.after_terminal = lambda:self.snapshot_path.write_bytes(self.snapshot_path.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'postflight source/snapshot drift'):self.invoke()
        self.validator.assert_called_once(); self.assert_no_child_result()

    def test_postflight_admission_still_required(self):
        with self.assertRaisesRegex(ValueError,'postflight admission failure'):self.invoke(post_verify_error=True)
        self.assertEqual(self.verify.call_count,2)
        self.validator.assert_called_once(); self.assert_no_child_result()

    def test_postflight_deadline_still_required(self):
        self.clock_values = [1000,1924]
        with self.assertRaisesRegex(ValueError,'postflight missed deadline'):self.invoke()
        self.validator.assert_called_once(); self.assert_no_child_result()


class EntryTests(unittest.TestCase):
    def test_producer_workspace_is_disjoint_before_generated_import(self):
        with tempfile.TemporaryDirectory() as name:
            parent=Path(name); source=parent/'source';source.mkdir()
            child=source/'producer';child.mkdir();sibling=parent/'producer';sibling.mkdir()
            with patch.object(C,'ROOT',source):
                self.assertEqual(A._producer_workspace(sibling),sibling)
                for path in (parent,source,child):
                    with self.subTest(path=path),self.assertRaises(ValueError):
                        A._producer_workspace(path)
                link=parent/'linked';link.symlink_to(sibling,target_is_directory=True)
                with self.assertRaises(ValueError):A._producer_workspace(link)

    def test_tiny_binding_checks_actual_files_and_delegates_schema(self):
        with tempfile.TemporaryDirectory() as name:
            m,q,p,lib,inputs,result,contract,package=synthetic_tiny_binding(name)
            with patch.dict(sys.modules,{package.__name__:package}):
                self.assertEqual(A.verify_tiny(m,q,p,lib),result)
                contract.shape.assert_called_once_with(inputs)
                contract.result.assert_called_once_with(result,q['ci']['commit'],inputs)
                contract.shape.side_effect=ValueError('invalid original input schema')
                with self.assertRaises(ValueError):A.verify_tiny(m,q,p,lib)
                contract.shape.side_effect=lambda value:value
                contract.result.side_effect=ValueError('invalid original result schema')
                with self.assertRaises(ValueError):A.verify_tiny(m,q,p,lib)

    def test_tiny_parent_hashes_and_current_source_bytes_fail_closed(self):
        with tempfile.TemporaryDirectory() as name:
            m,q,p,lib,inputs,result,contract,package=synthetic_tiny_binding(name)
            with patch.dict(sys.modules,{package.__name__:package}):
                for key in ('fresh_tiny_result_sha256','fresh_tiny_source_manifest_sha256'):
                    bad=copy.deepcopy(q);bad[key]='f'*64
                    with self.subTest(parent=key),self.assertRaises(ValueError):A.verify_tiny(m,bad,p,lib)
                for key in ('result','input_contract'):
                    bad=copy.deepcopy(m);bad['tiny'][key]['sha256']='f'*64
                    with self.subTest(pointer=key),self.assertRaises(ValueError):A.verify_tiny(bad,q,p,lib)
                for relative in ('original.py','generated.py'):
                    path=Path(m['tiny']['workspace'])/'source'/relative;raw=path.read_bytes()
                    path.write_bytes(raw+b'drift')
                    with self.subTest(source=relative),self.assertRaises(ValueError):A.verify_tiny(m,q,p,lib)
                    path.write_bytes(raw)

    def test_tiny_each_actual_runtime_identity_binds_current_producer_and_elf(self):
        with tempfile.TemporaryDirectory() as name:
            m,q,p,lib,inputs,result,contract,package=synthetic_tiny_binding(name)
            with patch.dict(sys.modules,{package.__name__:package}):
                for role in ('build','profile2','scalar_silu'):
                    for field,key,value in (('interpreter','sha256','f'*64),('compiler','sha256','f'*64),
                        ('compiler','version','changed compiler'),('combined_elf','sha256','f'*64),
                        ('combined_elf','bytes',8)):
                        changed=copy.deepcopy(result);changed['identities'][role][field][key]=value
                        raw=C.encoded(changed);Path(m['tiny']['result']['path']).write_bytes(raw)
                        badm=copy.deepcopy(m);badq=copy.deepcopy(q)
                        badm['tiny']['result']['sha256']=badq['fresh_tiny_result_sha256']=C.sha(raw)
                        with self.subTest(role=role,field=field,key=key),self.assertRaises(ValueError):
                            A.verify_tiny(badm,badq,p,lib)
                Path(m['tiny']['result']['path']).write_bytes(C.encoded(result))
                with self.assertRaises(ValueError):A.verify_tiny(m,q,p,dict(library_sha256='f'*64))

    def test_tiny_requires_exact_workspace_build_and_origin_paths(self):
        with tempfile.TemporaryDirectory() as name:
            m,q,p,lib,inputs,result,contract,package=synthetic_tiny_binding(name)
            extra=Path(name)/'other.json';extra.write_bytes(b'{}')
            other=Path(name)/'other-source';other.mkdir()
            with patch.dict(sys.modules,{package.__name__:package}):
                mutations=(('tiny','result','path',str(extra)),('library','receipt','path',str(extra)),
                           ('library','binary','path',str(extra)))
                for section,field,key,value in mutations:
                    bad=copy.deepcopy(m);bad[section][field][key]=value
                    with self.subTest(field=field),self.assertRaises(ValueError):A.verify_tiny(bad,q,p,lib)
                bad=copy.deepcopy(m);bad['library']['origin_root']=str(other)
                with self.assertRaises(ValueError):A.verify_tiny(bad,q,p,lib)

    def test_qualification_exact_and_non_authorizing(self):
        p,q = synthetic_qualification()
        self.assertEqual(A.validate_qualification(q,p,'d'*64),q)
        self.assertTrue(all(v is False for v in q['claims'].values()))
        for key in q:
            bad = copy.deepcopy(q); del bad[key]
            with self.subTest(missing=key),self.assertRaises(ValueError):
                A.validate_qualification(bad,p,'d'*64)

    def test_qualification_identity_fail_closed(self):
        p,q = synthetic_qualification()
        for key,val in [('schema',True),('status','PASS'),('profile','historical'),('attempt_nonce','e'*64),
            ('producer_manifest_sha256','e'*64),('producer_source_manifest_sha256','e'*64),
            ('host_sha256','e'*64),('runtime_identity_sha256','e'*64),('child_pid',True),
            ('child_exit_code',False),('child_exit_code',1),('owned_group_cleanup_complete',False),
            ('producer_native_gate_validated',False),('elapsed_seconds',float('nan'))]:
            bad = copy.deepcopy(q);bad[key]=val
            with self.subTest(key=key,val=val),self.assertRaises(ValueError):
                A.validate_qualification(bad,p,'d'*64)
        for key in A.CLAIMS:
            bad=copy.deepcopy(q);bad['claims'][key]=True
            with self.subTest(claim=key),self.assertRaises(ValueError):
                A.validate_qualification(bad,p,'d'*64)

    def test_only_first_ci_attempt(self):
        for attempt in ('2','01',1,True,'0','１'):
            with self.subTest(attempt=attempt),self.assertRaises(ValueError):
                A.ci_identity(dict(commit='a'*40,run_id='123',run_attempt=attempt))

    def test_manifest_only_fresh_canonical_m16(self):
        good=synthetic_manifest();self.assertEqual(A.validate_manifest(good),good)
        for key,val in [('rows',True),('rows',128),('past_tokens',True),('past_tokens',1),
                        ('enable_raw_kv',False),('enable_packed',False),('schema',True),
                        ('profile','qwen2-public-pv16-packed-m16-linked-v1'),('status','PASS'),
                        ('source_manifest_sha256','f'*64)]:
            bad=copy.deepcopy(good);bad[key]=val
            with self.subTest(key=key,val=val),self.assertRaises(ValueError):A.validate_manifest(bad)

    def test_modes_do_not_infer_fresh_or_launch(self):
        for enabled in (False,1,None):
            with self.assertRaises(ValueError):A.fresh_mode(enabled,'/tmp/not-read','a'*64,rows=16)
        for rows in (True,1,128):
            with self.assertRaises(ValueError):A.fresh_mode(True,'/tmp/not-read','a'*64,rows=rows)
        with self.assertRaises(ValueError):C.authorize_run({})

    def test_run_context_requires_independent_parent_binding(self):
        now=time.monotonic();sources={'synthetic.py':'a'*64}
        context=dict(profile=C.PROFILE,attempt=1,pid=os.getpid(),parent_pid=os.getppid(),started=now,
            work_deadline=now+C.WORK_SECONDS,outer_deadline=now+C.OUTER_SECONDS,
            source_manifest_sha256=C.sha(C.encoded(sources)),producer_receipt_sha256='a'*64,attempt_nonce='b'*64)
        with patch.object(C,'snapshot',return_value=sources),patch.object(C,'git_context',return_value={}):
            self.assertEqual(C.authorize_run(context),sources)
            for key,val in [('pid',os.getpid()+1),('parent_pid',os.getppid()+1),('attempt',True),
                            ('attempt',2),('producer_receipt_sha256',None),('attempt_nonce','x'),
                            ('work_deadline',now+1000),('outer_deadline',now+1000)]:
                bad=dict(context);bad[key]=val
                with self.subTest(key=key),self.assertRaises(ValueError):C.authorize_run(bad)

    def test_wholephase_numeric_validator_exact_preservation(self):
        self.assertTrue(P.check_terminal_scope())
        before=ast.parse((P.HERE/'terminal_original.py').read_text())
        after=ast.parse((P.HERE/'terminal_validator.py').read_text())
        functions=lambda tree:{n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,ast.FunctionDef)}
        b,a=functions(before),functions(after)
        changed={n for n in b if b[n]!=a[n]}
        self.assertEqual(changed,{'check_comparison','validate_terminal'})

    def test_composition_preserves_numeric_control_bodies(self):
        with tempfile.TemporaryDirectory() as name:
            temp=Path(name);producer=temp/'portable_official_producer';producer.mkdir()
            (producer/'driver.py').write_text('raise RuntimeError("cold synthetic driver must never execute")\n')
            (producer/'source-lock.json').write_text('{"schema":1,"sources":{}}\n')
            result=P.compose(temp/'source',git_head='a'*40,producer_package=producer)
            self.assertFalse(result['actual_chain_executed']);self.assertFalse(result['full_public_admission'])
            self.assertGreater(len(result['source_sha256']),316)
            for relative,expected in result['source_sha256'].items():
                self.assertEqual(P.sha(temp/'source'/relative),expected)
            code=(temp/'source'/P.TARGETS[0]).read_text()
            self.assertIn('gate.opened=True',code)
            self.assertIn("require(report['comparison']['fixed_arithmetic_pass']",code)
            self.assertIn('wall_budget<=900',code)
            self.assertIn('packed_contract.authorize_run(run_context)',code)

    def test_bound_json_duplicate_nonfinite_symlink(self):
        with tempfile.TemporaryDirectory() as name:
            p=Path(name)/'x.json'
            for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e999}'):
                p.write_bytes(raw)
                with self.assertRaises(ValueError):C.read_json(p)
            p.write_bytes(b'{}');link=p.with_name('link');link.symlink_to(p)
            with self.assertRaises(ValueError):C.read_json(link)

    def test_cold_import_no_native_or_tensor_packages(self):
        code = ('import sys; from candidates.qwen2_resident_matrix.attention_packed_m16_same_host '
                'import admission, contract, entry; '
                'assert not any(n in sys.modules for n in ("numpy","torch","ctypes")); '
                'print("COLD_METADATA_ONLY")')
        result=subprocess.run([sys.executable,'-B','-c',code],cwd=P.ROOT,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('COLD_METADATA_ONLY',result.stdout)

    def test_admission_has_explicit_hash_only_handoff(self):
        code=(P.HERE/'admission.py').read_text()
        tree=ast.parse(code)
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='verify_handoff']
        self.assertEqual(len(calls),1)
        self.assertEqual([(k.arg,ast.literal_eval(k.value)) for k in calls[0].keywords],[('decode_native',False)])


if __name__ == '__main__':
    unittest.main()

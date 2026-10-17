"""Cold, synthetic metadata and source tests. Never producer/ELF/numeric runs."""
import ast
import copy
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

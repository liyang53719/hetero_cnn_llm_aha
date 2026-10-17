"""Stdlib cold metadata/source boundaries only. No native or numeric execution."""
import ast
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from . import admission as A, contract as C, prepare as P, identity


def synthetic_manifest():
    ptr=dict(path='/synthetic/file',sha256='a'*64);sources={'synthetic.py':'b'*64}
    return dict(schema=1,profile=C.PROFILE,status=A.STATUS,rows=128,past_tokens=0,
        enable_raw_kv=True,enable_packed=True,source_sha256=sources,source_manifest_sha256=C.sha(C.encoded(sources)),
        producer_origin='/synthetic/origin',producer_workspace='/synthetic/job/producer128',
        **{k:dict(ptr) for k in ('producer_manifest','producer_receipt','producer_context','m16_prerequisite')},
        library=dict(receipt=dict(ptr),binary=dict(path='/synthetic/library.so',bytes=1,sha256='c'*64),origin_root='/synthetic/tiny/source'))


def synthetic_qualification():
    m=synthetic_manifest();p=dict(attempt_nonce='b'*64,ci=dict(commit='c'*40,run_id='1',run_attempt='1'),
        source_manifest_sha256='d'*64,parent_context_sha256='a'*64,host={'synthetic':True},runtime_identity={'synthetic':True})
    q=dict(schema=1,profile=A.QUALIFIED_PROFILE,status='PASS_FRESH_M128_PRODUCER',attempt_nonce=p['attempt_nonce'],
        ci=p['ci'],host_sha256=C.sha(C.encoded(p['host'])),runtime_identity_sha256=C.sha(C.encoded(p['runtime_identity'])),
        producer_manifest_sha256='a'*64,producer_source_manifest_sha256=p['source_manifest_sha256'],parent_context_sha256='a'*64,
        verifier_receipt_sha256='e'*64,child_pid=999,child_exit_code=0,owned_group_cleanup_complete=True,
        original_array_gate_revalidated=True,claims={k:False for k in A.CLAIMS})
    return m,p,q


class EntryTests(unittest.TestCase):
    def test_manifest_requires_exact128_and_fresh_identity(self):
        good=synthetic_manifest();self.assertEqual(A.validate_manifest(good),good)
        for key,value in [('rows',16),('rows',True),('rows',128.0),('past_tokens',False),('past_tokens',1),
            ('schema',True),('profile','historical'),('status','PASS'),('enable_raw_kv',False),('enable_packed',False),
            ('source_manifest_sha256','f'*64),('producer_workspace','/tmp/../producer128')]:
            bad=copy.deepcopy(good);bad[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):A.validate_manifest(bad)
        for key in good:
            bad=copy.deepcopy(good);del bad[key]
            with self.subTest(missing=key),self.assertRaises(ValueError):A.validate_manifest(bad)

    def test_qualification_requires_independent_original_array_gate_and_cleanup(self):
        m,p,q=synthetic_qualification();self.assertEqual(A.validate_qualification(q,p,m),q)
        for key,value in [('schema',True),('status','PASS'),('attempt_nonce','f'*64),('child_pid',True),
            ('child_exit_code',False),('child_exit_code',1),('owned_group_cleanup_complete',False),
            ('original_array_gate_revalidated',False),('producer_source_manifest_sha256','f'*64),
            ('parent_context_sha256','f'*64),('host_sha256','f'*64),('runtime_identity_sha256','f'*64),
            ('verifier_receipt_sha256','bad')]:
            bad=copy.deepcopy(q);bad[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):A.validate_qualification(bad,p,m)
        for key in q:
            bad=copy.deepcopy(q);del bad[key]
            with self.subTest(missing=key),self.assertRaises(ValueError):A.validate_qualification(bad,p,m)
        for key in A.CLAIMS:
            bad=copy.deepcopy(q);bad['claims'][key]=True
            with self.subTest(claim=key),self.assertRaises(ValueError):A.validate_qualification(bad,p,m)

    def test_context_enforces_original_fixed_envelope_current_parent_and_m16(self):
        now=time.monotonic();sources={'synthetic.py':'a'*64}
        value=dict(profile=C.PROFILE,attempt=1,pid=os.getpid(),parent_pid=os.getppid(),started=now,
            work_deadline=now+2424,outer_deadline=now+2430,source_manifest_sha256=C.sha(C.encoded(sources)),
            producer_receipt_sha256='b'*64,attempt_nonce='c'*64,m16_prerequisite_sha256='d'*64)
        with patch.object(C,'snapshot',return_value=sources),patch.object(C,'git_context',return_value={}):
            self.assertEqual(C.authorize_run(value),sources)
            for key,change in [('rows',16),('attempt',True),('attempt',2),('pid',os.getpid()+1),
                ('parent_pid',os.getppid()+1),('started',float('nan')),('work_deadline',now+2425),
                ('outer_deadline',now+2431),('m16_prerequisite_sha256',None),('attempt_nonce','x')]:
                bad=dict(value);bad[key]=change
                with self.subTest(key=key),self.assertRaises(ValueError):C.authorize_run(bad)
        self.assertEqual((C.NUMERIC_SECONDS,C.WORK_SECONDS,C.CLEANUP_SECONDS,C.OUTER_SECONDS),(2400,2424,2429,2430))

    def test_modes_reject_looped_or_smaller_geometry(self):
        for rows in (True,1,16,17,32,128.0):
            with self.subTest(rows=rows),self.assertRaises(ValueError):A.fresh_mode(True,'/tmp/manifest','a'*64,rows=rows)
        for flag in (False,1,None):
            with self.subTest(flag=flag),self.assertRaises(ValueError):A.fresh_mode(flag,'/tmp/manifest','a'*64,rows=128)
        with patch.object(C,'snapshot',return_value={}):
            self.assertEqual(C.modes(fresh_profile=True,enable_raw_kv=True,enable_packed=True,rows=128),{})
            with self.assertRaises(ValueError):C.modes(fresh_profile=True,enable_raw_kv=True,enable_packed=True,rows=16)

    def test_canonical_json_symlink_hardlink_and_nonfinite_boundaries(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);p=root/'value.json';p.write_bytes(b'{}');self.assertEqual(C.read_json(p),{})
            link=root/'link';link.symlink_to(p)
            with self.assertRaises(ValueError):C.read_json(link)
            os.link(p,root/'alias')
            with self.assertRaises(ValueError):C.read_json(p)
            (root/'alias').unlink()
            for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":Infinity}'):
                p.write_bytes(raw)
                with self.assertRaises(ValueError):C.read_json(p)
            p.write_bytes(b' '*100)
            with self.assertRaises(ValueError):C.read_json(p,limit=99)

    def test_full_output_must_be_current_job_disjoint_and_fresh(self):
        from . import entry
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir();outside=root/'wrong';inside=source/'full_m128'
            manifest=synthetic_manifest();manifest['producer_workspace']=str(root/'producer128')
            with patch.object(C,'ROOT',source),patch.object(C,'authorize_run',return_value={}), \
                 patch.object(A,'read_manifest',return_value=manifest),patch.object(A,'verify') as verify:
                for path in (inside,outside):
                    with self.subTest(path=path),self.assertRaises(ValueError):
                        entry.run(path,manifest='/unused',manifest_sha256='a'*64,run_context={})
                    self.assertFalse(path.exists())
                verify.assert_not_called()

    def test_terminal_identity_is_pure_and_has_only_five_keys(self):
        tree=ast.parse(Path(identity.__file__).read_bytes())
        self.assertFalse(any(isinstance(n,(ast.Import,ast.ImportFrom)) for n in ast.walk(tree)))
        self.assertEqual(identity.PROFILE,C.PROFILE)

    def test_original_terminal_exact_identity_only_transform(self):
        self.assertTrue(P.check_terminal_scope())
        before=ast.parse((P.HERE/'terminal_original.py').read_text());after=ast.parse((P.HERE/'terminal_validator.py').read_text())
        funcs=lambda t:{n.name:ast.dump(n,include_attributes=False) for n in t.body if isinstance(n,ast.FunctionDef)}
        a,b=funcs(before),funcs(after)
        self.assertEqual({n for n in a if a[n]!=b[n]},{'check_snapshot_identity','check_comparison','validate_terminal'})

    def test_profile_preserves_all_owner_and_host_type_guards(self):
        original=(P.ROOT/'candidates/qwen2_resident_matrix/attention_packed_m128_entry/profile.py').read_text()
        fresh=(P.HERE/'profile.py').read_text().replace('from . import admission','from ..attention_packed_m128_assets import admission')
        self.assertEqual(fresh,original)
        self.assertIn("type(job) is not public.group.PrefixJob",fresh)
        self.assertIn("type(job.m) is not int or job.m != 128",fresh)
        self.assertIn('schedule=PackedSchedule()',fresh)

    def test_profile_wrong_host_job_rejected_before_native_load(self):
        from .profile import PackedM128PublicProfile
        for obj in (object(),None,1):
            with self.subTest(owner=obj),self.assertRaises(ValueError):
                PackedM128PublicProfile('/missing','a'*64,'/missing','b'*64).install(obj,None,None,0)


def original_writer_sources():
    """Load only original encoder/save AST and literal PC map; never numeric imports."""
    base=P.ROOT/'candidates/qwen2_resident_matrix'
    encoder_tree=ast.parse((base/'ffn_public/check_prefix_numeric.py').read_text())
    encoder=next(n for n in encoder_tree.body if isinstance(n,ast.FunctionDef) and n.name=='encoded')
    original_tree=ast.parse((base/'dense_block_reduce/check_public_numeric.py').read_text())
    run=next(n for n in original_tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
    save=next(n for n in run.body if isinstance(n,ast.FunctionDef) and n.name=='save')
    policy=ast.parse((base/'official_bf16/execution.py').read_text())
    jobs=next(ast.literal_eval(n.value) for n in policy.body if isinstance(n,ast.Assign) and
              any(isinstance(t,ast.Name) and t.id=='JOBS' for t in n.targets))
    namespace={'json':json}
    exec(compile(ast.Module(body=[encoder],type_ignores=[]),'<original-encoder-only>','exec'),namespace)
    return namespace['encoded'],save,jobs


class WriterByteBoundaryTests(unittest.TestCase):
    def report(self):
        _,_,jobs=original_writer_sources()
        return dict(status_count=1,execution=dict(host=dict(validated_policy_jobs={
            pc:dict(kind=value[0]) for pc,value in jobs.items()})))

    def exercise(self,report,*,raw_change=None,read_change=None,error=None):
        from contextlib import ExitStack, nullcontext
        import importlib
        from types import SimpleNamespace
        from . import entry, terminal_validator
        original_encoded,save_node,_=original_writer_sources()
        original_package=importlib.import_module('candidates.qwen2_resident_matrix.dense_block_reduce')
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            root=Path(directory);workspace=root/'full_m128';producer=root/'producer.json'
            producer.write_bytes(C.encoded(dict(attempt_nonce='c'*64)))
            manifest=synthetic_manifest();manifest['producer_workspace']=str(root/'producer128')
            manifest['producer_manifest']=dict(path=str(producer),sha256=C.sha(producer.read_bytes()))
            context=dict(producer_receipt_sha256='a'*64,m16_prerequisite_sha256='a'*64,
                         attempt_nonce='c'*64,work_deadline=time.monotonic()+C.WORK_SECONDS)
            sources={'cold_source.py':'b'*64};admitted={'terminal_identity':{'source':'parent-bound fixture'}}
            def prepare(out,*args,**kwargs):
                out.mkdir();path=out/'SNAPSHOT.json';path.write_bytes(C.encoded({'fixture':True}))
                return path,{'fixture':True}
            def run(out,*args,**kwargs):
                out.mkdir();namespace=dict(out=out,report=report,encoded=original_encoded)
                exec(compile(ast.Module(body=[save_node],type_ignores=[]),'<original-save-only>','exec'),namespace)
                namespace['save']()
                if raw_change is not None:
                    path=out/'summary.json';path.write_bytes(raw_change(path.read_bytes(),report))
                return report
            fake=SimpleNamespace(prepare=prepare,run=run,encoded=original_encoded)
            stack.enter_context(patch.object(original_package,'check_public_numeric',fake,create=True))
            stack.enter_context(patch.object(C,'authorize_run',return_value=sources))
            stack.enter_context(patch.object(C,'snapshot',return_value=sources))
            stack.enter_context(patch.object(A,'read_manifest',return_value=manifest))
            admission=stack.enter_context(patch.object(A,'verify',return_value=admitted))
            terminal=stack.enter_context(patch.object(terminal_validator,'validate_terminal',return_value={'gate':'stub'}))
            original_read=C.read_json
            def strict_read(path,*args,**kwargs):
                if read_change is not None and Path(path).name=='summary.json':
                    read_change(Path(path))
                return original_read(path,*args,**kwargs)
            reader=stack.enter_context(patch.object(C,'read_json',side_effect=strict_read))
            with self.assertRaises(error) if error else nullcontext():
                output=entry.run(workspace,manifest='/unused',manifest_sha256='d'*64,run_context=context)
            if error:
                terminal.assert_not_called();self.assertFalse((workspace/'CHILD_RESULT.json').exists())
            else:
                self.assertEqual(output['status'],'VALIDATED_FRESH_M128_CHILD_RESULT')
                terminal.assert_called_once()
                self.assertEqual(terminal.call_args.kwargs['fresh_identity'],admitted['terminal_identity'])
                self.assertEqual(admission.call_count,2)
                calls=[c for c in reader.call_args_list if Path(c.args[0]).name=='summary.json']
                self.assertEqual(len(calls),1);self.assertEqual(calls[0].kwargs['limit'],16*1024*1024)
                raw=(workspace/'actual/summary.json').read_bytes()
                self.assertEqual(calls[0].args[1],C.sha(raw))
                self.assertEqual(output['summary_sha256'],C.sha(raw))
                self.assertEqual(original_encoded(report),raw)

    def test_genuine_original_encoder_and_integer_pc_ordering(self):
        encoded,_,jobs=original_writer_sources()
        self.assertTrue(all(type(pc) is int for pc in jobs))
        self.assertIn(2,jobs);self.assertIn(12,jobs)
        report=self.report();raw=encoded(report);disk=json.loads(raw)
        self.assertNotEqual(C.encoded(report),C.encoded(disk))
        self.assertEqual(raw,(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode())
        self.assertNotEqual(encoded(report),encoded(disk))
        # Minimal two-digit regression uses genuine dispatch PCs 2 and 12.
        pcs={'execution':{'host':{'validated_policy_jobs':{2:{},12:{}}}}}
        self.assertNotEqual(C.encoded(pcs),C.encoded(json.loads(encoded(pcs))))
        self.exercise(report)
        self.exercise(pcs)

    def test_original_writer_alias_chain_and_save_body_are_source_derived(self):
        base=P.ROOT/'candidates/qwen2_resident_matrix'
        for name,expected in (
            ('dense_block_reduce/check_public_numeric.py','prior.encoded'),
            ('official_bf16/check_numeric.py','base.encoded'),
            ('ffn_public/check_fullgraph_numeric.py','base.encoded')):
            tree=ast.parse((base/name).read_text())
            matches=[(target,node.value) for node in tree.body if isinstance(node,ast.Assign)
                     for target in node.targets if isinstance(target,ast.Tuple)]
            aliases=[ast.unparse(value.elts[index]) for target,value in matches
                     for index,item in enumerate(target.elts) if isinstance(item,ast.Name) and item.id=='encoded']
            self.assertEqual(aliases,[expected])
        _,save,_=original_writer_sources()
        self.assertEqual(ast.unparse(save),"def save():\n    (out / 'summary.json').write_bytes(encoded(report))")

    def test_scalar_int_float_bool_and_writer_byte_drift_fail_before_terminal(self):
        for value in (1.0,True,2):
            def changed_return(raw,report,value=value):
                report['status_count']=value
                return raw
            with self.subTest(returned_scalar=value,type=type(value)):
                self.exercise(self.report(),raw_change=changed_return,error=ValueError)
        for change in (lambda raw,r:raw.rstrip(b'\n'),lambda raw,r:raw+b' ',
                       lambda raw,r:raw.replace(b'"status_count": 1',b'"status_count": true'),
                       lambda raw,r:raw.replace(b'"status_count": 1',b'"status_count": 1.0'),
                       lambda raw,r:C.encoded(json.loads(raw))):
            with self.subTest(change=change):self.exercise(self.report(),raw_change=change,error=ValueError)

    def test_duplicate_nonfinite_truncated_disk_json_fail_before_terminal(self):
        for raw in (b'{"a":1,"a":2}\n',b'{"a":NaN}\n',b'{"a":Infinity}\n',
                    b'{"a":-Infinity}\n',b'{"a":1e999}\n',b'{"a":',b'{}{}'):
            with self.subTest(raw=raw):
                self.exercise(self.report(),raw_change=lambda old,r,raw=raw:raw,error=ValueError)
        for value in (float('nan'),float('inf'),float('-inf')):
            report=self.report();report['status_count']=value
            with self.subTest(returned=value):self.exercise(report,error=ValueError)

    def test_hash_drift_between_raw_read_and_strict_reader_fails_before_terminal(self):
        self.exercise(self.report(),read_change=lambda p:p.write_bytes(p.read_bytes()+b' '),error=ValueError)

    def test_exact_16mib_boundary_and_overflow_before_terminal(self):
        encoded,_,_=original_writer_sources();report=self.report();report['padding']=''
        report['padding']='x'*(16*1024*1024-len(encoded(report)))
        self.assertEqual(len(encoded(report)),16*1024*1024)
        self.exercise(report)
        report['padding']+='x'
        self.exercise(report,error=ValueError)

    def test_four_mib_metadata_boundary_retains_hash_and_size_fences(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'receipt.json';limit=4*1024*1024
            raw=b'{"padding":"'+b'x'*(limit-len(b'{"padding":""}'))+b'"}'
            self.assertEqual(len(raw),limit);path.write_bytes(raw)
            self.assertEqual(len(C.read_json(path,C.sha(raw),limit=limit)['padding']),limit-14)
            with self.assertRaises(ValueError):C.read_json(path,'f'*64,limit=limit)
            path.write_bytes(raw+b' ')
            with self.assertRaises(ValueError):C.read_json(path,C.sha(raw+b' '),limit=limit)


if __name__=='__main__':unittest.main()

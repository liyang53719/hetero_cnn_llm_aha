"""Cold synthetic orchestration and real bounded-file tests; no model/download.

Synthetic tiny payloads test the coordinator, never stand in for real reference
approval. The production source-derived mathematical gates remain independently
compiled and tested by test_capture_source, with no tensor import.
"""
import contextlib
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock
from . import pair as Q
from . import policy as P


class PairTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.patch=patch.object(Q,'ROOT',self.root);self.patch.start();self.addCleanup(self.patch.stop)

    def make_file(self,name,data=b'abcdef'):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);return p

    def receipts(self):
        items=[]
        for run in Q.RUNS:
            out=Q.run_out(run);out.mkdir(parents=True)
            outputs={}
            for i in range(29):
                name='n%02d'%i;data=bytes((i,0,0,0))*4;p=out/(name+'.f32le');p.write_bytes(data)
                outputs[name]=dict(file=p.name,bytes=len(data),shape=[4],native_bytes=8,native_dtype='torch.bfloat16',
                    export_dtype='FP32 exact BF16 widening',native_stride=[1],storage_offset=0,is_contiguous=True,
                    sha256=P.sha(data),native_sha256=P.sha(data),token_major_sha256=P.sha(data))
            common=dict(source_closure_sha256='a'*64,platform_files={'python':'same','libpython':'same'},
                sources={'source':'same'},raw13={'raw':'same'},native_files={'native':'same'})
            items.append(dict(run=run,out=out,outputs=outputs,common=common,inventory={},guard={},filesystem={}))
        return items

    def compare(self,receipts):
        with patch.object(Q,'validate_run',side_effect=lambda run:copy.deepcopy(receipts[Q.RUNS.index(run)])):
            return Q.compare_pair(copy.deepcopy(receipts))

    def test_direct_pair_checks_all29_and_stays_pending(self):
        rows=self.receipts();result=self.compare(rows)
        self.assertEqual(result['status'],'NEW_REFERENCE_PAIR_EQUAL_PENDING_REVIEW')
        self.assertEqual((result['checked_outputs'],result['equal_outputs']),(29,29))
        self.assertEqual(result['nodes'],[dict(node='OUTPUT_%02d'%i,equal=True) for i in range(29)])
        for flag in ('reference_freeze_available','independently_approved','numerical_acceptance_claimed','old_pass_inherited','dut_executed'):
            self.assertIs(result[flag],False)
        raw=json.dumps(result)
        for forbidden in ('sha256','shape','stride',str(self.root),'f32le','libpython'):
            self.assertNotIn(forbidden,raw)

    def test_legitimate_unequal_payload_is_pending_diagnostic(self):
        rows=self.receipts();record=rows[1]['outputs']['n01'];data=b'changed contents'
        (rows[1]['out']/record['file']).write_bytes(data)
        for key in Q.DIGEST_FIELDS:record[key]=P.sha(data)
        result=self.compare(rows)
        self.assertEqual(result['status'],'NEW_REFERENCE_PAIR_DIFFERENT_PENDING_REVIEW')
        self.assertEqual(result['equal_outputs'],28)

    def test_same_length_corruption_is_not_equal(self):
        rows=self.receipts();item=rows[1]['outputs']['n00'];path=rows[1]['out']/item['file']
        path.write_bytes(b'x'*item['bytes'])
        with self.assertRaisesRegex(ValueError,'hash evidence conflict'):self.compare(rows)

    def test_metadata_layout_platform_source_mismatch_rejected(self):
        for scope,key in [('common','platform_files'),('common','sources'),('common','raw13'),('common','native_files')]:
            with self.subTest(key=key):
                # Separate root each time because receipts are exclusive.
                for path in self.root.rglob('*.f32le'):path.unlink()
                for run in Q.RUNS:
                    out=Q.run_out(run)
                    if out.exists():out.rmdir()
                rows=self.receipts();rows[1][scope][key]={'drift':'different'}
                with self.assertRaisesRegex(ValueError,'source/raw/native/platform'):self.compare(rows)
        rows[1]['common']=copy.deepcopy(rows[0]['common']);rows[1]['outputs']['n00']['native_stride']=[2]
        with self.assertRaisesRegex(ValueError,'dtype/geometry/layout'):self.compare(rows)

    def test_post_comparison_identity_revalidation_rejects_mutation(self):
        rows=self.receipts();calls=[]
        def validate(run):
            calls.append(run);value=copy.deepcopy(rows[Q.RUNS.index(run)])
            if len(calls)>2:value['guard']={'drift':'after comparison'}
            return value
        with patch.object(Q,'validate_run',side_effect=validate):
            with self.assertRaisesRegex(ValueError,'after comparison'):Q.compare_pair(copy.deepcopy(rows))
        self.assertEqual(calls,['new01','new02','new01','new02'])

    def test_missing_seal_content_corruption_and_extra_inventory_rejected(self):
        path=self.make_file('out/a',b'1234');out=path.parent
        with self.assertRaisesRegex(ValueError,'exact sealed inventory'):Q.inventory(out,{'a','SEAL.json'})
        self.make_file('out/SEAL.json',b'{}')
        actual=Q.inventory(out,{'a','SEAL.json'})
        path.write_bytes(b'4321')
        self.assertNotEqual(actual,Q.inventory(out,{'a','SEAL.json'}))
        self.make_file('out/extra',b'bad')
        with self.assertRaisesRegex(ValueError,'exact sealed inventory'):Q.inventory(out,{'a','SEAL.json'})

    def test_symlink_and_hardlink_and_directory_rejected(self):
        path=self.make_file('one');(self.root/'symlink').symlink_to(path)
        with self.assertRaises(ValueError):Q.file_identity(self.root/'symlink')
        os.link(path,self.root/'hardlink')
        with self.assertRaises(ValueError):Q.file_identity(path)
        (self.root/'directory').mkdir()
        with self.assertRaises(ValueError):Q.inventory(self.root/'directory',{'missing'})

    def test_shared_budget_includes_both_runs_and_root_certificates(self):
        self.make_file(Q.WORK+'/new01/bootstrap/payload',b'a'*10)
        self.make_file(Q.WORK+'/new02/bootstrap/payload',b'b'*10)
        self.make_file(Q.WORK+'/EXTERNAL_new01.json',b'c'*5)
        with patch.object(Q,'TOTAL_CAP',24):
            with self.assertRaisesRegex(ValueError,'aggregate pair cap'):Q.disk_gate()
        with patch.object(Q,'TOTAL_CAP',25):Q.disk_gate()
        with patch.object(Q,'TOTAL_CAP',Q.RUN_CAP+24):
            with self.assertRaises(ValueError):Q.disk_gate(reserve=Q.RUN_CAP)

    def test_chunked_comparison_and_length_failure(self):
        a=self.make_file('a',b'a'*23);b=self.make_file('b',b'a'*23)
        with patch.object(Q,'CHUNK',3):self.assertTrue(Q.direct_equal(a,b,23))
        b.write_bytes(b'a'*22+b'b')
        with patch.object(Q,'CHUNK',3):self.assertFalse(Q.direct_equal(a,b,23))
        b.write_bytes(b'a'*22)
        with self.assertRaises(ValueError):Q.direct_equal(a,b,23)

    @contextlib.contextmanager
    def orchestration(self):
        pins=[dict(certificate_sha256=str(i)*64,source_closure_sha256='a'*64) for i in (1,2)]
        for run,pin in zip(Q.RUNS,pins):self.make_file(Q.certificate_path(run),b'opaque')
        events=[]
        def authorization(run):return pins[Q.RUNS.index(run)],b'opaque'
        def identity(path,cap=Q.RUN_CAP):
            for run,pin in zip(Q.RUNS,pins):
                if path==Q.private(Q.certificate_path(run)):return dict(bytes=6,sha256=pin['certificate_sha256'])
            return dict(bytes=1,sha256='a'*64)
        with patch.dict(os.environ,{'GITHUB_SHA':'abc'}),patch.object(Q.subprocess,'check_output',return_value='abc\n'),\
             patch.object(Q,'authorization',side_effect=authorization),patch.object(Q,'file_identity',side_effect=identity),\
             patch.object(Q,'call',side_effect=lambda *a,**k:events.append('prepare')),\
             patch.object(Q,'compare_pair',return_value=Q.aggregate('SYNTHETIC_TEST_ONLY',29,[])),\
             patch.object(Q,'read_json',return_value=Q.aggregate('SYNTHETIC_TEST_ONLY',29,[])):
            Q.private(Q.LOGS).mkdir(parents=True)
            yield events

    def test_first_guard_failure_prevents_second(self):
        with self.orchestration() as events:
            def capture(run):events.append('capture '+run);raise ValueError('synthetic first guard failure')
            with patch.object(Q,'capture_one',side_effect=capture),patch.object(Q,'validate_run') as validate:
                with self.assertRaises(ValueError):Q.capture()
                validate.assert_not_called()
            self.assertEqual(events,['prepare','capture new01'])

    def test_first_validation_failure_prevents_second(self):
        with self.orchestration() as events:
            def validate(run):events.append('validate '+run);raise ValueError('synthetic missing seal')
            with patch.object(Q,'capture_one',side_effect=lambda run:events.append('capture '+run)),patch.object(Q,'validate_run',side_effect=validate):
                with self.assertRaises(ValueError):Q.capture()
            self.assertEqual(events,['prepare','capture new01','validate new01'])

    def test_second_only_after_validated_first_and_prepare_once(self):
        with self.orchestration() as events:
            def validate(run):events.append('validate '+run);return {'run':run}
            with patch.object(Q,'capture_one',side_effect=lambda run:events.append('capture '+run)),patch.object(Q,'validate_run',side_effect=validate):Q.capture()
            self.assertEqual(events,['prepare','capture new01','validate new01','capture new02','validate new02'])

    def resource_fixture(self):
        files={name+'.log':dict(bytes=0,sha256=P.sha(b'')) for name in ('stdout','stderr')}
        resources=dict(returncode=0,limit_reason=None,cleanup_pids=[],rss_is_os_hard_cap=False,
            rss_limit_bytes=1536*(1<<20),independent_watchdog_enabled=False,independent_watchdog_record=None,
            overall_wall_limit_seconds=120,external_watchdog_deadline_seconds=122,cleanup_grace_seconds=2,
            independent_overall_watchdog_enabled=True,overall_clock_started_at='run entry before source/go/input/runtime preflight',
            overall_elapsed_seconds=1,wall_seconds=1,wall_limit_seconds=119,peak_sampled_process_tree_rss_bytes=123,
            rss_poll_seconds=0.02,descendant_cleanup=dict(reaped_descendant_pids=[],remaining_descendants={},cleanup_wait_limit_seconds=2),
            logs={name:dict(total_bytes=0,sha256_all_observed_bytes=P.sha(b''),retained_bytes=0,truncated=False,retained_sha256=P.sha(b'')) for name in ('stdout','stderr')})
        return resources,files

    def test_resources_reject_nonzero_missing_watchdog_and_changed_log(self):
        resources,files=self.resource_fixture()
        Q.resources_checked(resources,files)
        for key,value in [('returncode',2),('overall_elapsed_seconds',121),('independent_overall_watchdog_enabled',False),('rss_limit_bytes',True)]:
            bad=copy.deepcopy(resources);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):Q.resources_checked(bad,files)
        files['stderr.log']['sha256']='b'*64
        with self.assertRaises(ValueError):Q.resources_checked(resources,files)

    @contextlib.contextmanager
    def sealed_fixture(self):
        rows=self.receipts();boundaries={};authorizations={}
        resources,logs=self.resource_fixture()
        def fields(actual,expected,label=''):
            Q.need(type(actual) is dict and all(k in actual and Q.same(actual[k],v) for k,v in expected.items()),label)
        def metadata(outputs,pins):
            Q.need(len(outputs)==29 and all(spec['bytes']==16 for spec in outputs.values()),'synthetic geometry')
        pins=dict(budget={'payload_bytes_per_capture':29*16+32768},
            mask_contract={'native_sha256':P.sha(bytes(32768))},runtime_requirements={},capture_environment={})
        for index,row in enumerate(rows):
            run=row['run'];out=row['out'];identity={'bytes':1,'sha256':'a'*64}
            platform=dict(schema=1,status='CURRENT_PROCESS_PLATFORM_OBSERVED_ONLY',scope='PYTHON_ELF_AND_LOADED_LIBPYTHON_ONLY',
                python_version=[3,12,14],process_id=index+1,
                python=dict(path=str(Q.V.F.PYTHON_HOME/'bin/python3.12'),**Q.V.F.PYTHON_IDENTITY,device=1,inode=2),
                libpython=dict(path=str(Q.V.F.LIBPYTHON),bytes=1,sha256='b'*64,device=1,inode=3),
                independently_reviewed=False,historical_equivalence_claimed=False,full_system_closure=False,numeric_execution_allowed=False)
            certificate=('opaque-synthetic-'+run).encode();self.make_file(Q.certificate_path(run),certificate)
            before=dict(source_manifest=identity,external_certificate_sha256=P.sha(certificate),source_closure_sha256='a'*64,
                native_files={},sources={'synthetic':identity},raw13={'synthetic':identity},platform_files={k:platform[k] for k in ('python','libpython')})
            boundaries[run]=before;authorizations[run]=dict(certificate_sha256=P.sha(certificate),source_closure_sha256='a'*64)
            observations=dict(status=Q.STATUS,stage='bootstrap',contract_id=P.policy()['contract_id'],
                numerical_acceptance_claimed=False,dut_executed=False,old_pass_inherited=False,full_29_node_acceptance=False,
                official_model_ast_nodes=38,official_activation_ast_nodes=14,official_ast_subset_executed=True,
                full_official_forward_executed=False,dynamic_cache_executed=False,transformers_imported=False,
                actual_or_typed_input_read=False,materialized_producer_payload_read=False,saved_reference_payload_read=False,
                legacy_frozen29_comparison_performed=False,source_manifest=identity,source_pins_sha256='a'*64,
                outputs=row['outputs'],boundary=dict(unchanged=True,before_sha256=P.sha(P.encoded(before)),after_sha256=P.sha(P.encoded(before))),
                platform_before=platform,platform_after=copy.deepcopy(platform),runtime={'native_files':{},'environment':{}},
                legacy_contract_diagnostic=dict(status='LEGACY_CONTRACT_DIFFERENT',compared_count=18,equal_count=0,
                    records=[dict(node='NODE_%02d'%i,equal=False) for i in range(18)]))
            go_content=dict(schema=1,action='single-bootstrap',run_id=run,source_manifest=identity,maximum_invocations=1,
                no_retry=True,exclusive_numeric_slot=True,source_review={'synthetic':'not approval'})
            go_path=self.make_file(Q.WORK+'/'+run+'/GO.json',P.encoded(go_content))
            go_receipt=dict(path=str(go_path.relative_to(self.root)),**Q.file_identity(go_path))
            self.make_file(str((out/'GO.json').relative_to(self.root)),P.encoded(dict(receipt=go_receipt,content=go_content)))
            for label in ('BOUNDARY_BEFORE','BOUNDARY_AFTER','WRAPPER_BEFORE','WRAPPER_AFTER'):
                (out/(label+'.json')).write_bytes(P.encoded(before))
            (out/'mask.bf16le').write_bytes(bytes(32768))
            (out/'stdout.log').write_bytes(b'');(out/'stderr.log').write_bytes(b'')
            (out/'STAGES.jsonl').write_bytes(b''.join(P.encoded(dict(stage=stage))+b'\n' for stage in Q.STAGES))
            (out/'OBSERVATIONS.json').write_bytes(P.encoded(observations))
            (out/'BOOTSTRAP_REFERENCE.json').write_bytes(P.encoded(dict(observations,resources=resources,
                wrapper_boundary_unchanged=True,go_identity=go_receipt)))
            seal=dict(schema=1,status=Q.SEALED,mode='bootstrap',run_id=run,manifest='BOOTSTRAP_REFERENCE.json',
                files={p.name:Q.file_identity(p) for p in out.iterdir()},resources=resources,source_manifest=identity,
                numerical_acceptance_claimed=False,dut_executed=False,retries=0)
            (out/'SEAL.json').write_bytes(P.encoded(seal))
            self.make_file(str(Q.guard_log(run).relative_to(self.root)),P.encoded(dict(status=Q.SEALED,
                out=str(out.relative_to(self.root)),seal=Q.file_identity(out/'SEAL.json'),resources=resources)))
        @contextlib.contextmanager
        def configured(run):
            with patch.dict(os.environ,{'QWEN2_NEW_REFERENCE_RUN':run}):yield authorizations[run]
        R=SimpleNamespace(load_pins=lambda:pins,NAMES=tuple(rows[0]['outputs']),fields=fields,
            validate_new_observations=metadata,encoded=P.encoded,PINS_SHA256='a'*64)
        L=SimpleNamespace(snapshot=lambda R,pins:copy.deepcopy(boundaries[os.environ['QWEN2_NEW_REFERENCE_RUN']]))
        with patch.object(Q,'configured',side_effect=configured),patch.object(Q,'runtime',return_value=(R,L)),patch.object(Q,'review_checked'):
            yield rows,boundaries

    def test_full_sealed_fixture_validates_and_compares_actual_files(self):
        with self.sealed_fixture():
            receipts=[Q.validate_run(run) for run in Q.RUNS]
            result=Q.compare_pair(receipts)
            self.assertEqual(result['equal_outputs'],29)

    def test_actual_validator_missing_seal_rejects(self):
        with self.sealed_fixture():
            (Q.run_out('new01')/'SEAL.json').unlink()
            with self.assertRaises(FileNotFoundError):Q.validate_run('new01')

    def test_actual_validator_same_size_payload_corruption_rejects(self):
        with self.sealed_fixture():
            (Q.run_out('new01')/'n00.f32le').write_bytes(b'x'*16)
            with self.assertRaisesRegex(ValueError,'content identities'):Q.validate_run('new01')

    def test_actual_validator_source_and_loaded_platform_drift_rejects(self):
        with self.sealed_fixture() as (_,boundaries):
            boundaries['new01']['sources']={'drift':'different'}
            with self.assertRaisesRegex(ValueError,'source/raw/native/platform drift'):Q.validate_run('new01')
            boundaries['new02']['platform_files']['libpython']['inode']+=1
            with self.assertRaisesRegex(ValueError,'source/raw/native/platform drift'):Q.validate_run('new02')

    def test_actual_validator_original_guard_success_identity_rechecked(self):
        with self.sealed_fixture():
            answer=Q.read_json(Q.guard_log('new01'));answer['seal']['sha256']='f'*64
            Q.guard_log('new01').write_bytes(P.encoded(answer))
            with self.assertRaisesRegex(ValueError,'guard output identity'):Q.validate_run('new01')

    def test_cold_import_has_no_numerical_modules(self):
        result=subprocess.run([sys.executable,'-B','-c',
            'import sys; from candidates.qwen2_official_cpu_platform_reference import pair; '
            'assert not any(n in sys.modules for n in ("torch","numpy","transformers"))'],
            cwd=Q.HERE.parents[1],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()

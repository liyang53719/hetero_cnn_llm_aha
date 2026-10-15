"""Real metadata files and payload stat-only boundary with synthetic cold evidence."""
import copy
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from . import recipe as R
from candidates.qwen2_official_cpu_platform_reference import test_validator as validator_fixtures


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        original=R.ROOT
        self.pins=R.C.O.load_pins()
        # Tracked source geometry only. Sparse files below intentionally do not
        # claim payload hash validation; the function under test must not read them.
        self.outputs=R.parse((original/R.C.O.FROZEN_CONTRACT_FILE).read_bytes())['outputs']
        observed,_,_=validator_fixtures.ValidatorTests().fixture();self.platform=observed['platform_before']
        self.common=dict(source_manifest=dict(bytes=1,sha256='a'*64),platform_files={k:self.platform[k] for k in ('python','libpython')},
            native_files=self.pins['runtime_native_files'])
        self.context={'synthetic_context':'cold_only'}
        self.binding=dict(context=self.context,captures=[],reference_certificates={'new01':'b'*64,'new02':'c'*64},metadata_files={})
        for obj,key,value in ((R,'ROOT',self.root),(R.P,'ROOT',self.root)):
            p=patch.object(obj,key,value);p.start();self.addCleanup(p.stop)
        for run in R.P.RUNS:self.make_run(run)

    def write(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(value if type(value) is bytes else R.encoded(value))
        return R.identity(path)

    def resources(self):
        log=dict(total_bytes=0,sha256_all_observed_bytes=R.sha(b''),retained_bytes=0,truncated=False,retained_sha256=R.sha(b''))
        return dict(returncode=0,limit_reason=None,cleanup_pids=[],rss_is_os_hard_cap=False,
            rss_limit_bytes=1536*(1<<20),independent_watchdog_enabled=False,independent_watchdog_record=None,
            overall_wall_limit_seconds=120,external_watchdog_deadline_seconds=122,cleanup_grace_seconds=2,
            independent_overall_watchdog_enabled=True,overall_clock_started_at='run entry before source/go/input/runtime preflight',
            overall_elapsed_seconds=1.,wall_seconds=1.,wall_limit_seconds=120,peak_sampled_process_tree_rss_bytes=1,
            rss_poll_seconds=0.02,descendant_cleanup=dict(reaped_descendant_pids=[],remaining_descendants={},cleanup_wait_limit_seconds=2),
            logs=dict(stdout=copy.deepcopy(log),stderr=copy.deepcopy(log)))

    def make_run(self,run):
        out=R.P.run_out(run);out.mkdir(parents=True)
        inventory={}
        for name,spec in self.outputs.items():
            with (out/(name+'.f32le')).open('wb') as stream:stream.truncate(spec['bytes'])
            inventory[name+'.f32le']={k:spec[k] for k in ('bytes','sha256')}
        with (out/'mask.bf16le').open('wb') as stream:stream.truncate(32768)
        inventory['mask.bf16le']=dict(bytes=32768,sha256=self.pins['mask_contract']['native_sha256'])
        before=dict(self.common,external_certificate_sha256=self.binding['reference_certificates'][run])
        for name in R.BOUNDARIES:inventory[name]=self.write(out/name,before)
        runtime={**self.pins['runtime_requirements'],'native_files':self.pins['runtime_native_files'],'environment':self.pins['capture_environment']}
        obs=dict(status=R.P.STATUS,stage='bootstrap',contract_id=R.CONTRACT,numerical_acceptance_claimed=False,
            dut_executed=False,old_pass_inherited=False,full_29_node_acceptance=False,official_model_ast_nodes=38,
            official_activation_ast_nodes=14,official_ast_subset_executed=True,full_official_forward_executed=False,
            dynamic_cache_executed=False,transformers_imported=False,actual_or_typed_input_read=False,
            materialized_producer_payload_read=False,saved_reference_payload_read=False,legacy_frozen29_comparison_performed=False,
            source_manifest=self.common['source_manifest'],source_pins_sha256=R.PINS_SHA256,outputs=self.outputs,
            boundary=dict(unchanged=True,before_sha256=R.sha(R.encoded(before)),after_sha256=R.sha(R.encoded(before))),
            platform_before=self.platform,platform_after=self.platform,runtime=runtime,
            legacy_contract_diagnostic=dict(status='LEGACY_CONTRACT_DIFFERENT',compared_count=18,equal_count=0,
                records=[dict(node='NODE_%02d'%i,equal=False) for i in range(18)]))
        resources=self.resources()
        manifest={**obs,'resources':resources,'wrapper_boundary_unchanged':True,'go_identity':{}}
        for name,value in ((R.REFERENCE_MANIFEST,manifest),('OBSERVATIONS.json',obs),('GO.json',{}),
                           ('STAGES.jsonl',b''),('stdout.log',b''),('stderr.log',b'')):
            inventory[name]=self.write(out/name,value)
        seal=dict(schema=1,status=R.P.SEALED,mode='bootstrap',run_id=run,manifest=R.REFERENCE_MANIFEST,
            source_manifest=self.common['source_manifest'],numerical_acceptance_claimed=False,dut_executed=False,
            retries=0,files=copy.deepcopy(inventory),resources=resources)
        inventory['SEAL.json']=self.write(out/'SEAL.json',seal)
        guard=self.write(R.P.guard_log(run),{})
        self.binding['captures'].append(dict(run=run,reference_directory=str(out.relative_to(self.root)),
            outputs=self.outputs,common=self.common,inventory=inventory,guard=guard))

    def validate(self):
        with patch.object(R,'_common_metadata',return_value=self.common):
            return R._metadata_records(self.pins,self.binding,self.context)

    def test_full29_semantics_and_metadata_rechecked_without_payload_open(self):
        opens=[];original=io.open
        def guarded(path,*args,**kwargs):
            opens.append(str(path))
            if str(path).endswith(('.f32le','.bf16le','.bin')):raise AssertionError('preseal payload read')
            return original(path,*args,**kwargs)
        with patch('io.open',side_effect=guarded):result=self.validate()
        self.assertEqual(set(result['outputs']),R.NAMES)
        self.assertTrue(any('new02' in path and 'SEAL.json' in path for path in opens))

    def test_second_capture_metadata_drift_refused(self):
        path=R.P.run_out('new02')/'BOUNDARY_AFTER.json';path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(ValueError):self.validate()

    def test_missing_second_payload_stat_refused_without_read(self):
        (R.P.run_out('new02')/'y.f32le').unlink()
        with self.assertRaises(ValueError):self.validate()

    def test_platform_and_layout_drift_refused(self):
        self.binding['captures'][1]=copy.deepcopy(self.binding['captures'][1])
        self.binding['captures'][1]['common']['platform_files']['libpython']['sha256']='d'*64
        with self.assertRaises(ValueError):self.validate()

    def test_capture_identity_not_rebased_to_metadata(self):
        self.binding['captures'][1]=copy.deepcopy(self.binding['captures'][1])
        self.binding['captures'][1]['outputs']['y']['sha256']='d'*64
        with self.assertRaises(ValueError):self.validate()

    def test_new_native_context_cannot_replace_frozen_context(self):
        self.binding['context']={'different':'native'}
        with self.assertRaises(ValueError):self.validate()

if __name__=='__main__':unittest.main()

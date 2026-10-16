"""Portable cold regression tests; no numerical/native/runtime imports."""
from __future__ import annotations
import ast
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('cloud_failure_validator', HERE / 'validate_evidence.py')
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.directory = self.base / 'evidence'
        self.directory.mkdir()
        (self.directory / 'safe3').mkdir()
        for name in v.ROOT_FILES:
            shutil.copyfile(HERE / name, self.directory / name)
        for name in v.MEMBERS:
            shutil.copyfile(HERE / 'safe3' / name, self.directory / 'safe3' / name)

    def raw(self, name='summary.json'):
        return (self.directory / 'safe3' / name).read_bytes()

    def data(self, name='summary.json'):
        return json.loads(self.raw(name))

    def reject_summary(self, path, value):
        data = self.data()
        target = data
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value
        with self.assertRaises(v.EvidenceError):
            v.validate_schema('summary.json', data)

    def reject_checkpoint(self, path, value):
        data = copy.deepcopy(v.CHECKPOINT)
        target = data
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value
        (self.directory / 'checkpoint.json').write_bytes(v.encoded(data))
        with self.assertRaises(v.EvidenceError):
            v.validate_directory(self.directory)

    def test_exact_directory_preserves_failure(self):
        r = v.validate_directory(self.directory)
        self.assertEqual(r['status'], 'FAILED')
        self.assertEqual(r['phase'], 'numeric')
        self.assertEqual(r['process_exit_code'], 1)
        for key in ('numerical_acceptance', 'postflight_complete', 'full_29_node_acceptance',
                    'scala_executed', 'rtl_executed', 'numerical_execution_by_validator'):
            self.assertIs(r[key], False)

    def test_all_original_safe3_bytes(self):
        for name in v.MEMBERS:
            v.validate_member(name, self.raw(name))

    def test_no_pass_inheritance(self):
        for value in ('PASS', 'PASS_FRESH_RECIPE_PUBLIC_M128_OBSERVED_GATES', 'TIMEOUT', 'RUNNING'):
            self.reject_summary(['status'], value)
            self.reject_checkpoint(['recorded_facts', 'status'], value)

    def test_no_acceptance_flags(self):
        for key in ('numerical_acceptance', 'postflight_complete', 'full_29_node_acceptance',
                    'scala_executed', 'rtl_executed'):
            self.reject_summary([key], True)
            self.reject_checkpoint(['recorded_facts', key], True)

    def test_no_diagnostic_acceptance(self):
        for key in ('numerical_acceptance', 'postflight_complete'):
            self.reject_summary(['numeric_progress', key], True)
            self.reject_checkpoint(['last_valid_numeric_progress', key], True)

    def test_projection_no_acceptance(self):
        for key in ('numerical_acceptance', 'postflight_complete', 'full_29_node_acceptance', 'rtl_executed'):
            self.reject_checkpoint(['bounded_timing_projection', key], True)

    def test_no_historical_proof_extension(self):
        for name in ('native_pass', 'historical_pass', 'full_block_pass', 'ci_pass', 'postflight_receipt'):
            data = self.data()
            data[name] = True
            with self.assertRaises(v.EvidenceError):
                v.validate_schema('summary.json', data)

    def test_no_cpu_qualification_inheritance(self):
        self.reject_summary(['cpu_eligibility', 'backend_qualified'], True)
        self.reject_summary(['cpu_eligibility', 'eligibility_only'], False)
        self.reject_summary(['cpu_eligibility', 'status'], 'PASS')

    def test_bool_is_not_number(self):
        for key in ('schema', 'rows', 'elapsed_seconds'):
            self.reject_summary([key], True)
        for key in ('schema', 'sequence', 'ordinal', 'elapsed_seconds', 'phase_elapsed_seconds'):
            self.reject_summary(['numeric_progress', key], True)
        self.reject_checkpoint(['session', 'session_id'], True)

    def test_number_is_not_bool(self):
        for key in ('numeric_started', 'numerical_acceptance', 'postflight_complete'):
            self.reject_summary([key], int(self.data()[key]))
        self.reject_summary(['numeric_progress', 'capped'], 0)

    def test_integer_is_not_float(self):
        self.reject_summary(['numeric_progress', 'sequence'], 61.0)
        self.reject_summary(['elapsed_seconds'], 2762)

    def test_launch_identity_fixed(self):
        for key,value in [('checkout_commit','0'*40),('launch_contract_sha256','0'*64),
                          ('profile','other'),('rows',16),('phase','complete')]:
            self.reject_summary([key],value)

    def test_context_source_writer_fixed(self):
        for key in ('context_sha256','source_manifest_sha256','writer_sha256'):
            self.reject_summary(['numeric_progress',key],'0'*64)
            self.reject_checkpoint(['last_valid_numeric_progress',key],'0'*64)

    def test_progress_enum_counter_bounds_and_snapshot(self):
        for key,value in [('sequence',62),('phase_state','RETURNED'),('event','COMPLETION'),
                          ('operator','Attention'),('ordinal',17),('stage','comparison'),
                          ('elapsed_seconds',3421.0),('phase_elapsed_seconds',-1.0),('capped',True)]:
            self.reject_summary(['numeric_progress',key],value)
        for key,value in [('host_model_ticks',19929718),('request_fire',16),('owner_result_fire',15),
                          ('completion_fire',17),('result_fire',1)]:
            self.reject_summary(['numeric_progress','counts',key],value)

    def test_distinct_final_and_snapshot_counters(self):
        cp = v.CHECKPOINT
        self.assertEqual(cp['last_valid_numeric_progress']['counts']['host_model_ticks'],18941741)
        self.assertEqual(cp['bounded_timing_projection']['final_host_counts']['host_model_ticks'],19929718)
        self.reject_checkpoint(['bounded_timing_projection','final_host_counts','host_model_ticks'],18941741)

    def test_projection_pc_metadata_fixed(self):
        for key,value in [('completed_pc_count',17),('completed_pc_last',16),
                          ('completed_pcs_contiguous',False),('hardware_cycles',19929718)]:
            self.reject_checkpoint(['bounded_timing_projection',key],value)

    def test_guard_classification_fixed(self):
        for key,value in [('outer_timeout_reported',True),('numerical_mismatch_reported',True),
                          ('numerical_comparison_completed',True),('inner_wall_budget_seconds',2430),
                          ('runtime_guard_line',103)]:
            self.reject_checkpoint(['diagnosis',key],value)

    def test_diagnostic_frame_fixed(self):
        self.reject_summary(['diagnostic','frames',0,'line'],428)
        self.reject_summary(['diagnostic','frames',1,'source'],'../../private.log')
        self.reject_summary(['diagnostic','exception'],'TimeoutError')

    def test_unknown_or_missing_summary_fields(self):
        for remove in (True,False):
            data=self.data()
            if remove:del data['phase']
            else:data['unknown']=False
            with self.assertRaises(v.EvidenceError):v.validate_schema('summary.json',data)

    def test_progress_correspondence(self):
        data=self.data('progress.json');data['elapsed_seconds']=0.0
        with self.assertRaises(v.EvidenceError):v.validate_schema('progress.json',data)

    def test_unknown_member(self):
        for name in ('../summary.json','context.json','private.log'):
            with self.assertRaises(v.EvidenceError):v.validate_member(name,b'{}')

    def test_duplicate_json_keys(self):
        with self.assertRaises(v.EvidenceError):v.strict_json(b'{"schema":1,"schema":1}',100)

    def test_nonfinite_numbers(self):
        for value in ('NaN','Infinity','-Infinity','1e9999'):
            with self.assertRaises(v.EvidenceError):v.strict_json(('{"x":'+value+'}').encode(),100)

    def test_json_encoding_top_level_size(self):
        for raw in (b'[]',b'null',b'\xff',b'{}'*100,b'','{}'):
            with self.assertRaises(v.EvidenceError):v.strict_json(raw,20)

    def test_deep_json(self):
        with self.assertRaises(v.EvidenceError):v.strict_json(b'{"x":'*20+b'1'+b'}'*20,1000)

    def test_formatted_original_bytes_rejected(self):
        for name in v.MEMBERS:
            with self.assertRaises(v.EvidenceError):
                v.validate_member(name,json.dumps(self.data(name),indent=1).encode())

    def test_source_path_aliases(self):
        for path in ('/absolute','../escape','a/../b','./file','a//b','a\\b','a\x00b','x'*257,'','.'):
            with self.assertRaises(v.EvidenceError):v.safe_relative(path)

    def test_source_count_keys_types(self):
        for mutation in ('count','key','schema','extra','digest','closure'):
            data=self.data('source_hashes.json');first=next(iter(data['source_sha256']))
            if mutation=='count':del data['source_sha256'][first]
            elif mutation=='key':data['source_sha256']['unknown.py']=data['source_sha256'].pop(first)
            elif mutation=='schema':data['schema']=True
            elif mutation=='extra':data['unknown']=False
            elif mutation=='digest':data['source_sha256'][first]=True
            else:data['source_sha256'][v.TARGET_PREFIX+'checkpoint.json']=data['source_sha256'].pop(first)
            with self.assertRaises(v.EvidenceError):v.validate_source_schema(data)

    def test_source_digest_shape_contract(self):
        for digest in ('G'*64,'0'*63,True,'0'*64):
            data=self.data('source_hashes.json');data['source_sha256'][v.CONTRACT_PATH]=digest
            with self.assertRaises(v.EvidenceError):v.validate_schema('source_hashes.json',data)

    def test_composed_map_binding(self):
        data=self.data('source_hashes.json')
        first=next(iter(data['generated_sha256']));data['generated_sha256'][first]='0'*64
        with self.assertRaises(v.EvidenceError):v.validate_schema('source_hashes.json',data)

    def test_original_map_binding(self):
        data=self.data('source_hashes.json')
        first=next(iter(data['source_sha256']));data['source_sha256'][first]='0'*64
        with self.assertRaises(v.EvidenceError):v.validate_schema('source_hashes.json',data)

    def test_source_runtime_roles_differ(self):
        data=self.data('source_hashes.json');original=data['source_sha256'];composed=dict(original)
        composed.update(data['generated_sha256'])
        self.assertNotEqual(original,composed)
        self.assertEqual(sum(original[p]!=composed[p] for p in original),12)
        self.assertEqual(v.sha256(v.encoded(composed)),v.SUMMARY['numeric_progress']['source_manifest_sha256'])

    def test_tree_map_reads_only_listed_paths(self):
        root=self.base/'source';root.mkdir();(root/'a').write_bytes(b'source');(root/'private.log').write_bytes(b'ignored')
        self.assertEqual(v.verify_tree_map(root,{'a':v.sha256(b'source')}),6)
        with self.assertRaises(v.EvidenceError):v.verify_tree_map(root,{'a':v.sha256(b'changed')})

    def test_tree_limits(self):
        root=self.base/'source';root.mkdir();(root/'a').write_bytes(b'123456')
        entries={'a':v.sha256(b'123456')}
        with mock.patch.object(v,'SOURCE_LIMIT',5),self.assertRaises(v.EvidenceError):v.verify_tree_map(root,entries)
        with mock.patch.object(v,'SOURCE_TOTAL_LIMIT',5),self.assertRaises(v.EvidenceError):v.verify_tree_map(root,entries)

    def test_extra_missing_files(self):
        for target in (self.directory/'private.log',self.directory/'safe3/private.log'):
            target.write_text('no')
            with self.assertRaises(v.EvidenceError):v.validate_directory(self.directory)
            target.unlink()
        (self.directory/'safe3/progress.json').unlink()
        with self.assertRaises(v.EvidenceError):v.validate_directory(self.directory)

    def test_cache_rejected(self):
        (self.directory/'__pycache__').mkdir()
        with self.assertRaises(v.EvidenceError):v.validate_directory(self.directory)

    def test_file_symlink_rejected(self):
        target=self.directory/'safe3/progress.json';target.unlink();target.symlink_to(HERE/'safe3/progress.json')
        with self.assertRaises(v.EvidenceError):v.validate_directory(self.directory)

    def test_directory_symlink_rejected(self):
        link=self.base/'link';link.symlink_to(self.directory,target_is_directory=True)
        with self.assertRaises(v.EvidenceError):v.validate_directory(link)

    def test_ancestor_symlink_rejected(self):
        link=self.base/'link';link.symlink_to(self.base,target_is_directory=True)
        with self.assertRaises(v.EvidenceError):v.validate_directory(link/'evidence')

    def test_fifo_rejected_without_blocking(self):
        target=self.directory/'safe3/progress.json';target.unlink();os.mkfifo(target)
        with self.assertRaises(v.EvidenceError):v.validate_directory(self.directory)

    def test_empty_and_oversized_regular_file(self):
        target=self.base/'bad';target.write_bytes(b'')
        with self.assertRaises(v.EvidenceError):v.read_bounded(target,10)
        target.write_bytes(b'01234567890')
        with self.assertRaises(v.EvidenceError):v.read_bounded(target,10)

    def test_checkpoint_identity_mutation(self):
        for path in (['checkout_commit'],['source_binding','context_sha256'],
                     ['source_binding','runtime_source_manifest_sha256'],['timing_projection_identity','sha256']):
            self.reject_checkpoint(path,'0'*64)

    def test_checkpoint_duplicate_keys(self):
        (self.directory/'checkpoint.json').write_bytes(b'{"schema":1,"schema":1}')
        with self.assertRaises(v.EvidenceError):v.validate_directory(self.directory)

    def test_missing_control_rejected(self):
        with self.assertRaises(v.EvidenceError):v.validate_control_records(self.base,self.directory)

    def test_control_identity_rejected(self):
        control=self.base/'control';control.mkdir()
        for name in v.CHECKPOINT['control_record_identities']:(control/name).write_bytes(b'{}')
        with self.assertRaises(v.EvidenceError):v.validate_control_records(control,self.directory)

    def test_no_runtime_import_or_process_network_calls(self):
        tree=ast.parse((HERE/'validate_evidence.py').read_text())
        imports=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):imports.extend(a.name for a in node.names)
            elif isinstance(node,ast.ImportFrom):imports.append(node.module)
            elif isinstance(node,ast.Assert):self.fail('validation must survive -O')
        self.assertEqual(set(imports),{'__future__','argparse','hashlib','json','math','os','pathlib','re','stat'})
        for forbidden in ('exec','eval','compile','__import__'):
            self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id==forbidden for n in ast.walk(tree)))

    def test_cli_result_is_failed(self):
        with mock.patch('sys.argv',['validate_evidence.py','--directory',str(self.directory)]),mock.patch('sys.stdout',new_callable=io.StringIO) as out:
            v.main()
        value=json.loads(out.getvalue())
        self.assertEqual(value['status'],'FAILED')
        self.assertIs(value['numerical_acceptance'],False)


if __name__ == '__main__':
    unittest.main()

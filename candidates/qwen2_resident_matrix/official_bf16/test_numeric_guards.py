"""Small fail-closed replay/prerequisite checks; no payload or long execution."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from . import check_numeric as n
from . import recompare_m16 as post


class NumericPrerequisiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "m16.json"
        self.snapshot = dict(source_sha256={"arithmetic.py": "f"*64},
            binaries={"library_sha256": "e"*64}, input_spec={"raw_x": "d"*64})
        self.record = dict(status="PASS_BF16_DATAFLOW_NATIVE_GATE_REPORTED", rows=16,
            source_sha256=self.snapshot["source_sha256"],
            source_sha256_after=self.snapshot["source_sha256"],
            binaries=self.snapshot["binaries"], input_spec=self.snapshot["input_spec"],
            policy=n.policy.POLICY, comparison={"fixed_arithmetic_pass": True},
            native_acceptance="FAIL_OR_INCOMPLETE_OBSERVED_NODE_GATE",
            execution={"host": {"launch_result": {"status": None, "completed": 21, "jobs":17},
                "accepted": {"owner_result_fire":17, "result_fire":1}, "reset_required":False}})

    def tearDown(self):
        self.temp.cleanup()

    def call(self, record=None, digest=None):
        self.path.write_text(json.dumps(self.record if record is None else record))
        return n.prerequisite(self.path, digest or n.file_sha(self.path), self.snapshot)

    def test_exact_fixed_arithmetic_success_does_not_inherit_native_acceptance(self):
        self.assertFalse(self.call()["native_acceptance_inherited"])

    def test_any_failed_incomplete_or_wrong_workload_receipt_is_rejected(self):
        for key,value in (("status","FAILED"),("rows",128),("policy",{}),
                          ("comparison",{"fixed_arithmetic_pass":False})):
            r=copy.deepcopy(self.record);r[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.call(r)

    def test_source_post_source_library_and_input_must_all_match(self):
        for key in ("source_sha256","source_sha256_after","binaries","input_spec"):
            r=copy.deepcopy(self.record);r[key]={"changed":True}
            with self.subTest(key=key),self.assertRaises(ValueError):self.call(r)

    def test_completion_and_single_accepted_terminal_are_mandatory(self):
        for path,value in ((("launch_result","status"),"fault"),(("launch_result","completed"),20),
                (("launch_result","jobs"),16),(("accepted","owner_result_fire"),16),
                (("accepted","result_fire"),0),(("accepted","result_fire"),2)):
            r=copy.deepcopy(self.record);r["execution"]["host"][path[0]][path[1]]=value
            with self.subTest(path=path,value=value),self.assertRaises(ValueError):self.call(r)
        r=copy.deepcopy(self.record);r["execution"]["host"]["reset_required"]=True
        with self.assertRaises(ValueError):self.call(r)

    def test_modified_receipt_is_rejected_before_its_claims(self):
        with self.assertRaisesRegex(ValueError,"exact new M16"):
            self.call(digest="0"*64)

    def test_postprocessing_receipt_requires_exact_original_and_current_source(self):
        r=copy.deepcopy(self.record)
        r.update(status='PASS_RECOMPARISON_OF_SEALED_M16',
            postprocessor_sha256=n.file_sha(Path(post.__file__)),
            original_result_sha256=post.ORIGINAL_RESULT_SHA,
            original_snapshot_sha256=post.ORIGINAL_SNAPSHOT_SHA,
            arithmetic_and_physical_driver_sources_unchanged=True,
            functional_run_ast_unchanged_except_readonly_transport=True,
            actual_execution_repeated=False,reference_forward_repeated=False)
        self.assertTrue(self.call(r)['readonly_instrumentation_revalidated'])
        for key,value in (('postprocessor_sha256','0'*64),('original_result_sha256','0'*64),
                          ('original_snapshot_sha256','0'*64),('actual_execution_repeated',True),
                          ('arithmetic_and_physical_driver_sources_unchanged',False),
                          ('functional_run_ast_unchanged_except_readonly_transport',False)):
            bad=copy.deepcopy(r);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.call(bad)

    def test_run_ast_allows_only_monitor_class_selection(self):
        old='def run(x):\n    y = observation.OfficialAttentionObservation(x)\n    return execute(x, 17)\n'
        new=old.replace('OfficialAttentionObservation','OfficialAttentionMonitoringObservation')
        self.assertEqual(post.functional_run_ast(old),post.functional_run_ast(new))
        self.assertNotEqual(post.functional_run_ast(old),post.functional_run_ast(new.replace('17','16')))

    def test_default_twelve_hundred_explicit_eighteen_hundred_bound_and_fresh_output(self):
        for budget in (0,-1,1801):
            with self.subTest(budget=budget),self.assertRaisesRegex(ValueError,"fresh bounded"):
                n.run(Path(self.temp.name)/"never-created", self.path,"0"*64,wall_budget=budget)
        with self.assertRaisesRegex(ValueError,"fresh bounded"):
            n.run(Path(self.temp.name),self.path,"0"*64,wall_budget=1200)

    def test_only_exact_host_diagnostics_normalize_against_actual_m16(self):
        before = """def run(out, wall_budget=1200):
    out = Path(out)
    require(not out.exists() and 0 < wall_budget <= 1200, 'fresh bounded official model run required')
    try:
        with base.frozen_exec():
            report['status'] = 'ACTUAL_PREFIX_COMPLETE'; save()
            with capture:
                actual = execute(17)
            require(completed == 21, 'whole public terminal missing')
    except Exception as error:
        if 'physical' in locals(): report['failed_memory'] = physical.report()
        save(); raise
"""
        after=before.replace('<= 1200','<= 1800')
        after=after.replace("report['status'] = 'ACTUAL_PREFIX_COMPLETE'; save()", "report['status'] = 'ACTUAL_PREFIX_COMPLETE'; save()\n            report['prefix_host_wall_seconds'] = time.monotonic() - started")
        after=after.replace("            require(completed", "            report['whole_terminal_host_wall_seconds'] = time.monotonic() - started\n            require(completed")
        failure="        try:\n            report['failure_capture'] = retain_failed_run(out, locals().get('physical'), locals().get('capture'))\n        except Exception as preservation_error:\n            report['failure_capture_error'] = str(preservation_error)\n"
        after=after.replace('        save(); raise',failure+'        save(); raise')
        self.assertEqual(post.functional_run_ast(before),post.functional_run_ast(after))
        relocated=after.replace(failure,'').replace('    try:\n        with base.frozen_exec',
            '    try:\n'+failure+'        with base.frozen_exec',1)
        for bad in (after.replace('completed == 21','completed == 20'),
                    after.replace('<= 1800','<= 1801'),relocated,
                    after.replace("report['failure_capture_error'] = str(preservation_error)", 'pass'),
                    after.replace("locals().get('capture')",'reference_tensor')):
            with self.subTest(bad=bad):
                self.assertNotEqual(post.functional_run_ast(before),post.functional_run_ast(bad))

    def physical(self, *, corrupt=False, partial=False):
        raw=b'actual output bytes'.ljust(64,b'!')
        record=dict(bytes=64,written_bytes=64,ack_bytes=32 if partial else 64,
                    terminal=True,published=True,sha256=n.sha(raw))
        regions={'published':dict(readonly=False,published=True,virtual=False,terminal=True,
                                 extent=64,base=0x1000,dtype=1),
                 'unpublished':dict(readonly=False,published=False,virtual=False),
                 'virtual':dict(readonly=False,published=False,virtual=True),
                 'workspace':dict(readonly=False,published=True,virtual=False,workspace_transport=object()),
                 'weight':dict(readonly=True)}
        reads=[]
        def read(address,extent):
            self.assertEqual((address,extent),(0x1000,64))
            reads.append((address,extent))
            return raw[:-1]+b'?' if corrupt else raw
        memory=SimpleNamespace(regions=regions,report=lambda:dict(outputs={'published':record}),raw=read)
        return memory,raw,reads

    def test_failure_preserves_published_bytes_without_reading_weights_or_partial_state(self):
        memory,raw,reads=self.physical()
        before=copy.deepcopy(memory.report())
        observed=dict(status='INCOMPLETE',observer_error='driver exited with an exception',
                      terminal={'status':None,'tag':12},whole_block_terminal_observed=False)
        def save(path):
            path.mkdir();(path/'raw.u32le').write_bytes(b'actual capture')
            return observed
        capture=SimpleNamespace(closed=True,active=False,save=save)
        result=n.retain_failed_run(Path(self.temp.name),memory,capture)
        self.assertEqual((Path(result['path'])/'published.f32le').read_bytes(),raw)
        self.assertEqual(reads,[(0x1000,64)])
        self.assertEqual(memory.report(),before)
        self.assertEqual(result['attention'],observed)
        self.assertEqual(set(result['omitted']),{'unpublished','virtual','workspace'})
        for field in ('whole_block_pass','native_acceptance','resumable_checkpoint'):
            self.assertFalse(result[field])
        self.assertEqual(result['errors'],[])
        with self.assertRaisesRegex(ValueError,'fresh failure'):
            n.retain_failed_run(Path(self.temp.name),memory,capture)

    def test_invalid_published_hash_or_incomplete_ack_does_not_gain_saved_output(self):
        for index,kwargs in enumerate((dict(corrupt=True),dict(partial=True))):
            memory,_,_=self.physical(**kwargs)
            output=Path(self.temp.name)/str(index);output.mkdir()
            result=n.retain_failed_run(output,memory,None)
            self.assertFalse(result['outputs'])
            self.assertEqual(len(result['errors']),1)
            self.assertFalse((Path(result['path'])/'published.f32le').exists())

    def test_capture_save_failure_or_active_capture_does_not_claim_success(self):
        def failed(path):raise OSError('diagnostic disk failure')
        active=SimpleNamespace(closed=False,active=True,save=failed)
        (Path(self.temp.name)/'active').mkdir()
        (Path(self.temp.name)/'closed').mkdir()
        result=n.retain_failed_run(Path(self.temp.name)/'active',None,active)
        self.assertNotIn('attention',result)
        result=n.retain_failed_run(Path(self.temp.name)/'closed',None,
            SimpleNamespace(closed=True,active=False,save=failed))
        self.assertEqual(result['errors'],['attention: diagnostic disk failure'])
        self.assertFalse(result['whole_block_pass'])


if __name__ == "__main__":unittest.main()

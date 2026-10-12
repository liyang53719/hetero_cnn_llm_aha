"""Small fail-closed replay/prerequisite checks; no payload or long execution."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
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

    def test_original_twelve_hundred_second_bound_and_fresh_output_are_enforced(self):
        for budget in (0,-1,1201):
            with self.subTest(budget=budget),self.assertRaisesRegex(ValueError,"fresh bounded"):
                n.run(Path(self.temp.name)/"never-created", self.path,"0"*64,wall_budget=budget)
        with self.assertRaisesRegex(ValueError,"fresh bounded"):
            n.run(Path(self.temp.name),self.path,"0"*64,wall_budget=1200)


if __name__ == "__main__":unittest.main()

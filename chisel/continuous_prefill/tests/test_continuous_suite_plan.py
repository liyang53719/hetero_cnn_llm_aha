#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/plan_continuous_suites.py"
spec = importlib.util.spec_from_file_location("suite_plan", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class SuitePlanTest(unittest.TestCase):
    def make(self, root, names):
        directory = root / "src/test/scala/heteronpu/continuous"
        directory.mkdir(parents=True)
        for name in names:
            (directory / (name + ".scala")).write_text("// fixture identity test\n")
    def test_native_cannot_enter_general(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            names=[n.split(".")[-1] for n in module.FIXTURE_SUITES.values()]
            self.make(root,names+["DenseReadPlannerSpec","VectorSiluSpec","SiluScheduleProbe"])
            plan=module.plan(root)
            self.assertEqual(plan["native"],[module.FIXTURE_SUITES["native"]])
            self.assertEqual(set(plan["general"]),{"heteronpu.continuous.DenseReadPlannerSpec","heteronpu.continuous.VectorSiluSpec"})
            self.assertEqual(sum(map(len,plan.values())),5)
    def test_missing_fixture_suite_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.make(root,["HostBlockCommandsSpec","HostBlockCommandsRealLayersSpec"])
            with self.assertRaisesRegex(ValueError,"MISSING_FIXTURE_SUITE"):
                module.plan(root)
    def test_real_repository_partition_complete(self):
        project=SOURCE.parents[1];plan=module.plan(project)
        flat=[n for names in plan.values() for n in names]
        expected=list((project/"src/test/scala/heteronpu/continuous").glob("*Spec.scala"))
        self.assertEqual(len(flat),len(expected))
        self.assertEqual(len(flat),len(set(flat)))

if __name__ == "__main__": unittest.main(verbosity=2)

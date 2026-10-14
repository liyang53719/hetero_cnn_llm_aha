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
    def fixture_names(self):
        return [name.split(".")[-1] for name in
                (*module.FIXTURE_SUITES.values(), *module.EXTERNAL_FIXTURE_SUITES.values())]
    def assert_external_unique(self, plan):
        flat=[name for names in plan.values() for name in names]
        self.assertEqual(len(flat),len(set(flat)))
        self.assertEqual(set(plan),{"general",*module.FIXTURE_SUITES,*module.EXTERNAL_FIXTURE_SUITES})
        for group,name in module.EXTERNAL_FIXTURE_SUITES.items():
            self.assertEqual(plan[group],[name])
            self.assertEqual(flat.count(name),1)
            self.assertFalse(any(name in plan[run_group] for run_group in module.RUN_GROUPS))
    def test_native_cannot_enter_general(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            names=self.fixture_names()
            self.make(root,names+["DenseReadPlannerSpec","VectorSiluSpec","SiluScheduleProbe"])
            plan=module.plan(root)
            self.assertEqual(plan["native"],[module.FIXTURE_SUITES["native"]])
            self.assertEqual(set(plan["general"]),{"heteronpu.continuous.DenseReadPlannerSpec","heteronpu.continuous.VectorSiluSpec"})
            self.assertEqual(sum(map(len,plan.values())),len(names)+2)
            self.assert_external_unique(plan)
    def test_external_suites_keep_unique_dedicated_groups(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.make(root,self.fixture_names()+["OrdinarySpec"])
            plan=module.plan(root)
            self.assert_external_unique(plan)
            self.assertEqual(plan["general"],["heteronpu.continuous.OrdinarySpec"])
    def test_each_missing_external_suite_is_an_error(self):
        for name in module.EXTERNAL_FIXTURE_SUITES.values():
            with self.subTest(suite=name),tempfile.TemporaryDirectory() as d:
                root=Path(d);self.make(root,[n for n in self.fixture_names() if n!=name.split(".")[-1]])
                with self.assertRaises(ValueError) as error:module.plan(root)
                self.assertIn("MISSING_FIXTURE_SUITE:",str(error.exception))
                self.assertIn(name,str(error.exception))
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
        self.assert_external_unique(plan)

if __name__ == "__main__": unittest.main(verbosity=2)

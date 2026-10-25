"""Small synthetic evidence controls only. No JVM, DUT import, or real stream."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('checker',HERE/'check_behavior.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
E=json.loads((HERE/'BEHAVIOR_EXPECTATION.json').read_text())

def fixture(root):
    lines=['CORE_CLASS_ORIGIN '+n+' file:'+p.replace('${NEW_RUN_ROOT}',str(root))
           for n,p in E['class_origins'].items()]
    lines+=['CORE_SIM_READY case=normal_m1 m=1 backend=treadle2 scripted_matrix=true']
    cycle=100
    for head in range(12):
        for offset in range(34):
            phase=1 if offset<16 else 2 if offset<32 else 3 if offset==32 else 4
            lane=offset if offset<16 else offset-16 if offset<32 else 15
            lines.append(f'OBS cycle={cycle} token=0 head={head} phase={phase} lane={lane} selected=0 faults=0 scoreWrite={str(phase==4).lower()} scoreIndex=0 scoreData=0 max=4286578688 resultReady=false')
            cycle+=1
        cycle+=100
    lines+=['CORE_CASE_PASS case=normal_m1 m=1 cycles=2000 groups=12 qkAcceptedSteps=96 accounting512Steps=864 results=12 dones=12 scoreWrites=12 targetPrefix= ownerAccepts=1 pvRequests=96 pvReturns=96 requestHoldChecks=10 holdChecksByPort=(group,1),(memory,2),(pv,3),(step,4) memoryAccepted=384 memoryReturned=384 outputBytes=6144 numerical_matrix_verified=false',
            'Total number of tests run: 1','Suites: completed 1, aborted 0',
            'Tests: succeeded 1, failed 0, canceled 0, ignored 0, pending 0','All tests passed.']
    return ('\n'.join(lines)+'\n').encode()

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='synthetic_m1_');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.raw=fixture(self.root)
    def good(self,raw=None):return c.check_log(self.raw if raw is None else raw,E,self.root)
    def bad(self,a,b):
        if a not in self.raw:raise RuntimeError('control mutation missing')
        with self.assertRaises(ValueError):self.good(self.raw.replace(a,b,1))
    def materialize(self):
        (self.root/'worker.log').write_bytes(self.raw)
        p=self.root/E['required_low_ir'];p.parent.mkdir(parents=True)
        p.write_text('FIRRTL version 1.2.0\ncircuit OrderedQkBehaviorCore :\n  module OrderedQkBehaviorCore :\n    input clock : Clock\n    input reset : UInt<1>\n')
        return p
    def test_good_counts(self):
        r=self.good();self.assertEqual(r['interpreted_clock_steps_including_resets'],2003)
        self.assertEqual(r['vector_phase_clock_counts'],{'1':192,'2':192,'3':12,'4':12})
    def test_full_small_artifact(self):
        self.materialize();r=c.check(self.root,E)
        self.assertEqual(r['status'],c.STATUS);self.assertFalse(r['scope']['full_matrix_numerical_pass'])
        self.assertIsNone(r['scope']['matrix_mac_utilization'])
    def test_optional_annotation_bookkeeping(self):
        self.materialize();(self.root/E['allowed_backend_files'][1]).write_text('[{"class":"firrtl2.transforms.BlackBoxTargetDirAnno"}]')
        self.assertEqual(c.check(self.root,E)['status'],c.STATUS)
    def test_case(self):self.bad(b'case=normal_m1 m=1 cycles',b'case=normal_m2 m=2 cycles')
    def test_no_pass(self):self.bad(b'CORE_CASE_PASS',b'MISSING_CASE_PASS')
    def test_duplicate_pass(self):
        line=next(x for x in self.raw.splitlines() if x.startswith(b'CORE_CASE_PASS'))
        with self.assertRaises(ValueError):self.good(self.raw+line+b'\n')
    def test_no_ready(self):self.bad(b'CORE_SIM_READY',b'MISSING_SIM_READY')
    def test_backend(self):self.bad(b'backend=treadle2',b'backend=verilator')
    def test_pv_zero(self):self.bad(b'pvRequests=96',b'pvRequests=0')
    def test_memory_count(self):self.bad(b'memoryReturned=384',b'memoryReturned=383')
    def test_clock_cap(self):self.bad(b'cycles=2000 groups',b'cycles=99998 groups')
    def test_hold_missing(self):self.bad(b'(pv,3)',b'(pv,0)')
    def test_zero_port_is_uncovered_not_fabricated(self):
        r=self.good(self.raw.replace(b'(pv,3)',b'(pv,0)').replace(b'requestHoldChecks=10',b'requestHoldChecks=7'))
        self.assertEqual(r['stalled_request_hold_uncovered_ports'],['pv'])
    def test_zero_total_hold(self):
        raw=self.raw.replace(b'requestHoldChecks=10',b'requestHoldChecks=0')
        for p,n in [('group',1),('memory',2),('pv',3),('step',4)]:raw=raw.replace(f'({p},{n})'.encode(),f'({p},0)'.encode())
        with self.assertRaises(ValueError):self.good(raw)
    def test_hold_sum(self):self.bad(b'requestHoldChecks=10',b'requestHoldChecks=11')
    def test_one_hold_over_cycles(self):
        raw=self.raw.replace(b'(group,1)',b'(group,2001)').replace(b'requestHoldChecks=10',b'requestHoldChecks=2010')
        with self.assertRaises(ValueError):self.good(raw)
    def test_origin(self):self.bad(b'CORE_CLASS_ORIGIN scala.Predef$ file:',b'CORE_CLASS_ORIGIN scala.Predef$ http:')
    def test_missing_origin(self):self.bad(b'CORE_CLASS_ORIGIN scala.Predef$',b'MISSING_ORIGIN scala.Predef$')
    def test_fail_summary(self):self.bad(b'failed 0',b'failed 1')
    def test_two_tests(self):self.bad(b'Total number of tests run: 1',b'Total number of tests run: 2')
    def test_lane(self):self.bad(b'phase=1 lane=0',b'phase=1 lane=1')
    def test_fault(self):self.bad(b'faults=0',b'faults=2')
    def test_early_ready(self):self.bad(b'resultReady=false',b'resultReady=true')
    def test_wrong_score(self):self.bad(b'scoreWrite=true scoreIndex=0 scoreData=0',b'scoreWrite=true scoreIndex=0 scoreData=1')
    def test_extra_obs(self):
        line=next(x for x in self.raw.splitlines() if x.startswith(b'OBS '))
        with self.assertRaises(ValueError):self.good(self.raw+line+b'\n')
    def test_injection(self):
        with self.assertRaises(ValueError):self.good(self.raw+b'INJECT test\n')
    def test_unknown_obs_prefix(self):
        for extra in [b'OBS\tbogus\n',b'OBS_BAD bogus\n']:
            with self.assertRaises(ValueError):self.good(self.raw+extra)
    def test_no_ir(self):
        self.materialize().unlink()
        with self.assertRaises(ValueError):c.check(self.root,E)
    def test_extmodule(self):
        p=self.materialize();p.write_text(p.read_text()+'  extmodule External :\n')
        with self.assertRaises(ValueError):c.check(self.root,E)
    def test_bad_module(self):
        p=self.materialize();p.write_text(p.read_text()+'   module Missing? :\n')
        with self.assertRaises(ValueError):c.check(self.root,E)
    def test_duplicate_module(self):
        p=self.materialize();p.write_text(p.read_text()+'  module OrderedQkBehaviorCore :\n')
        with self.assertRaises(ValueError):c.check(self.root,E)
    def test_unsupported_artifact(self):
        p=self.materialize();(p.parent/'bad.sv').write_text('module bad; endmodule')
        with self.assertRaises(ValueError):c.check(self.root,E)
    def test_symlink(self):
        p=self.materialize();(p.parent/'linked').symlink_to(p)
        with self.assertRaises(ValueError):c.check(self.root,E)
    def test_blackbox_annotation(self):
        self.materialize();(self.root/E['allowed_backend_files'][1]).write_text('[{"class":"firrtl2.transforms.BlackBoxInlineAnno"}]')
        with self.assertRaises(ValueError):c.check(self.root,E)
    def test_small_ir_line_bound(self):
        p=self.materialize();small=dict(E,max_ir_line_bytes=8)
        with self.assertRaises(ValueError):c.low_ir(p,small)

if __name__=='__main__':unittest.main(verbosity=2)

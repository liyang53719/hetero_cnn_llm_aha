"""Real selected generator, original M1/M2 exact FMA harness; no native imports."""
import argparse
import ast
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve(strict=True).parent
sys.path.insert(0,str(HERE))
import ordered_work as w
if Path(w.__file__).resolve(strict=True)!=HERE/'ordered_work.py':raise ImportError('work origin')
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--source-root',required=True,type=Path)
parser.add_argument('--selected-root',type=Path)
args,rest=parser.parse_known_args()
pins=json.loads((HERE/'SOURCE_PINS.json').read_text())
selected=args.selected_root or args.source_root/'candidates/qwen2_selected_scala_model'
oldpath=selected/'test_schedule_numeric.py'
if hashlib.sha256(oldpath.read_bytes()).hexdigest()!=pins['numeric_harness_sha256']:
    raise ValueError('original numeric harness drift')
if hashlib.sha256((selected/'schedule.py').read_bytes()).hexdigest()!=pins['selected_schedule_before_sha256']:
    raise ValueError('original selected schedule drift')
if hashlib.sha256((HERE/'schedule.py').read_bytes()).hexdigest()!=pins['selected_schedule_after_sha256']:
    raise ValueError('candidate schedule drift')
sys.argv[:]=[sys.argv[0],'--source-root',str(args.source_root),*rest]
spec=importlib.util.spec_from_file_location('_pinned_selected_numeric',oldpath)
old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)
ns=dict(old.NS,OrderedFoldWork=w.OrderedFoldWork,OrderedRetired=w.OrderedRetired)
old.definitions(HERE/'schedule.py',('ProductionQk16Schedule',),ns)
Schedule=ns['ProductionQk16Schedule']
OriginalNumericRegression=old.ProductionQk16NumericTests
OriginalFaultRegression=old.ProductionQk16FaultOrderingTests
OriginalSourceRegression=old.ColdSourceIsolationTests


def strict_lanes():
    # Reuse the published exact RNE primitives, not ExactScalar/ScalarService.
    # Finite-domain flags derive from exact rational result and rounded word.
    def primitive(op,a,b):
        if not old.finite(a) or not old.finite(b):return w.LaneResult(0,0x10)
        exact=old.NS['exact']
        mathematical=exact(a)+exact(b) if op=='add' else exact(a)*exact(b)
        value=old.NS['ref_'+op](a,b)
        flags=0
        if not old.finite(value):flags=0x05
        elif exact(value)!=mathematical:
            flags=1
            if not value&0x7f800000:flags|=2
        return w.LaneResult(value,flags)
    return w.StrictLaneOps(add=lambda a,b:primitive('add',a,b),
                          mul=lambda a,b:primitive('mul',a,b),
                          bf=old.ref_bf,finite=old.finite)


class Driver(old.ProductionDriver):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.schedule=Schedule(ordered_fold=True);self.schedule.bind(self)
        self.lanes=strict_lanes()
        self.adapter=w.OrderedFoldAdapter(self.lanes)
        self.work_steps=0;self.work_replies=[];self.work_objects=[]
        self.with_stalls=True

    def _response(self,request):
        if type(request) is w.OrderedFoldWork:
            old.need(request.result.tag==self.held,'work not attached to held Matrix result')
            old.need(request.count==self.active_keys,'work tail differs from active QK')
            if not self.work_objects or self.work_objects[-1] is not request:self.work_objects.append(request)
            before=tuple(self.scalar.trace)
            for local_step in range(96):
                ready=not self.with_stalls or local_step%3==2
                response=self.adapter.tick(request,ready=ready)
                self.work_steps+=1
                old.need(tuple(self.scalar.trace)==before,'ordered work issued a Scalar request')
                old.need(self.held==request.result.tag,'work released Matrix result')
                if response is not None and ready:
                    self.work_replies.append(response)
                    return response
            raise AssertionError('bounded ordered work failed to reply')
        return super()._response(request)


def scores_at_ack(driver):
    return [(event[1],event[3]) for event in driver.events if event[0]=='ack']


def after_ack_scalars(driver):
    out={}
    for position,events in old.per_head_events(driver).items():
        ack=next(i for i,e in enumerate(events) if e[0]=='ack')
        out[position]=tuple(e[2] for e in events[ack+1:] if e[0]=='scalar')
    return out


class OrderedNumeric(unittest.TestCase):
    def test_m1_m2_full_attention_words_and_downstream_order(self):
        for m in (1,2):
            words=old.fixture(m,seed=271828)
            baseline=old.ProductionDriver(m,*words);expected=baseline.run()
            independent=old.ObservedOriginal(m,*words);self.assertEqual(expected,independent.run())
            actual=Driver(m,*words);self.assertEqual(actual.run(),expected)
            self.assertEqual(scores_at_ack(actual),scores_at_ack(baseline))
            self.assertEqual(after_ack_scalars(actual),after_ack_scalars(baseline))
            self.assertEqual(actual.reads,baseline.reads)
            self.assertEqual(actual.packed_requests,baseline.packed_requests)
            self.assertEqual(actual.acks,baseline.acks)
            count=12*m*(m+1)//2;groups=12*m
            self.assertEqual(actual.lanes.calls,dict(add=16*count,mul=count,bf=2*count))
            self.assertEqual(actual.adapter.events,dict(scan=16*groups,add_stripe=16*groups,scale=groups,retire=count))
            self.assertEqual(len(actual.scalar.trace),len(baseline.scalar.trace)-19*count)
            self.assertEqual(len(actual.output),m*1536)

    def test_default_off_is_exact_old_generator(self):
        words=old.fixture(1,seed=17)
        baseline=old.ProductionDriver(1,*words);expected=baseline.run()
        default=old.ProductionDriver(1,*words);default.schedule=Schedule();default.schedule.bind(default)
        self.assertFalse(default.schedule.ordered_fold)
        self.assertEqual(default.run(),expected)
        self.assertEqual(default.events,baseline.events)
        for bad in (1,None,'yes'):
            with self.assertRaises(ValueError):Schedule(ordered_fold=bad)

    def test_m2_later_scan_fault_preserves_prior_score_and_no_ack(self):
        words=old.fixture(2,seed=71)
        for key in (0,1):
            cells={(0,16*key):0x7fc00000}
            baseline=old.ProductionDriver(2,*words,injected_cells=cells)
            actual=Driver(2,*words,injected_cells=cells)
            for driver in (baseline,actual):
                with self.assertRaises(old.ArithmeticFault):driver.run()
            self.assertEqual(actual.fault_scores,baseline.fault_scores)
            self.assertEqual(len(actual.fault_scores),key)
            self.assertIsNotNone(actual.held);self.assertEqual(len(actual.acks),12)

    def test_m2_earlier_fold_or_scale_fault_beats_later_nan(self):
        words=old.fixture(2,seed=91)
        for first in ([0x7f7fffff]*16,[0x00010000]+[0]*15):
            cells={(r,r):first[r] for r in range(16)};cells[(0,16)]=0x7fc00000
            actual=Driver(2,*words,injected_cells=cells)
            with self.assertRaises(old.ArithmeticFault):actual.run()
            self.assertEqual(actual.fault_scores,())
            self.assertEqual(actual.work_replies[-1].key,0)
            self.assertTrue(actual.work_replies[-1].error)
            self.assertEqual(len(actual.acks),12)

    def test_m2_rounding_zero_subnormal_finite_overflow_boundaries(self):
        words=old.fixture(2,seed=9)
        values=([0x3f800000,0x33800000]+[0]*14,
                [0x3f800000,0xbf800000]+[0x80000000]*14,
                [0x80000000]*16,[1]+[0]*15,
                [0x7f7f0000,0x7a800000]+[0]*14)
        for key in values:
            cells={(r,r):v for r,v in enumerate(key)}
            baseline=old.ProductionDriver(2,*words,injected_cells=cells)
            actual=Driver(2,*words,injected_cells=cells)
            try:expected=baseline.run()
            except old.ArithmeticFault:
                with self.assertRaises(old.ArithmeticFault):actual.run()
                self.assertEqual(actual.fault_scores,baseline.fault_scores)
            else:
                self.assertEqual(actual.run(),expected)
                self.assertEqual(scores_at_ack(actual),scores_at_ack(baseline))

    def test_generator_rejects_forged_or_out_of_order_work_retirement(self):
        for change in ('foreign','skipped','score','early','pre_retire'):
            driver=Driver(1,*old.fixture(1,seed=27))
            driver.program=driver.schedule.run(driver,driver.job)
            response=None
            for _ in range(40):
                request=driver.program.send(response)
                if type(request) is w.OrderedFoldWork:break
                response=driver._response(request)
            self.assertIs(type(request),w.OrderedFoldWork)
            if change=='pre_retire':
                for _ in range(33):driver.adapter.tick(request)
                bad=w.OrderedRetired(request,0,request.acc[0],request.maximum,False)
            elif change=='early':
                bad=w.OrderedRetired(request,0,0,0xff800000,False)
            else:
                response=driver._response(request)
                if change=='foreign':bad=replace(response,work=object())
                elif change=='skipped':bad=replace(response,key=1)
                else:bad=replace(response,score=response.score^1)
            with self.assertRaises(old.PrefixFault):driver.program.send(bad)
            self.assertIsNotNone(driver.held);self.assertEqual(driver.acks,[])

    def test_work_reply_is_held_until_ready_and_no_ack_side_effect(self):
        class Tile:
            value=[[0x3f800000]*256 for _ in range(16)]
        result=Tile();work=w.OrderedFoldWork(result,1,0xff800000)
        adapter=w.OrderedFoldAdapter(strict_lanes())
        for _ in range(34):self.assertIsNone(adapter.tick(work))
        pending=work.pending;self.assertIsNotNone(pending)
        self.assertIsNone(adapter.tick(work,ready=True,result_valid=False))
        self.assertIs(work.pending,pending);self.assertIsNone(work.accepted)
        for _ in range(4):self.assertIs(adapter.tick(work),pending)
        self.assertEqual(work.state,'reply');self.assertIs(work.result,result)
        self.assertIs(adapter.tick(work,ready=True),pending)
        self.assertEqual(work.state,'complete');self.assertEqual(work.key,0)
        self.assertTrue(work.consume(pending,0));self.assertFalse(work.consume(pending,0))

    def test_next_work_waits_previous_owner_consumption(self):
        result=old.SimpleNamespace(value=[[0x3f800000]*256]*16)
        first=w.OrderedFoldWork(result,1,0xff800000)
        second=w.OrderedFoldWork(result,1,0xff800000)
        adapter=w.OrderedFoldAdapter(strict_lanes())
        for _ in range(40):
            response=adapter.tick(first,ready=True)
            if response is not None:break
        self.assertEqual(first.state,'complete')
        with self.assertRaises(ValueError):adapter.tick(second)
        self.assertTrue(first.consume(response,0))
        self.assertIsNone(adapter.tick(second));self.assertEqual(second.row,1)

    def test_all_tail_extents_no_inactive_reads(self):
        for count in range(1,17):
            class Live:
                def __getitem__(self,row):
                    class Row:
                        def __getitem__(self,col):
                            if col//16>=count or col%16!=row:raise AssertionError('tail read')
                            return 0x3f800000
                    return Row()
            result=old.SimpleNamespace(value=Live())
            work=w.OrderedFoldWork(result,count,0xff800000);adapter=w.OrderedFoldAdapter(strict_lanes())
            replies=[]
            for _ in range(100):
                if work.state=='complete':break
                response=adapter.tick(work,ready=True)
                if response is not None:
                    self.assertTrue(work.consume(response,len(replies)))
                    replies.append(response)
            self.assertEqual([r.key for r in replies],list(range(count)))
            self.assertTrue(all(not r.error for r in replies));self.assertEqual(work.key,count-1)
            self.assertEqual(adapter.lanes.calls['add'],16*count)

    def test_fatal_flags_mask_nx_allowed(self):
        for flags in (1,2,4,8,16):
            lanes=w.StrictLaneOps(add=lambda a,b:w.LaneResult(0x3f800000,flags),
                mul=lambda a,b:w.LaneResult(0x3f800000),bf=lambda a:a,finite=old.finite)
            result=old.SimpleNamespace(value=[[0x3f800000]*256]*16)
            work=w.OrderedFoldWork(result,1,0xff800000);adapter=w.OrderedFoldAdapter(lanes)
            for _ in range(40):
                r=adapter.tick(work,ready=True)
                if r is not None:break
            self.assertEqual(r.error,flags!=1)
        # Injected DZ verifies the mask only, not reachable finite Add/Mul DZ.

    def test_abort_never_returns_pending_score_or_releases_result(self):
        result=old.SimpleNamespace(value=[[0x3f800000]*256]*16)
        for steps in (0,15,16,31,32,33,34):
            work=w.OrderedFoldWork(result,1,0xff800000);adapter=w.OrderedFoldAdapter(strict_lanes())
            for _ in range(steps):adapter.tick(work)
            self.assertIsNone(adapter.tick(work,ready=True,abort=True))
            self.assertEqual(work.state,'cancelled');self.assertIs(work.result,result)
            self.assertIsNone(adapter.tick(work,ready=True))

if __name__=='__main__':unittest.main()

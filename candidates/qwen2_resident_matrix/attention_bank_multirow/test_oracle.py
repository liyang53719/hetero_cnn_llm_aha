import unittest
from .oracle import Oracle,Stream,ScalarTrace
from .profile import Controller
from ..attention_scheduled_numeric.controller import Timing,NumericalFault
from ..attention_matrix_batch.test_model import ExactScalar,ref_fma,exp_negative
from ..attention_matrix_batch.test_model import OriginalSchedule,fixture


class OracleTests(unittest.TestCase):
    def test_unchanged_actual_owner_arithmetic_and_full_trace(self):
        for m in (1,2):
            args=(m,*fixture(m))
            old=OriginalSchedule(*args);new=Oracle(*args)
            self.assertEqual(old.run(),new.run())
            self.assertEqual(old.scores(),new.scores())
            self.assertEqual(old.scalar.calls,new.scalar.calls)
            expected=ScalarTrace()
            for event in old.scalar.trace:expected.append(event)
            self.assertEqual((len(expected),expected.hexdigest()),(len(new.scalar.trace),new.scalar.trace.hexdigest()))
            self.assertEqual(len(new.scalar.trace.recent),2)
            for kind,records,found in (('request',old.requests,new.requests),('read',old.reads,new.reads),('write',old.writes,new.writes)):
                sink=Stream(kind)
                for record in records:sink.append(record)
                self.assertEqual((len(sink),sink.hexdigest()),(len(found),found.hexdigest()))
                self.assertEqual(set(vars(found)),{'kind','count','digest'})
            self.assertIs(new._attention.__func__,old._attention.__func__)
            self.assertIs(new._matrix_step.__func__,old._matrix_step.__func__)

    def test_packed_lane_observer_never_requires_sequential_score_adjacency(self):
        records=(('bf',0,0,0,'legacy_scalar'),('bf',0,0,0,'legacy_scalar'),
            ('mul',0,0x3db504f3,0,'legacy_scalar'),('mul',0,0x3db504f3,0,'legacy_scalar'),
            ('bf',0,0,0,'legacy_scalar'),('bf',0,0,0,'legacy_scalar'))
        strict=ScalarTrace()
        with self.assertRaises(ValueError):
            for event in records:strict.append(event)
        packed=ScalarTrace(capture_scores=False)
        for event in records:packed.append(event)
        self.assertEqual(len(packed),len(records))
        self.assertEqual((packed.dots,packed.scores),([],[]))
        self.assertEqual(len(packed.recent),2)

    def test_same_m4_fixture_old_fault_and_observer_transparency(self):
        data=fixture(4)
        def candidate(trace):
            scalar=ExactScalar(object());scalar.trace=trace
            return Controller(scalar,ref_fma,lambda a:exp_negative(scalar,scalar.client,a),
                timing=Timing(2,3,0,0),scratch_enabled=True)
        class OldObserver(ScalarTrace):
            failure=None
            def append(self,entry):
                try:return super().append(entry)
                except ValueError as exc:
                    self.failure=str(exc)
                    raise
        strict=OldObserver();bad=candidate(strict)
        with self.assertRaisesRegex(NumericalFault,'scalar failed'):bad.run(4,*data)
        self.assertEqual(strict.failure,'original QK boundary')
        self.assertTrue(bad.failed)
        self.assertTrue(bad.scratch.parent.raw.drained)
        self.assertFalse(bad.ordinary_owner_ready())
        packed_trace=ScalarTrace(capture_scores=False);observed=candidate(packed_trace)
        plain=candidate([])
        left,right=observed.run(4,*data),plain.run(4,*data)
        self.assertEqual(left,right)
        self.assertEqual(observed.observation_summary(),plain.observation_summary())
        original=Oracle(4,*data)
        self.assertEqual(left.output,original.run())
        self.assertEqual(left.scores,original.scores()[1])
        self.assertGreater(packed_trace.count,0)

    def test_trace_order_and_bad_score_boundary(self):
        a,b=ScalarTrace(),ScalarTrace()
        x=('add',0,0,0,'legacy_scalar');y=('mul',0,0,0,'legacy_scalar')
        for v in (x,y):a.append(v)
        for v in (y,x):b.append(v)
        self.assertNotEqual(a.hexdigest(),b.hexdigest())
        bad=ScalarTrace();bad.append(('mul',0,0x3db504f3,0,'legacy_scalar'))
        with self.assertRaises(ValueError):bad.append(('bf',0,0,0,'legacy_scalar'))

if __name__=='__main__':unittest.main()

"""Only short in-memory synthetic streams, no tool or real target reads."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('phase_observer', HERE/'phase_observer.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def line(file='V3Param.cpp', n=1534, body='param: '):
    return ('- ' + file + ':' + str(n) + ': ' + body + '\n').encode('ascii')


class Controls(unittest.TestCase):
    def test_empty(self):
        d=m.PhaseObserver().snapshot()
        self.assertEqual(d['last_received_phase'],m.INITIAL)
        self.assertEqual(d['log_sha256'],hashlib.sha256(b'').hexdigest())
        self.assertEqual(d['event_count'],0)
        self.assertEqual(d['stored_sample_count'],0)
        self.assertFalse(d['hardware_or_plan_acceptance'])
        self.assertFalse(d['observation_failed'])

    def test_known_functions(self):
        for (f,b),phase in m.FUNCTIONS.items():
            with self.subTest(phase=phase):
                p=m.PhaseObserver();p.feed(line(f.decode(),123,b.decode()),0)
                self.assertEqual(p.snapshot()['last_received_phase'],phase)
                self.assertEqual(p.snapshot()['events'][0]['source_line'],123)

    def test_partial_chunks_offsets_and_hash(self):
        p=m.PhaseObserver(); raw=b'noise\n'+line()+b'last'
        for i,b in enumerate(raw):p.feed(bytes([b]),i*.001)
        d=p.snapshot();self.assertEqual(d['log_bytes'],len(raw));self.assertEqual(d['log_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(d['events'][0]['byte_start'],6);self.assertEqual(d['events'][0]['byte_end_exclusive'],len(raw)-4)
        self.assertEqual(d['events'][0]['log_line'],2);self.assertEqual(d['trailing_unterminated_line_bytes'],4)

    def test_multiple_markers_same_chunk(self):
        p=m.PhaseObserver();p.feed(line('V3LinkDot.cpp',4353,'linkDotPrimary:')+line(),3)
        self.assertEqual([x['observed_elapsed']for x in p.snapshot()['events']],[3,3])

    def test_nonascii_unknown(self):
        p=m.PhaseObserver();p.feed(b'\xff\x00 not a marker\n',0)
        self.assertEqual(p.snapshot()['ordinary_lines'],1)
        self.assertEqual(p.snapshot()['last_received_phase'],m.INITIAL)

    def test_parseimp_not_authorized(self):
        p=m.PhaseObserver();p.feed(line('V3ParseImp.cpp',311,'parseFile: common'),0)
        self.assertEqual(p.snapshot()['last_received_phase'],m.INITIAL)
        self.assertEqual(p.snapshot()['ordinary_lines'],1)

    def test_known_file_othertext_counted(self):
        p=m.PhaseObserver();p.feed(line(body='not param: 0'),0)
        self.assertEqual(p.snapshot()['known_source_unrecognized_lines'],1)
        self.assertEqual(p.snapshot()['events'],[])

    def test_hierarchy_exact_messages(self):
        p=m.PhaseObserver();p.feed(line('V3HierBlock.cpp',366,"Add 'm_abc' with 0 parameters and 0 type parameters"),0)
        self.assertEqual(p.snapshot()['last_received_phase'],'hierarchy_block_add')
        p.feed(line('V3HierBlock.cpp',378,"Found usage relation 'top' uses 'm_abc'"),1)
        self.assertEqual(p.snapshot()['last_received_phase'],'hierarchy_usage_relation')

    def test_unrecognized_markers_do_not_reset_phase(self):
        p=m.PhaseObserver();p.feed(line(),0);p.feed(line('Wrong.cpp',1,'link:')+line('V3Param.cpp',1,'param: garbage'),1)
        self.assertEqual(p.snapshot()['last_received_phase'],'parameterization_entry')

    def test_impossible_source_line_not_marker(self):
        for n in (0,1000001):
            p=m.PhaseObserver();p.feed(line(n=n),0)
            self.assertEqual(p.snapshot()['events'],[])
            self.assertEqual(p.snapshot()['known_source_unrecognized_lines'],1)

    def test_crlf_not_marker(self):
        p=m.PhaseObserver();p.feed(line().replace(b'\n',b'\r\n'),0)
        self.assertEqual(p.snapshot()['events'],[])

    def test_no_unterminated_marker_promotion(self):
        p=m.PhaseObserver();p.feed(line()[:-1],0)
        self.assertEqual(p.snapshot()['events'],[])

    def test_marker_regression_reported_not_interpreted(self):
        p=m.PhaseObserver();p.feed(line(),0);p.feed(line('V3LinkCells.cpp',635,'link:'),1)
        d=p.snapshot();self.assertEqual(d['marker_order_regressions'],1)
        self.assertEqual(d['last_received_phase'],'module_cell_link_entry')

    def test_periodic_decimation_keeps_peaks_latest(self):
        p=m.PhaseObserver()
        for i in range(10000):p.sample(i*.00001,i,i*.00002,i*2)
        d=p.snapshot();self.assertEqual(d['sample_calls'],10000);self.assertEqual(len(d['samples']['rows']),1)
        self.assertEqual(d['all_sample_peaks']['rss_bytes'],9999);self.assertEqual(d['latest_sample'][1],9999)
        self.assertEqual(d['phase_labeled_peaks'][m.INITIAL]['sample_calls'],10000)

    def test_phase_change_forces_stored_sample(self):
        p=m.PhaseObserver();p.sample(0,1,0,0);p.feed(line(),.001);p.sample(.002,2,0,0)
        self.assertEqual(len(p.snapshot()['samples']['rows']),2)

    def test_cpu_may_decrease_without_losing_peak(self):
        p=m.PhaseObserver();p.sample(0,5,20,1);p.sample(.1,4,2,1)
        self.assertEqual(p.snapshot()['all_sample_peaks']['cpu_seconds'],20)

    def test_snapshot_cannot_mutate_internal_state(self):
        p=m.PhaseObserver();p.feed(line(),0);a=p.snapshot();a['events'][0]['phase']='fake'
        self.assertEqual(p.snapshot()['events'][0]['phase'],'parameterization_entry')

    def test_feed_clock_backwards_rejected(self):
        p=m.PhaseObserver();p.feed(b'',1)
        with self.assertRaises(ValueError):p.feed(b'',0)
        self.assertTrue(p.snapshot()['observation_failed'])

    def test_sample_clock_backwards_rejected(self):
        p=m.PhaseObserver();p.feed(b'',1)
        with self.assertRaises(ValueError):p.sample(0,0,0,0)

    def test_negative_and_nonfinite_numeric_rejected(self):
        for value in (-1,True,float('nan'),float('inf'),float('-inf'),10**400,'1'):
            with self.subTest(value=str(value)[:30]):
                p=m.PhaseObserver()
                with self.assertRaises(ValueError):p.sample(value,0,0,0)

    def test_invalid_counter_types_rejected(self):
        for value in (-1,True,1.2,1<<63,'1'):
            for index in (1,3):
                with self.subTest(value=value,index=index):
                    args=[0,0,0,0];args[index]=value;p=m.PhaseObserver()
                    with self.assertRaises(ValueError):p.sample(*args)

    def test_invalid_cpu_rejected(self):
        for value in (-1,True,float('nan'),float('inf'),'1'):
            p=m.PhaseObserver()
            with self.assertRaises(ValueError):p.sample(0,0,value,0)

    def test_nonbytes_feed_rejected(self):
        for value in ('abc',bytearray(b'a'),None):
            p=m.PhaseObserver()
            with self.assertRaises(ValueError):p.feed(value,0)

    def test_raw_byte_cap(self):
        p=m.PhaseObserver()
        with self.assertRaises(ValueError):p.feed(b'x'*(m.MAX_LOG_BYTES+1),0)

    def test_complete_line_cap(self):
        p=m.PhaseObserver()
        with self.assertRaises(ValueError):p.feed(b'x'*m.MAX_LINE_BYTES+b'\n',0)

    def test_pending_line_cap_across_chunks(self):
        p=m.PhaseObserver();p.feed(b'x'*m.MAX_LINE_BYTES,0)
        with self.assertRaises(ValueError):p.feed(b'y',1)

    def test_line_count_cap(self):
        p=m.PhaseObserver()
        with self.assertRaises(ValueError):p.feed(b'\n'*(m.MAX_LINES+1),0)

    def test_event_count_cap(self):
        p=m.PhaseObserver();p.feed(line()*m.MAX_EVENTS,0)
        with self.assertRaises(ValueError):p.feed(line(),1)
        self.assertEqual(len(p.snapshot()['events']),m.MAX_EVENTS)
        self.assertTrue(p.snapshot()['observation_failed'])

    def test_sample_count_cap_and_snapshot_size(self):
        p=m.PhaseObserver()
        for i in range(m.MAX_SAMPLES):p.sample(i*.2,2147483648,i*.1,134217728)
        d=p.snapshot();self.assertEqual(len(d['samples']['rows']),m.MAX_SAMPLES)
        self.assertLessEqual(len((json.dumps(d,sort_keys=True,indent=2)+'\n').encode()),m.MAX_SNAPSHOT_BYTES)
        with self.assertRaises(ValueError):p.sample(9999,0,0,0)

    def test_failed_observer_does_not_resume(self):
        p=m.PhaseObserver()
        with self.assertRaises(ValueError):p.feed('bad',0)
        with self.assertRaises(ValueError):p.feed(line(),1)
        with self.assertRaises(ValueError):p.sample(1,0,0,0)
        self.assertTrue(p.snapshot()['observation_failed'])


if __name__=='__main__':unittest.main(verbosity=2)

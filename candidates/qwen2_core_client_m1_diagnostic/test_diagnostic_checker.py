"""Synthetic text only; no JVM, PID opening, signal or real execution evidence."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('diag',HERE/'check_diagnostic.py');d=importlib.util.module_from_spec(sp);sp.loader.exec_module(d)
E=dict(schema='qwen2-m1-stack-diagnostic-v1',max_log_bytes=2*1024**2,max_lines=40000,max_line_bytes=16384)
TEXT=b'''Full thread dump OpenJDK 64-Bit Server VM (21.0.12.1+1 mixed mode, sharing):
"main" #1 prio=5 os_prio=0 cpu=45000ms elapsed=60s tid=0x1 nid=0x1 runnable
   java.lang.Thread.State: RUNNABLE
        at treadle2.executable.SymbolTable.build(Synthetic.scala:1)
JNI global refs: 12, weak refs: 0
Heap
 synthetic heap-only suffix
'''

class Tests(unittest.TestCase):
    def runtext(self,b=TEXT,rs=None):return d.classify(b,E,[{'sent':True}] if rs is None else rs)
    def test_one(self):
        r=self.runtext();self.assertEqual(r['complete_looking_thread_text_count'],1)
        self.assertFalse(r['scope']['hardware_behavior_acceptance']);self.assertEqual(r['dumps'][0]['threads'][0]['name'],'main')
    def test_two(self):self.assertEqual(self.runtext(TEXT*2,[{'sent':True},{'sent':True}])['dump_header_count'],2)
    def test_missing_attach_consumption(self):
        r=self.runtext(b'', [{'sent':True},{'sent':True}]);self.assertEqual(r['missing_dump_observation'],2)
    def test_no_request(self):self.assertEqual(self.runtext(b'',[])['sent_request_count'],0)
    def test_interrupted_send_is_unknown_not_absent(self):
        r=self.runtext(b'', [{'sent':False,'send_started':True,'delivery_unknown_if_send_started':True}])
        self.assertEqual(r['send_return_success_record_count'],0)
        self.assertEqual(r['send_started_delivery_not_confirmed_count'],1)
        self.assertTrue(r['sent_false_is_not_proof_of_no_signal'])
    def test_partial(self):self.assertEqual(self.runtext(TEXT.split(b'JNI global refs:')[0])['partial_thread_text_count'],1)
    def test_header_only(self):self.assertEqual(self.runtext(TEXT.splitlines(keepends=True)[0])['complete_looking_thread_text_count'],0)
    def test_no_thread(self):
        raw=TEXT.splitlines(keepends=True)[0]+b'JNI global refs: 12\n'
        self.assertEqual(self.runtext(raw)['partial_thread_text_count'],1)
    def test_unexpected_dump_recorded_not_acceptance(self):self.assertEqual(self.runtext(TEXT,[])['unexpected_dump_without_matching_sent_count'],1)
    def test_extra_request(self):
        with self.assertRaises(ValueError):self.runtext(TEXT,[{'sent':True}]*3)
    def test_extra_dump(self):
        with self.assertRaises(ValueError):self.runtext(TEXT*3)
    def test_duplicate_terminator(self):
        with self.assertRaises(ValueError):self.runtext(TEXT+b'JNI global refs: 12\n')
    def test_long_line(self):
        with self.assertRaises(ValueError):self.runtext(b'x'*16385)
    def test_marker_not_acceptance(self):
        r=self.runtext(b'CORE_SIM_READY case=normal_m1\nCORE_CASE_PASS case=normal_m1\n')
        self.assertEqual(r['phase_observations']['case_pass_lines'],1);self.assertFalse(r['scope']['numerical_acceptance'])
    def test_byte_offsets(self):
        raw=b'prefix\n'+TEXT;r=self.runtext(raw);x=r['dumps'][0]
        self.assertTrue(raw[x['byte_start']:x['byte_end']].startswith(b'Full thread dump'))
        self.assertTrue(raw[x['byte_start']:x['byte_end']].endswith(b'JNI global refs: 12, weak refs: 0\n'))
    def test_empty_regular_file(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t)/'worker.log').write_bytes(b'');self.assertEqual(d.check(t,E,[])['log_bytes'],0)

if __name__=='__main__':unittest.main(verbosity=2)

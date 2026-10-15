"""No native execution: public one-tile scope/source gates."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from . import probe
class Cold(unittest.TestCase):
    def test_default_no_execute(self):
        p=subprocess.run([sys.executable,'-B','-m',probe.__name__],capture_output=True,text=True,cwd=probe.ROOT)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['status'],'NOT_EXECUTED')
    def test_actual_public_api_order(self):
        text=Path(probe.__file__).read_text()
        order=[text.index(x) for x in ('norm=execute_prefix_owner','execution.publish_completions((0,))',
          "j1=execution.advance_to_request()",'driver=Exact64PublicDriver','while owner.tiles_acked<1:',
          'driver.tick(abort=True)','expected,control_stats=control')]
        self.assertEqual(order,sorted(order))
    def test_no_weight_fetch_or_full_runner(self):
        text=Path(probe.__file__).read_text()
        self.assertNotIn('huggingface',text);self.assertNotIn('runner.run(',text)
        self.assertIn('make_qwen2_21_fixture(16,7)',text);self.assertIn('owner.ack_bytes==256',text)
    def test_cold_sources_do_not_read_work(self):
        from unittest.mock import patch
        original=Path.read_text
        def guarded(path,*a,**kw):
            if path.is_relative_to(probe.ROOT/'work'):raise AssertionError('cold work dependency')
            return original(path,*a,**kw)
        with patch.object(Path,'read_text',guarded):self.assertGreater(len(probe.sources_now()),60)
    def test_projection_snapshot_unchanged(self):
        for p,h in probe.PROJECTION_SOURCE_PINS.items():self.assertEqual(probe.sha(probe.ROOT/p),h)
    def test_runtime_ordering_not_monkeypatched(self):
        text=Path(probe.__file__).read_text();tree=ast.parse(text)
        for n in ast.walk(tree):
            if isinstance(n,(ast.Assign,ast.AnnAssign)):
                targets=n.targets if isinstance(n,ast.Assign) else [n.target]
                self.assertFalse(any(isinstance(t,ast.Attribute) and t.attr in ('tick','acquire','bind_dense_job','_attention','_norm','pc','completed','jobs') for t in targets))
    def test_original_failed_host_result_stays_locked(self):
        # Cold terminal-only fixture: tests original Host handshake semantics;
        # the executable probe never assigns Host state or completion values.
        h=probe.public.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True)
        h.group=None;h.state='finish';h.poison=True;h.result={'status':'Protocol'}
        e=h.tick(result_ready=True,reset_required=True)
        self.assertTrue(e['result_fire']);self.assertEqual(e['launch_result']['status'],'Protocol')
        self.assertEqual(h.state,'locked');self.assertTrue(h.ports()['reset_required'])
        text=Path(probe.__file__).read_text()
        self.assertIn("execution.host.state=='locked'",text)
        self.assertIn("execution.counts['result_fire']==1",text)
    def test_no_public_success_claim(self):
        text=Path(probe.__file__).read_text()
        self.assertIn("status='EXPECTED_ABORT_PROTOCOL_PASS'",text)
        self.assertIn('full_projection=False,fullblock=False',text)
        self.assertIn("not physical.regions['qraw']['published']",text)
if __name__=='__main__':unittest.main()

import hashlib
import os
import signal
import subprocess
import sys
import threading
import time
import tempfile
import unittest
from pathlib import Path
from candidates.qwen2_resident_matrix.raw_kv.stimuli import generate, COLUMNS
from candidates.qwen2_resident_matrix.raw_kv.run_unit import memory_audit, run_group

class PrepareTests(unittest.TestCase):
    def test_same_stimulus_and_full_capacity(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'a.tsv';b=Path(tmp)/'b.tsv';ra=generate(a);rb=generate(b)
            self.assertEqual(ra,rb);self.assertEqual(a.read_bytes(),b.read_bytes())
            rows=[dict(zip(COLUMNS,(int(v,16) for v in l.split('\t')))) for l in a.read_text().splitlines()[1:]]
            for write in (0,1):
                self.assertEqual({r['line'] for r in rows if r['accepted'] and r['write']==write},set(range(4096)))
            self.assertTrue(any(r['abort'] and r['acked'] for r in rows))
            self.assertEqual(ra['cycles'],24640)
    def test_process_group_timeout_and_sigterm_cleanup(self):
        for terminate in (False,True):
            with self.subTest(sigterm=terminate),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);beat=root/'heartbeat'
                child="import signal,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);p=Path("+repr(str(beat))+");\nwhile True:p.write_text(str(time.time()));time.sleep(.02)"
                parent="import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',"+repr(child)+"]);time.sleep(10)"
                timer=threading.Timer(.3,lambda:os.kill(os.getpid(),signal.SIGTERM)) if terminate else None
                before=signal.getsignal(signal.SIGTERM);start=time.monotonic()
                try:
                    if timer:timer.start()
                    with (root/'log').open('w') as log:
                        with self.assertRaises(InterruptedError if terminate else subprocess.TimeoutExpired):
                            run_group([sys.executable,'-c',parent],cwd=root,env=os.environ.copy(),log=log,timeout=1 if terminate else .3,grace=.1)
                finally:
                    if timer:timer.cancel()
                self.assertLess(time.monotonic()-start,2)
                self.assertEqual(signal.getsignal(signal.SIGTERM),before)
                self.assertTrue(beat.exists());value=beat.read_text();time.sleep(.1);self.assertEqual(beat.read_text(),value)

    def test_ir_audit_rejects_extra_memory_or_port(self):
        good='\n'.join(f' smem b{i} : UInt<256>[{1376 if i<16 else 160}]\n read mport r{i} = b{i}[address], clock\n write mport w{i} = b{i}[address], clock' for i in range(32))
        self.assertEqual(memory_audit(good)['memories'],32)
        for bad in (good+'\n cmem shadow : UInt<512>[4096]',good+'\n read mport extra = b0[address], clock',good.replace('1376','1375',1)):
            with self.assertRaises(ValueError):memory_audit(bad)

if __name__=='__main__':unittest.main()

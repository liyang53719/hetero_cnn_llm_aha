"""No checkpoint/Torch: exact AST/shape guard and independent N32 C smoke."""
import ast,ctypes as C,json,subprocess,tempfile,unittest
from pathlib import Path
import numpy as np
from . import reference as r
from .run import checked_calibration

class ReferenceTests(unittest.TestCase):
    def test_original_separate_a_b_calls(self):
        ops=r.operators();self.assertEqual(set(ops),{'a','b'})
        for name,(assignment,call) in ops.items():
            self.assertEqual(ast.unparse(call),f'{name} = self.in_proj_{name}(hidden_states)')
            self.assertIn('self.num_v_heads',ast.unparse(assignment))
    def test_n8192_report_cannot_admit_n32(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'report.json';raw=json.dumps(dict(m=16,n=8192,k=2048,status='PASS_NEW_N32_PAIR_ORIGINAL_GATES')).encode();p.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'N32'):checked_calibration(p,r.sha(raw),16)
            with self.assertRaisesRegex(ValueError,'digest'):checked_calibration(p,'0'*64,16)
    def test_original_per_operator_gate_is_not_diluted(self):
        a=np.full((16,32),0x3c00,'<u2').tobytes()
        self.assertFalse(r.gate(a,bytes(len(a)))['passed'])
        self.assertTrue(r.gate(bytes(len(a)),bytes(len(a)))['passed'])
    def test_independent_n32_c_shape_counts_and_rne_environment(self):
        with tempfile.TemporaryDirectory() as td:
            lib=Path(td)/'r.so';source=Path(r.__file__).with_name('reference.c')
            subprocess.run(['gcc',*r.FLAGS,str(source),'-o',str(lib),'-lm'],check=True,capture_output=True,timeout=30)
            native=C.CDLL(str(lib));self.assertEqual(native.reference_self_test(),0)
            native.reference_run.argtypes=[C.c_uint,C.c_uint,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p]
            a=np.full((16,2048),0x3f80,'<u2');w=np.full((32,2048),0x3f80,'<u2')
            for mode in (0,1):
                out=np.zeros((16,32),'<u2');pre=np.zeros((16,32),'<f4');counts=np.zeros(3,'<u8')
                args=(16,mode,a.ctypes.data,w.ctypes.data,out.ctypes.data,pre.ctypes.data,counts.ctypes.data)
                self.assertEqual(native.reference_run(*args),0)
                self.assertTrue(np.all(out==0x4500));self.assertTrue(np.all(pre==2048))
                self.assertEqual(int(counts[0]),16*32*2048);self.assertEqual(int(counts[2]),16*32 if mode else 0)
                self.assertEqual(native.reference_run(8,*args[1:]),-1)

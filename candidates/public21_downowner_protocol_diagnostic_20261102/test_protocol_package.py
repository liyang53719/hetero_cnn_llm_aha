import unittest,copy,json,hashlib
from pathlib import Path
from prepare_protocol_input import project,verify
D=Path(__file__).resolve().parent
class Package(unittest.TestCase):
    def fixture(self):
        return {'tokens':128,'shape':{'H':1536,'unused':'not projected'},'commands':21,'tensors':{n:{'dims':[1536 if n=='wq' else 128,1536],'address':100000+i*10000000,'unused':'not projected'} for i,n in enumerate(('n0','wq','q'))}}
    def test_project_exact(self):
        raw=json.dumps(self.fixture()).encode();h=hashlib.sha256(raw).hexdigest();d=project(raw,h);self.assertTrue(verify(d,h));self.assertNotIn('unused',json.dumps(d));self.assertEqual(len(d['protocol_metadata_provenance']['selected_fields']),9)
    def test_original_sha_required(self):
        with self.assertRaises(ValueError):project(json.dumps(self.fixture()).encode(),'0'*64)
    def test_projected_value_drift(self):
        raw=json.dumps(self.fixture()).encode();h=hashlib.sha256(raw).hexdigest();d=project(raw,h);d['tensors']['n0']['address']+=64
        with self.assertRaises(ValueError):verify(d,h)
    def test_extra_payload_rejected(self):
        raw=json.dumps(self.fixture()).encode();h=hashlib.sha256(raw).hexdigest();d=project(raw,h);d['tensors']['n0']['data']=[0]
        with self.assertRaises(ValueError):verify(d,h)
    def test_original_metadata_pin_is_constant(self):
        d=json.loads((D/'P0_PROTOCOL_INPUT.json').read_text());self.assertTrue(verify(d,'4f201e1744b8aa2c604a478ca837076abaf41a7235b62d8aa7ef14fcdc830163'));self.assertEqual(d['protocol_metadata_provenance']['source_manifest_bytes'],15000)
    def test_emit_order_not_native_launch(self):
        s=(D/'Public21DownOwnerEmitOnly.scala').read_text();keys=['Compiler.elaborate(','Compiler.toLowFirrtl(','VerilatorCppJNAHarnessGenerator.codeGen(','Compiler.lowFirrtlToSystemVerilog(']
        positions=[s.index(k) for k in keys];self.assertEqual(positions,sorted(positions));self.assertTrue(all(s.count(k)==1 for k in keys))
        for bad in ('createContext(', 'runVerilator(', 'compileAndLoadJNAClass(', 'Runtime.getRuntime', 'ProcessBuilder', 'scala.sys.process'):
            self.assertNotIn(bad,s)
        self.assertIn('VerilatorCoverage.CoveragePasses',s)
if __name__=='__main__':unittest.main()

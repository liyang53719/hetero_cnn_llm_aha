import unittest,io
from pathlib import Path
from prepare_direct_driver import inventory,driver,verify_sv,verify_expected
LOW='''  module Public21DownOwnerProtocolHarness :
    input clock : Clock
    input reset : UInt<1>
    input io_data : UInt<512>
    output diagnostic_status : UInt<8>
    wire stop : UInt<1>
'''
H='''top->clock = 0; top->clock = 1;
inline void poke(int32_t id, int64_t value) { case 0 : dut->reset = u; break; }
inline int64_t peek(int32_t id) { case 0 : value = dut->reset; break; case 2 : value = dut->diagnostic_status; break; }
inline void poke_wide(int32_t id, int32_t offset, int64_t value) { case 1 : data = dut->io_data; words = 16; break; }
inline int64_t peek_wide(int32_t id, int32_t offset) { case 1 : data = dut->io_data; words = 16; break; }
inline void set_args(int32_t argc, const char** argv) {}
'''
class Mapping(unittest.TestCase):
    def test_order_width_direction(self):
        p=inventory(io.StringIO(LOW),H)['ports'];self.assertEqual([(x['id'],x['name'],x['width'],x['direction']) for x in p],[(0,'reset',1,'input'),(1,'io_data',512,'input'),(2,'diagnostic_status',8,'output')])
    def test_missing_leaf(self):
        with self.assertRaises(ValueError):inventory(io.StringIO(LOW),H.replace('case 2 : value = dut->diagnostic_status; break;',''))
    def test_duplicate_id(self):
        with self.assertRaises(ValueError):inventory(io.StringIO(LOW),H.replace('case 2 : value = dut->diagnostic_status; break;','case 0 : value = dut->diagnostic_status; break;'))
    def test_wrong_width(self):
        with self.assertRaises(ValueError):inventory(io.StringIO(LOW.replace('UInt<512>','UInt<480>')),H)
    def test_wrong_direction(self):
        with self.assertRaises(ValueError):inventory(io.StringIO(LOW.replace('output diagnostic_status','input diagnostic_status')),H)
    def test_unknown_switch(self):
        with self.assertRaises(ValueError):inventory(io.StringIO(LOW),H.replace('case 2 : value = dut->diagnostic_status; break;','case 2 : value = arbitrary(); break;'))
    def test_clock(self):
        with self.assertRaises(ValueError):inventory(io.StringIO(LOW.replace('input clock : Clock','input clock : UInt<1>')),H)
    def test_sv_exact_width(self):
        inv=inventory(io.StringIO(LOW),H)
        sv="module Public21DownOwnerProtocolHarness(\n  input clock,\n  input reset,\n  input [511:0] io_data,\n  output [7:0] diagnostic_status\n);\n"
        self.assertEqual(len(verify_sv(io.StringIO(sv),inv)),64)
        with self.assertRaises(ValueError):verify_sv(io.StringIO(sv.replace('[7:0]','[6:0]')),inv)
    def test_cloud_expected_typed_inventory(self):
        import json,hashlib,copy
        inv=inventory(io.StringIO(LOW),H);body={k:inv[k] for k in ('top','clocks','ports')}
        expected={'schema':'B_EXPECTED_TYPED_PORT_DIGEST_V1','top':inv['top'],'clocks':inv['clocks'],'port_count':len(inv['ports']),'typed_inventory_sha256':hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
        verify_expected(inv,expected)
        wrong=copy.deepcopy(inv);wrong['ports'][0]['width']=2
        with self.assertRaises(ValueError):verify_expected(wrong,expected)
    def test_inverse_body(self):
        s='''  val path="fixture"
  def run(d:Public21DownOwnerProtocolHarness):Unit={
    def fire(x:chisel3.util.DecoupledIO[_]):Boolean=x.valid.peek().litToBoolean && x.ready.peek().litToBoolean
    d.io.resetRequired.expect(false.B);d.clock.step()
  }
  "Real selected DownOwner" should "x" in {}
'''
        out,p=driver(s);body=out[out.index('  val path='):out.rfind('}\n')]
        body=body.replace('def run(d:DirectDut):Unit=','def run(d:Public21DownOwnerProtocolHarness):Unit=').replace('def fire(x:DirectPort):Boolean=','def fire(x:chisel3.util.DecoupledIO[_]):Boolean=')
        self.assertEqual(body,s[:s.index('  "Real selected DownOwner')]);self.assertEqual(p['reversible_type_substitutions'],2)
if __name__=='__main__':unittest.main()

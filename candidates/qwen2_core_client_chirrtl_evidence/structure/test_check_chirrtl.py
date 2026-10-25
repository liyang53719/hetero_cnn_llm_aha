"""Only tiny synthetic structure strings; no actual FIRRTL or JVM is generated."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('structure_under_test',HERE/'check_chirrtl.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
E=json.loads((HERE/'STRUCTURE_EXPECTATION.json').read_text())


def fixture():
    # Deliberately structural-only mock, not an executable or numerical circuit.
    lines=['FIRRTL version 3.3.0','circuit OrderedQkBehaviorCore :','  module OrderedQkBehaviorCore :',
           '    input clock : Clock','    input reset : UInt<1>',
           '    output io : { '+', '.join(x+' : UInt<1>' for x in E['required_io_fields'])+'}',
           '    output testScoreWrite : UInt<1>','    output observation : UInt<1>',
           '    regreset state : UInt<7>, clock, reset, UInt<7>(0h0)',
           '    reg acc : UInt<32>[16], clock','    regreset orderedQkFault : UInt<1>[16], clock, reset, x',
           '    smem scores : UInt<32> [1024]','    smem probs : UInt<32> [1024]',
           '    connect testScoreWrite.valid, UInt<1>(0h1)']
    for i in E['ordered_state_codes']:
        lines += ['    node stateTest'+str(i)+' = eq(state, UInt<7>(0h'+format(i,'x')+'))',
                  '    connect state, UInt<7>(0h'+format(i,'x')+')']
    for i in range(16):lines.append('    inst a'+str(i)+' of HeteroFP32Alu')
    for instance,child in [('scalar','BlockScalarFloat'),('fabric','SharedL2Fabric'),('packedQk','PackedAttentionStreamClient'),('elem','ElementwiseMemoryEngine'),('writeback','BlockWritebackFence')]:
        lines.append('    inst '+instance+' of '+child)
    for lhs,rhs in E['client_port_connections']:
        lines.append('    connect '+lhs.replace('$CLIENT','packedQk')+', '+rhs.replace('$CLIENT','packedQk'))
    lines += ['  module HeteroFP32Alu :','    output io : { exceptionFlags : UInt<5>}',
              '    inst add of AddRecFN','    inst mul of MulRecFN',
              '  module AddRecFN :','  module MulRecFN :','  module BlockScalarFloat :',
              '  module SharedL2Fabric :']
    lines += ['    smem bank_'+str(i)+' : UInt<8>[16] [2240]' for i in range(16)]
    lines += ['  module PackedAttentionStreamClient :','    regreset state : UInt<3>, clock, reset, UInt<3>(0h0)',
              '    reg descriptor : { tag : UInt<32>, pv : UInt<1>, count : UInt<8>}, clock',
              '    regreset index : UInt<8>, clock, reset, UInt<8>(0h0)',
              '    regreset poison : UInt<1>, clock, reset, UInt<1>(0h0)',
              '  module ElementwiseMemoryEngine :','  module BlockWritebackFence :']
    return ('\n'.join(lines)+'\n').encode()


class StructureControls(unittest.TestCase):
    def audit(self,data=None,e=None):return c.parse_bytes(fixture() if data is None else data,E if e is None else e)
    def reject(self,old,new):
        data=fixture();self.assertIn(old,data)
        with self.assertRaises(ValueError):self.audit(data.replace(old,new,1))
    def test_positive_scope_is_not_behavior(self):
        r=self.audit();self.assertEqual(r['status'],c.STATUS)
        self.assertEqual(r['direct_instance_counts']['HeteroFP32Alu'],16)
        self.assertEqual(r['client_control_registers'],['descriptor','index','poison','state'])
        self.assertFalse(r['scope']['behavior_executed']);self.assertFalse(r['scope']['numerical_pass'])
        self.assertIsNone(r['scope']['matrix_mac_utilization'])
    def test_wrong_top_and_version(self):
        self.reject(b'circuit OrderedQkBehaviorCore',b'circuit Wrong')
        self.reject(b'FIRRTL version 3.3.0',b'FIRRTL version 9.9.9')
    def test_blackboxes_intrinsics_rejected(self):
        for marker in ('extmodule','intmodule','intrinsic','defname'):
            with self.assertRaises(ValueError):self.audit(fixture()+('  '+marker+' Unexpected :\n').encode())
    def test_missing_real_child(self):self.reject(b'inst a0 of HeteroFP32Alu',b'inst a0 of Fake')
    def test_duplicate_module(self):
        with self.assertRaises(ValueError):self.audit(fixture()+b'  module HeteroFP32Alu :\n')
    def test_unreachable_module(self):
        with self.assertRaises(ValueError):self.audit(fixture()+b'  module Unused :\n')
    def test_recursive_hierarchy(self):
        self.reject(b'  module BlockWritebackFence :',b'  module BlockWritebackFence :\n    inst loop of OrderedQkBehaviorCore')
    def test_no_extra_alu(self):self.reject(b'    inst scalar',b'    inst a16 of HeteroFP32Alu\n    inst scalar')
    def test_ordered_mode_required(self):
        self.reject(b'regreset orderedQkFault',b'regreset notSelectedFault')
        self.reject(b'eq(state, UInt<7>(0h67))',b'eq(state, UInt<7>(0h66))')
    def test_state_and_memory_capacity(self):
        self.reject(b'regreset state : UInt<7>',b'regreset state : UInt<8>')
        self.reject(b'smem scores : UInt<32> [1024]',b'smem scores : UInt<32> [128]')
        self.reject(b'smem bank_0 : UInt<8>[16] [2240]',b'smem bank_0 : UInt<8>[16] [16]')
    def test_client_enabled_and_no_payload_copy(self):
        self.reject(b'regreset index : UInt<8>',b'regreset index : UInt<7>')
        self.reject(b'  module ElementwiseMemoryEngine :',b'    reg payload : UInt<32>[4096], clock\n  module ElementwiseMemoryEngine :')
    def test_actual_alu_primitives_and_flags(self):
        self.reject(b'inst mul of MulRecFN',b'inst other of AddRecFN')
        self.reject(b'exceptionFlags : UInt<5>',b'exceptionFlags : UInt<1>')
    def test_probe_and_port_connection(self):
        self.reject(b'connect testScoreWrite.valid, UInt<1>(0h1)',b'connect testScoreWrite.valid, UInt<1>(0h0)')
        self.reject(b'connect io.packedQk.step.valid, packedQk.io.port.step.valid',b'connect io.packedQk.step.valid, UInt<1>(0h0)')
    def test_top_reset_is_bool_not_child_abstract_reset(self):
        self.reject(b'input reset : UInt<1>',b'input reset : Reset')
        self.reject(b'input reset : UInt<1>',b'input reset : UInt<2>')
        self.reject(b'input reset : UInt<1>',b'input reset : AsyncReset')
    def test_single_clock_and_exact_top_ports(self):
        self.reject(b'    input reset',b'    input clock2 : Clock\n    input reset')
        self.reject(b'    input reset',b'    input unreviewed : UInt<1>\n    input reset')
    def test_profile_external_scalar_absent(self):
        self.reject(b'output io : { ownerJob',b'output io : { scalarService : UInt<1>, ownerJob')
    def test_unparsed_structure_declarations_rejected(self):
        for line in (b' module Strange :',b'  public module Strange :',b'    inst x of Missing?',
                     b'    inst x of HeteroFP32Alu trailing',b'  public extmodule Wrong :',
                     b'  private intmodule Wrong :',b'    reg !bad : UInt<1>, clock',
                     b'    mem unknown :'):
            with self.assertRaises(ValueError,msg=str(line)):self.audit(fixture()+line+b'\n')
    def test_no_extra_core_memory(self):
        self.reject(b'    smem scores',b'    smem extra : UInt<32> [1024]\n    smem scores')
    def test_bounded_inputs(self):
        for key,value in [('max_bytes',8),('max_lines',1),('max_line_bytes',8),('max_modules',1),('max_instances',1),('max_instances_per_module',1),('max_registers',1),('max_hierarchy_depth',0)]:
            e=copy.deepcopy(E);e[key]=value
            with self.assertRaises(ValueError,msg=key):self.audit(e=e)
        with self.assertRaises(UnicodeDecodeError):self.audit(b'\xff')
    def test_line_limit_counts_utf8_bytes(self):
        e=copy.deepcopy(E);e['max_line_bytes']=1024
        # 601 characters including comment prefix but 1801 UTF8 bytes.
        with self.assertRaisesRegex(ValueError,'line byte bound'):
            self.audit(fixture()+(';'+'中'*600+'\n').encode(),e)
    def test_regular_file_identity(self):
        with tempfile.TemporaryDirectory() as name:
            p=Path(name)/'mock.fir';p.write_bytes(fixture())
            self.assertEqual(c.check(p,E)['firrtl_bytes'],p.stat().st_size)
            link=Path(name)/'link.fir';link.symlink_to(p)
            with self.assertRaises(ValueError):c.check(link,E)


if __name__=='__main__':unittest.main(verbosity=2)

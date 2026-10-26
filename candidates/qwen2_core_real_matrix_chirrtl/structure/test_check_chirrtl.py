"""Tiny synthetic declarations only: not actual FIRRTL, numerical or JVM evidence."""
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

def original_core_fixture():
    # Deliberately structural-only mock, not an executable or numerical circuit.
    lines=['FIRRTL version 3.3.0','circuit OrderedQkRealMatrixCollection :','  module OrderedQkBehaviorCore :',
           '    input clock : Clock','    input reset : Reset',
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


def fma_type(child):
    return '{ '+', '.join(('flip ' if f['direction']=='input' else '')+n[3:]+' : UInt<'+str(f['width'])+'>' for n,f in E['fma_abi'][child].items())+'}'


def fixture():
    lines=original_core_fixture().decode().splitlines()
    for child in E['fma_abi']:
        lines+=['  module '+child+' :','    output io : '+fma_type(child)]
    lines+=['  module Queue8_Meta :','    cmem ram : { context : UInt<3>, last : UInt<1>, finish : UInt<1>, emit : UInt<1>} [8]',
            '  module MatrixResultFifo :','    reg storage : { value : UInt<32>[256][16], context : UInt<3>, last : UInt<1>, error : UInt<1>}[2], clock',
            '    regreset head : UInt<1>, clock, reset, UInt<1>(0h0)',
            '    regreset tail : UInt<1>, clock, reset, UInt<1>(0h0)',
            '    regreset count : UInt<2>, clock, reset, UInt<2>(0h0)',
            '  module LegacyMatrixStreamClient :','  module MatrixPipelineService :',
            '    output io : { packedStepsDrained : UInt<1>}',
            '    inst tags of Queue8_Meta','    inst values of MatrixResultFifo']
    for i in range(8):
        suffix='' if i==0 else '_'+str(i)
        lines+=['    inst leaves_'+str(i)+' of qwen2_matrix_command_endpoint'+suffix,'    inst gate_'+str(i)+' of tc_clk_gating'+suffix]
    for name,ports in E['external_ports'].items():
        for i in range(8):
            lines+=['  extmodule '+name+('' if i==0 else '_'+str(i))+' :']
            lines+=['    '+d+' '+n+' : '+t for n,(d,t) in ports.items()]
            lines+=['    defname = '+name]
    lines+=['  module OrderedQkRealMatrixCore :','    input clock : Clock','    input reset : Reset',
            '    output io : { ownerJob : UInt<1>}','    output observation : UInt<1>','    output scoreWrite : UInt<1>']
    lines+=['    inst '+i+' of '+n for i,n in E['shell_instances'].items()]
    lines+=['  module OrderedQkRealMatrixCollection :','    input clock : Clock','    input reset : UInt<1>',
            '    output port : { ownerJob : UInt<1>}','    output observation : UInt<1>','    output scoreWrite : UInt<1>']
    for i,n in E['collection_instances'].items():
        if i!='top':lines+=['    output '+i+'Port : '+fma_type(n)]
    lines+=['    inst '+i+' of '+n for i,n in E['collection_instances'].items()]
    # Annotation fixture is synthetic too; serializer envelope is source-bound.
    mods={};current=None
    for line in lines:
        m=c.MODULE.fullmatch(line)
        if m:
            current={'ports':{}};mods[m[2]]=current
        else:
            p=c.PORT.fullmatch(line)
            if p:current['ports'][p[2]]=[p[1],p[3]]
    a=c.annotation_expectation(mods,E)
    annotations=[{'class':c._DONT,'target':t} for t in a['dont_touch_targets']]
    annotations += [{'class':c._DEDUP,'target':'~'+E['top']+'|'+m,'group':m} for m in a['modules']]
    lines[1]='circuit '+E['top']+' :%['+json.dumps(annotations,indent=1)+']'
    return ('\n'.join(lines)+'\n').encode()


class StructureControls(unittest.TestCase):
    def audit(self,data=None,e=None):return c.parse_bytes(fixture() if data is None else data,E if e is None else e)
    def reject(self,old,new):
        data=fixture();self.assertIn(old,data)
        with self.assertRaises(ValueError):self.audit(data.replace(old,new,1))
    def test_positive_scope(self):
        r=self.audit();self.assertEqual(r['status'],c.STATUS)
        self.assertEqual(r['qualified_external_occurrences'],{'qwen2_matrix_command_endpoint':8,'tc_clk_gating':8})
        self.assertEqual(r['strict_vector_alu_instances'],16)
        for k in ('behavior_executed','numerical_pass','provider_sv_linted','physical_fma_closed','rtl_simulated','fullblock_accepted'):self.assertFalse(r['scope'][k])
        self.assertIsNone(r['scope']['matrix_mac_utilization'])
    def test_wrong_top_version(self):
        self.reject(b'circuit OrderedQkRealMatrixCollection',b'circuit OrderedQkBehaviorCore')
        self.reject(b'version 3.3.0',b'version 9.9.9')
    def test_external_unknown(self):
        for word in ('extmodule','intmodule','intrinsic','public extmodule','private intmodule'):
            with self.assertRaises(ValueError):self.audit(fixture()+('  '+word+' Unknown :\n').encode())
    def test_sixteen_distinct_external_definitions(self):
        self.reject(b'extmodule tc_clk_gating_7 :',b'module tc_clk_gating_7 :')
        self.reject(b'inst leaves_7 of qwen2_matrix_command_endpoint_7',b'inst leaves_7 of qwen2_matrix_command_endpoint_6')
        self.reject(b'extmodule tc_clk_gating_7 :',b'extmodule tc_clk_gating_8 :')
    def test_external_exact_ports(self):
        self.reject(b'input step_a_i : UInt<256>',b'input step_a_i : UInt<128>')
        self.reject(b'input step_a_i : UInt<256>',b'output step_a_i : UInt<256>')
        self.reject(b'input step_a_i : UInt<256>',b'input step_a_i : UInt<256>\n    input seed : UInt<1>')
        self.reject(b'input step_a_i : UInt<256>',b'input step_a_i : UInt<256>\n    input step_a_i : UInt<256>')
    def test_defname_and_params(self):
        self.reject(b'defname = tc_clk_gating',b'defname = Unknown')
        self.reject(b'defname = tc_clk_gating',b'defname = tc_clk_gating\n    parameter ENABLE_ACCUMULATOR_SEED = 1')
        self.reject(b'defname = tc_clk_gating',b'defname = tc_clk_gating\n    connect x, y')
    def test_instance_closure(self):
        self.reject(b'inst leaves_0 of qwen2_matrix_command_endpoint',b'inst leaves_0 of Unknown')
        self.reject(b'inst gate_0 of tc_clk_gating',b'inst gate_0 of qwen2_matrix_command_endpoint')
        self.reject(b'inst gate_0 of tc_clk_gating',b'inst gate_0 of tc_clk_gating\n    inst gate_extra of tc_clk_gating')
    def test_collection_not_simulation_top(self):
        self.reject(b'inst top of OrderedQkRealMatrixCore',b'inst top of OrderedQkBehaviorCore')
        self.reject(b'inst pre of HeteroBF16FmaPre',b'inst pre of HeteroBF16FmaMul')
        self.reject(b'inst top of OrderedQkRealMatrixCore',b'inst top of OrderedQkRealMatrixCore\n    inst extra of LegacyMatrixStreamClient')
    def test_shell_three_children(self):
        self.reject(b'inst legacy of LegacyMatrixStreamClient',b'inst legacy of OrderedQkBehaviorCore')
        self.reject(b'inst matrix of MatrixPipelineService',b'inst matrix of MatrixPipelineService\n    inst other of MatrixPipelineService')
    def test_resets(self):
        self.reject(b'input reset : Reset',b'input reset : UInt<1>')
        self.reject(b'input reset : UInt<1>',b'input reset : Reset')
        self.reject(b'input clock : Clock',b'input clock : Clock\n    input clock2 : Clock')
    def test_fma_exact_flat_abi(self):
        self.reject(b'flip mulAddA : UInt<24>',b'mulAddA : UInt<24>')
        self.reject(b'mulAddResult : UInt<49>',b'mulAddResult : UInt<48>')
        self.reject(b'  module HeteroBF16FmaMul :',b'  module HeteroBF16FmaMul :\n    input clock : Clock')
        self.reject(b'output prePort :',b'output notPrePort :')
    def test_queue_and_results(self):
        self.reject(b'cmem ram :',b'smem ram :')
        self.reject(b'} [8]',b'} [7]')
        self.reject(b'emit : UInt<1>} [8]',b'emit : UInt<1>, returnTag : UInt<1>} [8]')
        self.reject(b'error : UInt<1>}[2], clock',b'error : UInt<1>}[3], clock')
        self.reject(b'regreset count : UInt<2>',b'regreset count : UInt<3>')
    def test_duplicate_and_unreachable(self):
        for suffix in (b'  module HeteroFP32Alu :\n',b'  module Unused :\n'):
            with self.assertRaises(ValueError):self.audit(fixture()+suffix)
    def test_cycle(self):self.reject(b'  module BlockWritebackFence :',b'  module BlockWritebackFence :\n    inst loop of OrderedQkRealMatrixCollection')
    def test_original_core_selected_gates(self):
        for a,b in [(b'orderedQkFault',b'notSelectedFault'),(b'eq(state, UInt<7>(0h67))',b'eq(state, UInt<7>(0h66))'),
                    (b'regreset state : UInt<7>',b'regreset state : UInt<8>'),(b'smem scores : UInt<32> [1024]',b'smem scores : UInt<32> [128]'),
                    (b'smem bank_0 : UInt<8>[16] [2240]',b'smem bank_0 : UInt<8>[16] [16]'),
                    (b'connect testScoreWrite.valid, UInt<1>(0h1)',b'connect testScoreWrite.valid, UInt<1>(0h0)'),
                    (b'inst mul of MulRecFN',b'inst other of AddRecFN'),(b'exceptionFlags : UInt<5>',b'exceptionFlags : UInt<1>')]:self.reject(a,b)
    def test_original_client(self):
        self.reject(b'regreset index : UInt<8>',b'regreset index : UInt<7>')
        self.reject(b'connect io.packedQk.step.valid, packedQk.io.port.step.valid',b'connect io.packedQk.step.valid, UInt<1>(0h0)')
        self.reject(b'  module ElementwiseMemoryEngine :',b'    reg payload : UInt<32>[4096], clock\n  module ElementwiseMemoryEngine :')
    def test_unparsed_structural(self):
        for line in (b' module Strange :',b'  public module Strange :',b'    inst x of Unknown?',b'      inst conditional of HeteroFP32Alu',b'    reg !bad : UInt<1>, clock',b'    mem unknown :',b'    input strange ?',b'  class Weird :',b'    instchoice unknown of HeteroFP32Alu',b'  declgroup unexpected, bind :'):
            with self.assertRaises(ValueError,msg=str(line)):self.audit(fixture()+line+b'\n')
    def test_bounds(self):
        for key,value in [('max_bytes',8),('max_lines',1),('max_line_bytes',8),('max_modules',1),('max_instances',1),('max_instances_per_module',1),('max_registers',1),('max_hierarchy_depth',0)]:
            e=copy.deepcopy(E);e[key]=value
            with self.assertRaises(ValueError,msg=key):self.audit(e=e)
        with self.assertRaises(UnicodeDecodeError):self.audit(b'\xff')
        with self.assertRaises(ValueError):self.audit(fixture()+b'\x00')
    def mutate_annotations(self, fn):
        data=fixture();text=data.decode();annotations,end=c.extract_header(text,E['top']);fn(annotations)
        return ('FIRRTL version 3.3.0\ncircuit '+E['top']+' :%['+json.dumps(annotations)+']\n'+text[end:]).encode()
    def test_annotation_unknown_and_external_file(self):
        for cls in ('firrtl.transforms.BlackBoxPathAnno','firrtl.options.OutputAnnotationFileAnnotation','evil.Unknown'):
            data=self.mutate_annotations(lambda a:a.append({'class':cls,'target':'~'+E['top']+'|'+E['top']}))
            with self.assertRaises(ValueError):self.audit(data)
    def test_annotation_complete_target_sets(self):
        for fn in (lambda a:a.pop(),lambda a:a.append(dict(a[0])),lambda a:a.__setitem__(0,dict(a[0],target=a[0]['target']+'.unreviewed')),lambda a:a.__setitem__(0,dict(a[0],target='~Other|Other>io'))):
            with self.assertRaises(ValueError):self.audit(self.mutate_annotations(fn))
    def test_header_no_unparsed_material(self):
        data=fixture();text=data.decode();annotations,end=c.extract_header(text,E['top'])
        for header in ('FIRRTL version 3.3.0\ncircuit '+E['top']+' :\n',
                       'FIRRTL version 3.3.0\ncircuit '+E['top']+' :%['+json.dumps(annotations)+'] garbage\n'):
            with self.assertRaises(ValueError):self.audit((header+text[end:]).encode())
        with self.assertRaises(ValueError):self.audit((text[:end]+'unparsed prefix material\n'+text[end:]).encode())
    def test_large_compact_header_separate_bound(self):
        text=fixture().decode();ann,end=c.extract_header(text,E['top']);body=text[end:]
        body=body.replace('{ ownerJob : UInt<1>}','{ ownerJob : UInt<1>[9000]}')
        mods={};current=None
        for line in body.splitlines():
            m=c.MODULE.fullmatch(line)
            if m:current={'ports':{}};mods[m[2]]=current
            else:
                p=c.PORT.fullmatch(line)
                if p:current['ports'][p[2]]=[p[1],p[3]]
        a=c.annotation_expectation(mods,E)
        ann=[{'class':c._DONT,'target':t} for t in a['dont_touch_targets']]
        ann += [{'class':c._DEDUP,'target':'~'+E['top']+'|'+m,'group':m} for m in a['modules']]
        header='FIRRTL version 3.3.0\ncircuit '+E['top']+' :%['+json.dumps(ann,separators=(',',':'))+']\n'
        self.assertGreater(len(header),E['max_line_bytes']);self.assertLess(len(header),c.MAX_HEADER_BYTES)
        self.audit((header+body).encode())
    def test_type_leaf_outer_vector_order(self):
        self.assertEqual(c.type_leaf_paths('UInt<8>[2][3]','p'),['p[0][0]','p[0][1]','p[1][0]','p[1][1]','p[2][0]','p[2][1]'])
        self.assertEqual(c.type_leaf_paths('{ flip a : UInt<1>, b : { c : Clock}[2]}','p'),['p.a','p.b[0].c','p.b[1].c'])
    def test_type_leaf_failclosed(self):
        for t in ('UInt','UInt<-1>','UInt<0>','Unknown<3>','{ a : UInt<1>, a : UInt<1>}','{ a : UInt<1>,}','UInt<3>junk','UInt<3>[100001]','UInt<3>[2][100001]','{ a : UInt<1>'):
            with self.assertRaises(ValueError,msg=t):c.type_leaf_paths(t,'p')
        with self.assertRaises(ValueError):c.type_leaf_paths('UInt<1>[3]','p',limit=2)
        with self.assertRaises(ValueError):c.type_leaf_paths('{ a : '*34+'UInt<1>'+'}'*34,'p')
    def test_file(self):
        with tempfile.TemporaryDirectory() as n:
            p=Path(n)/'mock.fir';p.write_bytes(fixture());self.assertEqual(c.check(p,E)['firrtl_bytes'],len(fixture()))
            link=Path(n)/'link.fir';link.symlink_to(p)
            with self.assertRaises(ValueError):c.check(link,E)

if __name__=='__main__':unittest.main(verbosity=2)

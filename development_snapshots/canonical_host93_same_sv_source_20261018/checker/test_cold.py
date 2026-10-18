"""Tiny synthetic fixtures only. Never reads/checks the actual generated SV."""
import hashlib
import sys
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('use python -I -S -B')
raw = (HERE/'check_host_sv.py').read_bytes()
if len(raw) != 31470 or hashlib.sha256(raw).hexdigest() != '33820c6f28dbc1e90185bbe8cdb3911acb41934a01ec4adc0c933901a2fdf676':
    raise ValueError('fixed checker source SHA/size drift')
ns = {'__name__':'host93_same_sv_cold'}
exec(compile(raw,str(HERE/'check_host_sv.py'),'exec',dont_inherit=True),ns)

def concat_declaration(name, spec):
    width,(hi,lo)=spec
    return 'wire ['+str(width-1)+':0] '+name+' =\n { '+hi+' ,\n '+lo+' };'

def qualified(text):
    return ns['qualify'](ns['parse_modules'](ns['cleaned'](text)))

def fixture():
    rows={name:{'ports':{'clock':['input',1]},'edges':[], 'taps':{}} for name in ns['EXPECTED_MODULES']}
    rows['HostBlockTop']['ports']=ns['HOST_PORTS']
    for name,ports in ns['FMA_PORTS'].items():rows[name]['ports']=ports
    rows['HostBlockCollection']['edges']=list(ns['SIBLINGS'].items())
    for path,typ in ns['EXPECTED_PATHS'].items():
        fields=path.split('.'); parent='HostBlockTop' if len(fields)==1 else ns['EXPECTED_PATHS']['.'.join(fields[:-1])]
        rows[parent]['edges'].append((fields[-1],typ))
    for name,widths in ns['TAPS'].items():rows[name]['taps']=widths
    matrix=rows['MatrixPipelineService']
    for i in range(8):
        matrix['edges'] += [('leaves_'+str(i),'qwen2_matrix_command_endpoint'),('gate'+('_'+str(i) if i else ''),'tc_clk_gating')]
    used=set(ns['SIBLINGS'].values())|set(ns['EXPECTED_PATHS'].values())|{'HostBlockCollection'}
    for name in set(rows)-used:rows['HostBlockTop']['edges'].append(('extra_'+name,name))
    text=[]
    for name,row in rows.items():
        text.append('module '+name+'('+','.join(d+' '+('['+str(w-1)+':0] ' if w>1 else '')+p for p,(d,w) in row['ports'].items())+');')
        for p,w in row['taps'].items():text.append('wire '+('['+str(w-1)+':0] ' if w>1 else '')+p+' =\n 1\'h0;')
        if name==ns['TAP_CONCAT_MODULE']:
            for helper,spec in ns['TAP_CONCAT_DECLARATIONS'].items():text.append(concat_declaration(helper,spec))
        for inst,typ in row['edges']:
            spec=ns['EXTERNAL'].get(typ); ports=spec['ports'] if spec else rows[typ]['ports']
            param=' #(.ENABLE_ACCUMULATOR_SEED(1))' if typ=='qwen2_matrix_command_endpoint' else ''
            text.append(typ+param+' '+inst+'('+','.join('.'+p+'(1\'h0)' for p in ports)+');')
        text.append('endmodule')
    return '\n'.join(text)

REVIEW_REPRO_PINS = {'ROOT_PORT_DUPLICATE_REPRO.sv': {'bytes': 28298,
                                  'sha256': 'd478ea1f6dd64e05bae203baa90d5af238e419ab0c547f97e4a1bb3160fda6f0'},
 'ROOT_PORT_WRONG_WIDTH_REPRO.sv': {'bytes': 28290,
                                    'sha256': 'd7229378e52614a1848100707281f1d388be28b87ba0b2babdaf9dac8c189c79'},
 'STRING_ERASURE_REPRO.sv': {'bytes': 28238,
                             'sha256': '1c54c37a095c3f4bb063fc92961c4c75e28fddad5eaf73be4e47212a2633872b'}}

class Cold(unittest.TestCase):
    def test_concat_string_tokens_rejected(self):
        s=fixture()
        for name,(width,(hi,lo)) in ns['TAP_CONCAT_DECLARATIONS'].items():
            original=concat_declaration(name,(width,(hi,lo)))
            expressions=['{"discard_me" '+hi+','+lo+'}', '{'+hi+' "discard_me",'+lo+'}', '{'+hi+',"discard_me" '+lo+'}', '{'+hi+','+lo+' "discard_me"}', '{'+hi+','+lo+'} "discard_me"', '{"'+hi+'",'+lo+'}', '{'+hi+',"'+lo+'"}', '"discard_me" {'+hi+','+lo+'}']
            for expr in expressions:
                replacement='wire ['+str(width-1)+':0] '+name+' = '+expr+';'
                with self.subTest(name=name,expr=expr),self.assertRaisesRegex(ValueError,'fixed tap concat must be two complete identifiers'):
                    qualified(s.replace(original,replacement))
    def test_reserved_concat_names_cannot_be_ansi_ports(self):
        for name,spec in ns['TAP_CONCAT_DECLARATIONS'].items():
            for width in [spec[0],1]:
                for direction in ['input','output']:
                    port=direction+' '+('['+str(width-1)+':0] ' if width>1 else '')+name
                    for body in ['',concat_declaration(name,spec)]:
                        s='module Qwen2ContinuousBlock(input clock, '+port+');'+body+'endmodule'
                        with self.subTest(name=name,width=width,direction=direction,body=bool(body)),self.assertRaisesRegex(ValueError,'canonical tap/concat exposed as port'):
                            ns['parse_modules'](ns['cleaned'](s))
    def test_string_sentinel_comments_and_error_positive(self):
        s='/* outer "quoted" module fake */\n"module fake();\nendmodule" // last "quoted"\n'
        cleaned=ns['cleaned'](s)
        self.assertEqual(cleaned.count('\n'),s.count('\n'));self.assertEqual(cleaned.count('@'),1)
        self.assertNotIn('module',cleaned);self.assertNotIn('quoted',cleaned)
        self.assertEqual(ns['cleaned']('""').strip(),'@')
        source=fixture()
        for name,spec in ns['TAP_CONCAT_DECLARATIONS'].items():
            decl=concat_declaration(name,spec)
            commented=decl.replace(' { ',' { /* "ignored" */ ').replace(' ,\n',' , // "module fake(); endmodule"\n')
            source=source.replace(decl,commented)
        source=source.replace('module Qwen2ContinuousBlock(input clock);','module Qwen2ContinuousBlock(input clock); always @(posedge clock) begin $error("module fake(); endmodule /* \\"quoted\\" */"); end')
        result=qualified(source)
        self.assertEqual(result['observation_leaf_count'],75);self.assertEqual(result['auxiliary_tap_declaration_count'],28)
        self.assertEqual(result['tap_concat_terminal_count'],2);self.assertFalse(result['tap_complete_driver_or_value_proof'])
    def test_exact_reviewer_reproductions_rejected(self):
        pins=REVIEW_REPRO_PINS
        for name,spec in pins.items():
            raw=(HERE/name).read_bytes()
            self.assertEqual(len(raw),spec['bytes']);self.assertEqual(hashlib.sha256(raw).hexdigest(),spec['sha256'])
            expected='fixed tap concat must be two complete identifiers' if name.startswith('STRING') else 'canonical tap/concat exposed as port'
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,expected):qualified(raw.decode('utf-8'))
    def test_auxiliary_exact_inventory_relation_source(self):
        # Independently spell the observed tree, without deriving expected operands from production constants.
        expected={}
        for prefix,bank in [('canonicalCosTap_value','cv'),('canonicalSinTap_value','dv')]:
            for suffix,upper in [('lo_lo_lo',1),('lo_lo_hi',3),('lo_hi_lo',5),('lo_hi_hi',7),('hi_lo_lo',9),('hi_lo_hi',11),('hi_hi_lo',13),('hi_hi_hi',15)]:
                expected[prefix+'_'+suffix]=(64,(bank+'_'+str(upper),bank+'_'+str(upper-1)))
            for suffix in ['lo_lo','lo_hi','hi_lo','hi_hi']:
                expected[prefix+'_'+suffix]=(128,(prefix+'_'+suffix+'_hi',prefix+'_'+suffix+'_lo'))
            for suffix in ['lo','hi']:
                expected[prefix+'_'+suffix]=(256,(prefix+'_'+suffix+'_hi',prefix+'_'+suffix+'_lo'))
        self.assertEqual(ns['AUX_TAPS'],expected)
        self.assertEqual(ns['TAP_CONCAT_ROOTS'],{
            '_canonicalCosTap_value_T':(512,('canonicalCosTap_value_hi','canonicalCosTap_value_lo')),
            '_canonicalSinTap_value_T':(512,('canonicalSinTap_value_hi','canonicalSinTap_value_lo'))})
        r=qualified(fixture())
        self.assertEqual(r['observation_bundles'],9);self.assertEqual(r['observation_leaf_count'],75);self.assertEqual(r['observation_bits'],2604)
        self.assertEqual(r['auxiliary_tap_declaration_count'],28);self.assertEqual(r['auxiliary_tap_declared_bits'],3072)
        self.assertEqual(r['tap_concat_terminal_count'],2)
        self.assertEqual(len(r['tap_concat_declaration_bindings']['Qwen2ContinuousBlock']),30)
        self.assertFalse(r['auxiliary_declared_bits_are_primary_observation_bits']);self.assertFalse(r['tap_complete_driver_or_value_proof'])
    def test_auxiliary_missing_and_wrong_width(self):
        s=fixture()
        for name,spec in ns['AUX_TAPS'].items():
            decl=concat_declaration(name,spec)
            self.assertEqual(s.count(decl),1)
            for bad in [s.replace(decl,''),s.replace(decl,concat_declaration(name,(spec[0]-1,spec[1])))]:
                with self.subTest(name=name),self.assertRaises(ValueError):qualified(bad)
    def test_auxiliary_wrong_module_kind_duplicate(self):
        s=fixture()
        for name,spec in ns['AUX_TAPS'].items():
            decl=concat_declaration(name,spec)
            wrong_module=s.replace(decl,'').replace('module HostBlockCommands(input clock);','module HostBlockCommands(input clock);'+decl)
            for bad in [wrong_module,s.replace(decl,decl.replace('wire ','reg ',1)),s.replace(decl,decl+'\n'+decl)]:
                with self.subTest(name=name),self.assertRaises(ValueError):qualified(bad)
    def test_auxiliary_unknown_names_rejected(self):
        s=fixture();anchor='module Qwen2ContinuousBlock(input clock);'
        for name in ['canonicalCosTap_value_lo_extra','canonicalCosTap_value_hi_hi_unknown','canonicalSinTap_value_lo_lo_lo_extra','canonicalUnknownTap_value_lo','canonicalCosTap_unknown']:
            bad=s.replace(anchor,anchor+'wire [63:0] '+name+' = {cv_1,cv_0};')
            with self.subTest(name=name),self.assertRaises(ValueError):qualified(bad)
    def test_primary_missing_after_auxiliary_classification(self):
        s=fixture()
        for name,width in [('canonicalCosTap_value',512),('canonicalSinTap_value',512),('canonicalScoreTap_valid',1),('canonicalTileTap_value_0',32)]:
            decl='wire '+('['+str(width-1)+':0] ' if width>1 else '')+name+" =\n 1'h0;"
            self.assertEqual(s.count(decl),1)
            with self.subTest(name=name),self.assertRaises(ValueError):qualified(s.replace(decl,''))
    def test_auxiliary_wrong_ordered_connections(self):
        s=fixture()
        for name,spec in ns['AUX_TAPS'].items():
            width,(hi,lo)=spec;decl=concat_declaration(name,spec)
            for pair in [(lo,hi),('wrong_source',lo),(hi,'wrong_source')]:
                bad=s.replace(decl,concat_declaration(name,(width,pair)))
                with self.subTest(name=name,pair=pair),self.assertRaises(ValueError):qualified(bad)
    def test_concat_two_complete_identifiers_only(self):
        for name in ['canonicalCosTap_value_lo_lo_lo','_canonicalSinTap_value_T']:
            width,(hi,lo)=ns['TAP_CONCAT_DECLARATIONS'][name]
            for expr in ['{'+hi[:2]+' '+hi[2:]+','+lo+'}','{'+hi+','+lo+',extra}','{'+hi+'[0],'+lo+'}','{('+hi+'),'+lo+'}','{'+hi+'+other,'+lo+'}','{{'+hi+'},'+lo+'}',"'{"+hi+','+lo+'}','{2{'+hi+','+lo+'}}','{'+hi+','+lo+'} ? x : y']:
                body='wire ['+str(width-1)+':0] '+name+' = '+expr+';'
                with self.subTest(name=name,expr=expr),self.assertRaises(ValueError):ns['parse_body'](body,set(),module_name='Qwen2ContinuousBlock')
            valid='wire ['+str(width-1)+':0] '+name+' = \n {\t'+hi+'  ,\n'+lo+'  } ;'
            r=ns['parse_body'](valid,set(),module_name='Qwen2ContinuousBlock')
            self.assertEqual(r['tap_concat_bindings'],{name:(width,(hi,lo))})
    def test_terminal_concat_root_fail_closed(self):
        s=fixture()
        for name,spec in ns['TAP_CONCAT_ROOTS'].items():
            width,(hi,lo)=spec;decl=concat_declaration(name,spec)
            wrong_module=s.replace(decl,'').replace('module HostBlockCommands(input clock);','module HostBlockCommands(input clock);'+decl)
            for bad in [s.replace(decl,''),s.replace(decl,concat_declaration(name,(511,(hi,lo)))),s.replace(decl,concat_declaration(name,(width,(lo,hi)))),s.replace(decl,decl.replace('wire ','reg ',1)),s.replace(decl,decl+'\n'+decl),wrong_module,s.replace(decl,decl+"\nwire [31:0][7:0] "+name+" = 0;")]:
                with self.subTest(name=name),self.assertRaises(ValueError):qualified(bad)
    def test_top_level_declarator_comma_rejected(self):
        invalid=["wire [31:0][7:0] x = 1'b0, canonicalExtraTap_valid = 1'b1;", "wire x = 1'b0, canonicalExtraTap_valid = 1'b1;", "reg [3:0] x = 0, y = 1;", "wire [31:0] canonicalScoreTap_value = 0, canonicalExtraTap_valid = 1;", "wire x = f(a,b), canonicalExtraTap_valid = 1;", "wire x = {a,b}, canonicalExtraTap_valid = 1;", "wire [31:0][7:0] x = '{a,b}, y = 0;"]
        for body in invalid:
            with self.subTest(body=body),self.assertRaises(ValueError):ns['parse_body'](body,set(),module_name='HostBlockCommands')
    def test_nested_initializer_commas_preserved(self):
        valid=["wire x = f(a,b);", "wire x = {a,b};", "reg [7:0] x = f({a,b},g(c,d));", "wire [31:0][7:0] x = '{a,b};", "wire [3:0][23:0] x = {{a,b},{c,d}};", "wire canonicalPvAckTap_valid = f(a,b);"]
        for body in valid:
            with self.subTest(body=body):
                row=ns['parse_body'](body,set(),module_name='HostBlockCommands')
                self.assertEqual(row['edges'],[])
        row=ns['parse_body']("wire canonicalPvAckTap_valid = f(a,b);",set())
        self.assertEqual(row['taps'],{'canonicalPvAckTap_valid':1})
        self.assertEqual(ns['parse_body']("assign x = f(a,b), y = g(c,d);",set())['edges'],[])
    def test_observed_double_packed_wire_shapes(self):
        self.assertEqual(len(ns['DOUBLE_PACKED_WIRE_SHAPES']),17)
        for hi,lo in ns['DOUBLE_PACKED_WIRE_SHAPES']:
            body="wire [%d:0][%d:0] _GEN =\n '{1'h0, 1'h1};" % (hi,lo)
            row=ns['parse_body'](body,set(),module_name='HostBlockCommands')
            self.assertEqual(row['edges'],[]);self.assertEqual(row['taps'],{})
        row=ns['parse_body']("wire [3:0][23:0] _GEN_12 = {{roots_0}, {roots_2}, {roots_1}, {roots_0}};",set(),module_name='HostBlockCommands')
        self.assertEqual(row['taps'],{})
    def test_double_packed_shape_fail_closed(self):
        invalid=["reg [31:0][7:0] x = 0;", "wire signed [31:0][7:0] x = 0;", "wire [31:0][7:0][1:0] x = 0;", "wire [31:0][7:1] x = 0;", "wire [N:0][7:0] x = 0;", "wire [31:0][N:0] x = 0;", "wire [31:0][7:0] x;", "wire [31:0][7:0] x[0:1] = 0;", "wire [31:0][7:0] x,y = 0;", "wire [31:0][31:0] x = 0;", "wire [31:0][7:0] canonicalExtraTap_valid = 0;", "wire [31:0][7:0] canonicalScoreTap_value = 0;"]
        for body in invalid:
            with self.subTest(body=body),self.assertRaises(ValueError):ns['parse_body'](body,set(),module_name='HostBlockCommands')
    def test_double_packed_module_scope(self):
        body="wire [31:0][7:0] x = 0;"
        for module in [None,'HostBlockTop','HostBlockCollection','HeteroBF16FmaPre','Unknown']:
            with self.subTest(module=module),self.assertRaises(ValueError):ns['parse_body'](body,set(),module_name=module)
        self.assertEqual(len(ns['DOUBLE_PACKED_WIRE_MODULES']),9)
    def test_double_packed_tiny_contract(self):
        s=fixture().replace('module HostBlockCommands(input clock);', "module HostBlockCommands(input clock); wire [31:0][7:0] _GEN = '{8'h32, 8'h30};")
        row=ns['qualify'](ns['parse_modules'](ns['cleaned'](s)))
        self.assertEqual(row['observation_leaf_count'],75);self.assertEqual(row['observation_bits'],2604)
        self.assertEqual(row['host_port_count'],83);self.assertFalse(row['numerical_qualification'])
    def test_ansi_grouped(self):
        self.assertEqual(ns['ports']('input clock, reset, input [63:0] a, b, output [7:0] c, d, output e'),{'clock':['input',1],'reset':['input',1],'a':['input',64],'b':['input',64],'c':['output',8],'d':['output',8],'e':['output',1]})
    def test_ansi_negative(self):
        for s in ['clock','input clock,clock','input [7:1] x','input clock,','input [W:0] x','inout x','input clock; output x','input clock,,reset']:
            with self.subTest(s=s),self.assertRaises(ValueError): ns['ports'](s)
    def test_complete_tiny_contract(self):
        r=ns['qualify'](ns['parse_modules'](ns['cleaned'](fixture())))
        self.assertEqual(r['definition_count'],59);self.assertEqual(r['host_port_count'],83)
        self.assertEqual(r['observation_bits'],2604);self.assertEqual(r['observation_leaf_count'],75)
        self.assertEqual(r['external_counts'],{'qwen2_matrix_command_endpoint':8,'tc_clk_gating':8,'idma_backend_rw_axi_flat_wrap':1})
        self.assertFalse(r['numerical_qualification']);self.assertTrue(r['dpi_provider_source_and_function_mapping'].startswith('PENDING'))
    def test_bad_contract_mutations(self):
        s=fixture()
        mutations=[s.replace('input clock,','input wrong_clock,',1),s.replace('qwen2_matrix_command_endpoint #','unknown_endpoint #',1),s.replace('ENABLE_ACCUMULATOR_SEED(1)','ENABLE_ACCUMULATOR_SEED(0)',1),s.replace('.seed_abort_i(','.wrong_seed_abort_i(',1),s.replace('wire [31:0] canonicalTileTap_value_0','wire [30:0] canonicalTileTap_value_0',1),s.replace('wire [31:0] canonicalTileTap_value_0','reg [31:0] canonicalTileTap_value_0',1),s.replace('HostBlockTop top(','HostBlockTop wrong_top(',1),s+'\nmodule extra(input clock);endmodule']
        for i,bad in enumerate(mutations):
            with self.subTest(i=i),self.assertRaises(ValueError): ns['qualify'](ns['parse_modules'](ns['cleaned'](bad)))
    def test_exact_host_and_tap_mutations(self):
        s=fixture();start=s.index('module HostBlockTop(');end=s.index(');',start)
        header=s[start:end]
        for changed in [header.replace('io_launch_bits_commands','wrong_commands'),header.replace('input [15:0] io_launch_bits_commands','input [14:0] io_launch_bits_commands'),header+', input extra_port']:
            bad=s[:start]+changed+s[end:]
            with self.assertRaises(ValueError):ns['qualify'](ns['parse_modules'](ns['cleaned'](bad)))
        for bad in [s.replace('canonicalPvAckTap_valid','canonicalPvAckTap_wrong'),s.replace('wire canonicalPvAckTap_valid', 'wire canonicalExtraTap_valid = 1; wire canonicalPvAckTap_valid'),s.replace('leaves_7(', 'leaves_0(')]:
            with self.assertRaises(ValueError):ns['qualify'](ns['parse_modules'](ns['cleaned'](bad)))
    def test_external_cardinality_and_orphan(self):
        import re
        s=fixture()
        for typ,inst in [('qwen2_matrix_command_endpoint','leaves_7'),('tc_clk_gating','gate_7'),('idma_backend_rw_axi_flat_wrap','backend')]:
            bad=re.sub(re.escape(typ)+r'(?: #\([^\n]*?\))? '+inst+r'\([^;]*;', '', s, count=1)
            self.assertNotEqual(bad,s)
            with self.assertRaises(ValueError):ns['qualify'](ns['parse_modules'](ns['cleaned'](bad)))
        bad=s.replace('ScheduledSiluOwner silu(', 'ScheduledSiluOwner missing_silu(')
        with self.assertRaises(ValueError):ns['qualify'](ns['parse_modules'](ns['cleaned'](bad)))
    def test_opaque_observed_statements(self):
        body="wire [3:0] x = {a,b}; reg [7:0] mem[0:15]; assign x = y; always @(posedge clock) begin if (r) begin x <= y; end else x <= z; end `ifndef SYNTHESIS\n always @(posedge clock) begin if (`STOP_COND_) $fatal; end\n `endif\n"
        self.assertEqual(ns['parse_body'](body,set())['edges'],[])
    def test_unknown_and_conditional_instances(self):
        for body in ['Unknown u(.clock(clock));','if (1) Known u(.clock(clock));','generate Known u(.clock(clock)); endgenerate','`ifndef SYNTHESIS\nKnown u(.clock(clock));\n`endif','wire x, canonicalExtraTap_valid;','bind Known x();','always @(*) x = y;','Known u(1);','Known u(.clock(a),.clock(b));','Known u(.clock(a)),v(.clock(b));','wire [7:1] x;','wire x = (y;']:
            with self.subTest(body=body),self.assertRaises(ValueError):ns['parse_body'](body,{'Known'})
    def test_comments_strings_and_unclosed(self):
        x='module X(input clock); // module bad();\n always @(posedge clock) begin $error("module fake(); endmodule"); end endmodule'
        self.assertEqual(set(ns['parse_modules'](ns['cleaned'](x))),{'X'})
        for bad in ['module X(input clock);','module X(input clock);endmodule trailing','module X(input clock);endmodule module X(input clock);endmodule','module X(input clock); module Y(input clock);endmodule endmodule','module X(input clock); /* unclosed endmodule']:
            with self.subTest(bad=bad),self.assertRaises(ValueError):ns['parse_modules'](ns['cleaned'](bad))
    def test_graph_cycle(self):
        with self.assertRaises(ValueError):ns['walk']({'X':{'edges':[('u','X')]}},'X')
    def test_fixed_bytes_entrypoint(self):
        for raw in [b'',b'module HostBlockTop(input clock);endmodule','x',bytearray(b'x')]:
            with self.assertRaises(ValueError):ns['check_bytes'](raw)
    def test_source_boundaries(self):
        self.assertEqual(ns['MAX_BYTES'],128*1024*1024);self.assertEqual(ns['MAX_DEFINITIONS'],768);self.assertEqual(ns['MAX_PATHS'],20000)
        self.assertNotIn('open(', (HERE/'check_host_sv.py').read_text());self.assertNotIn('importlib',(HERE/'check_host_sv.py').read_text())

if __name__=='__main__':unittest.main()

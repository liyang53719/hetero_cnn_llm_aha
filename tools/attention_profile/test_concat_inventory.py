# SPDX-License-Identifier: Apache-2.0
"""Pure synthetic generated-source checks; no EDA, compiler or model data."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('concat_inventory', HERE / 'concat_inventory.py')
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)

SOURCE = r'''
// VL_CONCAT_WWI(999, 999, 0, fake, fake, fake)
const char* note = R"mark(VL_CONCAT_WWI(888, 888, 0, fake, fake, fake))mark";
void before();
VL_INLINE_OPT void VHostBlockTop___024root___nba_comb__TOP__282(
    VHostBlockTop___024root* vlSelf) {
    if (vlSelf->HostBlockTop__DOT__owner__DOT__gqa__DOT__state == 7U) {
        VL_CONCAT_WWI(8192, 8160U, 0x20U,
            __Vtemp_1, vlSelf->HostBlockTop__DOT__owner__DOT__gqa__DOT__incomingRows_0,
            pick(vlSelf->x[3], 9U));
    }
    VL_CONCAT_WWI(96, 64, 32, __Vtemp_2,
        VL_CONCAT_WWI(128, 96, 32, __Vtemp_3, left, right), right);
}
void second() {
    const char* s = "escaped \\\" VL_CONCAT_WWI(0,0,0,0,0,0)";
    VL_CONCAT_WWI(WIDTH, 32 + 32, (32), dst, left, right);
}
'''


class ParserTests(unittest.TestCase):
    def test_nested_multiline_calls_with_exact_functions_and_widths(self):
        calls, receipt = inventory.parse_source(SOURCE, 'obj/generated.cpp')
        self.assertEqual(len(calls), 4)
        self.assertFalse(receipt['lexical_errors'])
        self.assertFalse(receipt['delimiter_errors'])
        self.assertFalse(receipt['call_limit_reached'])
        first = calls[0]
        self.assertEqual(first['function']['name'], 'VHostBlockTop___024root___nba_comb__TOP__282')
        self.assertEqual(first['width_constants'], {'obits': 8192, 'lbits': 8160, 'rbits': 32})
        self.assertEqual(first['output_words_32'], 256)
        self.assertEqual(len(first['parameters']), 6)
        self.assertEqual(first['parameters'][5]['text'], 'pick(vlSelf->x[3], 9U)')
        self.assertGreater(first['line_end'], first['line_start'])
        self.assertIn('HostBlockTop__DOT__owner__DOT__gqa__DOT__incomingRows_0', first['signal_identifiers'])
        self.assertEqual(first['temporary_identifiers'], ['__Vtemp_1'])
        self.assertTrue(any('state == 7U' in row['text'] for row in first['nearby_condition_evidence']))
        self.assertEqual(calls[1]['width_constants']['obits'], 96)
        self.assertEqual(calls[2]['width_constants']['obits'], 128)
        self.assertEqual(calls[3]['function']['name'], 'second')
        self.assertEqual(calls[3]['width_constants'], {'obits': None, 'lbits': None, 'rbits': 32})
        self.assertIsNone(calls[3]['output_words_32'])

    def test_declarations_and_literals_are_not_calls(self):
        source = r'''
static inline WDataOutP VL_CONCAT_WWI(int o, int l, int r, WDataOutP d, WDataInP p, IData x) {
    return d;
}
WDataOutP VL_CONCAT_WWI(int, int, int, WDataOutP, WDataInP, IData);
void run() { /* VL_CONCAT_WWI(1, 2, 3, d, p, x); */
    char x = '\''; VL_CONCAT_WWI(96, 64, 32, d, p, x);
}
'''
        calls, receipt = inventory.parse_source(source, 'a.cpp')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['function']['name'], 'run')
        self.assertFalse(receipt['lexical_errors'])

    def test_unknown_syntax_and_bounds_are_explicit(self):
        source = 'void f() { VL_CONCAT_WWI(96, 64, 32, d, f<A, B>(x), r); }\n'
        calls, _ = inventory.parse_source(source, 'a.cpp')
        self.assertNotEqual(calls[0]['parse_status'], 'parsed')
        self.assertTrue(all(p['integer_constant'] is None for p in calls[0]['parameters']))
        self.assertIsNone(calls[0]['output_words_32'])
        broken, receipt = inventory.parse_source('void f() { VL_CONCAT_WWI(96, 64,', 'a.cpp')
        self.assertEqual(broken[0]['parse_status'], 'unmatched_call_parenthesis')
        self.assertIsNone(broken[0]['function'])
        self.assertTrue(receipt['delimiter_errors'])
        calls, receipt = inventory.parse_source(SOURCE, 'a.cpp', limit=1)
        self.assertEqual(len(calls), 1)
        self.assertTrue(receipt['call_limit_reached'])

    def test_no_preceding_function_guess_and_no_literal_eval(self):
        calls, _ = inventory.parse_source('void f() {}\nVL_CONCAT_WWI(0x60U, 0100, (32), d, p, x);', 'a.cpp')
        self.assertIsNone(calls[0]['function'])
        self.assertEqual(calls[0]['width_constants'], {'obits': 96, 'lbits': 64, 'rbits': 32})
        for value in ('32 + 32', 'sizeof(x)', 'f()', '(1)+(2)', '08', '-1'):
            self.assertIsNone(inventory.literal_int(value), value)
        self.assertIsNone(inventory.literal_int('9' * 5000))

    def test_else_if_and_return_calls_keep_real_function(self):
        source = '''
WDataOutP actual() {
    if (a) { x = 0; }
    else if (b) {
        VL_CONCAT_WWI(96, 64, 32, d, p, r);
    }
    VL_CONCAT_WWI(96, 64, 32, d, p, r);
    return VL_CONCAT_WWI(96, 64, 32, d, p, r);
}
'''
        calls, receipt = inventory.parse_source(source, 'a.cpp')
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(call['function']['name'] == 'actual' for call in calls))
        self.assertEqual(receipt['recognized_functions'], 1)


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='concat-evidence-')
        self.root = Path(self.tmp.name)
        self.build = self.root / 'build'
        (self.build / 'obj').mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative, contents):
        path = self.build / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        return path

    def test_manifest_source_cap_priority_and_runtime_header(self):
        a = self.write(inventory.PRIORITY_CPP[0], SOURCE)
        b = self.write(inventory.PRIORITY_CPP[1], 'void b() {}\n')
        self.write('obj/VHostBlockTop___024root.h', 'struct Root { unsigned state; };\n')
        runtime = self.root / 'runtime'
        (runtime / 'include').mkdir(parents=True)
        helper = runtime / 'include/verilated_funcs.h'
        helper.write_text('static inline void helper() {}\n')
        self.write('obj/VHostBlockTop.mk', f'VERILATOR_ROOT = {runtime}\n')
        original_sv = self.write('generated/HostBlockTop.sv', 'module HostBlockTop; wire [8191:0] incomingRows_0; endmodule\n')
        self.write('fixture/model.npz', 'private model payload must not be read or copied')
        out = self.root / 'evidence'
        result = inventory.collect(self.build, out)
        self.assertEqual(result['cpp_files_hashed'], 2)
        self.assertEqual(result['calls'], 4)
        self.assertEqual(result['unresolved_calls'], 0)
        self.assertFalse(result['truncated'])
        self.assertTrue(result['required_source_complete'])
        self.assertEqual(result['original_sv']['sha256'], hashlib.sha256(original_sv.read_bytes()).hexdigest())
        self.assertEqual((out / 'source/generated/HostBlockTop.sv').read_bytes(), original_sv.read_bytes())
        manifest = json.loads((out / 'cpp_manifest.json').read_text())
        self.assertEqual({x['sha256'] for x in manifest}, {hashlib.sha256(p.read_bytes()).hexdigest() for p in (a, b)})
        copied = list((out / 'source').rglob('*'))
        self.assertFalse(any(x.suffix == '.npz' for x in copied))
        self.assertEqual((out / 'source' / inventory.PRIORITY_CPP[0]).read_bytes(), a.read_bytes())
        self.assertEqual((out / 'source/runtime_0/verilated_funcs.h').read_bytes(), helper.read_bytes())
        self.assertLessEqual(result['selected_source_bytes'], inventory.MAX_SOURCE_BYTES)
        with self.assertRaises(ValueError):
            inventory.collect(self.build, out)

    def test_file_scan_and_source_budgets_and_symlinks(self):
        a = self.write(inventory.PRIORITY_CPP[0], 'void f() { VL_CONCAT_WWI(96, 64, 32, d, p, r); }\n')
        self.write(inventory.PRIORITY_CPP[1], SOURCE)
        outside = self.root / 'untrusted.cpp'
        outside.write_text(SOURCE)
        (self.build / 'obj/escape.cpp').symlink_to(outside)
        out = self.root / 'capped'
        with mock.patch.object(inventory, 'MAX_SCAN_BYTES', a.stat().st_size), mock.patch.object(inventory, 'MAX_SOURCE_BYTES', a.stat().st_size):
            result = inventory.collect(self.build, out)
        self.assertTrue(result['truncated'])
        self.assertEqual(result['cpp_files_hashed'], 1)
        self.assertEqual(result['selected_source_bytes'], a.stat().st_size)
        self.assertTrue(any(x['reason'] == 'source_byte_budget' for x in result['selection_skipped']))
        scan = json.loads((out / 'scan_receipt.json').read_text())
        self.assertTrue(any(x['reason'] == 'symlink_or_outside_obj' for x in scan['skipped']))
        self.assertFalse((out / 'source/obj/escape.cpp').exists())
        self.assertFalse(result['required_source_complete'])

    def test_oversized_sv_is_hashed_but_not_truncated_or_copied(self):
        self.write('obj/a.cpp', 'void f() {}\n')
        sv = self.write('generated/HostBlockTop.sv', 'module HostBlockTop;\n' + 'wire x;\n' * 100 + 'endmodule\n')
        out = self.root / 'sv-capped'
        with mock.patch.object(inventory, 'MAX_SOURCE_BYTES', 100):
            result = inventory.collect(self.build, out)
        self.assertEqual(result['original_sv']['sha256'], hashlib.sha256(sv.read_bytes()).hexdigest())
        self.assertFalse((out / 'source/generated/HostBlockTop.sv').exists())
        self.assertTrue(any(x['file'] == 'generated/HostBlockTop.sv' and x['reason'] == 'source_byte_budget' for x in result['selection_skipped']))

    def test_long_context_and_parameter_truncation_are_counted(self):
        self.write('obj/a.cpp', 'void f() { VL_CONCAT_WWI(96, 64, 32, d, ' + 'x' * 17000 + ', r); }')
        out = self.root / 'long'
        result = inventory.collect(self.build, out)
        self.assertEqual(result['parameter_or_context_truncation_count'], 1)
        calls = json.loads((out / 'calls.json').read_text())
        self.assertTrue(calls[0]['parameters'][4]['truncated'])
        self.assertTrue(calls[0]['nearby_source']['truncated'])

    def test_nonfiles_nontext_and_runtime_payload_symlink_are_not_copied(self):
        path = self.write(inventory.PRIORITY_CPP[0], '')
        path.write_bytes(b'\xff\x00')
        (self.build / 'obj/bad.cpp').mkdir()
        runtime = self.root / 'runtime'
        (runtime / 'include').mkdir(parents=True)
        payload = self.root / 'fixture_model.npz'
        payload.write_bytes(b'UNAUTHORIZED_FIXTURE_CONTENT')
        (runtime / 'include/verilated_funcs.h').symlink_to(payload)
        self.write('obj/VHostBlockTop.mk', f'VERILATOR_ROOT = {runtime}\n')
        out = self.root / 'invalid-source'
        result = inventory.collect(self.build, out)
        self.assertTrue(result['truncated'])
        self.assertFalse(result['required_source_complete'])
        self.assertFalse(any(p.is_file() and b'UNAUTHORIZED_FIXTURE_CONTENT' in p.read_bytes() for p in out.rglob('*')))
        self.assertTrue(any(x['reason'] == 'not_utf8' for x in result['selection_skipped']))

    def test_single_file_and_text_evidence_budgets_are_explicit(self):
        path = self.write('obj/a.cpp', SOURCE)
        out = self.root / 'file-limit'
        with mock.patch.object(inventory, 'MAX_FILE_BYTES', 10):
            result = inventory.collect(self.build, out)
        self.assertTrue(result['truncated'])
        self.assertEqual(result['cpp_files_hashed'], 1)
        self.assertEqual(result['cpp_bytes_hashed'], path.stat().st_size)
        self.assertEqual(result['cpp_bytes_scanned'], 0)
        scan = json.loads((out / 'scan_receipt.json').read_text())
        self.assertEqual(scan['skipped'][0]['reason'], 'single_file_parse_budget')
        calls, receipt = inventory.parse_source(SOURCE, 'a.cpp', evidence_budget=[5])
        self.assertEqual(len(calls), 4)
        self.assertTrue(receipt['text_evidence_budget_exhausted'])
        self.assertTrue(calls[-1]['parameters'][0]['truncated'])


if __name__ == '__main__':
    unittest.main()

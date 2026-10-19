"""Tiny Python-only fixtures; no native generation, C++, network, or real RTL."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Use -I -S -B')
import ast
import builtins
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).absolute().parent

LOAD_PINS = {
    str(HERE / 'generation_diagnostics.py'): (51843, 'fb1b7bf9a747d02827233a820975231c151788f6aff2b54c8f7a7e589e5c0bf7'),
    str(HERE.parent / 'safe_build_diagnostics.py'): (11942, '97ab72651c9acadf1e4d242225bdfc21dea3807aa911e448ce7330b762fa4a60'),
}


def load(path):
    expected = LOAD_PINS.get(str(path))
    if expected is None:
        raise ValueError('unfixed source before compile')
    raw = path.read_bytes()
    if type(raw) is not bytes or len(raw) != expected[0] or hashlib.sha256(raw).hexdigest() != expected[1]:
        raise ValueError('source identity before compile')
    module = types.ModuleType(path.stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module

g = load(HERE / 'generation_diagnostics.py')
s = load(HERE.parent / 'safe_build_diagnostics.py')
LEAF = 'qwen2_matrix_command_endpoint_cold'
SOURCE = '/private/source/HostBlockCollection.sv'
MAP = [{'path': SOURCE, 'id': 'host/HostBlockCollection.sv', 'bytes': 7, 'sha256': 'a' * 64}]

def fixture(root, leaf=LEAF):
    obj = root / 'obj'
    obj.mkdir(exist_ok=True)
    args = obj / ('V' + leaf + '__hierMkArgs.f')
    args.write_text('--lib-create ' + leaf + ' --hierarchical-child 1 --top-module-encoded ' + leaf + ' -GENABLE_ACCUMULATOR_SEED=1\n')
    folder = obj / ('V' + leaf)
    folder.mkdir(exist_ok=True)
    wrapper = folder / (leaf + '.sv')
    wrapper.write_text('''// always_comb and import "DPI-C" in a comment do not count.
module ''' + leaf + ''' (
  input logic seed_begin_valid_i,
  output logic seed_begin_ready_o,
  input logic seed_commit_valid_i,
  output logic seed_commit_ready_o
);
import "DPI-C" function longint ''' + leaf + '''_protectlib_combo_update(
 chandle handle__V,
 input logic seed_begin_valid_i,
 output logic seed_begin_ready_o,
 input logic seed_commit_valid_i,
 output logic seed_commit_ready_o
);
chandle handle__V;
always_comb begin
 last_combo_seqnum__V = ''' + leaf + '''_protectlib_combo_update(
 handle__V, seed_begin_valid_i, seed_begin_ready_o_combo__V,
 seed_commit_valid_i, seed_commit_ready_o_combo__V);
end
always_comb begin
 seed_begin_ready_o = seed_begin_ready_o_combo__V;
 seed_commit_ready_o = seed_commit_ready_o_combo__V;
end
endmodule
''')
    (obj / 'VHostBlockTop__hierMkArgs.f').write_text('V' + leaf + '/' + leaf + '.sv /private/HostBlockCollection.sv\n')
    return args, wrapper


CLUSTER = 'bf16_context_lane_cluster16_rev8b_b_candidate'


def cluster_fixture(root, leaf=CLUSTER + '_cold', handles=256, libraries=None):
    args, wrapper = fixture(root, leaf)
    raw = wrapper.read_text()
    for a, b in (('seed_begin_valid_i', 'seed_block_i'), ('seed_begin_ready_o', 'lane_out_o'),
                 ('seed_commit_valid_i', 'seed_commit_i'), ('seed_commit_ready_o', 'cluster_flags_o')):
        raw = raw.replace(a, b)
    wrapper.write_text(raw)
    if libraries is None:
        libraries = [leaf]
    graph = '# Hierarchical Verilation -*- Makefile -*-\nifndef VM_HIER_VERILATION_INCLUDED\nVM_HIER_VERILATION_INCLUDED = 1\n\nVM_HIER_LIBS := \\\n'
    for name in libraries:
        graph += '  V' + name + '/lib' + name + '.a \\\n'
    graph += '\n'
    for name in libraries:
        child = 'V' + name
        graph += (child + '/lib' + name + '.a: ' + child + '/' + child + '.mk \n'
                  '\t$(MAKE) -f ' + child + '.mk -C ' + child + ' VM_PREFIX=' + child + '\n\n')
    graph += 'endif  # Guard\n'
    mk = root / 'obj/VHostBlockTop_hier.mk'
    mk.write_text(graph)
    header = root / 'obj/VHostBlockTop___024root.h'
    text = 'class VHostBlockTop___024root final : public VerilatedModule {\npublic:\n'
    for i in range(handles):
        text += ('    void* HostBlockTop__DOT__owner__DOT__matrix__DOT__leaves_' + str(i // 32) +
                 '__DOT__matrix__DOT__g_production__DOT__g_cluster__BRA__' + str(i % 32) +
                 '__KET____DOT__u_cluster__DOT__handle___05FV;\n')
    header.write_text(text + '};\n')
    return args, wrapper, mk, header


class Cold(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.log = self.root / 'native.log'
        self.log.write_bytes(b'')

    def collect(self, raw=None, **kwargs):
        if raw is not None:
            self.log.write_bytes(raw)
        return g.collect(self.log, self.root, kwargs.get('source_map', MAP), kwargs.get('sanitizer', s))

    def collect_header_reads(self, header, outcomes):
        original, calls, pending = g._read, [], iter(outcomes)
        def observed(path, cap):
            if path == header:
                calls.append(cap)
                outcome = next(pending)
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome
            return original(path, cap)
        with mock.patch.object(g, '_read', side_effect=observed):
            result = self.collect()
        return result, calls

    def warning(self, number=1, rule='UNOPTFLAT', source=SOURCE):
        return ('%Warning-' + rule + ': ' + source + ':' + str(number) + ':16: Signal unoptimizable: Circular combinational logic: \'private_signal\'\n').encode()

    def test_01_no_native_network_asserts(self):
        nodes = list(ast.walk(ast.parse((HERE / 'generation_diagnostics.py').read_text())))
        imports = {a.name for n in nodes if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        self.assertFalse(imports & {'subprocess', 'socket', 'requests', 'urllib'})
        self.assertFalse(any(isinstance(n, ast.Assert) for n in nodes))

    def test_02_empty_and_missing(self):
        self.assertEqual(g.validate_report(g.empty_report())['state'], 'NOT_COLLECTED')
        self.log.unlink()
        result = self.collect()
        self.assertEqual(result['state'], 'READ_ERROR')
        self.assertEqual(result['wrapper']['state'], 'MISSING')

    def test_03_entire_log_all_35_before_long_examples(self):
        raw = b''.join(self.warning(n) + ((' ' * 12 + SOURCE + ':4:2: Example path: secret/internal.sv\n').encode() * 20) for n in range(1, 36))
        raw += b'%Error: Exiting due to 35 warning(s)\n'
        result = self.collect(raw)
        self.assertEqual(result['state'], 'AVAILABLE')
        self.assertEqual(result['counts']['warning_headers'], 35)
        self.assertEqual(result['counts']['error_headers'], 1)
        self.assertEqual(len(result['records']), 36)
        self.assertEqual(result['by_rule']['WARNING:UNOPTFLAT'], 35)
        self.assertEqual(result['fatal_summaries']['header_count_comparison'], 'GLOBAL_HEADERS_MATCH')
        self.assertEqual(result['fatal_summaries']['process_attribution'], 'NOT_AVAILABLE')
        self.assertEqual(result['omission']['records'], 0)
        self.assertEqual(result['omission']['examples'], 684)
        self.assertTrue(result['caps']['partial'])
        self.assertEqual(result['log_identity']['sha256'], hashlib.sha256(raw).hexdigest())
        text = g.canonical_json(result)
        self.assertNotIn(b'private', text)
        self.assertNotIn(b'internal.sv', text)
        self.assertLessEqual(len(text), 65536)

    def test_04_exact_source_only_never_open_log_paths(self):
        raw = self.warning() + self.warning(2, source='/private/source/../source/HostBlockCollection.sv')
        raw += self.warning(3, source='host/HostBlockCollection.sv') + self.warning(4, source='/secret/token.txt')
        observed = []
        original = g._read
        def track(path, cap):
            observed.append(str(path))
            return original(path, cap)
        with mock.patch.object(g, '_read', side_effect=track):
            result = self.collect(raw)
        self.assertEqual(observed, [str(self.log)])
        self.assertEqual(result['records'][0]['source_id'], MAP[0]['id'])
        self.assertEqual(result['records'][0]['source_sha256'], MAP[0]['sha256'])
        self.assertEqual([r['source_id'] for r in result['records'][1:]], ['UNKNOWN_PATH'] * 3)

    def test_05_unknown_rule_controls_credentials(self):
        raw = b'%Warning-secret_password: /secret/private.sv:2:4: token=supersecret Authorization: Bearer abc123\x1b\x00\n'
        raw += b'%Error-NEWUNKNOWN: /secret/xxx.sv:5:1: credential=confidential file private.sv\n'
        result = self.collect(raw)
        text = g.canonical_json(result)
        for forbidden in (b'supersecret', b'abc123', b'confidential', b'private.sv', b'xxx.sv', b'secret_password'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(result['by_rule'], {'WARNING:UNKNOWN': 1, 'ERROR:UNKNOWN': 1})
        self.assertTrue(all(32 <= ord(c) <= 126 for r in result['records'] for c in r['message']))

    def test_06_multiple_fatal_summaries_not_one_process(self):
        result = self.collect(self.warning() + b'%Error: Exiting due to 1 warning(s)\n%Error: Exiting due to 2 warning(s)\n')
        self.assertIsNone(result['fatal_summaries']['warning_total'])
        self.assertIsNone(result['fatal_summaries']['error_total'])
        self.assertEqual(result['fatal_summaries']['header_count_comparison'], 'NOT_AVAILABLE')
        self.assertEqual(result['counts']['fatal_summary_headers'], 2)
        result = self.collect(b'%Error: Exiting due to 1 warning(s)\n%Error: Exiting due to 2 error(s)\n%Error: Exiting due to 3 warning(s)\n')
        self.assertEqual(result['counts']['fatal_summary_headers'], 3)
        self.assertIsNone(result['fatal_summaries']['warning_total'])
        self.assertIsNone(result['fatal_summaries']['error_total'])
        self.assertEqual(result['fatal_summaries']['header_count_comparison'], 'NOT_AVAILABLE')

    def test_07_error_fatal_and_mismatch(self):
        result = self.collect(b'%Error-UNSUPPORTED: /bad:1:1: unsupported\n%Error: Exiting due to 1 error(s)\n')
        self.assertEqual(result['fatal_summaries']['error_total'], 1)
        self.assertEqual(result['fatal_summaries']['header_count_comparison'], 'GLOBAL_HEADERS_MATCH')
        result = self.collect(self.warning() + b'%Error: Exiting due to 35 warning(s)\n')
        self.assertEqual(result['fatal_summaries']['header_count_comparison'], 'GLOBAL_HEADERS_DIFFER')

    def test_08_records_and_examples_cap(self):
        result = self.collect(b''.join(self.warning(n) for n in range(1, 181)))
        self.assertEqual(result['counts']['warning_headers'], 180)
        self.assertEqual(len(result['records']), 128)
        self.assertEqual(result['omission']['records'], 52)
        self.assertTrue(result['caps']['record_cap'])
        self.assertTrue(result['caps']['partial'])

    def test_09_report_byte_budget(self):
        mapping = [dict(MAP[0], id='host/' + 'a' * 235)]
        with mock.patch.object(g, 'MAX_REPORT_BYTES', 16 * 1024):
            result = self.collect(b''.join(self.warning(n) for n in range(1, 129)), source_map=mapping)
        self.assertLessEqual(len(g.canonical_json(result)), g.MAX_REPORT_BYTES)
        self.assertTrue(result['caps']['report_byte_cap'])
        self.assertTrue(result['omission']['records'])
        result35 = self.collect(b''.join(self.warning(n) for n in range(1, 36)), source_map=mapping)
        self.assertEqual(len(result35['records']), 35)
        self.assertEqual(result35['omission']['records'], 0)

    def test_10_unparsed_header_and_coordinate_bounds(self):
        raw = b'%Warning not fixed syntax\n%Error-bad no colon\n'
        raw += b'%Warning-LATCH: /private/source/HostBlockCollection.sv:0:4: bad\n'
        raw += b'%Error: /private/source/HostBlockCollection.sv:10000000:4: bad\n'
        result = self.collect(raw)
        self.assertEqual(result['counts']['unparsed_headers'], 2)
        self.assertTrue(result['caps']['partial'])
        self.assertTrue(all(r['line'] is None for r in result['records']))

    def test_11_log_symlink_fifo_directory_and_oversize(self):
        real = self.root / 'real'
        real.write_bytes(self.warning())
        self.log.unlink()
        self.log.symlink_to(real)
        self.assertEqual(self.collect()['state'], 'READ_ERROR')
        self.log.unlink()
        os.mkfifo(self.log)
        self.assertEqual(self.collect()['state'], 'READ_ERROR')
        self.log.unlink()
        self.log.mkdir()
        self.assertEqual(self.collect()['state'], 'READ_ERROR')
        self.log.rmdir()
        with self.log.open('wb') as stream:
            stream.truncate(g.MAX_LOG_BYTES + 1)
        self.assertEqual(self.collect()['state'], 'READ_ERROR')

    def test_12_sanitizer_failure_preserves_finite_census(self):
        bad = types.SimpleNamespace(sanitize_build_context=mock.Mock(side_effect=RuntimeError('/secret')))
        result = self.collect(self.warning(), sanitizer=bad)
        self.assertEqual(result['state'], 'SANITIZER_ERROR')
        self.assertEqual(result['counts']['warning_headers'], 1)
        self.assertNotIn(b'/secret', g.canonical_json(result))

    def test_13_source_map_contract(self):
        for bad in ([], MAP + MAP, [dict(MAP[0], path='/private/../file')], [dict(MAP[0], id='../escape')], [dict(MAP[0], sha256='a')], [dict(MAP[0], bytes=True)], [dict(MAP[0], extra=1)]):
            with self.subTest(bad=bad):
                self.assertEqual(self.collect(self.warning(), source_map=bad)['state'], 'CONTRACT_ERROR')

    def test_14_wrapper_positive_finite(self):
        args, wrapper = fixture(self.root)
        result = self.collect(self.warning())['wrapper']
        self.assertEqual(result['state'], 'AVAILABLE')
        self.assertEqual(result['syntax_state'], 'FINITE_PARSE_AVAILABLE')
        self.assertEqual(result['module'], 'qwen2_matrix_command_endpoint')
        self.assertEqual(result['specialization'], 'ENABLED')
        self.assertEqual(result['always_comb_count'], 2)
        self.assertEqual(result['dpi_import_count'], 1)
        self.assertEqual(result['combo_update_import_count'], 1)
        self.assertEqual(result['combo_update_call_count'], 1)
        self.assertEqual(result['combo_input_count'], 2)
        self.assertEqual(result['combo_output_count'], 2)
        self.assertEqual(result['wrapper_identity']['sha256'], hashlib.sha256(wrapper.read_bytes()).hexdigest())
        self.assertTrue(result['top_references_wrapper'])
        self.assertEqual(result['dependency_conclusion'], 'NOT_ESTABLISHED')
        self.assertEqual(result['handshakes'][1]['combo_binding'], 'COMBO_RESULT')
        self.assertNotIn(b'/private', g.canonical_json(result))

    def test_15_wrapper_missing_and_symlink(self):
        args, wrapper = fixture(self.root)
        wrapper.unlink()
        self.assertEqual(self.collect()['wrapper']['state'], 'MISSING')
        wrapper.symlink_to(self.log)
        self.assertEqual(self.collect()['wrapper']['state'], 'READ_ERROR')

    def test_16_args_duplicates_and_traversal(self):
        args, wrapper = fixture(self.root)
        original = args.read_text()
        for bad in (original + ' --lib-create ' + LEAF, original.replace('--hierarchical-child 1', '--hierarchical-child 2'), original.replace('--lib-create ' + LEAF, '--lib-create ../../secret'), original.replace('--top-module-encoded ' + LEAF, '--top-module-encoded other'), original + ' -GENABLE_ACCUMULATOR_SEED=0', original + ' --lib-create=evil', original + ' --hierarchical-child=0'):
            args.write_text(bad)
            self.assertEqual(self.collect()['wrapper']['state'], 'CONTRACT_ERROR')
        args.write_text(original)
        (args.parent / 'Vqwen2_matrix_command_endpoint_other__hierMkArgs.f').write_text(original)
        self.assertEqual(self.collect()['wrapper']['state'], 'CONTRACT_ERROR')

    def test_17_args_symlink_parent_and_sizes(self):
        args, wrapper = fixture(self.root)
        args.unlink()
        args.symlink_to(self.log)
        self.assertEqual(self.collect()['wrapper']['state'], 'READ_ERROR')
        args.unlink()
        with args.open('wb') as stream:
            stream.truncate(g.MAX_ARGS_BYTES + 1)
        self.assertEqual(self.collect()['wrapper']['state'], 'CONTRACT_ERROR')

    def test_18_wrapper_unknown_syntax(self):
        args, wrapper = fixture(self.root)
        wrapper.write_text('module ' + LEAF + '; endmodule\n')
        result = self.collect()['wrapper']
        self.assertEqual(result['state'], 'AVAILABLE')
        self.assertEqual(result['syntax_state'], 'UNRECOGNIZED_SYNTAX')
        self.assertIsNone(result['combo_input_count'])
        self.assertEqual(result['handshakes'], [])

    def test_19_top_args_optional_and_symlink(self):
        fixture(self.root)
        top = self.root / 'obj/VHostBlockTop__hierMkArgs.f'
        top.unlink()
        result = self.collect()['wrapper']
        self.assertEqual(result['state'], 'AVAILABLE')
        self.assertIsNone(result['top_references_wrapper'])
        top.symlink_to(self.log)
        self.assertEqual(self.collect()['wrapper']['state'], 'READ_ERROR')

    def test_20_strict_report_tampering(self):
        original = self.collect(self.warning())
        mutations = [('extra', 1), ('state', 'SUCCESS'), ('schema_version', 2), ('log_identity', {'bytes': 1, 'sha256': 'bad'})]
        for key, value in mutations:
            bad = copy.deepcopy(original)
            bad[key] = value
            with self.assertRaises(ValueError): g.validate_report(bad)
        for modify in (
            lambda r: r['records'][0].update(source_id='/secret'),
            lambda r: r['records'][0].update(message='password=bad'),
            lambda r: r['records'][0].update(line=0),
            lambda r: r['counts'].update(warning_headers=True),
            lambda r: r['fatal_summaries'].update(process_attribution='ONE_PROCESS'),
            lambda r: r['wrapper'].update(module='../escape'),
            lambda r: r['wrapper'].update(dependency_conclusion='ACYCLIC')):
            bad = copy.deepcopy(original)
            modify(bad)
            with self.assertRaises(ValueError): g.validate_report(bad)

    def test_21_parent_directory_link_rejected(self):
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir()
        (self.root / 'obj').symlink_to(elsewhere, target_is_directory=True)
        self.assertEqual(self.collect()['wrapper']['state'], 'READ_ERROR')

    def test_22_stable_read_checks_metadata(self):
        original = g.os.fstat
        counter = [0]
        def drift(fd):
            info = original(fd)
            counter[0] += 1
            if counter[0] == 2:
                return types.SimpleNamespace(**{name: getattr(info, name) + (1 if name == 'st_mtime_ns' else 0) for name in ('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns')})
            return info
        with mock.patch.object(g.os, 'fstat', side_effect=drift):
            self.assertEqual(self.collect(self.warning())['state'], 'READ_ERROR')

    def test_23_example_unknown_path_and_malformed(self):
        raw = self.warning() + b'  /secret/private:2:4: Example path: sk-credential12345\n  bad Example path: text\n'
        result = self.collect(raw)
        self.assertEqual(result['counts']['example_paths'], 2)
        self.assertEqual(result['omission']['examples'], 1)
        self.assertEqual(result['records'][0]['examples'][0]['source_id'], 'UNKNOWN_PATH')
        self.assertNotIn(b'credential', g.canonical_json(result))

    def test_24_every_known_frozen_rule_and_json_roundtrip(self):
        raw = b''.join(self.warning(rule=rule) for rule in sorted(g.RULE_IDS))
        result = self.collect(raw)
        self.assertEqual(len(result['by_rule']), len(g.RULE_IDS))
        self.assertEqual(g.validate_report(json.loads(g.canonical_json(result))), result)
        self.assertNotIn('WARNING:UNKNOWN', result['by_rule'])


    def test_25_whole_4mib_log_not_1mib_or_tail_only(self):
        first = self.warning(1)
        last = self.warning(2)
        raw = first + b'x' * (g.MAX_LOG_BYTES - len(first) - len(last) - 1) + b'\n' + last
        result = self.collect(raw)
        self.assertEqual(result['log_identity']['bytes'], g.MAX_LOG_BYTES)
        self.assertTrue(result['scan_complete'])
        self.assertEqual(result['counts']['warning_headers'], 2)
        self.assertEqual([r['line'] for r in result['records']], [1, 2])

    def test_26_wrapper_tamper_between_reads_is_rejected(self):
        args, wrapper = fixture(self.root)
        original = g._read
        reads = [0]
        def mutate(path, cap):
            raw = original(path, cap)
            if str(path) == str(wrapper):
                reads[0] += 1
                if reads[0] == 1:
                    wrapper.write_bytes(raw + b'// tamper\n')
            return raw
        with mock.patch.object(g, '_read', side_effect=mutate):
            self.assertEqual(self.collect()['wrapper']['state'], 'CONTRACT_ERROR')

    def test_27_zero_summary_and_rule_named_errors(self):
        result = self.collect(b'%Error: Exiting due to 0 warning(s)\n')
        self.assertEqual(result['fatal_summaries']['header_count_comparison'], 'GLOBAL_HEADERS_MATCH')
        result = self.collect(b'%Error-UNSUPPORTED: /secret:9:1: unsupported secret\n')
        self.assertEqual(result['by_rule'], {'ERROR:UNSUPPORTED': 1})

    def test_28_wrapper_argument_fifo_and_wrapper_size(self):
        args, wrapper = fixture(self.root)
        original = args.read_bytes()
        args.unlink()
        os.mkfifo(args)
        self.assertEqual(self.collect()['wrapper']['state'], 'CONTRACT_ERROR')
        args.unlink()
        args.write_bytes(original)
        with wrapper.open('wb') as stream:
            stream.truncate(g.MAX_WRAPPER_BYTES + 1)
        self.assertEqual(self.collect()['wrapper']['state'], 'CONTRACT_ERROR')

    def test_29_strict_scalar_and_extra_nested_keys(self):
        original = self.collect(self.warning())
        for modify in (
            lambda r: r.update(schema_version=True),
            lambda r: r.update(scan_complete=False),
            lambda r: r.update(state=[]),
            lambda r: r['caps'].update(record_cap=True),
            lambda r: r['records'][0].update(examples=[{'source_id': 'UNKNOWN_PATH', 'source_sha256': None, 'line': 1, 'column': 1, 'raw': 'secret'}]),
            lambda r: r['wrapper'].update(hierarchical_child=True),
            lambda r: r['records'][0].update(source_id='other/secret.sv'),
            lambda r: r['wrapper'].update(always_comb_lines=[0])):
            bad = copy.deepcopy(original)
            modify(bad)
            with self.assertRaises(ValueError): g.validate_report(bad)

    def test_30_wrapper_comments_and_unknown_call_binding(self):
        args, wrapper = fixture(self.root)
        raw = wrapper.read_text()
        wrapper.write_text('/* module wrong(); endmodule always_comb */\n' + raw.replace('seed_begin_ready_o_combo__V,', 'unrecognized_output,'))
        result = self.collect()['wrapper']
        self.assertEqual(result['syntax_state'], 'FINITE_PARSE_AVAILABLE')
        self.assertEqual(result['handshakes'][1]['combo_binding'], 'UNKNOWN')
        self.assertEqual(result['always_comb_count'], 2)
        self.assertEqual(result['handshakes'][0]['declaration_line'], 4)



    def test_31_official_mixed_fatal_single_comparison(self):
        prefix = b''.join(self.warning(n) for n in range(1, 36))
        prefix += b'%Error-UNSUPPORTED: /private/source/HostBlockCollection.sv:1:1: first\n'
        prefix += b'%Error: /private/source/HostBlockCollection.sv:2:1: second\n'
        result = self.collect(prefix + b'%Error: Exiting due to 2 error(s), 35 warning(s)\n')
        self.assertEqual(result['counts']['fatal_summary_headers'], 1)
        self.assertEqual(result['fatal_summaries']['warning_total'], 35)
        self.assertEqual(result['fatal_summaries']['error_total'], 2)
        self.assertEqual(result['fatal_summaries']['header_count_comparison'], 'GLOBAL_HEADERS_MATCH')
        self.assertEqual(result['fatal_summaries']['process_attribution'], 'NOT_AVAILABLE')
        self.assertEqual(result['records'][-1]['message'], 'Mixed error/warning-fatal exit summary reported.')
        self.assertFalse(result['caps']['partial'])
        mismatch = self.collect(prefix + b'%Error: Exiting due to 3 error(s), 35 warning(s)\n')
        self.assertEqual(mismatch['fatal_summaries']['header_count_comparison'], 'GLOBAL_HEADERS_DIFFER')
        mismatch = self.collect(prefix + b'%Error: Exiting due to 2 error(s), 34 warning(s)\n')
        self.assertEqual(mismatch['fatal_summaries']['header_count_comparison'], 'GLOBAL_HEADERS_DIFFER')
        multiple = self.collect(prefix + b'%Error: Exiting due to 2 error(s), 35 warning(s)\n%Error: Exiting due to 2 error(s)\n')
        self.assertEqual(multiple['counts']['fatal_summary_headers'], 2)
        self.assertIsNone(multiple['fatal_summaries']['warning_total'])
        self.assertIsNone(multiple['fatal_summaries']['error_total'])
        self.assertEqual(multiple['fatal_summaries']['header_count_comparison'], 'NOT_AVAILABLE')

    def test_32_record_count_agreement_full_and_truncated(self):
        original = self.collect(self.warning())
        for key, value in (('rule', 'WIDTH'), ('severity', 'ERROR')):
            bad = copy.deepcopy(original)
            bad['records'][0][key] = value
            with self.assertRaises(ValueError): g.validate_report(bad)
        original = self.collect(b''.join(self.warning(n) for n in range(1, 130)) + self.warning(130, rule='WIDTH'))
        self.assertTrue(original['omission']['records'])
        bad = copy.deepcopy(original)
        bad['records'][0]['rule'] = 'WIDTH'
        self.assertEqual(g.validate_report(bad), bad)  # One retained WIDTH is bounded by the whole-log one.
        bad['records'][1]['rule'] = 'WIDTH'
        with self.assertRaises(ValueError): g.validate_report(bad)
        bad = copy.deepcopy(original)
        bad['records'][0]['severity'] = 'ERROR'
        with self.assertRaises(ValueError): g.validate_report(bad)
        bad = copy.deepcopy(original)
        bad['by_rule']['WARNING:LATCH'] = 0
        with self.assertRaises(ValueError): g.validate_report(bad)

    def test_33_fixed_loader_rejects_mutation_before_compile(self):
        for source in (HERE / 'generation_diagnostics.py', HERE.parent / 'safe_build_diagnostics.py'):
            raw = source.read_bytes()
            for changed in (raw + b'raise RuntimeError("unfixed-source-marker-executed")\n', b'X' + raw[1:]):
                with mock.patch.object(Path, 'read_bytes', return_value=changed), mock.patch.object(builtins, 'compile', side_effect=RuntimeError('compile must not run')) as compiler:
                    with self.assertRaisesRegex(ValueError, 'source identity before compile'): load(source)
                    compiler.assert_not_called()
        source = HERE / 'generation_diagnostics.py'
        raw = source.read_bytes()
        class Unfixed:
            stem = 'unfixed_marker'
            def __str__(self): return '/synthetic/unfixed.py'
            def read_bytes(self): raise RuntimeError('unfixed read must not run')
        with mock.patch.object(builtins, 'compile', side_effect=RuntimeError('compile must not run')) as compiler:
            with self.assertRaisesRegex(ValueError, 'unfixed source before compile'): load(Unfixed())
            compiler.assert_not_called()
        with mock.patch.object(Path, 'read_bytes', side_effect=[raw, b'raise RuntimeError("second-read-executed")']) as reader:
            loaded = load(source)
            self.assertEqual(loaded.MAX_LOG_BYTES, g.MAX_LOG_BYTES)
            self.assertEqual(reader.call_count, 1)

    def test_34_wrapper_specialization_suffix_is_private(self):
        leaf = 'qwen2_matrix_command_endpoint_syntheticsecretABC'
        args, wrapper = fixture(self.root, leaf)
        result = self.collect(self.warning())
        self.assertEqual(result['wrapper']['module'], 'qwen2_matrix_command_endpoint')
        self.assertEqual(result['wrapper']['syntax_state'], 'FINITE_PARSE_AVAILABLE')
        self.assertEqual(result['wrapper']['wrapper_identity']['sha256'], hashlib.sha256(wrapper.read_bytes()).hexdigest())
        self.assertNotIn(b'syntheticsecretABC', g.canonical_json(result))
        bad = copy.deepcopy(result)
        bad['wrapper']['module'] = leaf
        with self.assertRaises(ValueError): g.validate_report(bad)

    def test_35_malformed_header_clears_example_association(self):
        for malformed in (b'%Error not fixed syntax\n', b'%Warning-LATCH no colon\n'):
            raw = self.warning() + malformed + ('  ' + SOURCE + ':4:2: Example path: private\n').encode()
            result = self.collect(raw)
            self.assertEqual(result['counts']['unparsed_headers'], 1)
            self.assertEqual(result['counts']['example_paths'], 1)
            self.assertEqual(result['omission']['examples'], 1)
            self.assertNotIn('examples', result['records'][0])
            self.assertTrue(result['caps']['partial'])

    def test_36_fatal_comparison_and_mixed_scalar_mutations(self):
        original = self.collect(b'%Error: Exiting due to 2 error(s), 35 warning(s)\n')
        self.assertEqual(original['fatal_summaries']['header_count_comparison'], 'GLOBAL_HEADERS_DIFFER')
        for key, value in (('header_count_comparison', 'GLOBAL_HEADERS_MATCH'), ('warning_total', True), ('warning_total', None)):
            bad = copy.deepcopy(original)
            bad['fatal_summaries'][key] = value
            if key == 'warning_total' and value is None:
                # One reported category may be absent; both cannot be absent.
                bad['fatal_summaries']['error_total'] = None
            with self.assertRaises(ValueError): g.validate_report(bad)


    def test_37_cluster_complete_counts_are_observed(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        result = self.collect()
        w = result['wrapper']; c = w['cluster_structure']
        self.assertEqual(w['module'], CLUSTER)
        self.assertEqual(w['candidate_count'], 1)
        self.assertEqual(w['syntax_state'], 'FINITE_PARSE_AVAILABLE')
        self.assertEqual((w['combo_input_count'], w['combo_output_count']), (2, 2))
        self.assertEqual(w['handshakes'], [])
        self.assertEqual(c['library_target_count'], 1)
        self.assertEqual(c['matching_library_target_count'], 1)
        self.assertEqual(c['handle_declaration_count'], 256)
        self.assertEqual(c['instance_handle_count'], 256)
        self.assertTrue(c['expected_structure_observed'])
        self.assertEqual(w['dependency_conclusion'], 'NOT_ESTABLISHED')
        self.assertEqual(c['root_header_identity']['sha256'], hashlib.sha256(header.read_bytes()).hexdigest())
        self.assertEqual(g.validate_report(json.loads(g.canonical_json(result))), result)

    def test_38_cluster_missing_files_remain_missing(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        mk.unlink(); header.unlink()
        c = self.collect()['wrapper']['cluster_structure']
        self.assertEqual(c['makegraph_state'], 'MISSING')
        self.assertEqual(c['root_header_state'], 'MISSING')
        self.assertIsNone(c['library_target_count'])
        self.assertIsNone(c['instance_handle_count'])
        self.assertIsNone(c['handle_declaration_count'])
        self.assertFalse(c['expected_structure_observed'])

    def test_39_cluster_unknown_syntax_and_mapping(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        mk.write_text('VM_HIER_LIBS = guessed.a\n')
        header.write_text(header.read_text().replace('g_cluster__BRA__', 'private_cluster__BRA__'))
        r = self.collect(); c = r['wrapper']['cluster_structure']
        self.assertEqual(c['makegraph_state'], 'UNRECOGNIZED_SYNTAX')
        self.assertEqual(c['root_header_state'], 'UNRECOGNIZED_SYNTAX')
        self.assertEqual(c['handle_declaration_count'], 256)
        self.assertIsNone(c['instance_handle_count'])
        self.assertFalse(c['expected_structure_observed'])
        self.assertNotIn(b'private_cluster', g.canonical_json(r))

    def test_40_cluster_actual_countercounts_and_duplicate(self):
        args, wrapper, mk, header = cluster_fixture(self.root, handles=255, libraries=[CLUSTER + '_cold', CLUSTER + '_other'])
        c = self.collect()['wrapper']['cluster_structure']
        self.assertEqual(c['library_target_count'], 2)
        self.assertEqual(c['instance_handle_count'], 255)
        self.assertFalse(c['expected_structure_observed'])
        header.write_text(header.read_text().replace('};', header.read_text().splitlines()[2] + '\n};'))
        c = self.collect()['wrapper']['cluster_structure']
        self.assertEqual(c['root_header_state'], 'CONTRACT_ERROR')
        self.assertIsNone(c['instance_handle_count'])

    def test_41_cluster_secret_suffix_is_never_exported(self):
        leaf = CLUSTER + '_secretProductionIdentifier'
        cluster_fixture(self.root, leaf=leaf)
        r = self.collect()
        self.assertTrue(r['wrapper']['cluster_structure']['expected_structure_observed'])
        self.assertNotIn(b'secretProductionIdentifier', g.canonical_json(r))
        r['wrapper']['module'] = leaf
        with self.assertRaises(ValueError): g.validate_report(r)

    def test_42_cluster_schema_rejects_contradictions(self):
        cluster_fixture(self.root)
        original = self.collect()
        for modify in (
            lambda r: r['wrapper'].update(candidate_count=2),
            lambda r: r['wrapper'].update(cluster_structure=None),
            lambda r: r['wrapper'].update(top_references_wrapper=False),
            lambda r: r['wrapper'].update(specialization='UNKNOWN'),
            lambda r: r['wrapper']['cluster_structure'].update(instance_handle_count=255),
            lambda r: r['wrapper']['cluster_structure'].update(root_header_state='MISSING'),
            lambda r: r['wrapper']['cluster_structure'].update(matching_library_target_count=2),
            lambda r: r['wrapper']['cluster_structure'].update(handle_declaration_count=True),
            lambda r: r['wrapper']['cluster_structure'].update(expected_structure_observed=False),
            lambda r: r['wrapper']['cluster_structure'].update(extra='secret')):
            bad = copy.deepcopy(original); modify(bad)
            with self.assertRaises(ValueError): g.validate_report(bad)

    def test_43_cluster_graph_and_header_bounds_and_symlinks(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        with mk.open('wb') as f: f.truncate(g.MAX_MAKEGRAPH_BYTES + 1)
        with header.open('wb') as f: f.truncate(g.MAX_ROOT_HEADER_BYTES + 1)
        c = self.collect()['wrapper']['cluster_structure']
        self.assertEqual(c['makegraph_state'], 'CONTRACT_ERROR')
        self.assertEqual(c['root_header_state'], 'UNRECOGNIZED_SYNTAX')
        self.assertEqual(c['root_header_read']['first_code'], 'SIZE_LIMIT')
        self.assertEqual(c['root_header_read']['retry_outcome'], 'SUCCEEDED')
        mk.unlink(); mk.symlink_to(self.log)
        header.unlink(); header.symlink_to(self.log)
        c = self.collect()['wrapper']['cluster_structure']
        self.assertEqual(c['makegraph_state'], 'READ_ERROR')
        self.assertEqual(c['root_header_state'], 'READ_ERROR')

    def test_44_cluster_multiple_candidates_counted_without_disclosure(self):
        cluster_fixture(self.root)
        (self.root / ('obj/V' + CLUSTER + '_secretOther__hierMkArgs.f')).write_text('private')
        r = self.collect()
        self.assertEqual(r['wrapper']['candidate_count'], 2)
        self.assertEqual(r['wrapper']['state'], 'CONTRACT_ERROR')
        self.assertNotIn(b'secretOther', g.canonical_json(r))

    def test_45_source_derivation_exact_identity_even_without_warnings(self):
        source = dict(MAP[0], id=g._FIFO_SOURCE, **g._FIFO_DERIVED)
        result = self.collect(source_map=[source])
        self.assertEqual(result['source_derivations'], [{'source_id': g._FIFO_SOURCE,
            'base_identity': g._FIFO_BASE, 'derived_identity': g._FIFO_DERIVED}])
        self.assertEqual(result['counts']['warning_headers'], 0)
        for identity in (g._FIFO_BASE, dict(g._FIFO_DERIVED, sha256='b' * 64), dict(g._FIFO_DERIVED, bytes=4661)):
            r = self.collect(source_map=[dict(source, **identity)])
            self.assertEqual(r['source_derivations'], [])
        bad = copy.deepcopy(result); bad['source_derivations'][0]['derived_identity']['bytes'] = 4661
        with self.assertRaises(ValueError): g.validate_report(bad)

    def test_46_cluster_tampering_is_not_observed_closure(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        original = g._read; reads = [0]
        def mutate(path, cap):
            raw = original(path, cap)
            if str(path) == str(header):
                reads[0] += 1
                if reads[0] == 1: header.write_bytes(raw + b'// changed\n')
            return raw
        with mock.patch.object(g, '_read', side_effect=mutate):
            c = self.collect()['wrapper']['cluster_structure']
        self.assertEqual(c['root_header_state'], 'CONTRACT_ERROR')
        self.assertIsNone(c['instance_handle_count'])
        self.assertFalse(c['expected_structure_observed'])


    def test_47_cluster_partial_wrapper_preserves_other_observations(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        wrapper.unlink()
        w = self.collect()['wrapper']; c = w['cluster_structure']
        self.assertEqual(w['state'], 'MISSING')
        self.assertEqual(c['library_target_count'], 1)
        self.assertEqual(c['instance_handle_count'], 256)
        self.assertFalse(c['expected_structure_observed'])

    def test_48_cluster_unknown_handle_spelling_and_out_of_range(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        raw = header.read_text()
        for altered in (raw.replace('leaves_7', 'leaves_8'),
                        raw.replace('g_cluster__BRA__31', 'g_cluster__BRA__32'),
                        raw.replace('__BRA__', '__05B').replace('__KET__', '__05D')):
            header.write_text(altered)
            c = self.collect()['wrapper']['cluster_structure']
            self.assertEqual(c['handle_declaration_count'], 256)
            self.assertIsNone(c['instance_handle_count'])
            self.assertEqual(c['root_header_state'], 'UNRECOGNIZED_SYNTAX')
            self.assertFalse(c['expected_structure_observed'])

    def test_49_cluster_graph_rule_contradiction_and_comments(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        raw = mk.read_text()
        mk.write_text(raw.replace(' VM_PREFIX=V', ' VM_PREFIX=otherV'))
        c = self.collect()['wrapper']['cluster_structure']
        self.assertEqual(c['makegraph_state'], 'UNRECOGNIZED_SYNTAX')
        self.assertIsNone(c['library_target_count'])
        mk.write_text(raw)
        header.write_text(header.read_text().replace('    void* ', '//  void* ', 1))
        c = self.collect()['wrapper']['cluster_structure']
        self.assertEqual(c['instance_handle_count'], 255)
        self.assertFalse(c['expected_structure_observed'])

    def test_50_source_derivation_rejects_contradictory_record(self):
        mapping = [dict(MAP[0], id=g._FIFO_SOURCE, **g._FIFO_DERIVED)]
        r = self.collect(self.warning(), source_map=mapping)
        r['records'][0]['source_sha256'] = g._FIFO_BASE['sha256']
        with self.assertRaises(ValueError): g.validate_report(r)

    def test_51_header_requires_closed_target_scope(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        raw = header.read_text()
        lines = raw.splitlines()
        mutations = [raw.removesuffix('};\n'),
                     raw.replace('public:\n', 'public:\n#if 0\n').replace('};\n', '#endif\n};\n'),
                     '\n'.join(lines[:2]) + '\n};\nnamespace synthetic {\n' + '\n'.join(lines[2:-1]) + '\n}\n']
        for changed in mutations:
            with self.subTest(changed=changed[:50]):
                header.write_text(changed)
                c = self.collect()['wrapper']['cluster_structure']
                self.assertEqual(c['root_header_state'], 'UNRECOGNIZED_SYNTAX')
                self.assertIsNone(c['instance_handle_count'])
                self.assertFalse(c['expected_structure_observed'])

    def test_52_header_fixed_guard_positive_unknown_guard_negative(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        raw = header.read_text(); guard = 'VERILATED_VHOSTBLOCKTOP___024ROOT_H_'
        guarded = '#ifndef ' + guard + '\n#define ' + guard + '\n#include "verilated.h"\n' + raw + '#endif\n'
        header.write_text(guarded)
        self.assertTrue(self.collect()['wrapper']['cluster_structure']['expected_structure_observed'])
        header.write_text(guarded.replace('#ifndef ' + guard, '#ifdef OTHER'))
        self.assertFalse(self.collect()['wrapper']['cluster_structure']['expected_structure_observed'])

    def test_53_make_only_fixed_outer_guard(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        raw = mk.read_text()
        for start, end in (('define synthetic\n', 'endef\n'), ('ifeq (0,1)\n', 'endif\n')):
            mk.write_text(raw.replace('VM_HIER_LIBS := ', start + 'VM_HIER_LIBS := ', 1).replace('endif  # Guard\n', end + 'endif  # Guard\n'))
            c = self.collect()['wrapper']['cluster_structure']
            self.assertEqual(c['makegraph_state'], 'UNRECOGNIZED_SYNTAX')
            self.assertIsNone(c['library_target_count'])
            self.assertFalse(c['expected_structure_observed'])

    def test_54_candidate_set_is_rechecked(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        original = g._read; inserted = [False]
        def read_and_insert(path, cap):
            raw = original(path, cap)
            if path == args and not inserted[0]:
                inserted[0] = True
                (self.root / ('obj/V' + CLUSTER + '_private_marker__hierMkArgs.f')).write_bytes(b'unparsed')
            return raw
        with mock.patch.object(g, '_read', side_effect=read_and_insert):
            report = self.collect()
        self.assertEqual(report['wrapper']['state'], 'CONTRACT_ERROR')
        self.assertFalse(report['wrapper']['cluster_structure']['expected_structure_observed'])
        self.assertNotIn(b'private_marker', g.canonical_json(report))

    def test_55_finite_parse_counter_coherence(self):
        cluster_fixture(self.root)
        original = self.collect()
        for edit in (dict(always_comb_count=None), dict(dpi_import_count=0),
                     dict(always_comb_count=0, always_comb_lines=[]),
                     dict(dpi_import_count=None), dict(always_comb_lines=[])):
            report = copy.deepcopy(original); report['wrapper'].update(edit)
            with self.subTest(edit=edit):
                with self.assertRaises(ValueError): g.validate_report(report)

    def test_56_nested_type_declarations_remain_unknown(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        raw = header.read_text()
        for kind in ('class unused', 'struct unused', 'union unused', 'struct', 'void unused()'):
            header.write_text(raw.replace('public:\n', 'public:\n' + kind + ' {\n').replace('};\n', '};\n};\n'))
            c = self.collect()['wrapper']['cluster_structure']
            self.assertEqual(c['root_header_state'], 'UNRECOGNIZED_SYNTAX')
            self.assertIsNone(c['instance_handle_count'])
            self.assertFalse(c['expected_structure_observed'])

    def test_57_zero_comb_constructor_retains_census_unknown(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        wrapper.write_text(wrapper.read_text().replace('always_comb', 'initial'))
        report = self.collect(self.warning())
        self.assertEqual(report['counts']['warning_headers'], 1)
        self.assertEqual(report['wrapper']['always_comb_count'], 0)
        self.assertEqual(report['wrapper']['syntax_state'], 'UNRECOGNIZED_SYNTAX')
        self.assertFalse(report['wrapper']['cluster_structure']['expected_structure_observed'])
        self.assertIs(g.validate_report(report), report)


    def test_58_root_read_normal_missing_and_parser_failure(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        raw = header.read_bytes()
        c = self.collect()['wrapper']['cluster_structure']
        self.assertEqual(c['root_header_read'], {
            'first_code': 'OK', 'first_observed_size': len(raw),
            'retry_outcome': 'NOT_ATTEMPTED', 'final_code': 'OK',
            'final_observed_size': len(raw)})
        header.unlink()
        c = self.collect()['wrapper']['cluster_structure']
        self.assertEqual(c['root_header_read'], {
            'first_code': 'MISSING', 'first_observed_size': None,
            'retry_outcome': 'NOT_ATTEMPTED', 'final_code': 'MISSING',
            'final_observed_size': None})
        for payload, state in ((b'private unknown grammar', 'UNRECOGNIZED_SYNTAX'),
                               (b'\xffprivate parser error', 'READ_ERROR'),
                               (raw.replace(b'};', raw.splitlines()[2] + b'\n};'), 'CONTRACT_ERROR')):
            header.write_bytes(payload)
            c = self.collect()['wrapper']['cluster_structure']
            self.assertEqual(c['root_header_state'], state)
            self.assertEqual(c['root_header_read']['first_code'], 'OK')
            self.assertEqual(c['root_header_read']['final_code'], 'OK')
            self.assertEqual(c['root_header_read']['retry_outcome'], 'NOT_ATTEMPTED')

    def test_59_read_reason_comes_from_same_fd_fstat_before_read(self):
        self.log.write_bytes(b'tiny')
        baseline = os.stat(self.log)
        for mode, size, code in ((g.stat.S_IFREG, g.MAX_ROOT_HEADER_BYTES + 1, 'SIZE_LIMIT'),
                                 (g.stat.S_IFIFO, g.MAX_ROOT_HEADER_RETRY_BYTES + 1, 'NOT_REGULAR'),
                                 (g.stat.S_IFDIR, 4, 'NOT_REGULAR'),
                                 (g.stat.S_IFREG, -1, 'INVALID_SIZE')):
            info = types.SimpleNamespace(**{name: getattr(baseline, name) for name in
                ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')})
            info.st_mode = mode; info.st_size = size
            with self.subTest(code=code), mock.patch.object(g.os, 'fstat', return_value=info), \
                    mock.patch.object(g.os, 'fdopen', side_effect=RuntimeError('must not read')) as opener:
                expected_error = IsADirectoryError if mode == g.stat.S_IFDIR else g._ReadContractError
                with self.assertRaises(expected_error) as caught:
                    g._read(self.log, g.MAX_ROOT_HEADER_BYTES)
                if mode == g.stat.S_IFDIR:
                    self.assertEqual((caught.exception._generation_read_code,
                                      caught.exception._generation_observed_size), (code, size))
                else:
                    self.assertIsInstance(caught.exception, ValueError)
                    self.assertEqual((caught.exception.code, caught.exception.observed_size), (code, size))
                self.assertNotIn(str(self.log), str(caught.exception))
                opener.assert_not_called()

    def test_60_bounded_size_retry_and_exact_limits(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        small = header.read_bytes()
        raw = small + b' ' * (g.MAX_ROOT_HEADER_BYTES + 1 - len(small))
        first = g._ReadContractError('SIZE_LIMIT', len(raw))
        report, calls = self.collect_header_reads(header, [first, raw, raw])
        c = report['wrapper']['cluster_structure']
        self.assertEqual(calls, [4 * 1024**2, 16 * 1024**2, 16 * 1024**2])
        self.assertEqual(c['root_header_read'], {
            'first_code': 'SIZE_LIMIT', 'first_observed_size': len(raw),
            'retry_outcome': 'SUCCEEDED', 'final_code': 'OK', 'final_observed_size': len(raw)})
        self.assertEqual(c['root_header_identity'], g._identity(raw))
        self.assertEqual(c['instance_handle_count'], 256)
        self.assertTrue(c['expected_structure_observed'])
        self.assertLessEqual(len(g.canonical_json(report)), 64 * 1024)
        self.assertEqual((g.MAX_LOG_BYTES, g.MAX_REPORT_BYTES), (4 * 1024**2, 64 * 1024))
        # The inclusive 16 MiB gate is checked with tiny mocked outcomes, not a large file.
        first = g._ReadContractError('SIZE_LIMIT', g.MAX_ROOT_HEADER_RETRY_BYTES)
        last = g._ReadContractError('SIZE_LIMIT', g.MAX_ROOT_HEADER_RETRY_BYTES + 1)
        report, calls = self.collect_header_reads(header, [first, last])
        c = report['wrapper']['cluster_structure']
        self.assertEqual(calls, [4 * 1024**2, 16 * 1024**2])
        self.assertEqual(c['root_header_read']['retry_outcome'], 'FAILED')
        self.assertEqual(c['root_header_read']['final_code'], 'SIZE_LIMIT')
        self.assertEqual(c['root_header_read']['final_observed_size'], 16 * 1024**2 + 1)
        self.assertIsNone(c['root_header_identity'])
        self.assertFalse(c['expected_structure_observed'])

    def test_61_over_16mib_is_unknown_without_retry_or_parser(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        size = g.MAX_ROOT_HEADER_RETRY_BYTES + 1
        with mock.patch.object(g, '_root_handles', side_effect=RuntimeError('parser must not run')) as parser:
            report, calls = self.collect_header_reads(header, [g._ReadContractError('SIZE_LIMIT', size)])
        parser.assert_not_called()
        c = report['wrapper']['cluster_structure']
        self.assertEqual(calls, [4 * 1024**2])
        self.assertEqual(c['root_header_state'], 'CONTRACT_ERROR')
        self.assertEqual(c['root_header_read'], {
            'first_code': 'SIZE_LIMIT', 'first_observed_size': size,
            'retry_outcome': 'NOT_ATTEMPTED', 'final_code': 'SIZE_LIMIT', 'final_observed_size': size})
        self.assertIsNone(c['root_header_identity'])
        self.assertIsNone(c['instance_handle_count'])
        self.assertFalse(c['expected_structure_observed'])

    def test_62_only_precise_size_limit_can_retry(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        failures = [(g._ReadContractError('NOT_REGULAR', g.MAX_ROOT_HEADER_BYTES + 1), 'NOT_REGULAR'),
                    (g._ReadContractError('INVALID_SIZE', -1), 'INVALID_SIZE'),
                    (g._ReadContractError('FILE_CHANGED', 4), 'FILE_CHANGED'),
                    (g._ReadContractError('DIRECTORY_CHANGED', 4), 'DIRECTORY_CHANGED'),
                    (ValueError('/private/SIZE_LIMIT secret'), 'CONTRACT_ERROR'),
                    (PermissionError('/private/SIZE_LIMIT secret'), 'READ_ERROR'),
                    (FileNotFoundError('/private/SIZE_LIMIT secret'), 'MISSING')]
        for failure, code in failures:
            with self.subTest(code=code):
                report, calls = self.collect_header_reads(header, [failure])
                c = report['wrapper']['cluster_structure']
                self.assertEqual(calls, [4 * 1024**2])
                self.assertEqual(c['root_header_read']['first_code'], code)
                self.assertEqual(c['root_header_read']['final_code'], code)
                self.assertEqual(c['root_header_read']['retry_outcome'], 'NOT_ATTEMPTED')
                self.assertEqual(c['root_header_state'], g._READ_FAILURE_STATES[code])
                self.assertIsNone(c['root_header_identity'])
                for token in (b'/private', b'secret', b'errno', b'traceback'):
                    self.assertNotIn(token, g.canonical_json(report))

    def test_63_descriptor_and_directory_changes_have_distinct_codes(self):
        self.log.write_bytes(b'tiny')
        original = g.os.fstat
        for changed_call, key, expected in ((2, 'st_mtime_ns', 'FILE_CHANGED'),
                                             (4, 'st_ino', 'DIRECTORY_CHANGED')):
            count = [0]
            def changed(fd):
                info = original(fd); count[0] += 1
                if count[0] == changed_call:
                    return types.SimpleNamespace(**{name: getattr(info, name) + (1 if name == key else 0)
                        for name in ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')})
                return info
            with self.subTest(code=expected), mock.patch.object(g.os, 'fstat', side_effect=changed):
                raw, code, size = g._root_header_read_attempt(self.log, g.MAX_ROOT_HEADER_BYTES)
            self.assertEqual((raw, code, size), (None, expected, 4))
        self.log.unlink(); self.log.mkdir()
        self.assertEqual(g._root_header_read_attempt(self.log, g.MAX_ROOT_HEADER_BYTES)[1], 'NOT_REGULAR')
        self.log.rmdir(); os.mkfifo(self.log)
        self.assertEqual(g._root_header_read_attempt(self.log, g.MAX_ROOT_HEADER_BYTES)[1], 'NOT_REGULAR')

    def test_64_directory_errors_keep_fstat_size_without_exception_text(self):
        self.log.write_bytes(b'tiny')
        original = g._directory
        for number in (1, 2):
            for error_type, expected in ((PermissionError, 'DIRECTORY_READ_ERROR'),
                                         (FileNotFoundError, 'DIRECTORY_MISSING')):
                count = [0]
                def failed(path):
                    count[0] += 1
                    if count[0] == number:
                        raise error_type('/private/secret_directory')
                    return original(path)
                with self.subTest(number=number, code=expected), mock.patch.object(g, '_directory', side_effect=failed):
                    raw, code, size = g._root_header_read_attempt(self.log, g.MAX_ROOT_HEADER_BYTES)
                self.assertEqual((raw, code, size), (None, expected, None if number == 1 else 4))
        # Legacy missing-file exception classification is preserved.
        self.log.unlink()
        with self.assertRaises(FileNotFoundError): g._read(self.log, g.MAX_LOG_BYTES)

    def test_65_failed_retry_and_recheck_never_become_available(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        size = g.MAX_ROOT_HEADER_BYTES + 1
        for failure, expected in ((PermissionError('/private/retry_secret'), 'READ_ERROR'),
                                  (FileNotFoundError('/private/retry_secret'), 'MISSING'),
                                  (g._ReadContractError('FILE_CHANGED', size), 'FILE_CHANGED'),
                                  (g._ReadContractError('NOT_REGULAR', 0), 'NOT_REGULAR'),
                                  (g._ReadContractError('DIRECTORY_CHANGED', size), 'DIRECTORY_CHANGED')):
            report, calls = self.collect_header_reads(header, [g._ReadContractError('SIZE_LIMIT', size), failure])
            c = report['wrapper']['cluster_structure']
            self.assertEqual(calls, [4 * 1024**2, 16 * 1024**2])
            self.assertEqual(c['root_header_read']['retry_outcome'], 'FAILED')
            self.assertEqual(c['root_header_read']['final_code'], expected)
            self.assertIsNone(c['root_header_identity'])
            self.assertIsNone(c['instance_handle_count'])
            self.assertFalse(c['expected_structure_observed'])
            self.assertNotIn(b'retry_secret', g.canonical_json(report))
        raw = header.read_bytes()
        report, calls = self.collect_header_reads(header, [raw, raw + b' '])
        c = report['wrapper']['cluster_structure']
        self.assertEqual(calls, [4 * 1024**2, 4 * 1024**2])
        self.assertEqual(c['root_header_read']['first_code'], 'OK')
        self.assertEqual(c['root_header_read']['final_code'], 'FILE_CHANGED')
        self.assertEqual(c['root_header_read']['final_observed_size'], len(raw) + 1)
        self.assertEqual(c['root_header_identity'], g._identity(raw))
        self.assertFalse(c['expected_structure_observed'])
        large = raw + b' ' * (size - len(raw))
        report, calls = self.collect_header_reads(header, [g._ReadContractError('SIZE_LIMIT', size), large,
            g._ReadContractError('FILE_CHANGED', size)])
        c = report['wrapper']['cluster_structure']
        self.assertEqual(calls, [4 * 1024**2, 16 * 1024**2, 16 * 1024**2])
        self.assertEqual(c['root_header_read']['retry_outcome'], 'SUCCEEDED')
        self.assertEqual(c['root_header_read']['final_code'], 'FILE_CHANGED')
        self.assertEqual(c['root_header_identity'], g._identity(large))
        self.assertIsNone(c['instance_handle_count'])
        self.assertFalse(c['expected_structure_observed'])

    def test_66_root_read_schema_rejects_scalar_and_state_tampering(self):
        cluster_fixture(self.root)
        original = self.collect()
        for update in ({'extra': '/private'}, {'first_code': 'private'}, {'final_code': True},
                       {'first_observed_size': True}, {'first_observed_size': 1.0},
                       {'first_observed_size': '1'}, {'first_observed_size': -1},
                       {'first_observed_size': 2**63}, {'final_observed_size': None},
                       {'first_observed_size': g.MAX_ROOT_HEADER_BYTES + 1},
                       {'first_code': 'CONTRACT_ERROR'}, {'retry_outcome': 'SUCCEEDED'},
                       {'retry_outcome': 'FAILED'}, {'retry_outcome': True},
                       {'final_code': 'NOT_COLLECTED'}, {'final_code': 'FILE_CHANGED'}):
            report = copy.deepcopy(original)
            report['wrapper']['cluster_structure']['root_header_read'].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                g.validate_report(report)
        for replacement in (None, [], {}, 'private'):
            report = copy.deepcopy(original)
            report['wrapper']['cluster_structure']['root_header_read'] = replacement
            with self.assertRaises(ValueError): g.validate_report(report)

    def test_67_retry_schema_correlates_first_size_outcome_and_identity(self):
        args, wrapper, mk, header = cluster_fixture(self.root)
        size = g.MAX_ROOT_HEADER_BYTES + 1
        raw = header.read_bytes() + b' ' * (size - header.stat().st_size)
        success, unused = self.collect_header_reads(header, [g._ReadContractError('SIZE_LIMIT', size), raw, raw])
        failed, unused = self.collect_header_reads(header, [g._ReadContractError('SIZE_LIMIT', size), PermissionError('secret')])
        oversized, unused = self.collect_header_reads(header, [g._ReadContractError('SIZE_LIMIT', g.MAX_ROOT_HEADER_RETRY_BYTES + 1)])
        edits = [(success, {'first_observed_size': g.MAX_ROOT_HEADER_BYTES}),
                 (success, {'first_observed_size': g.MAX_ROOT_HEADER_RETRY_BYTES + 1}),
                 (success, {'first_observed_size': None}),
                 (success, {'retry_outcome': 'NOT_ATTEMPTED'}),
                 (success, {'retry_outcome': 'FAILED'}),
                 (success, {'final_observed_size': size - 1}),
                 (failed, {'retry_outcome': 'SUCCEEDED'}),
                 (failed, {'final_code': 'OK'}),
                 (failed, {'final_code': 'SIZE_LIMIT', 'final_observed_size': g.MAX_ROOT_HEADER_RETRY_BYTES}),
                 (oversized, {'retry_outcome': 'FAILED'}),
                 (oversized, {'final_observed_size': g.MAX_ROOT_HEADER_RETRY_BYTES + 2}),
                 (oversized, {'final_code': 'NOT_REGULAR'})]
        for original, update in edits:
            report = copy.deepcopy(original)
            report['wrapper']['cluster_structure']['root_header_read'].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError): g.validate_report(report)
        report = copy.deepcopy(failed)
        report['wrapper']['cluster_structure']['root_header_identity'] = g._identity(b'')
        with self.assertRaises(ValueError): g.validate_report(report)
        report = copy.deepcopy(success)
        report['wrapper']['cluster_structure']['root_header_identity'] = None
        with self.assertRaises(ValueError): g.validate_report(report)

    def test_68_frozen_parsers_and_fifo_exact_identities(self):
        source = (HERE / 'generation_diagnostics.py').read_text()
        expected = {'_makegraph': (2097, 'de68244bf412a07fab7cfc8e630556e623a4eaca81782590956563a8c625286c'),
                    '_root_handles': (3153, '96333de18799d3199280323ffea507f50d518fcfd8aaf2ae8c08f41f368eaef3')}
        found = {}
        for node in ast.parse(source).body:
            if isinstance(node, ast.FunctionDef) and node.name in expected:
                raw = ast.get_source_segment(source, node).encode()
                found[node.name] = (len(raw), hashlib.sha256(raw).hexdigest())
        self.assertEqual(found, expected)
        self.assertEqual(g._FIFO_BASE, {'bytes': 4411, 'sha256': '68de1c713e40d97950591111dccd37a7546025f7fe6750fa3092826422557352'})
        self.assertEqual(g._FIFO_DERIVED, {'bytes': 4662, 'sha256': 'cf5607bf61d0e1ca95d523689ba5170fe937dcfb2f94c001661b4a897bf9e5f6'})
        old_split = {'bytes': 4536, 'sha256': 'd5482112dccd8a60bb142982fded05b64658b097b4227bf21a514f2da5d34e70'}
        report = self.collect(source_map=[dict(MAP[0], id=g._FIFO_SOURCE, **old_split)])
        self.assertEqual(report['source_derivations'], [])


if __name__ == '__main__':
    unittest.main()

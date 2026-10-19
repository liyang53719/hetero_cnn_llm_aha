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
    str(HERE / 'generation_diagnostics.py'): (31577, 'ec844694b0c42809dcb0cb06df83e28c6057868566473d36ff988f79ef4cb9db'),
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


if __name__ == '__main__':
    unittest.main()

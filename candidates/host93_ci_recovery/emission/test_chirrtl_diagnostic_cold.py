"""Synthetic-only diagnostic/resume contract tests. No project/native/network run."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Require Python -I -S -B before project source read.')
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).absolute().parent
MODULE_PIN = {'bytes': 30065, 'sha256': '337f08fc4917c0229f58d2fb168ceae6797dc3232d4baa8c3b1b762ed60c968d'}
BASE_PIN = {'bytes': 26517, 'sha256': 'f1cb8595247b2c991c77e4fa7404fc1cd618bb28f9e173eb43d7e00a58c49b50'}


def fixed(name, pin):
    path = HERE / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size != pin['bytes'] or pin['bytes'] > 128*1024:
        raise ValueError('fixed bounded cold-test source')
    with path.open('rb') as stream:
        raw = stream.read(pin['bytes'] + 1)
    if len(raw) != pin['bytes'] or hashlib.sha256(raw).hexdigest() != pin['sha256']:
        raise ValueError('fixed cold-test source identity')
    return raw


def load(name, raw):
    module = types.ModuleType(name)
    module.__file__ = str(HERE / (name + '.py'))
    exec(compile(raw, module.__file__, 'exec', dont_inherit=True), module.__dict__)
    return module


MODULE_RAW = fixed('chirrtl_diagnostic.py', MODULE_PIN)
BASE_RAW = fixed('host_emission.py', BASE_PIN)
g = load('chirrtl_diagnostic', MODULE_RAW)
EMITTER = fixed('EmitCanonicalHost93Diagnostic.scala', g.EMITTER_PIN)
BYTES_ANCHOR = b'  val bytes = ir.getBytes(StandardCharsets.UTF_8)\n'
ASSERTION_ANCHOR = b'  require("(?m)^circuit HostBlockCollection'
ORIGINAL = (EMITTER.split(BYTES_ANCHOR, 1)[0] + BYTES_ANCHOR +
            b'  require(bytes.length <= 48*1024*1024, "48 MiB CHIRRTL cap")\n' +
            ASSERTION_ANCHOR + EMITTER.split(ASSERTION_ANCHOR, 1)[1])
if {'bytes': len(ORIGINAL), 'sha256': hashlib.sha256(ORIGINAL).hexdigest()} != g.ORIGINAL_EMITTER_PIN:
    raise ValueError('exact reverse projection to original emitter')
FIR = ('circuit HostBlockCollection :\n' + ''.join('  module ' + name + ' : @[scala/src/' + name + '.scala 1:2]\n'
       for name in ('HostBlockTop', 'HeteroBF16FmaPre', 'HeteroBF16FmaMul', 'HeteroBF16FmaPost', 'HeteroBF16FmaRound')) +
       '  extmodule External : @[lib/é.scala 2:3]\n').encode('utf-8')


def marker(values):
    return g.MARKER + b' '.join(key.encode() + b'=' + str(values[key]).encode() for key in g.METRICS) + b'\n'


class Fixture:
    """Tiny fabricated 121/111/93/87/20 maps, with all children mocked."""
    def __init__(self, root):
        self.root = root
        self.base = load('host_emission', BASE_RAW)
        b = self.base
        self.repo = root / 'repo'
        self.repo.mkdir()
        (self.repo / '.git').mkdir()
        self.work = root / 'work'
        self.target = 'source/EmitCanonicalHost93.scala'
        self.sources = {'src/F%02d.scala' % n: ('// source %d\n' % n).encode() for n in range(92)}
        self.sources[self.target] = ORIGINAL
        self.expected = {name: b.byte_identity(raw)['sha256'] for name, raw in self.sources.items()}
        self.extra = {'synthetic/input%03d' % n: b'x' for n in range(111)}
        self.plan = {'input_sha256': {name: b.byte_identity(raw)['sha256'] for name, raw in self.extra.items()},
                     'expected93': self.expected, 'emitter': {'target': self.target}}
        self.artifacts = {'jar87': {'jars/j%02d.jar' % n: ('j%d' % n).encode() for n in range(87)},
                          'hardfloat20': {'hardfloat/src/main/scala/H%02d.scala' % n: b'// hf' for n in range(20)},
                          'firtool': {'firtool.jar': b'fake-archive'}}
        self.plans = {group: {'artifacts': [{'relative_destination': name, 'sha256': b.byte_identity(raw)['sha256'],
                                            'known_size_bytes': len(raw), 'max_transfer_bytes': len(raw)+1}
                                           for name, raw in files.items()]} for group, files in self.artifacts.items()}
        class_source = b'''def command(java,jars,classes,source,expected,jplan):
 return [str(java),'-Xmx1024m','-XX:ActiveProcessorCount=1','scala.tools.nsc.Main','-d',str(classes)]+[str(source/name) for name in sorted(expected)]
'''
        emit_source = b'''def command(java,classes,jars,jplan,structure):
 return [str(java),'-Xmx1024m','-XX:ActiveProcessorCount=1','heteronpu.continuous.EmitCanonicalHost93',str(structure)]
'''
        sv_source = b'''def command(tool,fir,rtl):
 return [str(tool),str(fir),str(rtl)]
'''
        inputs = {b.REPLAY: json.dumps(self.plan).encode(), b.CLASS_HELPER: class_source,
                  b.CHIRRTL_HELPER: emit_source, b.SV_HELPER: sv_source,
                  b.ASSEMBLER: b'# fake assembly never executed\n', b.ACQUIRER: b'# fake acquisition never executed\n',
                  b.MEMBER_HELPER: b'# fake extraction never executed\n', **self.extra}
        for group in self.plans:
            inputs[b.BASE + 'acquisition/plans/' + group + '.json'] = json.dumps(self.plans[group]).encode()
        self.pins = {name: b.byte_identity(raw) for name, raw in inputs.items()}
        if len(self.pins) != 121:
            raise ValueError('synthetic fixture cardinality')
        for name, raw in inputs.items():
            b.write_new(self.repo / name, raw)
        self.java_home = root / 'jdk'
        self.java = self.java_home / 'bin/java'
        b.write_new(self.java, b'not-an-executable')
        b.write_new(self.java_home / 'release', b'JAVA_VERSION="21.0.0"\n')
        self.java_pin = {'environment_key': 'JAVA_HOME_21_X64', 'java': b.byte_identity(b'not-an-executable'),
                         'release': b.byte_identity(b'JAVA_VERSION="21.0.0"\n')}
        self.calls = []
        self.fir = FIR
        self.sv = b'// fake SV fixture\n'
        self.tool = b'not-a-firtool-executable'
        self.mutate = None

    def callback(self, name, argv, cwd, env, limits):
        b = self.base
        self.calls.append((name, argv, cwd, env, limits))
        log = b'synthetic\n'
        if name == 'host93_java_version':
            log = b'openjdk version "21.0.0"\n'
        elif name in ('host93_acquire_jar87', 'host93_acquire_hardfloat20', 'host93_acquire_firtool'):
            group = name.removeprefix('host93_acquire_')
            destination = Path(argv[argv.index('--output-root') + 1])
            for relative, raw in self.artifacts[group].items():
                b.write_new(destination / relative, raw)
            b.write_new(destination / 'ACQUISITION.json', b'{}')
            if group == 'firtool':
                b.write_new(destination / 'firtool', self.tool)
                b.save(destination / 'MEMBER.json', {'extracted_member_count': 1, 'binary_executed': False,
                    'member_name': 'org.chipsalliance/llvm-firtool/linux-x64/bin/firtool'})
        elif name == 'host93_assemble':
            destination = Path(argv[argv.index('--output') + 1])
            for relative, raw in self.sources.items():
                b.write_new(destination / 'scala' / relative, raw)
            b.write_new(destination / 'SOURCE_RECEIPT.json', b'{}')
        elif name == 'host93_class':
            destination = Path(argv[argv.index('-d') + 1])
            b.write_new(destination / 'heteronpu/continuous/EmitCanonicalHost93.class', b'fake-class')
        elif name == 'host93_chirrtl_diagnostic':
            destination = Path(argv[-1])
            b.write_new(destination / 'HostBlockCollection.fir', self.fir)
            log = (b'CANONICAL_HOST93_CHIRRTL_BEGIN new_derived_source_identity=1 actual_job=none\n' +
                   marker(g.measure_fir(self.fir)) + b'CANONICAL_HOST93_CHIRRTL_WRITTEN bytes=' +
                   str(len(self.fir)).encode() + b' execution_top=HostBlockTop\n')
        elif name == 'host93_sv':
            b.write_new(Path(argv[-1]) / 'HostBlockCollection.sv', self.sv)
        else:
            raise ValueError('unexpected synthetic child phase')
        if self.mutate is not None:
            log = self.mutate(name, argv, log)
        return {'record': {'exit_code': 0, 'cleanup_confirmed': True}, 'raw_log': log,
                'usage': {'synthetic': True}, 'evidence_root': str(cwd)}

    def patch(self):
        stack = __import__('contextlib').ExitStack()
        stack.enter_context(mock.patch.object(self.base, 'source_pins', return_value=self.pins))
        stack.enter_context(mock.patch.object(self.base, '_java21', return_value=(self.java_home, self.java, self.java_pin)))
        stack.enter_context(mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('no child permitted in cold test')))
        return stack

    def run(self):
        return g.run(self.repo, self.work, self.callback, self.base, EMITTER)


class Cold(unittest.TestCase):
    def fixture(self, action):
        with tempfile.TemporaryDirectory(prefix='chirrtl-diagnostic-cold-') as temporary:
            fixture = Fixture(Path(temporary))
            with fixture.patch():
                return action(fixture)

    def test_reverse_projection_exact_original_and_lines(self):
        self.assertEqual(ORIGINAL.split(BYTES_ANCHOR, 1)[0], EMITTER.split(BYTES_ANCHOR, 1)[0])
        self.assertEqual(EMITTER.split(BYTES_ANCHOR, 1)[0].count(b'\n'), 24)
        self.assertLess(EMITTER.index(g.MARKER), EMITTER.index(b'require(bytes.length <= 96*1024*1024'))
        self.assertLess(EMITTER.index(b'Console.out.flush()'), EMITTER.index(b'require(bytes.length <= 96*1024*1024'))
        self.assertEqual(ORIGINAL.split(ASSERTION_ANCHOR, 1)[1], EMITTER.split(ASSERTION_ANCHOR, 1)[1])

    def test_no_optimization_sensitive_assert_or_process_runner(self):
        tree = ast.parse(MODULE_RAW)
        self.assertFalse(any(isinstance(node, ast.Assert) for node in ast.walk(tree)))
        self.assertNotIn(b'import subprocess', MODULE_RAW)
        self.assertNotIn(b'os.system', MODULE_RAW)
        self.assertNotIn(b'exec(', MODULE_RAW)

    def test_emitter_tamper_rejected_before_work_or_callback(self):
        def check(f):
            for bad in (bytearray(EMITTER), EMITTER[:-1], EMITTER.replace(b'96*', b'97*', 1)):
                with self.assertRaises(g.DiagnosticContractError) as error:
                    g.run(f.repo, f.work, f.callback, f.base, bad)
                self.assertEqual(error.exception.safe_contract_code, 'DIAGNOSTIC_EMITTER')
                self.assertFalse(f.work.exists())
                self.assertEqual(f.calls, [])
        self.fixture(check)

    def test_metrics_utf8_and_line_rules(self):
        values = g.measure_fir(FIR)
        self.assertEqual(values['line_count'], 7)
        self.assertEqual(values['module_count'], 5)
        self.assertEqual(values['extmodule_count'], 1)
        self.assertEqual(values['source_info_count'], 6)
        self.assertEqual(values['project_source_info_count'], 5)
        self.assertEqual(values['library_source_info_count'], 0)
        self.assertEqual(values['other_source_info_count'], 1)
        self.assertLessEqual(len(marker(dict.fromkeys(g.METRICS, 999999999999)).rstrip(b'\n')), 512)
        library = g.measure_fir(FIR.replace(b'@[lib/', b'@[src/'))
        self.assertEqual(library['library_source_info_count'], 1)
        self.assertEqual(library['other_source_info_count'], 0)
        self.assertEqual(values['utf8_bytes'], len(FIR))
        self.assertEqual(g.measure_fir(FIR[:-1])['line_count'], values['line_count'])
        self.assertEqual(values['source_info_utf8_bytes'], sum(len(m.group(0).encode()) for m in g.SOURCE_INFO.finditer(FIR.decode())))
        self.assertEqual(g.parse_observation(marker(values)), values)
        with self.assertRaises(UnicodeDecodeError):
            g.measure_fir(b'\xff')

    def test_numeric_parser_rejects_paths_duplicate_missing_malformed(self):
        good = marker(g.measure_fir(FIR))
        for raw in (b'', good + good, b'prefix ' + good, good.replace(b'utf8_bytes=', b'utf8_bytes=/tmp/'),
                    good.rstrip() + b' private_path=/secret\n', good.replace(b'module_count=5', b'module_count=-5'),
                    good.replace(b'line_count=7', b'line_count=9999999999999'),
                    good.replace(b'project_source_info_count=5', b'project_source_info_count=4')):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    g.parse_observation(raw)

    def test_pre_cap_marker_can_record_oversize(self):
        values = g.measure_fir(FIR)
        values['utf8_bytes'] = g.FIR_CAP + 1
        self.assertEqual(g.parse_observation(marker(values))['utf8_bytes'], g.FIR_CAP + 1)

    def test_all_six_mock_phases_and_clean_environment(self):
        def check(f):
            with mock.patch.dict(f.base.os.environ, {'HTTPS_PROXY': 'private-proxy-fixture', 'TOP_SECRET': 'never-copy'}, clear=True):
                result = f.run()
            self.assertEqual([x[0] for x in f.calls], ['host93_java_version','host93_acquire_jar87',
                'host93_acquire_hardfloat20','host93_assemble','host93_class','host93_chirrtl_diagnostic'])
            for name, argv, cwd, env, limits in f.calls:
                self.assertEqual(cwd, f.work / 'phases' / name.removeprefix('host93_'))
                self.assertNotIn('TOP_SECRET', env)
                self.assertEqual('HTTPS_PROXY' in env, name in ('host93_acquire_jar87','host93_acquire_hardfloat20'))
                self.assertEqual(limits, g.DIAGNOSTIC_LIMITS if name.endswith('chirrtl_diagnostic') else f.base.LIMITS[name.removeprefix('host93_')])
            command = f.calls[4][1]
            prop = '-Dchisel.project.root=' + str(f.work / 'derived')
            self.assertEqual(command[1], prop)
            self.assertLess(command.index(prop), command.index('scala.tools.nsc.Main'))
            self.assertEqual(sum(x.startswith('-Dchisel.project.root=') for x in command), 1)
            self.assertFalse(any(x.startswith('-Dchisel.project.root=') for x in f.calls[5][1]))
            for name, original in f.sources.items():
                self.assertEqual((f.work / 'assembled/scala' / name).read_bytes(), original)
                self.assertEqual((f.work / 'derived/scala' / name).read_bytes(), EMITTER if name == f.target else original)
            self.assertEqual(result['observation'], {**g.measure_fir(FIR), 'historical_fir_equal': False})
            self.assertTrue(all(type(v) in (int, bool) for v in result['observation'].values()))
            self.assertEqual(result['fir']['sha256'], hashlib.sha256(FIR).hexdigest())
            self.assertEqual(result['derivation']['preserved_source_count'], 92)
            self.assertEqual(result['status'], 'PASS_HOST93_CHIRRTL_DIAGNOSTIC_ONLY')
            self.assertFalse((f.work / 'acquired/firtool').exists())
            self.assertFalse((f.work / 'rtl').exists())
            self.assertTrue(result['structural_assertions_passed'])
        self.fixture(check)

    def test_unchanged_diagnostic_limits_except_fsize(self):
        base = load('host_emission', BASE_RAW)
        expected = dict(base.LIMITS['chirrtl'])
        expected['fsize_bytes'] = 96*1024*1024
        self.assertEqual(g.DIAGNOSTIC_LIMITS, expected)

    def test_marker_mismatch_fails_and_retains_private_receipt(self):
        def check(f):
            f.mutate = lambda name, argv, log: log.replace(b'module_count=5', b'module_count=4') if name.endswith('chirrtl_diagnostic') else log
            with self.assertRaises(g.DiagnosticContractError) as error:
                f.run()
            self.assertEqual(error.exception.safe_contract_code, 'DIAGNOSTIC_STATS')
            self.assertTrue((f.work / 'CHIRRTL_DIAGNOSTIC_FAILED.json').is_file())
            self.assertFalse((f.work / 'CHIRRTL_DIAGNOSTIC_RESULT.json').exists())
        self.fixture(check)

    def test_derived_mutation_after_compile_rejected(self):
        def check(f):
            def mutate(name, argv, log):
                if name == 'host93_class':
                    (f.work / 'derived/scala/src/F00.scala').write_bytes(b'changed')
                return log
            f.mutate = mutate
            with self.assertRaises(ValueError):
                f.run()
            self.assertEqual(f.calls[-1][0], 'host93_class')
        self.fixture(check)

    def test_original_mutation_after_compile_rejected(self):
        def check(f):
            def mutate(name, argv, log):
                if name == 'host93_class':
                    (f.work / 'assembled/scala/src/F00.scala').write_bytes(b'changed')
                return log
            f.mutate = mutate
            with self.assertRaises(ValueError):
                f.run()
            self.assertEqual(f.calls[-1][0], 'host93_class')
        self.fixture(check)

    def test_resume_rejects_nonhistorical_fir_without_children(self):
        def check(f):
            result = f.run()
            with self.assertRaises(g.DiagnosticContractError) as error:
                g.resume_sv(f.repo, f.work, f.callback, f.base, result['resume_context'])
            self.assertEqual(error.exception.safe_contract_code, 'DIAGNOSTIC_RESUME_IDENTITY')
            self.assertEqual(len(f.calls), 6)
            self.assertFalse((f.work / 'acquired/firtool').exists())
        self.fixture(check)

    def synthetic_historical(self, f, action):
        pin = f.base.byte_identity(FIR)
        with mock.patch.object(g, 'HISTORICAL_FIR_PIN', pin), mock.patch.object(f.base, 'FIR_PIN', pin), \
             mock.patch.object(f.base, 'SV_PIN', f.base.byte_identity(f.sv)), \
             mock.patch.object(f.base, 'FIRTOOL_PIN', f.base.byte_identity(f.tool)):
            return action(f.run())

    def test_resume_exact_historical_fixture_only_two_new_mock_phases(self):
        def check(f):
            def resume(first):
                result = g.resume_sv(f.repo, f.work, f.callback, f.base, first['resume_context'])
                self.assertEqual(len(f.calls), 8)
                self.assertEqual([x[0] for x in f.calls[-2:]], ['host93_acquire_firtool','host93_sv'])
                self.assertEqual(result['status'], 'PASS_HOST93_FRESH_EMISSION_ONLY')
                self.assertEqual(result['fir']['sha256'], hashlib.sha256(FIR).hexdigest())
                self.assertEqual(result['sv']['sha256'], hashlib.sha256(f.sv).hexdigest())
                self.assertFalse(result['host_executed'])
                self.assertFalse(result['numerical_qualification'])
                self.assertEqual(result['full_block_rtl_passes'], 0)
                self.assertEqual((f.work / 'assembled/scala' / f.target).read_bytes(), ORIGINAL)
                for call in f.calls[-2:]:
                    self.assertEqual(call[4], f.base.LIMITS[call[0].removeprefix('host93_')])
            self.synthetic_historical(f, resume)
        self.fixture(check)

    def test_resume_failed_sv_does_not_claim_binary_was_unstarted(self):
        def check(f):
            def fail(name, argv, log):
                if name == 'host93_sv':
                    raise ValueError('synthetic child failure')
                return log
            def resume(first):
                f.mutate = fail
                with self.assertRaises(ValueError):
                    g.resume_sv(f.repo, f.work, f.callback, f.base, first['resume_context'])
                receipt = json.loads((f.work / 'HOST_EMISSION_FAILED.json').read_bytes())
                self.assertIsNone(receipt['firtool_executed'])
                self.assertIsNone(receipt['rtl_generated'])
                self.assertEqual(receipt['status'], 'INCOMPLETE_HOST93_RESUMED_SV')
                self.assertEqual(len(f.calls), 8)
            self.synthetic_historical(f, resume)
        self.fixture(check)

    def test_resume_tampered_fir_rejected_before_new_children(self):
        def check(f):
            def resume(first):
                (f.work / 'structure/HostBlockCollection.fir').write_bytes(FIR + b'changed')
                with self.assertRaises(ValueError):
                    g.resume_sv(f.repo, f.work, f.callback, f.base, first['resume_context'])
                self.assertEqual(len(f.calls), 6)
            self.synthetic_historical(f, resume)
        self.fixture(check)

    def test_resume_tampered_receipt_rejected_before_new_children(self):
        def check(f):
            def resume(first):
                (f.work / 'CHIRRTL_DIAGNOSTIC_RESULT.json').write_bytes(b'{}')
                with self.assertRaises(ValueError):
                    g.resume_sv(f.repo, f.work, f.callback, f.base, first['resume_context'])
                self.assertEqual(len(f.calls), 6)
            self.synthetic_historical(f, resume)
        self.fixture(check)

    def test_resume_wrong_work_or_context_rejected(self):
        def check(f):
            result = f.run()
            for context in ({}, {**result['resume_context'], 'extra': '/secret'},
                            {**result['resume_context'], 'work': str(f.root / 'elsewhere')}):
                with self.assertRaises(g.DiagnosticContractError):
                    g.resume_sv(f.repo, f.work, f.callback, f.base, context)
            self.assertEqual(len(f.calls), 6)
        self.fixture(check)


if __name__ == '__main__':
    unittest.main(verbosity=2)
